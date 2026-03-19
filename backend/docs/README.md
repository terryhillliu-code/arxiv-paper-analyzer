# ArXiv Paper Analyzer - 系统扩展文档

## 概述

本文档描述了 ArXiv Paper Analyzer 系统的扩展模块，包括：

- **Exporter 模块**：论文导出功能（BibTeX、Obsidian）
- **Publisher 模块**：多平台发布功能（飞书、邮件、Webhook）
- **MCP Server**：AI 助手集成（Claude Desktop 等）
- **CLI Tool**：命令行管理工具

## 模块架构

```
backend/app/
├── exporters/           # 导出器模块
│   ├── base.py         # 基类和结果类型
│   ├── bibtex.py       # BibTeX 导出
│   └── obsidian.py     # Obsidian 导出
├── publishers/          # 发布器模块
│   ├── base.py         # 基类和注册表
│   ├── feishu.py       # 飞书发布
│   ├── email.py        # 邮件发布
│   └── webhook.py      # 通用 Webhook
├── mcp/                 # MCP Server
│   ├── server.py       # 主服务器
│   ├── config.py       # 配置管理
│   ├── tools/          # MCP 工具
│   └── transport/      # 传输层
└── cli/                 # CLI 工具
    ├── main.py         # 入口
    └── commands.py     # 命令实现
```

## 快速开始

### CLI 使用

```bash
# 进入 backend 目录
cd backend

# 搜索论文
python -m app.cli search "transformer" -c cs.AI -n 10

# 获取论文详情
python -m app.cli get 123 --analysis

# 查看热门论文
python -m app.cli trending -d 7 -n 20

# 分析论文
python -m app.cli analyze 123

# 生成摘要
python -m app.cli summary 123 -s detailed

# 导出论文
python -m app.cli export 1 2 3 -f bibtex -o papers.bib

# 发布到飞书
python -m app.cli publish 1 2 3 -p feishu
```

### MCP Server 使用

```bash
# STDIO 模式（用于 Claude Desktop）
python -m app.mcp.server --transport stdio

# SSE 模式（用于远程客户端）
python -m app.mcp.server --transport sse --port 8001

# 完全访问模式
python -m app.mcp.server --full-access

# 使用配置文件
python -m app.mcp.server --config config/mcp_config.yaml
```

### Claude Desktop 配置

在 Claude Desktop 配置文件中添加：

```json
{
  "mcpServers": {
    "arxiv-paper-analyzer": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/arxiv-paper-analyzer/backend"
    }
  }
}
```

## 配置

### MCP 配置 (`config/mcp_config.yaml`)

```yaml
# 权限配置
permission:
  mode: read_only  # 或 full_access

# 后端 API
api_base_url: http://localhost:8000

# Obsidian 服务
obsidian_service_url: http://127.0.0.1:8766
```

### 权限模式

| 模式 | 允许的操作 |
|------|-----------|
| `read_only` | 搜索、查看、导出 BibTeX |
| `full_access` | 分析、生成摘要、导出 Obsidian、发布 |

## API 参考

### Exporter API

```python
from app.exporters import BibTeXExporter, ObsidianExporter

# BibTeX 导出
exporter = BibTeXExporter()
bibtex_content = exporter.export_papers(papers_data)
exporter.export_to_file(papers_data, "output.bib")

# Obsidian 导出
exporter = ObsidianExporter()
markdown = exporter.export_paper(paper_data)
result = await exporter.export_to_vault(paper_data, folder="Inbox")
```

### Publisher API

```python
from app.publishers import FeishuPublisher, EmailPublisher, WebhookPublisher

# 飞书发布
publisher = FeishuPublisher({"webhook_url": "https://..."})
result = await publisher.publish(content, papers_data)

# 邮件发布
publisher = EmailPublisher({
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "username": "user@example.com",
    "password": "password",
    "from_addr": "user@example.com",
    "to_addrs": ["recipient@example.com"]
})
result = await publisher.publish(subject, content, papers_data)

# Webhook 发布
publisher = WebhookPublisher({
    "url": "https://api.example.com/webhook",
    "headers": {"Authorization": "Bearer token"}
})
result = await publisher.publish(papers_data)
```

### MCP Tools

| 工具名 | 功能 | 权限 |
|--------|------|------|
| `search_papers` | 搜索论文 | read_only |
| `get_paper` | 获取论文详情 | read_only |
| `get_trending` | 获取热门论文 | read_only |
| `export_to_bibtex` | 导出 BibTeX | read_only |
| `analyze_paper` | 深度分析 | full_access |
| `generate_summary` | 生成摘要 | full_access |
| `export_to_obsidian` | 导出 Obsidian | full_access |

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 查看覆盖率
pytest --cov=app tests/
```

## 扩展开发

### 添加新的导出器

```python
from app.exporters.base import BaseExporter, ExportResult

class MyExporter(BaseExporter):
    name = "my_format"

    def export_paper(self, paper: dict) -> str:
        # 实现导出逻辑
        return "formatted content"

    def export_papers(self, papers: list) -> str:
        return "\n".join(self.export_paper(p) for p in papers)
```

### 添加新的发布器

```python
from app.publishers.base import BasePublisher, PublishResult

class MyPublisher(BasePublisher):
    name = "my_platform"
    requires_auth = True

    def _validate_config(self) -> None:
        if not self.config.get("api_key"):
            raise ValueError("缺少 api_key")

    async def publish(self, content: str, papers: list) -> PublishResult:
        # 实现发布逻辑
        return PublishResult(success=True, platform=self.name)
```

### 添加新的 MCP 工具

```python
from app.mcp.tools.base import BaseTool, ToolDefinition, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "工具描述"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "param": {"type": "string"}
                },
                "required": ["param"]
            }
        )

    async def execute(self, arguments, config, db_session=None):
        # 实现工具逻辑
        return ToolResult(success=True, data={})
```

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-19 | 初始版本：Exporter、Publisher、MCP Server、CLI |

## 贡献

欢迎提交 Issue 和 Pull Request。