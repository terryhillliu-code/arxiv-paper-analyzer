# ArXiv 论文智能分析平台 - 项目架构文档

> 文档版本: 1.0
> 最后更新: 2026-03-18

---

## 一、项目概述

### 1.1 项目名称
ArXiv 论文智能分析平台 (ArXiv Paper Intelligence Analysis Platform)

### 1.2 功能描述
基于 Claude AI 的 ArXiv 论文聚合、检索与深度分析系统。主要功能包括：
- 从 ArXiv 自动抓取指定学科/关键词的论文
- AI 生成中文一句话总结
- AI 驱动的论文深度分析报告
- 自动识别论文主题标签和作者机构
- 多维度筛选和全文检索
- PDF 自动下载与文本提取

### 1.3 技术栈

**后端技术栈：**
| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 核心开发语言 |
| FastAPI | 0.104+ | Web 框架 |
| SQLAlchemy | 2.0+ | 异步 ORM |
| Pydantic | 2.5+ | 数据验证 |
| SQLite + aiosqlite | - | 数据库 |
| ArXiv API | 2.1+ | 论文元数据获取 |
| PyMuPDF | 1.24+ | PDF 文本提取 |
| Anthropic Claude API | 0.39+ | AI 分析 |

**前端技术栈：**
| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19.2+ | UI 框架 |
| Vite | 5.4+ | 构建工具 |
| Tailwind CSS | 3.4+ | 原子化 CSS |
| React Router | 7.13+ | 路由管理 |
| React Markdown | 10.1+ | Markdown 渲染 |
| KaTeX | 0.16+ | 数学公式渲染 |
| date-fns | 4.1+ | 日期处理 |

---

## 二、系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户交互层 (Frontend)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  PaperList  │  │PaperDetail  │  │  PaperCard  │  │  AnalysisReport     │ │
│  │   (列表页)  │  │  (详情页)   │  │  (卡片组件) │  │  (Markdown渲染)     │ │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────────────┘ │
│         │                │                                                    │
│         └────────────────┼────────────────────────────────────────────────────┤
│                          ▼                                                    │
│                   api/papers.js (API 调用层)                                  │
└──────────────────────────┬────────────────────────────────────────────────────┘
                           │ HTTP/REST API
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            功能服务层 (Backend)                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        FastAPI Application                              ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ ││
│  │  │  main.py     │  │routers/      │  │  schemas.py  │  │  config.py  │ ││
│  │  │  (入口)      │→ │papers.py     │→ │  (验证)      │  │  (配置)     │ ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                          │                                                   │
│  ┌───────────────────────┼─────────────────────────────────────────────────┐│
│  │                       ▼                服务层                           ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  ││
│  │  │arxiv_service │  │ pdf_service  │  │  ai_service  │                  ││
│  │  │(论文抓取)    │  │(PDF处理)     │  │ (AI分析)     │                  ││
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  ││
│  └─────────┼────────────────┼────────────────┼────────────────────────────┘│
└────────────┼────────────────┼────────────────┼─────────────────────────────┘
             │                │                │
             ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            外部服务与数据层                                  │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │  ArXiv API   │  │  PDF Files   │  │ Claude API   │  │    SQLite DB    │ │
│  │  (论文元数据)│  │  (论文全文)  │  │  (AI分析)    │  │   (本地存储)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、目录结构

```
arxiv-paper-analyzer/
├── backend/                          # 后端代码目录
│   ├── app/                          # 应用主目录
│   │   ├── __init__.py               # 包初始化
│   │   ├── main.py                   # FastAPI 应用入口，配置中间件和路由
│   │   ├── config.py                 # 配置管理，使用 pydantic-settings
│   │   ├── database.py               # 异步数据库连接管理
│   │   ├── models.py                 # SQLAlchemy 数据模型定义
│   │   ├── schemas.py                # Pydantic 数据验证模型
│   │   ├── routers/                  # API 路由目录
│   │   │   ├── __init__.py           # 路由包初始化
│   │   │   └── papers.py             # 论文相关 API 端点
│   │   ├── services/                 # 业务服务目录
│   │   │   ├── __init__.py           # 服务包初始化
│   │   │   ├── arxiv_service.py      # ArXiv 论文抓取服务
│   │   │   ├── pdf_service.py        # PDF 下载与文本提取服务
│   │   │   └── ai_service.py         # AI 分析服务
│   │   └── prompts/                  # 提示词目录
│   │       ├── __init__.py           # 提示词包初始化
│   │       └── templates.py          # AI 提示词模板
│   ├── data/                         # 数据目录（运行时创建）
│   │   ├── papers.db                 # SQLite 数据库文件
│   │   └── pdfs/                     # PDF 文件存储目录
│   ├── .env                          # 环境变量配置
│   ├── requirements.txt              # Python 依赖列表
│   ├── run.py                        # 应用启动脚本
│   └── test_api.py                   # API 测试脚本
│
├── frontend/                         # 前端代码目录
│   ├── src/                          # 源代码目录
│   │   ├── api/                      # API 调用层
│   │   │   └── papers.js             # 后端 API 封装函数
│   │   ├── components/               # 可复用组件
│   │   │   ├── PaperCard.jsx         # 论文卡片组件
│   │   │   └── AnalysisReport.jsx    # Markdown 分析报告渲染组件
│   │   ├── pages/                    # 页面组件
│   │   │   ├── PaperList.jsx         # 论文列表页
│   │   │   └── PaperDetail.jsx       # 论文详情页
│   │   ├── App.jsx                   # 根组件，路由配置
│   │   ├── main.jsx                  # 应用入口
│   │   └── index.css                 # 全局样式（Tailwind + 自定义）
│   ├── index.html                    # HTML 入口文件
│   ├── package.json                  # Node.js 依赖配置
│   ├── vite.config.js                # Vite 构建配置
│   ├── tailwind.config.js            # Tailwind CSS 配置
│   ├── postcss.config.js             # PostCSS 配置
│   └── eslint.config.js              # ESLint 配置
│
├── verify_system.py                  # 系统功能验证脚本
├── verify_frontend.py                # 前端功能验证脚本
├── README.md                         # 项目说明文档
└── package-lock.json                 # 根目录 npm 锁文件
```

---

## 四、后端架构详解

### 4.1 技术栈说明
- **FastAPI**：异步 Web 框架，自动生成 OpenAPI 文档
- **SQLAlchemy 2.0**：支持异步操作的 ORM
- **aiosqlite**：SQLite 异步驱动
- **Pydantic v2**：数据验证和序列化

### 4.2 各模块功能详解

#### config.py - 配置管理
```python
# 主要配置项
- anthropic_api_key: AI API 密钥
- database_url: 数据库连接字符串
- arxiv_fetch_max: 单次抓取最大数量
- pdf_storage_path: PDF 存储路径
- ai_model: AI 模型名称
- ai_max_tokens: 最大 token 数
- predefined_tags: 预设标签列表
```

#### database.py - 数据库连接
```python
# 功能
- 创建异步引擎 (create_async_engine)
- 创建异步会话工厂 (async_sessionmaker)
- 提供 get_db() 依赖注入
- 提供 init_db() 初始化函数
```

#### models.py - 数据模型
```python
# Paper 模型字段
- id: 主键
- arxiv_id: ArXiv 论文 ID（唯一索引）
- title: 标题
- authors: 作者列表 (JSON)
- institutions: 机构列表 (JSON)
- abstract: 摘要
- categories: 分类列表 (JSON)
- tags: 标签列表 (JSON)
- summary: AI 生成的一句话总结
- publish_date: 发布日期
- pdf_url, arxiv_url: 链接
- pdf_local_path: 本地 PDF 路径
- full_text: 提取的全文
- has_analysis: 是否已分析
- analysis_report: 分析报告 (Markdown)
- analysis_json: 结构化分析数据 (JSON)
- created_at, updated_at: 时间戳
- view_count: 浏览次数
- is_featured: 是否精选

# FetchLog 模型字段
- id: 主键
- query: 查询语句
- total_fetched: 抓取总数
- new_papers: 新增数量
- fetch_time: 抓取时间
- status: 状态 (pending/success/failed)
- error_message: 错误信息
```

#### schemas.py - 数据验证
```python
# 请求模型
- FetchRequest: 抓取请求参数
- FetchByCategoriesRequest: 按分类抓取参数
- AnalysisRequest: 分析请求参数

# 响应模型
- PaperCard: 列表页卡片数据
- PaperDetail: 详情页完整数据
- PaperListResponse: 分页列表响应
- FetchResponse: 抓取响应
- AnalysisResponse: 分析响应
- StatsResponse: 统计响应
```

#### routers/papers.py - API 路由

| 端点 | 方法 | 功能 |
|------|------|------|
| `GET /api/papers` | GET | 获取论文列表（分页、筛选、排序） |
| `GET /api/papers/{id}` | GET | 获取论文详情 |
| `GET /api/papers/arxiv/{arxiv_id}` | GET | 通过 ArXiv ID 查询论文 |
| `POST /api/fetch` | POST | 从 ArXiv 抓取论文 |
| `POST /api/fetch/categories` | POST | 按分类抓取论文 |
| `POST /api/papers/generate-summaries` | POST | 批量生成摘要 |
| `POST /api/papers/{id}/analyze` | POST | 生成深度分析 |
| `GET /api/stats` | GET | 获取统计数据 |
| `GET /api/tags` | GET | 获取标签列表 |
| `GET /api/categories` | GET | 获取分类列表 |

#### services/arxiv_service.py - ArXiv 服务
```python
# 主要方法
- fetch_papers(db, query, max_results): 按查询语句抓取
- fetch_by_categories(db, categories, max_results): 按分类抓取
- fetch_by_keywords(db, keywords, max_results): 按关键词抓取

# 支持的分类
cs.AI, cs.CL, cs.LG, cs.CV, cs.NE, cs.IR, cs.RO, cs.SE, cs.DC, cs.CR,
stat.ML, eess.AS, eess.IV
```

#### services/pdf_service.py - PDF 服务
```python
# 主要方法
- download_pdf(pdf_url, arxiv_id): 下载 PDF 到本地
- extract_text(pdf_path, max_pages): 提取 PDF 文本
- get_paper_text(pdf_url, arxiv_id): 完整流程（下载+提取）

# 文本清理功能
- 移除过多空行
- 移除孤立页码
- 合并被截断的英文单词
```

#### services/ai_service.py - AI 服务
```python
# 主要方法
- generate_summary(title, authors, abstract, categories): 生成摘要
- generate_deep_analysis(...): 生成深度分析报告
- _extract_analysis_json(report): 提取结构化数据
- _parse_json(text): 多策略 JSON 解析
```

#### prompts/templates.py - 提示词模板
```python
# 摘要生成提示词 (SUMMARY_PROMPT)
- 任务：标签匹配、机构推断、一句话总结
- 输出：JSON 格式 {tags, institutions, summary}

# 深度分析提示词 (DEEP_ANALYSIS_PROMPT)
- 板块：基础信息、一句话总结、论文大纲、深度解析、综合评估、结论
- 格式：Markdown，支持 LaTeX 公式

# 结构化提取提示词 (ANALYSIS_JSON_PROMPT)
- 字段：one_line_summary, outline, key_contributions, strengths, weaknesses,
        methodology, datasets, metrics, future_directions, overall_rating, recommendation
```

---

## 五、前端架构详解

### 5.1 技术栈说明
- **React 19**：最新版 React，支持并发特性
- **Vite 5**：快速开发服务器和构建工具
- **Tailwind CSS 3**：原子化 CSS 框架
- **React Router 7**：声明式路由

### 5.2 页面组件详解

#### App.jsx - 根组件
```jsx
// 功能
- 整体布局（顶部导航、二级导航、主内容区、底部 Footer）
- 路由配置（/ → PaperList, /paper/:id → PaperDetail）
- 紫色主题风格
```

#### PaperList.jsx - 列表页
```jsx
// 区域划分
- 区域1：分类选择（CATEGORY + 智能分类）+ 统计数字
- 区域2：搜索框 + FILTER 行（日期、排序、刷新、抓取、AI摘要）
- 区域3：论文卡片列表 + 分页

// 状态管理
- papers: 论文列表
- stats: 统计数据
- search, selectedCategory, selectedTag, dateFrom, sortBy, page: 筛选条件
- loading, fetching, summarizing: 加载状态
```

#### PaperDetail.jsx - 详情页
```jsx
// 卡片划分
- 卡片1：基础信息（标题、作者、机构、日期、分类、ArXiv/PDF 按钮）
- 卡片2：一段话总结
- 卡片3：思维导图/论文大纲（OutlineTree 组件）
- 卡片4：深度分析（生成按钮/加载动画/分析报告）
- 卡片5：综合评估（主要贡献、优势、不足、未来方向）

// 状态管理
- paper: 论文详情
- analyzing: 分析状态
- analysisProgress: 分析进度提示
```

#### PaperCard.jsx - 论文卡片组件
```jsx
// Props
- paper: 论文数据对象
- index: 序号

// 显示内容
- 序号 + 分类标签 + 主题标签
- 标题（链接到详情页）
- 作者（最多6个）
- 机构（第一个加粗显示）
- 日期
- 一段话总结（紫色左边框样式）
- 深度分析按钮
```

#### AnalysisReport.jsx - Markdown 渲染组件
```jsx
// 功能
- 渲染 Markdown 格式的分析报告
- 支持 GFM（GitHub Flavored Markdown）
- 支持数学公式（KaTeX）
- 支持表格、代码块、引用等

// 自定义组件
- 标题（h1-h3）
- 表格（响应式）
- 代码（行内/块级）
- 引用块
- 列表
```

### 5.3 API 调用层 (api/papers.js)
```javascript
// 主要函数
- fetchPapers(params): 获取论文列表
- fetchPaperDetail(id): 获取论文详情
- triggerFetch(query, maxResults): 触发抓取
- generateSummaries(limit): 批量生成摘要
- analyzePaper(paperId, forceRefresh): 生成深度分析
- fetchStats(): 获取统计数据
- fetchTags(): 获取标签列表
- fetchCategories(): 获取分类列表
```

---

## 六、数据流程图

### 6.1 论文抓取流程
```
用户点击「抓取论文」
       │
       ▼
前端调用 POST /api/fetch
       │
       ▼
ArxivService.fetch_papers()
       │
       ├─── 构建 ArXiv 查询
       │
       ▼
调用 ArXiv API 获取论文列表
       │
       ├─── 解析 arxiv_id
       ├─── 提取 authors, categories
       │
       ▼
检查数据库是否已存在
       │
       ├─── 不存在 → 创建 Paper 对象
       ├─── 存在 → 跳过
       │
       ▼
保存到 SQLite 数据库
       │
       ▼
返回抓取统计 {total_fetched, new_papers}
```

### 6.2 AI 摘要生成流程
```
用户点击「AI摘要」
       │
       ▼
前端调用 POST /api/papers/generate-summaries
       │
       ▼
查询 summary 为空的论文
       │
       ▼
遍历每篇论文:
       │
       ├─── 构建 SUMMARY_PROMPT
       │         │
       │         ▼
       │    调用 Claude API
       │         │
       │         ▼
       │    解析 JSON 响应
       │         │
       │         ├─── tags: 主题标签
       │         ├─── institutions: 机构
       │         └─── summary: 一句话总结
       │
       ▼
更新论文记录
       │
       ▼
返回处理统计 {processed, success, failed}
```

### 6.3 深度分析生成流程
```
用户点击「生成深度分析」
       │
       ▼
前端调用 POST /api/papers/{id}/analyze
       │
       ▼
检查是否已有分析（可强制刷新）
       │
       ▼
获取论文全文内容
       │
       ├─── 有 full_text → 直接使用
       ├─── 无 full_text 但有 pdf_url →
       │         │
       │         ▼
       │    PDFService.get_paper_text()
       │         │
       │         ├─── 下载 PDF
       │         └─── 提取文本
       │
       ▼
构建 DEEP_ANALYSIS_PROMPT
       │
       ▼
调用 Claude API 生成报告
       │
       ▼
提取结构化数据 (ANALYSIS_JSON_PROMPT)
       │
       ▼
保存 analysis_report 和 analysis_json
       │
       ▼
返回分析结果
```

### 6.4 用户浏览流程
```
用户访问首页
       │
       ▼
加载 PaperList 页面
       │
       ├─── GET /api/stats → 统计数据
       └─── GET /api/papers → 论文列表
              │
              ▼
         渲染论文卡片列表
              │
              ├─── 分类筛选
              ├─── 标签筛选
              ├─── 搜索
              └─── 排序
              │
              ▼
用户点击论文卡片
       │
       ▼
跳转到 /paper/{id}
       │
       ▼
加载 PaperDetail 页面
       │
       └─── GET /api/papers/{id}
              │
              ▼
         显示论文详情
              │
              ├─── 查看基础信息
              ├─── 查看一段话总结
              ├─── 查看思维导图
              ├─── 查看/生成深度分析
              └─── 查看综合评估
```

---

## 七、数据库设计

### 7.1 papers 表结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | 主键，自增 |
| arxiv_id | VARCHAR(50) | ArXiv 论文 ID，唯一索引 |
| title | TEXT | 论文标题，非空 |
| authors | JSON | 作者列表 |
| institutions | JSON | 机构列表 |
| abstract | TEXT | 摘要 |
| categories | JSON | ArXiv 分类列表 |
| tags | JSON | AI 生成的主题标签 |
| summary | TEXT | AI 生成的一句话总结 |
| publish_date | DATETIME | 发布日期 |
| pdf_url | VARCHAR(500) | PDF 下载链接 |
| arxiv_url | VARCHAR(500) | ArXiv 页面链接 |
| pdf_local_path | VARCHAR(500) | 本地 PDF 路径 |
| full_text | TEXT | 提取的全文内容 |
| has_analysis | BOOLEAN | 是否已分析，默认 false |
| analysis_report | TEXT | Markdown 分析报告 |
| analysis_json | JSON | 结构化分析数据 |
| created_at | DATETIME | 创建时间，自动生成 |
| updated_at | DATETIME | 更新时间，自动更新 |
| view_count | INTEGER | 浏览次数，默认 0 |
| is_featured | BOOLEAN | 是否精选，默认 false |

### 7.2 fetch_logs 表结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | 主键，自增 |
| query | TEXT | ArXiv 查询语句 |
| total_fetched | INTEGER | 抓取总数 |
| new_papers | INTEGER | 新增论文数 |
| fetch_time | DATETIME | 抓取时间 |
| status | VARCHAR(20) | 状态：pending/success/failed |
| error_message | TEXT | 错误信息 |

---

## 八、API 接口文档

### 8.1 健康检查

**GET /health**

响应示例：
```json
{
  "status": "ok"
}
```

### 8.2 获取论文列表

**GET /api/papers**

查询参数：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| search | string | 否 | 搜索关键词 |
| categories | string | 否 | 分类，逗号分隔 |
| tags | string | 否 | 标签，逗号分隔 |
| date_from | datetime | 否 | 开始日期 |
| date_to | datetime | 否 | 结束日期 |
| has_analysis | boolean | 否 | 是否有分析 |
| sort_by | string | 否 | 排序：newest/oldest/views |
| page | integer | 否 | 页码，默认 1 |
| page_size | integer | 否 | 每页数量，默认 20 |

响应示例：
```json
{
  "papers": [
    {
      "id": 1,
      "arxiv_id": "2301.00001",
      "title": "论文标题",
      "authors": ["作者1", "作者2"],
      "categories": ["cs.AI", "cs.LG"],
      "tags": ["大模型基础架构"],
      "summary": "一句话总结...",
      "has_analysis": true,
      "view_count": 10,
      "created_at": "2026-03-18T00:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

### 8.3 获取论文详情

**GET /api/papers/{id}**

响应示例：
```json
{
  "id": 1,
  "arxiv_id": "2301.00001",
  "title": "论文标题",
  "authors": ["作者1", "作者2"],
  "institutions": ["机构1"],
  "categories": ["cs.AI"],
  "tags": ["大模型基础架构"],
  "summary": "一句话总结...",
  "abstract": "原始摘要...",
  "publish_date": "2026-03-18",
  "arxiv_url": "https://arxiv.org/abs/2301.00001",
  "pdf_url": "https://arxiv.org/pdf/2301.00001",
  "has_analysis": true,
  "analysis_report": "# 深度分析报告...",
  "analysis_json": {
    "one_line_summary": "...",
    "outline": [...],
    "main_contributions": [...]
  }
}
```

### 8.4 抓取论文

**POST /api/fetch**

请求体：
```json
{
  "query": "cat:cs.AI OR cat:cs.CL",
  "max_results": 20
}
```

响应示例：
```json
{
  "total_fetched": 20,
  "new_papers": 15,
  "message": "成功抓取 20 篇论文，其中 15 篇为新论文"
}
```

### 8.5 批量生成摘要

**POST /api/papers/generate-summaries?limit=10**

响应示例：
```json
{
  "processed": 10,
  "success": 8,
  "failed": 2,
  "message": "处理完成: 成功 8 篇，失败 2 篇"
}
```

### 8.6 生成深度分析

**POST /api/papers/{id}/analyze?force_refresh=false**

响应示例：
```json
{
  "paper_id": 1,
  "status": "completed",
  "report": "# 深度分析报告\n\n## 基础信息...",
  "message": "分析完成"
}
```

### 8.7 获取统计数据

**GET /api/stats**

响应示例：
```json
{
  "total_papers": 100,
  "analyzed_papers": 20,
  "categories": {
    "cs.AI": 50,
    "cs.CL": 30,
    "cs.LG": 20
  },
  "tags": {
    "大模型基础架构": 30,
    "GPU硬件架构": 15
  },
  "recent_papers_count": 10
}
```

### 8.8 获取标签列表

**GET /api/tags**

响应示例：
```json
{
  "tags": [
    "大模型基础架构",
    "GPU硬件架构",
    "AI集群",
    "训练推理框架"
  ]
}
```

### 8.9 获取分类列表

**GET /api/categories**

响应示例：
```json
{
  "categories": {
    "cs.AI": {
      "name": "人工智能",
      "description": "Artificial Intelligence"
    },
    "cs.CL": {
      "name": "计算语言学",
      "description": "Computation and Language"
    }
  }
}
```

---

## 九、AI 提示词设计

### 9.1 摘要生成提示词设计思路

**目标**：快速为论文生成标签、机构和一句话总结

**设计要点**：
1. **预设标签库**：提供 20 个预定义标签，确保标签一致性
2. **结构化输出**：强制 JSON 格式输出，便于解析和存储
3. **约束条件**：
   - 标签最多 3 个
   - 总结控制在 150 字以内
   - 必须包含研究问题、核心方法、主要结论

**提示词结构**：
```
任务说明 → 预设标签库 → 论文信息 → 输出格式要求
```

### 9.2 深度分析提示词设计思路

**目标**：生成专业、全面、结构化的论文分析报告

**设计要点**：
1. **专业角色设定**：学术论文分析专家
2. **完整分析框架**：7 大板块覆盖论文全貌
3. **数据准确性**：要求引用论文具体数据，禁止编造
4. **格式规范**：Markdown 格式，支持 LaTeX 公式

**分析板块**：
- 📋 基础信息
- 💡 一句话总结
- 📑 论文大纲
- 🔍 深度解析（7 个子板块）
- ⭐ 综合评估
- 📝 结论

### 9.3 结构化提取提示词设计思路

**目标**：从 Markdown 报告中提取结构化数据，便于前端展示

**设计要点**：
1. **字段定义清晰**：11 个字段，类型明确
2. **可选值约束**：如 overall_rating 必须是 A/B/C
3. **空值处理**：无法提取时返回空列表

**提取字段**：
- one_line_summary: 一句话总结
- outline: 论文大纲
- key_contributions: 主要贡献
- strengths: 优势
- weaknesses: 不足
- methodology: 方法类型
- datasets: 数据集
- metrics: 评估指标
- future_directions: 未来方向
- overall_rating: 综合评级
- recommendation: 推荐语

---

## 十、部署说明

### 10.1 环境要求

| 软件 | 版本要求 |
|------|----------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

### 10.2 安装步骤

**后端安装**：
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

**前端安装**：
```bash
cd frontend
npm install
```

### 10.3 启动方式

**启动后端**：
```bash
cd backend
source venv/bin/activate
python run.py
# 服务运行在 http://localhost:8000
```

**启动前端**：
```bash
cd frontend
npm run dev
# 服务运行在 http://localhost:5173
```

### 10.4 环境变量配置

创建 `backend/.env` 文件：

```env
# API 配置（必填）
ANTHROPIC_API_KEY=your_api_key_here

# 数据库配置（可选）
DATABASE_URL=sqlite+aiosqlite:///./data/papers.db

# PDF 存储（可选）
PDF_STORAGE_PATH=./data/pdfs

# AI 模型配置（可选）
AI_MODEL=glm-5
AI_MAX_TOKENS=8000
```

---

## 十一、功能验证

### 11.1 验证脚本说明

**verify_system.py** - 系统功能验证
- 检查后端服务连通性
- 检查数据库连接
- 检查 ArXiv API 连接
- 检查 AI API 连接
- 检查论文抓取功能
- 检查摘要生成功能
- 检查深度分析功能

**verify_frontend.py** - 前端功能验证
- 检查前端服务运行状态
- 检查后端 API 连通性
- 检查论文数据完整性
- 检查详情页数据
- 输出验证报告

### 11.2 手动验证清单

**基础功能**：
- [ ] 访问 http://localhost:5173 能正常显示页面
- [ ] 点击「抓取论文」能成功抓取
- [ ] 论文列表能正常显示
- [ ] 分类筛选功能正常
- [ ] 搜索功能正常

**AI 功能**：
- [ ] 点击「AI摘要」能生成摘要
- [ ] 论文卡片显示一句话总结
- [ ] 点击「深度分析」能生成报告
- [ ] 分析报告能正常渲染（Markdown + 公式）

**详情页**：
- [ ] 论文详情页正常显示
- [ ] 思维导图正常显示
- [ ] 综合评估正常显示
- [ ] ArXiv/PDF 链接可点击

---

*文档结束*