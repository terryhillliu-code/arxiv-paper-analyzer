# 深度分析架构完整报告

## 一、数据现状

### 1.1 分析模式分布

| 模式 | 数量 | 平均报告长度 | 说明 |
|------|------|-------------|------|
| quick | 8534篇 | 3613字符 | 仅基于摘要 |
| full | 23篇 | 4463字符 | 基于PDF全文 |
| historical | 5篇 | 1876字符 | 历史遗留 |

### 1.2 报告长度分布

| 长度区间 | quick | full |
|---------|-------|------|
| <1.5k | 3801篇 | 0篇 |
| 1.5k-3k | 2284篇 | 0篇 |
| 3k-5k | 0篇 | 18篇 |
| 5k-10k | 2191篇 | 5篇 |
| >10k | 258篇 | 0篇 |

**关键发现**：99.7%的论文使用quick模式，full模式仅23篇。

---

## 二、代码流程

### 2.1 入口点

```
scripts/task_worker.py
    └─→ TaskQueue.run_worker()
        └─→ AnalysisTaskHandler.handle()
```

### 2.2 分析任务流程 (analysis_task.py)

```
┌─────────────────────────────────────────────────────────────────┐
│ handle(task, queue)                                             │
│                                                                 │
│ 参数:                                                            │
│   - quick_mode: 默认 True (第161行)                              │
│   - use_mineru: 默认 False                                       │
│   - force_refresh: 任务类型为 force_refresh 时自动 True           │
│                                                                 │
│ 流程:                                                            │
│   1. 读取论文信息 (paper_abstract, paper_full_text, etc.)         │
│   2. 获取内容:                                                    │
│      - quick_mode=True → 只用摘要 (第204-215行)                   │
│      - quick_mode=False → 下载PDF并解析 (第217-242行)             │
│   3. 调用AI分析: ai_service.generate_deep_analysis()             │
│   4. 验证结果: validate_analysis_result()                        │
│   5. 保存到数据库: db_write_service.submit()                     │
│   6. 创建PDF下载任务 (quick_mode时)                               │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 关键代码位置

**analysis_task.py 第161行**：
```python
quick_mode = payload.get("quick_mode", True)  # 默认True
```

**analysis_task.py 第204-215行**：
```python
# 快速模式：直接使用摘要，绝不下载PDF
if quick_mode:
    logger.info(f"快速模式: 使用摘要分析 {paper_arxiv_id}")
    content = paper_abstract
```

**analysis_task.py 第217-242行**：
```python
# 常规模式：下载 PDF 并解析（仅当quick_mode=False时执行）
elif not content and paper_pdf_url and paper_arxiv_id:
    # 下载PDF
    # use_mineru=True → MinerU解析（保留结构）
    # use_mineru=False → PyMuPDF纯文本
```

---

## 三、AI服务层 (ai_service.py)

### 3.1 generate_deep_analysis() 流程

```
┌─────────────────────────────────────────────────────────────────┐
│ generate_deep_analysis(..., quick_mode=False)                   │
│                                                                 │
│ 第304-324行:                                                    │
│   if quick_mode:                                                │
│       prompt = QUICK_MODE_ANALYSIS_PROMPT  # 摘要专用            │
│   else:                                                         │
│       prompt = DEEP_ANALYSIS_PROMPT  # 全文专用                  │
│                                                                 │
│ 第329行:                                                        │
│   max_tokens = 4000 if quick_mode else self.max_tokens          │
│                                                                 │
│ 第335-436行 (quick模式):                                         │
│   - 使用 QUICK_MODE_JSON_PROMPT 提取JSON                         │
│   - 最多3次重试                                                  │
│   - 总结太短时自动扩展                                           │
│                                                                 │
│ 第437-445行 (full模式):                                          │
│   - 调用 _extract_analysis_json()                               │
│   - 使用 ANALYSIS_JSON_PROMPT 提取JSON                           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 提示词对比

| 特性 | QUICK_MODE_ANALYSIS_PROMPT | DEEP_ANALYSIS_PROMPT |
|------|---------------------------|---------------------|
| 输入 | 仅摘要 | PDF全文 |
| 报告长度 | ~3000字符 | ~5000+字符 |
| 分析板块 | 基础 | 完整（7个板块） |
| 约束 | "不要虚构论文大纲" | 完整方法详解 |
| 公式 | 不允许 | 支持LaTeX |

---

## 四、PDF处理 (pdf_service.py)

### 4.1 双轨策略

```
extract_markdown():
  1. 尝试 MinerU (保留结构、表格、公式)
  2. 失败 → 回退到 PyMuPDF (纯文本)
```

### 4.2 MinerU配置

**.env**：
```
MINERU_PATH=/Users/liufang/zhiwei-rag/mineru-venv/bin/mineru
MINERU_CACHE_DIR=./data/mineru_cache
MINERU_TIMEOUT=600
```

**当前状态**：❌ MinerU未安装在该路径

---

## 五、质量检查 (analysis_task.py)

### 5.1 validate_analysis_result() 验证项

1. **JSON长度**：≥500字符
2. **报告长度**：≥500字符
3. **必需字段**：tier, one_line_summary, outline, key_contributions
4. **总结长度**：80-150字
5. **贡献长度**：每条≥25字
6. **数字编造检查**：总结中的数字必须在摘要中存在

### 5.2 验证失败处理

```python
if not is_valid:
    return {
        "status": "failed",
        "reason": f"验证失败: {missing_fields}",
    }
    # 不保存结果，论文可重新分析
```

---

## 六、配置项总结

### .env 关键配置

```bash
# AI模型
AI_MODEL=qwen3.5-plus
CODING_PLAN_API_KEY=sk-sp-xxx

# PDF处理
PDF_PARSER=auto
MINERU_PATH=/Users/liufang/mineru-venv/bin/mineru  # 需安装
MINERU_CACHE_DIR=./data/mineru_cache

# 存储
PDF_STORAGE_PATH=./data/pdfs
DATABASE_URL=sqlite+aiosqlite:///./data/papers.db
```

---

## 七、问题根因

### 为什么深度分析质量下降？

1. **默认quick_mode=True**：所有新论文只基于摘要分析
2. **PDF下载与分析分离**：下载后不触发深度分析
3. **MinerU未安装**：无法保留PDF结构（公式、表格）

### 历史对比

| 时期 | 模式 | 内容来源 | 质量 |
|------|------|---------|------|
| 早期(3月) | quick默认 | 摘要 | 基础 |
| 测试期 | full少量 | PDF全文 | 专业 |
| 现在 | quick默认 | 摘要 | 基础 |

---

## 八、修复方案

### 方案：分阶段处理

1. **新论文**：先quick评估Tier，Tier A/B触发full分析
2. **存量论文**：批量重处理Tier A/B

### 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `app/tasks/pdf_download_task.py` | PDF下载后根据Tier触发深度分析 |
| `app/tasks/analysis_task.py` | force_refresh时检测PDF并强制full |
| `.env` | 安装MinerU或更新路径 |

---

## 九、执行建议

1. **安装MinerU**（可选但推荐）
2. **修改触发逻辑**：Tier A/B论文自动深度分析
3. **批量重处理**：91篇Tier A + 4653篇Tier B