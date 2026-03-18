# ArXiv 论文智能分析平台 - 系统架构

> 生成时间: 2026-03-18

## 一、项目概览

基于 AI 的 ArXiv 论文聚合、检索与深度分析系统。

**核心功能**：
- 论文抓取（ArXiv API）
- 智能摘要生成
- 深度分析报告
- 多维度筛选检索

## 二、技术栈

### 后端
| 技术 | 用途 |
|------|------|
| Python 3.11+ | 运行时 |
| FastAPI | Web 框架 |
| SQLAlchemy 2.0 | 异步 ORM |
| Pydantic v2 | 数据验证 |
| PyMuPDF | PDF 文本提取 |
| Anthropic Claude API | AI 分析 |

### 前端
| 技术 | 用途 |
|------|------|
| React 19 | UI 框架 |
| Vite 5 | 构建工具 |
| Tailwind CSS 3 | 样式 |
| React Router 7 | 路由 |
| React Markdown + KaTeX | 内容渲染 |

## 三、目录结构

```
arxiv-paper-analyzer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── database.py          # 数据库连接
│   │   ├── models.py            # ORM 模型
│   │   ├── schemas.py           # Pydantic 模式
│   │   ├── routers/
│   │   │   └── papers.py        # API 路由（所有端点）
│   │   ├── services/
│   │   │   ├── arxiv_service.py # ArXiv 抓取
│   │   │   ├── pdf_service.py   # PDF 下载/提取
│   │   │   └── ai_service.py    # AI 分析
│   │   └── prompts/
│   │       └── templates.py     # 提示词模板
│   ├── data/
│   │   ├── papers.db            # SQLite 数据库
│   │   └── pdfs/                # PDF 存储
│   ├── requirements.txt
│   └── run.py
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── papers.js        # API 封装
│   │   ├── components/
│   │   │   ├── PaperCard.jsx    # 论文卡片
│   │   │   └── AnalysisReport.jsx # 分析报告渲染
│   │   ├── pages/
│   │   │   ├── PaperList.jsx    # 列表页
│   │   │   └── PaperDetail.jsx  # 详情页
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
│
├── verify_system.py             # 后端验证脚本
├── verify_frontend.py           # 前端验证脚本
└── README.md
```

## 四、数据模型

### Paper（论文）
```
id              INTEGER PRIMARY KEY
arxiv_id        STRING(50) UNIQUE      # ArXiv 编号
title           TEXT                   # 标题
authors         JSON                   # 作者列表
institutions    JSON                   # 机构列表
abstract        TEXT                   # 摘要
categories      JSON                   # ArXiv 分类
tags            JSON                   # 智能标签
summary         TEXT                   # 一句话总结
publish_date    DATETIME               # 发布日期
pdf_url         STRING                 # PDF 链接
arxiv_url       STRING                 # ArXiv 链接
pdf_local_path  STRING                 # 本地 PDF 路径
full_text       TEXT                   # 提取的全文
has_analysis    BOOLEAN                # 是否已分析
analysis_report TEXT                   # Markdown 分析报告
analysis_json   JSON                   # 结构化分析数据
view_count      INTEGER                # 浏览量
created_at      DATETIME
updated_at      DATETIME
```

### FetchLog（抓取日志）
```
id             INTEGER PRIMARY KEY
query          TEXT                   # 查询语句
total_fetched  INTEGER                # 抓取总数
new_papers     INTEGER                # 新增数量
fetch_time     DATETIME               # 抓取时间
status         STRING                 # pending/success/failed
error_message  TEXT                   # 错误信息
```

## 五、API 端点

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | 根路由信息 |
| GET | `/api/papers` | 论文列表（分页、筛选） |
| GET | `/api/papers/{id}` | 论文详情 |
| GET | `/api/papers/arxiv/{arxiv_id}` | 按 ArXiv ID 查询 |
| POST | `/api/fetch` | 从 ArXiv 抓取论文 |
| POST | `/api/fetch/categories` | 按分类抓取 |
| POST | `/api/papers/generate-summaries` | 批量生成摘要 |
| POST | `/api/papers/{id}/analyze` | 深度分析 |
| GET | `/api/stats` | 统计数据 |
| GET | `/api/tags` | 预设标签列表 |
| GET | `/api/categories` | ArXiv 分类信息 |

## 六、核心数据流

### 1. 论文抓取流程
```
用户触发 → POST /api/fetch
    ↓
ArxivService.fetch_papers()
    ↓
调用 ArXiv API → 解析结果
    ↓
检查数据库是否存在
    ↓
创建 Paper 记录 → 存入 SQLite
    ↓
返回抓取统计
```

### 2. 摘要生成流程
```
POST /api/papers/generate-summaries
    ↓
查询 summary 为空的论文
    ↓
AIService.generate_summary()
    ↓
调用 Claude API → 解析 JSON 响应
    ↓
更新 Paper.tags / institutions / summary
    ↓
返回处理统计
```

### 3. 深度分析流程
```
POST /api/papers/{id}/analyze
    ↓
检查是否已有分析（可强制刷新）
    ↓
PDFService.get_paper_text()
    ├─ 下载 PDF 到本地
    └─ PyMuPDF 提取文本
    ↓
AIService.generate_deep_analysis()
    ├─ 构建 DEEP_ANALYSIS_PROMPT
    ├─ 调用 Claude API
    └─ 提取结构化数据
    ↓
保存 analysis_report / analysis_json
    ↓
返回分析结果
```

## 七、关键配置

### 环境变量 (.env)
```
ANTHROPIC_API_KEY=sk-ant-xxxxx     # AI API 密钥
DATABASE_URL=sqlite+aiosqlite:///./data/papers.db
PDF_STORAGE_PATH=./data/pdfs
AI_MODEL=glm-5                      # 模型名称
AI_MAX_TOKENS=8000                  # 最大 token
ARXIV_FETCH_MAX=50                  # 单次抓取上限
```

### 预设标签（20 个）
```
大模型基础架构, GPU硬件架构, AI集群, 训练推理框架,
代码生成, 图像&视频生成, 多模态, 自然语言处理,
计算机视觉, 强化学习, 知识图谱, 推荐系统,
语音处理, 机器人, 自动驾驶, 医疗AI,
科学计算, 数据挖掘, 计算机存储故障诊断, 安全与隐私
```

## 八、前端页面结构

### PaperList（列表页）
- 分类筛选按钮（CATEGORY）
- 智能标签筛选
- 搜索框
- 日期筛选
- 排序切换
- 抓取论文 / AI摘要 按钮
- 论文卡片列表（PaperCard）
- 分页器

### PaperDetail（详情页）
- 基础信息卡片
- 一段话总结
- 思维导图（大纲树）
- 深度分析报告（Markdown 渲染）
- 综合评估（贡献/优势/不足/方向）

## 九、启动命令

```bash
# 后端
cd backend && source venv/bin/activate && python run.py
# → http://localhost:8000

# 前端
cd frontend && npm run dev
# → http://localhost:5173
```

## 十、验证脚本

```bash
# 后端完整验证
python verify_system.py

# 跳过 AI 测试
python verify_system.py --skip-ai

# 前端验证
python verify_frontend.py
```

---

**文档说明**：此架构文档描述了系统的整体结构、数据流和关键组件，便于快速理解项目。具体实现细节请参考各源代码文件。