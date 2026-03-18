# ArXiv 论文智能分析平台 - 项目文件清单

> 文档版本: 1.0
> 最后更新: 2026-03-18

---

## 文件统计

| 类别 | 文件数 | 代码行数 |
|------|--------|----------|
| 后端代码 | 13 | 1,858 |
| 前端代码 | 9 | 1,612 |
| 配置文件 | 8 | 126 |
| 验证脚本 | 2 | 834 |
| 文档文件 | 3 | 1,199 |
| **总计** | **35** | **5,629** |

---

## 一、后端代码文件

| 文件路径 | 说明 | 行数 |
|----------|------|------|
| `backend/app/__init__.py` | 应用包初始化文件 | 0 |
| `backend/app/config.py` | 配置管理模块，使用 pydantic-settings 管理环境变量 | 74 |
| `backend/app/database.py` | 异步数据库连接管理，创建 SQLAlchemy 引擎和会话工厂 | 70 |
| `backend/app/models.py` | SQLAlchemy 数据模型定义，包含 Paper 和 FetchLog 模型 | 104 |
| `backend/app/schemas.py` | Pydantic 数据验证模型，定义请求和响应数据结构 | 167 |
| `backend/app/main.py` | FastAPI 应用入口，配置 CORS、路由和中间件 | 134 |
| `backend/app/prompts/__init__.py` | 提示词包初始化文件 | 0 |
| `backend/app/prompts/templates.py` | AI 提示词模板，包含摘要生成和深度分析提示词 | 251 |
| `backend/app/routers/__init__.py` | 路由包初始化文件 | 0 |
| `backend/app/routers/papers.py` | 论文相关 API 端点，包含列表、详情、抓取、分析等接口 | 465 |
| `backend/app/services/__init__.py` | 服务包初始化文件 | 0 |
| `backend/app/services/arxiv_service.py` | ArXiv 论文抓取服务，封装 ArXiv API 调用 | 198 |
| `backend/app/services/pdf_service.py` | PDF 下载与文本提取服务，使用 PyMuPDF 处理 PDF | 175 |
| `backend/app/services/ai_service.py` | AI 分析服务，调用 Claude API 生成摘要和分析报告 | 277 |
| `backend/run.py` | 应用启动脚本，初始化数据库并启动 Uvicorn 服务器 | 13 |
| `backend/test_api.py` | API 接口测试脚本，用于验证各端点功能 | 225 |
| `backend/.env` | 环境变量配置文件，存储 API 密钥等敏感信息 | 1 |
| `backend/requirements.txt` | Python 依赖列表 | 13 |

---

## 二、前端代码文件

| 文件路径 | 说明 | 行数 |
|----------|------|------|
| `frontend/index.html` | HTML 入口文件 | 14 |
| `frontend/src/main.jsx` | React 应用入口，渲染根组件 | 12 |
| `frontend/src/App.jsx` | 根组件，配置路由和整体布局 | 71 |
| `frontend/src/index.css` | 全局样式，包含 Tailwind 指令和自定义 CSS | 236 |
| `frontend/src/api/papers.js` | 后端 API 封装函数，处理所有 HTTP 请求 | 119 |
| `frontend/src/components/PaperCard.jsx` | 论文卡片组件，显示论文摘要信息 | 153 |
| `frontend/src/components/AnalysisReport.jsx` | Markdown 分析报告渲染组件，支持 LaTeX 公式 | 131 |
| `frontend/src/pages/PaperList.jsx` | 论文列表页，包含筛选、搜索、分页功能 | 415 |
| `frontend/src/pages/PaperDetail.jsx` | 论文详情页，显示完整信息和深度分析 | 475 |

---

## 三、配置文件

| 文件路径 | 说明 | 行数 |
|----------|------|------|
| `frontend/vite.config.js` | Vite 构建配置，设置代理和端口 | 15 |
| `frontend/tailwind.config.js` | Tailwind CSS 配置 | 10 |
| `frontend/postcss.config.js` | PostCSS 配置 | 5 |
| `frontend/eslint.config.js` | ESLint 代码检查配置 | 29 |
| `frontend/package.json` | Node.js 项目配置和依赖列表 | 39 |
| `frontend/README.md` | 前端项目说明文档 | 16 |
| `package-lock.json` | npm 依赖锁定文件 | 6 |
| `frontend/package-lock.json` | 前端 npm 依赖锁定文件 | 5648 |

---

## 四、验证脚本

| 文件路径 | 说明 | 行数 |
|----------|------|------|
| `verify_system.py` | 系统功能验证脚本，检查后端服务和 AI 功能 | 531 |
| `verify_frontend.py` | 前端功能验证脚本，检查服务连通性和数据完整性 | 303 |

---

## 五、文档文件

| 文件路径 | 说明 | 行数 |
|----------|------|------|
| `README.md` | 项目说明文档 | 241 |
| `PROJECT_ARCHITECTURE.md` | 项目架构文档，详细描述系统设计和 API 接口 | 942 |
| `FILE_LIST.md` | 本文件，项目文件清单 | - |

---

## 六、运行时生成目录

以下目录在运行时自动创建，不应纳入版本控制：

| 目录路径 | 说明 |
|----------|------|
| `backend/data/` | 数据目录 |
| `backend/data/papers.db` | SQLite 数据库文件 |
| `backend/data/pdfs/` | PDF 文件存储目录 |
| `backend/venv/` | Python 虚拟环境 |
| `frontend/node_modules/` | Node.js 依赖目录 |
| `frontend/dist/` | 构建输出目录 |

---

## 七、文件依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                         后端依赖链                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  run.py → main.py → routers/papers.py                       │
│                     ├── config.py                           │
│                     ├── database.py                         │
│                     ├── models.py                           │
│                     ├── schemas.py                          │
│                     └── services/                           │
│                         ├── arxiv_service.py                │
│                         ├── pdf_service.py                  │
│                         └── ai_service.py                   │
│                             └── prompts/templates.py        │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         前端依赖链                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  index.html → main.jsx → App.jsx                            │
│                         ├── pages/PaperList.jsx             │
│                         │   └── api/papers.js               │
│                         │   └── components/PaperCard.jsx    │
│                         └── pages/PaperDetail.jsx           │
│                             ├── api/papers.js               │
│                             └── components/AnalysisReport.jsx│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

*文档结束*