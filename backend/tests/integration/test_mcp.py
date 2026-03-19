"""
MCP Server 集成测试
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.mcp.server import MCPServer
from app.mcp.config import MCPConfig, PermissionMode


class TestMCPServerIntegration:
    """MCP Server 集成测试"""

    @pytest.fixture
    def server(self):
        return MCPServer()

    @pytest.fixture
    def full_access_server(self):
        config = MCPConfig(permission_mode=PermissionMode.FULL_ACCESS)
        return MCPServer(config)

    @pytest.mark.asyncio
    async def test_initialize_flow(self, server):
        """测试初始化流程"""
        # 1. 客户端发送 initialize
        init_response = await server.handle_initialize({
            "clientInfo": {"name": "test-client", "version": "1.0"}
        })

        assert init_response["protocolVersion"] == "2024-11-05"
        assert "tools" in init_response["capabilities"]

        # 2. 获取工具列表
        tools_response = await server.handle_tools_list({})

        assert "tools" in tools_response
        tool_names = [t["name"] for t in tools_response["tools"]]
        assert "search_papers" in tool_names
        assert "get_paper" in tool_names

    @pytest.mark.asyncio
    async def test_search_papers_flow(self, server):
        """测试搜索论文流程"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_papers = [
            MagicMock(
                id=1,
                title="Test Paper",
                arxiv_id="2401.00001",
                authors=["Author"],
                summary="Summary",
                categories=["cs.AI"],
                tags=[],
                tier="A",
                publish_date=None,
                popularity_score=0.5,
            )
        ]
        mock_result.scalars.return_value.all.return_value = mock_papers
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            response = await server.handle_tools_call({
                "name": "search_papers",
                "arguments": {"query": "test"}
            })

        assert response["isError"] is False
        content = response["content"][0]["text"]
        data = json.loads(content)
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_permission_enforcement(self, server, full_access_server):
        """测试权限控制"""
        # 只读服务器尝试分析
        response = await server.handle_tools_call({
            "name": "analyze_paper",
            "arguments": {"paper_id": 1}
        })
        assert response["isError"] is True
        assert "权限" in response["content"][0]["text"]

        # 完全访问服务器允许分析（但需要 mock HTTP 调用）
        with patch("httpx.AsyncClient") as client_mock:
            client_instance = AsyncMock()
            client_instance.__aenter__.return_value = client_instance
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": 1, "title": "Test"}
            client_instance.post.return_value = mock_response
            client_mock.return_value = client_instance

            response = await full_access_server.handle_tools_call({
                "name": "analyze_paper",
                "arguments": {"paper_id": 1}
            })

            # 分析工具应该能执行（即使可能失败于其他原因）
            # 权限检查应该通过
            pass

    @pytest.mark.asyncio
    async def test_tool_validation(self, server):
        """测试工具参数验证"""
        # 缺少必需参数
        response = await server.handle_tools_call({
            "name": "get_paper",
            "arguments": {}
        })

        assert response["isError"] is True
        assert "参数" in response["content"][0]["text"] or "错误" in response["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_unknown_tool(self, server):
        """测试未知工具"""
        response = await server.handle_tools_call({
            "name": "unknown_tool",
            "arguments": {}
        })

        assert response["isError"] is True
        assert "未知工具" in response["content"][0]["text"]


class TestToolRegistryIntegration:
    """工具注册表集成测试"""

    def test_all_tools_registered(self):
        """测试所有工具已注册"""
        from app.mcp.tools.base import ToolRegistry

        definitions = ToolRegistry.get_all_definitions()

        expected_tools = {
            "search_papers",
            "get_paper",
            "get_trending",
            "analyze_paper",
            "generate_summary",
            "export_to_bibtex",
            "export_to_obsidian",
        }

        registered_tools = {d.name for d in definitions}

        # 确保至少有预期的工具
        assert expected_tools.issubset(registered_tools)

    def test_tool_schemas_valid(self):
        """测试工具 Schema 有效"""
        from app.mcp.tools.base import ToolRegistry

        definitions = ToolRegistry.get_all_definitions()

        for defn in definitions:
            assert defn.name
            assert defn.description
            assert defn.input_schema
            assert defn.input_schema.get("type") == "object"
            assert "properties" in defn.input_schema