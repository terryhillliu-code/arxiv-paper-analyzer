# 论文抓取与系统对接规范

## 概述

本文档规范 ArXiv 论文抓取机制，以及 Obsidian CLI 与 Paper Analyzer 的对接方式。

---

## 一、论文抓取机制

### 1.1 抓取入口

| 入口 | 方式 | 触发场景 |
|------|------|----------|
| REST API | `POST /api/fetch` | 用户手动触发、前端按钮 |
| REST API | `POST /api/fetch/categories` | 按分类批量抓取 |
| REST API | `POST /api/fetch/date-range` | 按日期范围抓取 |
| CLI | `python scripts/manage.py fetch` | 命令行/定时任务 |

### 1.2 抓取流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        论文抓取流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户触发 ──→ ArxivService.fetch_*()                            │
│                     │                                           │
│                     ▼                                           │
│              ┌──────────────┐                                   │
│              │ ArXiv API    │  搜索/分类/日期查询                │
│              │ (Python SDK) │                                   │
│              └──────┬───────┘                                   │
│                     │                                           │
│                     ▼                                           │
│              ┌──────────────┐                                   │
│              │ PaperScorer  │  预筛选评分                        │
│              │ .should_fetch│  决定是否入库                      │
│              └──────┬───────┘                                   │
│                     │                                           │
│         ┌──────────┴──────────┐                                 │
│         ▼                     ▼                                 │
│    score >= 25           score < 25                             │
│    或热门关键词 >= 3        ↓                                   │
│         │              跳过不入库                                │
│         ▼                                                       │
│  ┌──────────────┐                                               │
│  │ 计算 Tier    │  A/B/C 初始评级                                │
│  │ score >= 80→A│                                               │
│  │ score >= 50→B│                                               │
│  │ else → C     │                                               │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────┐                                               │
│  │ 入库到       │  papers.db                                    │
│  │ papers 表    │  has_analysis = False                         │
│  └──────────────┘                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 预筛选规则

**评分维度**（满分 100）：

| 维度 | 权重 | 说明 |
|------|------|------|
| 热门方向 | 40分 | LLM、Agent、RAG、多模态等 |
| 主题相关性 | 20分 | AI 系统方向匹配度 |
| 创新信号 | 15分 | novel、SOTA、breakthrough 等 |
| 机构权重 | 15分 | Google、OpenAI、Stanford 等 |
| 低质量扣分 | -20分 | survey、tutorial、review 等 |

**快速通道**（绕过评分）：
- 热门关键词匹配 >= 3 个
- 超高热度关键词在标题中（llm、agent、rag 等）
- 顶级机构论文（Google、OpenAI、DeepMind 等）

**入库阈值**：score >= 25

### 1.4 抓取方式详解

#### 按关键词抓取

```python
# REST API
POST /api/fetch?query=transformer+attention&max_results=50

# Python 调用
result = await ArxivService.fetch_papers(db, query="transformer attention", max_results=50)
```

#### 按分类抓取

```python
# REST API
POST /api/fetch/categories?categories=["cs.AI","cs.LG"]&max_results=100

# Python 调用
result = await ArxivService.fetch_by_categories(db, categories=["cs.AI", "cs.LG"], max_results=100)
```

#### 按日期范围抓取

```python
# REST API
POST /api/fetch/date-range?from=2024-01-01&to=2024-01-31&max_results=200

# Python 调用
result = await ArxivService.fetch_by_date_range(
    db,
    date_from=datetime(2024, 1, 1),
    date_to=datetime(2024, 1, 31),
    max_results=200,
    prefilter=True  # 启用预筛选
)
```

---

## 二、分析流程

### 2.1 分析触发

```python
# REST API
POST /api/papers/{paper_id}/analyze?force_refresh=false

# MCP Tool
analyze_paper(paper_id=123, force_refresh=False)
```

### 2.2 分析流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        论文分析流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  触发分析 ──→ AnalysisTaskHandler.handle()                      │
│                     │                                           │
│                     ▼                                           │
│  ┌──────────────────────────────────────┐                       │
│  │ Phase 1: 读取论文信息                 │                       │
│  │ (标题、摘要、arxiv_id、pdf_url)       │                       │
│  └────────────────┬─────────────────────┘                       │
│                   ▼                                             │
│  ┌──────────────────────────────────────┐                       │
│  │ Phase 2: 获取内容                     │                       │
│  │ - 快速模式：使用摘要                   │                       │
│  │ - 完整模式：下载 PDF + 解析            │                       │
│  └────────────────┬─────────────────────┘                       │
│                   ▼                                             │
│  ┌──────────────────────────────────────┐                       │
│  │ Phase 3: AI 分析                      │                       │
│  │ - 生成 Tier、Tags、Summary            │                       │
│  │ - 生成分析报告                        │                       │
│  └────────────────┬─────────────────────┘                       │
│                   ▼                                             │
│  ┌──────────────────────────────────────┐                       │
│  │ Phase 4: 验证结果                     │                       │
│  │ - 必要字段检查                        │                       │
│  │ - 质量门槛验证                        │                       │
│  └────────────────┬─────────────────────┘                       │
│                   ▼                                             │
│  ┌──────────────────────────────────────┐                       │
│  │ Phase 5: 导出到 Obsidian              │                       │
│  │ - Tier A → 96_Papers_Archive/重要论文 │                       │
│  │ - Tier B/C → Inbox                    │                       │
│  └────────────────┬─────────────────────┘                       │
│                   ▼                                             │
│  ┌──────────────────────────────────────┐                       │
│  │ Phase 6: 同步到 RAG                   │                       │
│  │ - 调用 ingest_incremental.py          │                       │
│  │ - 更新 rag_indexed 字段               │                       │
│  └──────────────────────────────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、Obsidian CLI 与 Paper Analyzer 对接

### 3.1 Obsidian CLI 概述

Obsidian CLI 是一个 Claude Code Skill，用于操作 Obsidian Vault：

```bash
# 读取笔记
obsidian read file="PAPER_2026-04-02_Title"

# 搜索笔记
obsidian search query="RAG optimization" limit=10

# 创建笔记
obsidian create name="PAPER_2026-04-02_New" content="# Title\n..."

# 设置属性
obsidian property:set name="tier" value="A" file="PAPER_xxx"
```

### 3.2 对接场景

#### 场景 A：用户在 Obsidian 中发现论文，想抓取分析

**当前方式**：无直接对接，需要：
1. 手动在 Paper Analyzer 前端/API 抓取
2. 手动触发分析

**建议改进**：创建 Obsidian 命令面板命令或 Templater 脚本调用 Paper Analyzer API

#### 场景 B：论文分析后自动同步到 Obsidian

**当前方式**：自动
- 分析完成后调用 `markdown_generator.py` 导出到 Vault
- 路径根据 Tier 决定（A→归档，B/C→Inbox）

#### 场景 C：从 Obsidian 搜索已分析论文

**当前方式**：
1. 直接在 Obsidian 中搜索
2. 通过 MCP Tool `search_obsidian` 搜索

#### 场景 D：论文移动后追踪

**当前方式**：
- `vault_locations` 字段记录论文在 Vault 的所有位置
- `sync_vault_locations.py` 定期扫描更新

### 3.3 推荐工作流

```
┌─────────────────────────────────────────────────────────────────┐
│                     完整工作流                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 抓取论文                                                    │
│     ├─→ 前端按钮 "抓取新论文"                                    │
│     ├─→ API: POST /api/fetch?query=...                          │
│     └─→ CLI: python scripts/manage.py fetch --query ...         │
│                                                                 │
│  2. 分析论文                                                    │
│     ├─→ 前端点击 "分析"                                          │
│     ├─→ API: POST /api/papers/{id}/analyze                      │
│     └─→ CLI: python scripts/manage.py analyze                   │
│                                                                 │
│  3. 自动导出到 Obsidian                                         │
│     └─→ Inbox/ 或 96_Papers_Archive/重要论文/                    │
│                                                                 │
│  4. 自动同步到 RAG                                              │
│     └─→ LanceDB + rag_indexed 更新                              │
│                                                                 │
│  5. 用户在 Obsidian 中管理                                      │
│     ├─→ 阅读笔记                                                │
│     ├─→ 移动到分类目录                                          │
│     └─→ 添加个人标注                                            │
│                                                                 │
│  6. 定期同步                                                    │
│     ├─→ VaultSyncMaster 扫描 Vault → LanceDB                    │
│     ├─→ sync_vault_locations.py 更新路径追踪                    │
│     └─→ 每日 3:00 自动执行                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、接口规范

### 4.1 抓取 API

```yaml
# 按关键词抓取
POST /api/fetch
Body:
  query: string           # ArXiv 查询语句
  max_results: int        # 最大数量，默认 50
Response:
  total_fetched: int
  new_papers: int
  message: string

# 按分类抓取
POST /api/fetch/categories
Body:
  categories: string[]    # ArXiv 分类
  max_results: int
Response:
  同上

# 按日期范围抓取
POST /api/fetch/date-range
Body:
  categories: string[]    # 可选，默认 ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]
  date_from: date         # YYYY-MM-DD
  date_to: date
  max_results: int        # 建议 200-500
Response:
  total_fetched: int
  new_papers: int
  filtered_papers: int    # 日期范围内
  skipped_by_score: int   # 预筛选跳过
  message: string
```

### 4.2 分析 API

```yaml
POST /api/papers/{paper_id}/analyze
Params:
  force_refresh: bool     # 是否重新分析
Response:
  task_id: string         # 异步任务 ID
  status: pending|processing|completed|failed
  message: string
```

### 4.3 Obsidian CLI 命令

```bash
# 搜索已导出论文
obsidian search query="PAPER_" limit=20

# 读取论文笔记
obsidian read file="PAPER_2026-04-02_Title"

# 创建新论文笔记（手动）
obsidian create \
  name="PAPER_2026-04-02_Manual-Entry" \
  template="Paper Template" \
  content="# 标题\n\n摘要..."

# 更新论文属性
obsidian property:set name="tier" value="A" file="PAPER_xxx"
obsidian property:set name="tags" value="rag, llm, research" file="PAPER_xxx"
```

---

## 五、数据模型

### 5.1 Paper 核心字段

```python
class Paper:
    # 基本信息
    id: int
    arxiv_id: str           # 唯一标识
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    publish_date: datetime

    # 分析结果
    has_analysis: bool      # 是否已分析
    tier: str               # A/B/C
    tags: List[str]
    summary: str
    analysis_report: str
    analysis_json: dict

    # 追踪字段
    md_output_path: str     # 导出路径
    vault_locations: List[str]  # Vault 中所有位置
    rag_indexed: bool       # 是否同步到 LanceDB
    lancedb_id: str         # LanceDB ID
```

### 5.2 字段更新时机

| 字段 | 更新时机 | 更新方式 |
|------|----------|----------|
| tier | 分析时 / 定期重估 | AI 评估 + 引用数 + 时效 |
| md_output_path | 导出到 Obsidian 时 | markdown_generator.py |
| vault_locations | Vault 扫描时 | sync_vault_locations.py |
| rag_indexed | LanceDB 同步时 | update_rag_indexed.py |

---

## 六、待优化事项

### 6.1 短期优化

1. **Obsidian 插件集成**
   - 创建 Obsidian 插件调用 Paper Analyzer API
   - 支持在 Obsidian 中直接抓取和分析论文

2. **CLI 工具增强**
   - `scripts/manage.py` 增加 `--obsidian` 参数
   - 抓取后自动在 Obsidian 中打开

### 6.2 长期优化

1. **双向同步**
   - Obsidian 修改 → 同步回 Paper Analyzer
   - 支持在 Obsidian 中修改 Tier、Tags

2. **智能推荐**
   - 基于阅读历史推荐论文
   - 基于笔记内容推荐相关论文

---

## 版本信息

- 文档版本: v1.0
- 更新日期: 2026-04-02
- 相关文件:
  - `app/services/arxiv_service.py`
  - `app/services/paper_scorer.py`
  - `app/tasks/analysis_task.py`
  - `app/outputs/markdown_generator.py`