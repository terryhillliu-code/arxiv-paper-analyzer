# ArXiv 论文智能分析平台

基于 AI 的 ArXiv 论文聚合、检索与深度分析系统。

## 功能特性

- **论文抓取**：从 ArXiv 自动抓取指定学科/关键词的论文
- **智能摘要**：AI 生成中文一句话总结，快速了解论文主旨
- **深度分析**：AI 驱动的论文深度分析，包括：
  - 研究背景与动机
  - 核心方法与创新点
  - 实验设计与结果
  - 局限性与未来方向
  - 结构化评估（贡献、优势、不足）
- **智能标签**：自动识别论文主题标签
- **机构识别**：提取论文作者所属机构
- **多维度筛选**：按学科分类、主题标签、日期范围筛选
- **全文检索**：支持标题、摘要关键词搜索
- **PDF 处理**：自动下载并提取 PDF 文本内容

## 技术栈

### 后端
- **Python 3.11+**
- **FastAPI** - 现代、高性能的 Web 框架
- **SQLAlchemy 2.0** - 异步 ORM
- **Pydantic v2** - 数据验证
- **ArXiv API** - 论文元数据获取
- **PyMuPDF** - PDF 文本提取
- **Anthropic Claude API**（或兼容 API）- AI 分析

### 前端
- **React 19** - UI 框架
- **Vite 8** - 构建工具
- **Tailwind CSS 4** - 原子化 CSS
- **React Router 7** - 路由管理
- **React Markdown** - Markdown 渲染
- **KaTeX** - 数学公式渲染
- **Lucide React** - 图标库
- **date-fns** - 日期处理

## 安装步骤

### 环境要求
- Python 3.11+
- Node.js 18+
- npm 或 yarn

### 后端安装

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 API 密钥
```

### 环境变量配置

创建 `backend/.env` 文件：

```env
# API 配置（必填）
ANTHROPIC_API_KEY=your_api_key_here

# 可选配置
DATABASE_URL=sqlite+aiosqlite:///./data/papers.db
PDF_STORAGE_PATH=./data/pdfs
AI_MODEL=glm-5
AI_MAX_TOKENS=8000
```

### 前端安装

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install
```

## 使用流程

### 1. 启动后端服务

```bash
cd backend
source venv/bin/activate
python run.py
```

后端服务将在 `http://localhost:8000` 启动。

API 文档：`http://localhost:8000/docs`

### 2. 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端服务将在 `http://localhost:5173` 启动。

### 3. 使用系统

1. 访问 `http://localhost:5173`
2. 点击「抓取新论文」按钮，输入搜索条件（如 `cat:cs.AI`）
3. 等待论文抓取完成
4. 点击「AI生成摘要」批量生成论文摘要
5. 点击论文卡片查看详情
6. 在详情页点击「生成深度分析」获取 AI 分析报告

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/fetch` | 从 ArXiv 抓取论文 |
| GET | `/api/papers` | 获取论文列表（支持分页、筛选） |
| GET | `/api/papers/{id}` | 获取论文详情 |
| POST | `/api/papers/generate-summaries` | 批量生成摘要 |
| POST | `/api/papers/{id}/analyze` | 生成深度分析报告 |
| GET | `/api/stats` | 获取统计数据 |
| GET | `/api/tags` | 获取所有标签 |
| GET | `/api/categories` | 获取所有分类 |

### 请求示例

```bash
# 抓取论文
curl -X POST http://localhost:8000/api/fetch \
  -H "Content-Type: application/json" \
  -d '{"query": "cat:cs.AI", "max_results": 10}'

# 获取论文列表
curl "http://localhost:8000/api/papers?page=1&page_size=10&categories=cs.AI"

# 生成深度分析
curl -X POST http://localhost:8000/api/papers/1/analyze
```

## 项目结构

```
arxiv-paper-analyzer/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI 应用入口
│   │   ├── config.py        # 配置管理
│   │   ├── database.py      # 数据库连接
│   │   ├── models.py        # SQLAlchemy 模型
│   │   ├── schemas.py       # Pydantic 模式
│   │   ├── routers/
│   │   │   └── papers.py    # API 路由
│   │   ├── services/
│   │   │   ├── arxiv_service.py   # ArXiv 服务
│   │   │   ├── pdf_service.py     # PDF 服务
│   │   │   └── ai_service.py      # AI 服务
│   │   └── prompts/
│   │       └── templates.py # AI 提示模板
│   ├── data/                # 数据目录
│   │   ├── papers.db        # SQLite 数据库
│   │   └── pdfs/            # PDF 存储
│   ├── requirements.txt
│   └── run.py
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── papers.js    # API 封装
│   │   ├── components/
│   │   │   ├── SearchBar.jsx
│   │   │   ├── FilterBar.jsx
│   │   │   ├── PaperCard.jsx
│   │   │   └── AnalysisReport.jsx
│   │   ├── pages/
│   │   │   ├── PaperList.jsx
│   │   │   └── PaperDetail.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

## 注意事项

### API 费用提醒
- 本系统使用 AI API 进行论文分析，每次分析会消耗 API 额度
- 深度分析单篇论文约消耗 2000-5000 tokens
- 建议先测试少量论文，确认费用可接受后再批量使用

### 网络要求
- 需要稳定的网络连接访问 ArXiv API
- 需要能访问 AI API 服务
- PDF 下载可能需要较长时间，建议在网络良好时操作

### 数据存储
- 论文数据存储在 SQLite 数据库中
- PDF 文件存储在本地 `backend/data/pdfs/` 目录
- 首次运行会自动创建数据目录

### 性能建议
- 单次抓取论文数量建议不超过 50 篇
- 批量生成摘要时，每批建议不超过 20 篇
- 深度分析是异步操作，分析期间请勿关闭页面

## 开发

### 运行测试

```bash
# 后端测试
cd backend
python test_api.py
```

### 构建生产版本

```bash
# 前端构建
cd frontend
npm run build
```

## License

MIT License