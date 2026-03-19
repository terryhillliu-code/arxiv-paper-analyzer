"""
MCP Server 单元测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.mcp.config import MCPConfig, PermissionMode
from app.mcp.server import MCPServer
from app.mcp.tools.base import ToolRegistry, ToolResult, ToolDefinition
from app.mcp.tools.search import SearchPapersTool
from app.mcp.tools.paper import GetPaperTool
from app.mcp.tools.trending import GetTrendingTool
from app.mcp.tools.analyze import AnalyzePaperTool
from app.mcp.tools.summary import GenerateSummaryTool
from app.mcp.tools.export_obsidian import ExportToObsidianTool
from app.mcp.tools.export_bibtex import ExportToBibtexTool


class TestMCPConfig:
    """测试 MCP 配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = MCPConfig()
        assert config.permission_mode == PermissionMode.READ_ONLY
        assert len(config.allowed_tools) > 0

    def test_full_access_mode(self):
        """测试完全访问模式"""
        config = MCPConfig(permission_mode=PermissionMode.FULL_ACCESS)
        # 完全访问模式应包含所有工具
        assert "analyze_paper" in config.allowed_tools
        assert "generate_summary" in config.allowed_tools
        assert "search_papers" in config.allowed_tools

    def test_read_only_mode(self):
        """测试只读模式"""
        config = MCPConfig(permission_mode=PermissionMode.READ_ONLY)
        # 只读模式不应包含分析和生成工具
        assert "analyze_paper" not in config.allowed_tools
        assert "generate_summary" not in config.allowed_tools
        # 应包含查询工具
        assert "search_papers" in config.allowed_tools
        assert "get_paper" in config.allowed_tools

    def test_custom_allowed_tools(self):
        """测试自定义工具列表"""
        config = MCPConfig(permission_mode=PermissionMode.READ_ONLY)
        # 自定义只读工具列表
        config.read_only_tools = {"search_papers", "get_paper"}
        assert "search_papers" in config.allowed_tools
        assert "get_paper" in config.allowed_tools

    def test_is_tool_allowed(self):
        """测试工具权限检查"""
        config = MCPConfig(permission_mode=PermissionMode.READ_ONLY)
        assert config.is_tool_allowed("search_papers") is True
        assert config.is_tool_allowed("analyze_paper") is False

    def test_from_yaml(self, tmp_path):
        """测试从 YAML 加载配置"""
        yaml_content = """
permission:
  mode: full_access
api_base_url: http://localhost:9000
"""
        config_file = tmp_path / "mcp_config.yaml"
        config_file.write_text(yaml_content)

        config = MCPConfig.from_yaml(str(config_file))
        assert config.permission_mode == PermissionMode.FULL_ACCESS
        assert config.api_base_url == "http://localhost:9000"


class TestToolRegistry:
    """测试工具注册表"""

    def test_register_tool(self):
        """测试工具注册"""
        # 工具应该已经在模块加载时注册
        assert ToolRegistry.get("search_papers") == SearchPapersTool
        assert ToolRegistry.get("get_paper") == GetPaperTool
        assert ToolRegistry.get("get_trending") == GetTrendingTool

    def test_get_nonexistent_tool(self):
        """测试获取不存在的工具"""
        assert ToolRegistry.get("nonexistent_tool") is None

    def test_get_all_definitions(self):
        """测试获取所有工具定义"""
        definitions = ToolRegistry.get_all_definitions()
        assert len(definitions) >= 7  # 至少 7 个工具

        # 检查定义格式
        for defn in definitions:
            assert isinstance(defn, ToolDefinition)
            assert defn.name
            assert defn.description
            assert defn.input_schema

    def test_get_allowed_definitions(self):
        """测试获取允许的工具定义"""
        allowed = ["search_papers", "get_paper"]
        definitions = ToolRegistry.get_allowed_definitions(allowed)

        names = [d.name for d in definitions]
        assert "search_papers" in names
        assert "get_paper" in names
        assert "analyze_paper" not in names


class TestMCPServer:
    """测试 MCP Server"""

    @pytest.fixture
    def server(self):
        """创建服务器实例"""
        return MCPServer()

    @pytest.fixture
    def full_access_server(self):
        """创建完全访问模式服务器"""
        config = MCPConfig(permission_mode=PermissionMode.FULL_ACCESS)
        return MCPServer(config)

    def test_server_init(self, server):
        """测试服务器初始化"""
        assert server.name == "arxiv-paper-analyzer"
        assert server.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_handle_initialize(self, server):
        """测试初始化请求处理"""
        params = {"clientInfo": {"name": "test-client", "version": "1.0"}}
        result = await server.handle_initialize(params)

        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "arxiv-paper-analyzer"

    @pytest.mark.asyncio
    async def test_handle_tools_list(self, server):
        """测试工具列表请求"""
        result = await server.handle_tools_list({})

        assert "tools" in result
        assert len(result["tools"]) >= 3  # 至少 3 个只读工具

        # 检查工具格式
        for tool in result["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    @pytest.mark.asyncio
    async def test_handle_tools_call_unknown(self, server):
        """测试未知工具调用"""
        result = await server.handle_tools_call({"name": "unknown_tool"})
        assert result["isError"] is True
        assert "未知工具" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_tools_call_permission_denied(self, server):
        """测试权限拒绝"""
        # 只读模式服务器调用分析工具
        result = await server.handle_tools_call({
            "name": "analyze_paper",
            "arguments": {"paper_id": 1}
        })
        assert result["isError"] is True
        assert "权限" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_handle_tools_call_invalid_args(self, full_access_server):
        """测试无效参数"""
        result = await full_access_server.handle_tools_call({
            "name": "search_papers",
            "arguments": {}  # 缺少必需参数
        })
        # 搜索工具可以接受空参数（返回所有）
        # 但让我们测试缺少必需参数的情况
        result = await full_access_server.handle_tools_call({
            "name": "get_paper",
            "arguments": {}  # 缺少 paper_id
        })
        assert result["isError"] is True

    def test_format_result(self, server):
        """测试结果格式化"""
        result = ToolResult(success=True, data={"key": "value"})
        formatted = server._format_result(result)
        assert "key" in formatted
        assert "value" in formatted

    def test_format_result_none(self, server):
        """测试空结果格式化"""
        result = ToolResult(success=True, data=None)
        formatted = server._format_result(result)
        assert formatted == "操作成功"


class TestSearchPapersTool:
    """测试搜索论文工具"""

    def test_definition(self):
        """测试工具定义"""
        defn = SearchPapersTool.get_definition()
        assert defn.name == "search_papers"
        assert "query" in defn.input_schema["properties"]
        assert "categories" in defn.input_schema["properties"]

    def test_validate_arguments(self):
        """测试参数验证"""
        tool = SearchPapersTool()

        # 空参数应该允许（搜索全部）
        assert tool.validate_arguments({}) is None

        # 有效参数
        assert tool.validate_arguments({"keyword": "test"}) is None

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行搜索"""
        tool = SearchPapersTool()
        config = MCPConfig()

        # 模拟数据库会话
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_papers = [
            MagicMock(
                id=1,
                title="Test Paper",
                arxiv_id="2401.00001",
                authors=["Author"],
                abstract="Abstract",
                categories=["cs.AI"],
                publish_date=None,
                popularity_score=0.5,
                pdf_url="http://example.com/pdf"
            )
        ]
        mock_result.scalars.return_value.all.return_value = mock_papers
        mock_session.execute.return_value = mock_result

        result = await tool.execute({"keyword": "test"}, config, mock_session)

        assert result.success is True
        assert result.data is not None
        assert result.data["total"] == 1


class TestGetPaperTool:
    """测试获取论文工具"""

    def test_definition(self):
        """测试工具定义"""
        defn = GetPaperTool.get_definition()
        assert defn.name == "get_paper"
        assert "paper_id" in defn.input_schema["properties"]
        assert defn.input_schema["required"] == ["paper_id"]

    def test_validate_arguments(self):
        """测试参数验证"""
        tool = GetPaperTool()

        # 缺少必需参数
        assert tool.validate_arguments({}) is not None

        # 有效参数
        assert tool.validate_arguments({"paper_id": 1}) is None


class TestGetTrendingTool:
    """测试热门论文工具"""

    def test_definition(self):
        """测试工具定义"""
        defn = GetTrendingTool.get_definition()
        assert defn.name == "get_trending"
        assert "limit_per_day" in defn.input_schema["properties"]

    @pytest.mark.asyncio
    async def test_execute(self):
        """测试执行"""
        tool = GetTrendingTool()
        config = MCPConfig()

        # 模拟数据库会话
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_papers = [
            MagicMock(
                id=1,
                title="Trending Paper",
                arxiv_id="2401.00001",
                authors=["Author"],
                abstract="Abstract",
                categories=["cs.AI"],
                publish_date=None,
                popularity_score=0.9,
                pdf_url="http://example.com/pdf"
            )
        ]
        mock_result.scalars.return_value.all.return_value = mock_papers
        mock_session.execute.return_value = mock_result

        result = await tool.execute({"limit": 10}, config, mock_session)

        assert result.success is True


class TestAnalyzePaperTool:
    """测试分析论文工具"""

    def test_definition(self):
        """测试工具定义"""
        defn = AnalyzePaperTool.get_definition()
        assert defn.name == "analyze_paper"
        assert "paper_id" in defn.input_schema["required"]

    def test_requires_full_access(self):
        """测试需要完全访问权限"""
        tool = AnalyzePaperTool()
        config = MCPConfig(permission_mode=PermissionMode.READ_ONLY)

        assert config.is_tool_allowed("analyze_paper") is False


class TestExportToBibtexTool:
    """测试导出 BibTeX 工具"""

    def test_definition(self):
        """测试工具定义"""
        defn = ExportToBibtexTool.get_definition()
        assert defn.name == "export_to_bibtex"
        assert "paper_ids" in defn.input_schema["required"]

    def test_validate_arguments(self):
        """测试参数验证"""
        tool = ExportToBibtexTool()

        # 缺少必需参数
        assert tool.validate_arguments({}) is not None

        # 空列表
        assert tool.validate_arguments({"paper_ids": []}) is None  # 空列表允许

        # 有效参数
        assert tool.validate_arguments({"paper_ids": [1, 2]}) is None


class TestExportToObsidianTool:
    """测试导出 Obsidian 工具"""

    def test_definition(self):
        """测试工具定义"""
        defn = ExportToObsidianTool.get_definition()
        assert defn.name == "export_to_obsidian"
        assert "paper_id" in defn.input_schema["required"]

    def test_requires_full_access(self):
        """测试需要完全访问权限"""
        config = MCPConfig(permission_mode=PermissionMode.READ_ONLY)
        assert config.is_tool_allowed("export_to_obsidian") is False


class TestToolResult:
    """测试工具结果"""

    def test_success_result(self):
        """测试成功结果"""
        result = ToolResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.error is None

    def test_error_result(self):
        """测试错误结果"""
        result = ToolResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.data is None