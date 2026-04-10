# 深度分析架构梳理

## 当前状态

### 测试结果

| 论文 | 结果 | 原因 |
|------|------|------|
| 2603.16870 | ✅ 成功 | PyMuPDF解析正常，质量通过 |
| 2603.16806 | ❌ 失败 | MinerU不存在 + 检测到编造数字被拦截 |

### 组件状态

| 组件 | 状态 | 说明 |
|------|------|------|
| PDF下载 | ✅ 正常 | 下载到 `data/pdfs/` |
| MinerU解析 | ❌ 未安装 | 配置路径不存在 |
| PyMuPDF回退 | ✅ 正常 | 仅提取纯文本，无结构 |
| AI分析 | ✅ 正常 | qwen3.5-plus (Coding Plan) |
| 质量检查 | ✅ 正常 | 成功拦截编造数据 |
| 前端渲染 | ⚠️ 待优化 | Markdown显示需美化 |

---

## 深度分析流程

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PDF下载                                                   │
│    pdf_service.download_pdf() → data/pdfs/{arxiv_id}.pdf    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. PDF解析                                                   │
│    MinerU (优先) → Markdown (保留结构、公式、表格)            │
│    PyMuPDF (回退) → 纯文本                                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. AI深度分析                                                │
│    DEEP_ANALYSIS_PROMPT + 全文 → 完整专业报告                │
│    (~2-5分钟/篇，包含8个分析板块)                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. JSON提取                                                  │
│    从报告提取结构化数据 (tier, tags, contributions等)         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. 质量检查 (guardrails)                                     │
│    - 字段完整性检查                                           │
│    - 数字来源验证 (拦截编造)                                   │
│    - 总结长度检查 (80-150字)                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. 保存到数据库                                               │
│    analysis_report, analysis_json, analysis_mode='full'      │
└─────────────────────────────────────────────────────────────┘
```

---

## 依赖清单

### 已安装 ✅

| 依赖 | 版本/路径 | 用途 |
|------|-----------|------|
| PyMuPDF | fitz | PDF纯文本提取 |
| OpenAI SDK | - | AI API调用 |
| httpx | - | PDF下载 |
| SQLite | - | 数据存储 |

### 未安装 ❌

| 依赖 | 说明 | 安装方式 |
|------|------|----------|
| MinerU | PDF结构化解析 | `pip install mineru` 或创建独立venv |

---

## MinerU 安装方案

### 方案A：创建独立venv（推荐）

```bash
# 1. 创建独立虚拟环境
python3 -m venv ~/mineru-venv

# 2. 激活并安装
source ~/mineru-venv/bin/activate
pip install mineru

# 3. 更新 .env 配置
MINERU_PATH=~/mineru-venv/bin/mineru
```

### 方案B：安装到zhiwei-rag venv

```bash
# 1. 激活现有venv
source ~/zhiwei-rag/venv/bin/activate

# 2. 安装MinerU
pip install mineru

# 3. 更新 .env 配置
MINERU_PATH=~/zhiwei-rag/venv/bin/mineru
```

### 方案C：使用PyMuPDF回退（无需安装）

- 继续使用当前配置
- 仅提取纯文本，无结构保留
- 分析质量略低但稳定可靠

---

## 配置文件

### `.env` 关键配置

```bash
# AI模型
AI_MODEL=qwen3.5-plus
CODING_PLAN_API_KEY=sk-sp-xxx

# PDF解析
PDF_PARSER=auto  # auto=mineru优先，pymupdf=强制回退
MINERU_PATH=/Users/liufang/mineru-venv/bin/mineru
MINERU_CACHE_DIR=./data/mineru_cache
MINERU_TIMEOUT=600

# PDF存储
PDF_STORAGE_PATH=./data/pdfs
```

---

## 待办事项

- [ ] 安装MinerU或更新配置
- [ ] 批量重处理Tier A/B论文（91篇Tier A + 4653篇Tier B）
- [ ] 前端Markdown渲染优化
- [ ] 固化处理流程配置

---

## 下一步建议

1. **安装MinerU**：选择方案A或B
2. **测试验证**：重新运行第二篇论文深度分析
3. **批量处理**：确认后批量处理Tier A/B