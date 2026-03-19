# ArXiv Paper Analyzer - 系统扩展使用说明

> 版本: 1.0.0
> 更新日期: 2026-03-19

---

## 一、系统概述

ArXiv Paper Analyzer 系统扩展包含以下核心模块：

| 模块 | 功能 | 入口 |
|------|------|------|
| **Exporter** | 论文导出（BibTeX、Obsidian） | `app.exporters` |
| **Publisher** | 多平台发布（飞书、邮件、Webhook） | `app.publishers` |
| **MCP Server** | AI 助手集成（Claude Desktop） | `app.mcp` |
| **CLI Tool** | 命令行管理工具 | `app.cli` |

---

## 二、CLI 命令行工具

### 2.1 基本用法

```bash
cd backend
python -m app.cli [命令] [选项]
```

### 2.2 命令列表

#### `search` - 搜索论文

```bash
# 关键词搜索
python -m app.cli search "transformer"

# 分类过滤
python -m app.cli search "attention" -c cs.AI -c cs.CL

# 标签过滤
python -m app.cli search "LLM" -t important -t follow

# 日期范围
python -m app.cli search "GPT" --from 2024-01-01 --to 2024-12-31

# 排序和数量
python -m app.cli search "RAG" -s popularity -n 50

# 导出到文件
python -m app.cli search "agent" -o results.json
```

**选项说明**：

| 选项 | 简写 | 说明 |
|------|------|------|
| `--category` | `-c` | 分类过滤（可多次使用） |
| `--tag` | `-t` | 标签过滤（可多次使用） |
| `--from` | | 起始日期 (YYYY-MM-DD) |
| `--to` | | 结束日期 (YYYY-MM-DD) |
| `--sort` | `-s` | 排序方式: newest / popularity |
| `--limit` | `-n` | 返回数量（默认 20） |
| `--output` | `-o` | 输出 JSON 文件 |

#### `get` - 获取论文详情

```bash
# 基本信息
python -m app.cli get 123

# 包含分析结果
python -m app.cli get 123 --analysis

# 导出到文件
python -m app.cli get 123 -o paper.json
```

#### `trending` - 获取热门论文

```bash
# 最近 7 天热门
python -m app.cli trending

# 最近 30 天，每天 10 篇
python -m app.cli trending -d 30 -n 10

# 包含分析结果
python -m app.cli trending --analyze

# 导出到文件
python -m app.cli trending -o trending.json
```

**选项说明**：

| 选项 | 简写 | 说明 |
|------|------|------|
| `--days` | `-d` | 最近几天（默认 7） |
| `--limit` | `-n` | 每天数量（默认 20） |
| `--analyze` | | 包含分析结果 |
| `--output` | `-o` | 输出 JSON 文件 |

#### `analyze` - 深度分析论文

```bash
# 分析论文
python -m app.cli analyze 123

# 强制重新分析
python -m app.cli analyze 123 --force
```

#### `summary` - 生成 AI 摘要

```bash
# 简洁摘要
python -m app.cli summary 123

# 详细摘要
python -m app.cli summary 123 -s detailed
```

**选项说明**：

| 选项 | 简写 | 说明 |
|------|------|------|
| `--style` | `-s` | 摘要风格: brief / detailed |

#### `export` - 导出论文

```bash
# 导出 BibTeX
python -m app.cli export 1 2 3 -f bibtex

# 导出到文件
python -m app.cli export 1 2 3 -f bibtex -o papers.bib

# 导出到 Obsidian
python -m app.cli export 1 2 3 -f obsidian --folder "10-19_AI-Systems"
```

**选项说明**：

| 选项 | 简写 | 说明 |
|------|------|------|
| `--format` | `-f` | 格式: bibtex / obsidian |
| `--output` | `-o` | 输出文件（BibTeX） |
| `--folder` | | Obsidian 目标文件夹 |

#### `publish` - 发布论文

```bash
# 发布到飞书
python -m app.cli publish 1 2 3 -p feishu

# 发布到邮件
python -m app.cli publish 1 2 3 -p email

# 发布到 Webhook
python -m app.cli publish 1 2 3 -p webhook
```

#### `list-platforms` - 列出发布平台

```bash
python -m app.cli list-platforms
```

---

## 三、MCP Server（AI 助手集成）

### 3.1 启动方式

```bash
cd backend

# STDIO 模式（用于 Claude Desktop）
python -m app.mcp.server --transport stdio

# SSE 模式（用于远程客户端）
python -m app.mcp.server --transport sse --port 8001

# 完全访问模式
python -m app.mcp.server --full-access

# 使用配置文件
python -m app.mcp.server --config config/mcp_config.yaml
```

### 3.2 Claude Desktop 配置

在 Claude Desktop 配置文件中添加：

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "arxiv-paper-analyzer": {
      "command": "/path/to/arxiv-paper-analyzer/backend/venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/arxiv-paper-analyzer/backend"
    }
  }
}
```

### 3.3 MCP 工具列表

| 工具 | 功能 | 权限模式 |
|------|------|----------|
| `search_papers` | 搜索论文 | read_only |
| `get_paper` | 获取论文详情 | read_only |
| `get_trending` | 获取热门论文 | read_only |
| `export_to_bibtex` | 导出 BibTeX | read_only |
| `analyze_paper` | 深度分析 | full_access |
| `generate_summary` | 生成摘要 | full_access |
| `export_to_obsidian` | 导出 Obsidian | full_access |

### 3.4 工具参数

#### `search_papers`

```json
{
  "query": "transformer",
  "categories": ["cs.AI", "cs.CL"],
  "tags": ["important"],
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "sort_by": "popularity",
  "limit": 20
}
```

#### `get_paper`

```json
{
  "paper_id": 123,
  "include_analysis": true
}
```

#### `get_trending`

```json
{
  "days": 7,
  "limit_per_day": 20,
  "include_analysis": false
}
```

#### `analyze_paper`

```json
{
  "paper_id": 123,
  "force": false
}
```

#### `generate_summary`

```json
{
  "paper_id": 123,
  "style": "brief"
}
```

#### `export_to_bibtex`

```json
{
  "paper_ids": [1, 2, 3],
  "output_file": "papers.bib"
}
```

#### `export_to_obsidian`

```json
{
  "paper_id": 123,
  "folder": "Inbox"
}
```

### 3.5 配置文件

`config/mcp_config.yaml`:

```yaml
# 权限配置
permission:
  mode: read_only  # 或 full_access

# 后端 API
api_base_url: http://localhost:8000

# Obsidian 服务
obsidian_service_url: http://127.0.0.1:8766
```

---

## 四、Exporter 导出器

### 4.1 BibTeX 导出

```python
from app.exporters import BibTeXExporter

exporter = BibTeXExporter()

# 导出单篇
bibtex = exporter.export_paper(paper_data)

# 导出多篇
bibtex = exporter.export_papers([paper1, paper2])

# 导出到文件
from app.exporters.base import ExportResult
result = exporter.export_to_file([paper1, paper2], "output.bib")
```

**输出示例**：

```bibtex
@article{vaswani2017attention,
  author = {Ashish Vaswani and Noam Shazeer and Niki Parmar},
  title = {Attention Is All You Need},
  year = {2017},
  eprint = {1706.03762},
  archiveprefix = {arXiv},
  primaryclass = {cs.LG},
  abstract = {The dominant sequence transduction models...}
}
```

### 4.2 Obsidian 导出

```python
from app.exporters import ObsidianExporter

# 本地导出
exporter = ObsidianExporter(prefer_service=False)
markdown = exporter.export_paper(paper_data)

# 通过服务导出到 Vault
from app.services.obsidian_client import ObsidianClient
client = ObsidianClient()
exporter = ObsidianExporter(client=client, prefer_service=True)
result = await exporter.export_to_vault(paper_data, folder="Inbox")
```

**输出示例**：

```markdown
---
title: Attention Is All You Need
arxiv_id: '1706.03762'
authors:
- Ashish Vaswani
- Noam Shazeer
date: '2017-06-12'
categories:
- cs.LG
- cs.CL
tags:
- transformer
- attention
tier: S
url: https://arxiv.org/abs/1706.03762
type: paper
---

# Attention Is All You Need

> **内容等级**：⭐⭐⭐ 深度干货 | **综合评级**：S

## 📋 基础信息
...
```

---

## 五、Publisher 发布器

### 5.1 飞书发布

```python
from app.publishers import FeishuPublisher

publisher = FeishuPublisher({
    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
})

result = await publisher.publish(
    content="论文推荐",
    papers=[paper1, paper2],
    message_type="card"  # 或 "text"
)
```

### 5.2 邮件发布

```python
from app.publishers import EmailPublisher

publisher = EmailPublisher({
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your@gmail.com",
    "password": "app_password",
    "sender": "your@gmail.com",
    "recipients": ["recipient@example.com"]
})

result = await publisher.publish(
    subject="每周论文推荐",
    content="论文内容...",
    papers=[paper1, paper2]
)
```

### 5.3 Webhook 发布

```python
from app.publishers import WebhookPublisher

publisher = WebhookPublisher({
    "url": "https://api.example.com/webhook",
    "headers": {
        "Authorization": "Bearer token",
        "Content-Type": "application/json"
    }
})

result = await publisher.publish(
    title="论文推荐",
    papers=[paper1, paper2]
)
```

### 5.4 使用 PublisherRegistry

```python
from app.publishers import PublisherRegistry

# 列出可用平台
platforms = PublisherRegistry.list_available()
# ['wechat_mp', 'feishu', 'email', 'webhook']

# 创建发布器
publisher = PublisherRegistry.create("feishu", {
    "webhook_url": "https://..."
})
```

---

## 六、权限控制

### 6.1 权限模式

| 模式 | 允许的工具 |
|------|-----------|
| `read_only` | search_papers, get_paper, get_trending, export_to_bibtex |
| `full_access` | 所有工具（包括 analyze_paper, generate_summary, export_to_obsidian） |

### 6.2 使用方式

**命令行**：
```bash
python -m app.mcp.server --full-access
```

**配置文件**：
```yaml
permission:
  mode: full_access
```

**代码中**：
```python
from app.mcp import MCPConfig, PermissionMode

config = MCPConfig(permission_mode=PermissionMode.FULL_ACCESS)
server = MCPServer(config)
```

---

## 七、测试验证

### 7.1 运行测试

```bash
cd backend

# 运行所有测试
pytest tests/

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 查看覆盖率
pytest --cov=app tests/
```

### 7.2 测试统计

| 类型 | 数量 |
|------|------|
| 单元测试 | 88 |
| 集成测试 | 12 |
| **总计** | **100** |

---

## 八、故障排查

### 8.1 CLI 命令无法运行

```bash
# 确保在 backend 目录
cd /path/to/arxiv-paper-analyzer/backend

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 8.2 MCP Server 无法启动

```bash
# 检查依赖
pip install sse-starlette

# 检查配置文件
cat config/mcp_config.yaml
```

### 8.3 Claude Desktop 无法连接

1. 确认配置文件路径正确
2. 确认 Python 解释器路径正确
3. 查看 Claude Desktop 日志：
   - macOS: `~/Library/Logs/Claude/mcp*.log`

---

## 九、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-03-19 | 初始版本 |

---

## 十、支持

如有问题，请提交 Issue 或联系开发团队。