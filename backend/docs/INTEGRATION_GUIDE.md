# ArXiv 论文分析系统对接指南

## 系统概述

**Paper Analyzer** 是一个完整的论文管理与分析系统，提供多层次的对接能力：

```
┌─────────────────────────────────────────────────────────────────┐
│                     对接层次架构                                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: REST API     → 直接 HTTP 调用                          │
│  Layer 2: MCP Tools    → AI Agent 调用 (Claude/其他 LLM)         │
│  Layer 3: CLI Scripts  → 命令行/定时任务                          │
│  Layer 4: Obsidian     → 知识库导出/双向同步                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: REST API

### 基础信息

- **服务地址**: `http://localhost:8000`
- **API 前缀**: `/api`
- **文档**: `http://localhost:8000/docs` (需启用)

### 核心接口

#### 1. 论文搜索

```http
GET /api/papers?query=transformer&limit=20&sort_by=newest
```

**参数**:
- `query`: 搜索关键词（标题/摘要/总结）
- `categories`: 分类过滤 `["cs.AI", "cs.LG"]`
- `tags`: 标签过滤
- `date_from/date_to`: 日期范围
- `sort_by`: `newest` | `popularity`
- `limit`: 返回数量

#### 2. 获取论文详情

```http
GET /api/papers/{paper_id}
GET /api/papers/arxiv/{arxiv_id}
```

#### 3. 触发论文分析

```http
POST /api/papers/{paper_id}/analyze?force_refresh=false
```

**返回**: 分析任务状态（异步处理）

#### 4. 抓取新论文

```http
POST /api/fetch?query=agent&max_results=50
POST /api/fetch/categories?categories=["cs.AI","cs.LG"]&max_results=20
POST /api/fetch/date-range?from=2024-01-01&to=2024-01-31
```

#### 5. 导出到 Obsidian

```http
POST /api/papers/{paper_id}/export-to-obsidian
```

#### 6. 统计信息

```http
GET /api/stats
GET /api/tier-stats
GET /api/tags
GET /api/categories
```

### 示例：Python 调用

```python
import httpx

async def search_papers(query: str, limit: int = 10):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/papers",
            params={"query": query, "limit": limit}
        )
        return response.json()

async def analyze_paper(paper_id: int):
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"http://localhost:8000/api/papers/{paper_id}/analyze"
        )
        return response.json()
```

---

## Layer 2: MCP Tools

MCP (Model Context Protocol) 工具供 AI Agent 直接调用。

### 可用工具

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `search_papers` | 搜索论文 | query, categories, tags, date_from, date_to, limit |
| `get_paper` | 获取论文详情 | paper_id 或 arxiv_id |
| `get_trending` | 获取热门论文 | period, category, limit |
| `analyze_paper` | 深度分析论文 | paper_id, force_refresh |
| `generate_summary` | 生成总结 | paper_id, style |
| `export_to_obsidian` | 导出到 Obsidian | paper_id |
| `search_obsidian` | 搜索已导出论文 | query, limit |
| `read_obsidian` | 读取 Obsidian 笔记 | filename |

### MCP 配置

```json
{
  "mcpServers": {
    "paper-analyzer": {
      "command": "/Users/liufang/arxiv-paper-analyzer/backend/venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/Users/liufang/arxiv-paper-analyzer/backend"
    }
  }
}
```

---

## Layer 3: CLI Scripts

### 数据同步脚本

```bash
# 同步 Vault 路径到数据库
python scripts/sync_vault_locations.py

# 更新 RAG 同步状态
python scripts/update_rag_indexed.py

# 检测重复论文
python scripts/detect_duplicates.py --all

# 清理重复
python scripts/cleanup_duplicates.py

# 批量同步到 RAG
python scripts/sync_to_rag.py --batch --limit 100
```

### 与 zhiwei-scheduler 集成

已配置定时任务：
- `vault_sync_master`: 每日 3:00 同步 LanceDB + 自动更新 rag_indexed

---

## Layer 4: Obsidian 集成

### 导出结构

论文导出到 Obsidian Vault，自动生成：

```
~/Documents/ZhiweiVault/
├── Inbox/                          # Tier B/C 论文（默认）
│   └── PAPER_2026-04-02_Title.md
└── 90-99_系统与归档_System/
    └── 96_Papers_Archive/
        └── 重要论文/                # Tier A 论文
            └── PAPER_2026-04-02_Title.md
```

### Markdown 格式

```markdown
---
title: "论文标题"
arxiv_id: "2401.12345"
date: 2024-01-15
type: paper
tags: [深度学习, 计算机视觉]
tier: A
---

# 论文标题

> **内容等级**：⭐⭐⭐ 深度干货

## 📋 基础信息
...

## 💡 一句话总结
...

## 🎯 核心贡献
...

## ✅ 行动建议
...
```

---

## 现有集成案例

### 1. zhiwei-bot 集成

**文件**: `~/zhiwei-bot/core/research_report_executor.py`

**调用方式**: 子进程调用 `scripts/manage.py export-notebook`

```python
cmd = [
    str(self.analyzer_python), "scripts/manage.py", "export-notebook",
    "--query", actual_topic,
    "--limit", "10",
    "--tiers", "A,B",
    "--template", template_key,
]
```

### 2. zhiwei-rag 集成

**文件**: `~/zhiwei-rag/scripts/reconcile_obsidian.py`

**调用方式**: VaultSyncMaster 扫描 Vault → LanceDB

**新增回调**: 同步完成后自动调用 `update_rag_indexed.py`

---

## 数据模型

### Paper 核心字段

```python
class Paper:
    id: int
    arxiv_id: str           # arXiv ID (如 2401.12345)
    title: str              # 标题
    authors: List[str]      # 作者列表
    abstract: str           # 原始摘要
    summary: str            # AI 生成总结
    
    # 分析结果
    has_analysis: bool      # 是否已分析
    tier: str               # 质量等级 A/B/C
    tags: List[str]         # AI 生成标签
    analysis_report: str    # 深度分析报告
    analysis_json: dict     # 结构化分析结果
    
    # 追踪字段
    md_output_path: str     # Obsidian 导出路径
    vault_locations: List[str]  # Vault 中所有位置
    rag_indexed: bool       # 是否已同步到 LanceDB
    lancedb_id: str         # LanceDB 标识
```

---

## 对接建议

### 场景 1: 外部系统搜索论文

```python
# 推荐: REST API
response = requests.get("http://localhost:8000/api/papers", params={"query": "transformer"})
```

### 场景 2: AI Agent 分析论文

```python
# 推荐: MCP Tools
# 在 Claude Code 中直接调用 search_papers, analyze_paper
```

### 场景 3: 批量处理/定时任务

```python
# 推荐: CLI Scripts
python scripts/sync_to_rag.py --all
```

### 场景 4: 知识库集成

```python
# 推荐: Obsidian 导出 + LanceDB RAG
# 1. 导出论文到 Obsidian
# 2. VaultSyncMaster 自动同步到 LanceDB
# 3. 通过 RAG API 检索
```

---

## 服务状态检查

```bash
# API 状态
curl http://localhost:8000/api/stats

# 数据库状态
sqlite3 ~/arxiv-paper-analyzer/backend/data/papers.db "SELECT COUNT(*) FROM papers"

# LanceDB 状态
python -c "
import lancedb
db = lancedb.connect('~/zhiwei-rag/data/lance_db')
print(db.open_table('documents').count_rows())
"
```

---

## 版本信息

- Paper Analyzer: v1.0.0
- 最后更新: 2026-04-02
- 维护者: Claude Code