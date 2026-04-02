# Paper Analysis Skill

This skill defines the correct workflow and validation logic for the arxiv-paper-analyzer system.

## Overview

The paper analysis system processes academic papers through AI analysis. The core principle is:

> **Failure must not pollute data** - Only write results when validation passes.

## Complete Workflow

### Phase 1: Paper Fetching (daily_workflow.py)

```bash
# Daily workflow: fetch + create tasks
python scripts/daily_workflow.py

# Manual fetch with specific categories
python scripts/daily_workflow.py --categories cs.AI,cs.CL --days 3

# Skip fetch, only create tasks
python scripts/daily_workflow.py --skip-fetch

# Limit task creation
python scripts/daily_workflow.py --task-limit 300
```

**Default Categories** (DEFAULT_CATEGORIES):
```python
["cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.RO",
 "cs.NE", "cs.SE", "cs.DC", "cs.CR", "cs.HC"]
```

**Flow**:
1. Connect to arXiv API
2. Fetch papers from specified categories (date_from = now - days)
3. Apply prefilter (basic quality check, per_category_limit=100)
4. Store in papers table with `has_analysis=False`
5. Create analysis tasks for new papers (quick_mode=True)

### Phase 2: Task Creation (create_analysis_tasks.py)

```bash
# Create tasks for pending papers
python scripts/create_analysis_tasks.py --limit 500

# Priority: Tier A papers first
python scripts/create_analysis_tasks.py --tier A --limit 100

# Full mode (PDF parsing)
python scripts/create_analysis_tasks.py --full
```

**Flow**:
1. Query papers where `has_analysis=False AND abstract IS NOT NULL`
2. Check existing tasks to avoid duplicates
3. Create task with payload: `{paper_id, quick_mode}`
4. Task status: `pending`

### Phase 3: Worker Processing (task_worker.py)

```bash
# Start worker (safe concurrency)
python scripts/task_worker.py --concurrent 3

# Safe range: 3-5 workers
# Max safe: 10 workers (will hit rate limits)
```

**Worker Lifecycle**:
1. Pull task → `status=running`
2. Execute handler (AnalysisTaskHandler)
3. On success → `status=completed`
4. On failure → `status=failed`

### Phase 4: Analysis Execution (analysis_task.py)

**Quick Mode** (摘要分析):
- Input: Abstract only (< 5000 chars)
- Prompt: `QUICK_MODE_ANALYSIS_PROMPT`
- Output: Simplified report, no formulas/chapters

**Full Mode** (全文分析):
- Input: Full PDF text
- Prompt: `DEEP_ANALYSIS_PROMPT`
- Output: Complete report with outline, formulas, data

**Critical Steps**:
1. Read paper info (session 1)
2. Get content (download PDF if needed)
3. Call AI analysis
4. **VALIDATE** results (see Validation Rules)
5. If valid → Write to database
6. If invalid → Return `{"status": "failed"}`

### Phase 5: Database Write (write_service.py)

**Write Queue Mechanism**:
- API calls can be parallel
- Database writes are serialized (single consumer)
- Avoids SQLite lock contention

**WriteTask Fields**:
```python
paper_id: int
analysis_report: str
analysis_json: dict
tier: str
summary: str
has_analysis: bool = True  # Only set True on success
```

---

## Analysis Modes Comparison

| Aspect | Quick Mode | Full Mode |
|--------|------------|-----------|
| Input | Abstract only | Full PDF text |
| Prompt | `QUICK_MODE_ANALYSIS_PROMPT` | `DEEP_ANALYSIS_PROMPT` |
| Speed | **~90-120 seconds** (实测) | **~180-300 seconds** (实测) |
| Report Length | ~2000 chars | ~8000+ chars |
| Outline | 3 items (simple) | 5+ items (detailed) |
| Formulas | ❌ None (would be fake) | ✅ LaTeX formulas |
| Data | ❌ No specific numbers | ✅ Actual metrics |
| Cost | Low | High |

**实测速度**（基于日志 2026-04-01）：
- Quick Mode: 平均 1-2 分钟/篇（两次 API 调用）
- 并发 5: 约 2-4 篇/分钟

### 分级分析策略

**根据 Tier 选择分析模式**：

| Tier | 分析模式 | 原因 |
|------|----------|------|
| A | Full Mode | 顶尖论文需要深度理解 |
| B | Full Mode | 有价值贡献需要详细分析 |
| C | Quick Mode | 一般参考，快速筛选即可 |

**初始处理流程**：
```
1. 所有新论文先用 Quick Mode 分析
2. 根据 Quick Mode 结果确定初始 Tier
3. Tier A/B 的论文标记需要 Full Mode 补充分析
```

### Tier 升级后重新分析

**触发条件**：每月 Tier 重新评估时，若 Tier 升级（C→B 或 B→A），需要重新分析。

**重新分析流程**：
```
1. 每月重新评估 Tier
2. 检测 Tier 变化：
   - C → B: 重新用 Full Mode 分析
   - B → A: 重新用 Full Mode 分析
   - A → B 或 B → C: 不重新分析（已有详细内容）
3. 更新分析结果和文档
```

**实现方式**：
```python
# 在 monthly_retier.py 中添加
async def check_reanalyze_needed(old_tier: str, new_tier: str, current_mode: str) -> bool:
    """检查是否需要重新分析"""
    # Tier 升级且当前是 Quick Mode
    tier_upgrade = (old_tier == "C" and new_tier in ["A", "B"]) or \
                   (old_tier == "B" and new_tier == "A")
    is_quick = current_mode == "quick"  # 可通过 report 长度或 outline 项数判断
    return tier_upgrade and is_quick
```

### 分析模式判断

通过以下指标判断当前是哪种模式：
- **报告长度**: < 3000 字符 → Quick Mode
- **大纲项数**: ≤ 3 项 → Quick Mode
- **数据库字段**: 可添加 `analysis_mode` 字段记录

```sql
-- 添加分析模式字段
ALTER TABLE papers ADD COLUMN analysis_mode TEXT DEFAULT 'quick';
-- 值: 'quick' 或 'full'
```

**Decision Rule**:
- Quick mode: Initial screening, large batch processing
- Full mode: Tier A papers, detailed research

---

## Validation Rules

### Mandatory Checks

```python
def validate_analysis_result(analysis_json: dict, report: str) -> tuple[bool, list]:
    """
    Returns: (is_valid, missing_fields)

    Validation criteria:
    1. report length >= 500 characters
    2. JSON string length >= 500 bytes
    3. tier must be "A", "B", or "C"
    4. one_line_summary must exist and > 10 chars
    5. outline must be non-empty list
    6. key_contributions must be non-empty list
    """
```

### Data State Definitions

| has_analysis | analysis_json | analysis_report | Status |
|--------------|---------------|-----------------|--------|
| False | NULL | NULL | ✅ Not analyzed |
| True | NULL | NULL | ❌ ILLEGAL |
| True | {} (empty) | "" (empty) | ❌ ILLEGAL - should retry |
| True | >=500 bytes | >=500 chars | ✅ Complete |

---

## Tier Evaluation Criteria

### Target Distribution
- **A**: 15% (top innovation)
- **B**: 35% (valuable contribution)
- **C**: 50% (general reference)

### Tier A (顶尖创新) - Must satisfy 2+ conditions:
1. New paradigm/methodology (not incremental)
2. Significant breakthrough (>10% improvement on major benchmarks)
3. Top institution work (OpenAI/DeepMind/Google/Stanford/MIT)
4. Creates new research direction

**⚠️ Regular improvements, applications, engineering → NOT A**

### Tier B (有价值贡献) - Must satisfy 2+ conditions:
1. Clear method innovation (not simple combination)
2. Good results with specific data support
3. Valuable empirical research or tools
4. Reasonable improvement in hot direction

**⚠️ Only 1 condition met → Give C, not B**

### Tier C (一般参考) - Any of:
1. Incremental improvement
2. Application-oriented research
3. Preliminary exploration
4. Tool/dataset construction
5. Only 1 innovation point

**C is NOT a bad rating - means "useful but not outstanding"**

---

## Prompt Templates Location

| Template | File | Purpose |
|----------|------|---------|
| `QUICK_MODE_ANALYSIS_PROMPT` | templates.py:107 | Abstract-only analysis |
| `DEEP_ANALYSIS_PROMPT` | templates.py:198 | Full paper analysis |
| `QUICK_MODE_JSON_PROMPT` | templates.py:312 | Extract JSON from quick mode report |
| `ANALYSIS_JSON_PROMPT` | templates.py:413 | Extract JSON from full report |
| `TIER_REEVALUATION_PROMPT` | templates.py:825 | Retier papers |

**Prompt Design Principle**:
- Quick mode prompts explicitly forbid formulas/chapters
- Prevents fabrication when only abstract is available

---

## Guardrails Module (guardrails.py)

### Usage

```python
from app.services.guardrails import analysis_guardrail

# Pre-analysis check
check = guard.pre_analysis_check(quick_mode=True, content=abstract, abstract=abstract)
if not check.valid:
    logger.warning(check.warnings)

# Post-analysis validation
post = guard.post_analysis_validate(analysis_json, quick_mode=True)
if post.warnings:
    logger.warning(f"质量警告: {post.warnings}")

# Fabrication detection
fabrication = guard.detect_fabrication(analysis_json, quick_mode=True)
if not fabrication.valid:
    logger.error(f"疑似捏造: {fabrication.warnings}")
```

### Detection Rules

| Check | Quick Mode | Full Mode |
|-------|------------|-----------|
| Formula symbols ($, \[) | ❌ Must not exist | ✅ Allowed |
| Chapter numbers (1. 引言) | ❌ Must not exist | ✅ Allowed |
| Specific metrics (提升 5.2%) | ❌ Suspicious | ✅ Allowed |
| Outline depth > 2 | ❌ Suspicious | ✅ Allowed |

---

## API Rate Limiting

### Limits
- Default concurrency: 3-5 workers
- Max safe concurrency: 10 workers
- Hour quota: varies by API plan

### Rate Limit Handling
```
1. If 429 error → Wait 60 seconds
2. Retry up to 3 times with exponential backoff
3. If still fails → Return failed, do NOT write results
4. Wait for quota reset before restarting workers
```

### Rate Limit Constants (ai_service.py)
```python
MAX_RETRIES = 3
RETRY_DELAY = 5.0  # seconds
RETRY_BACKOFF = 2.0  # exponential factor
```

---

## Error Handling

### DO NOT
- ❌ Write empty results when API fails
- ❌ Set has_analysis=True on failure
- ❌ Use default empty values for required fields
- ❌ Mark task as completed on validation failure
- ❌ Fabricate data when only abstract is available

### DO
- ✅ Return {"status": "failed"} on any error
- ✅ Leave has_analysis=False for failed papers
- ✅ Log detailed error messages
- ✅ Allow retry of failed papers
- ✅ Validate before marking complete

---

## Script Reference

| Script | Purpose |
|--------|---------|
| `daily_workflow.py` | Fetch papers + create tasks |
| `create_analysis_tasks.py` | Batch create analysis tasks |
| `task_worker.py` | Background worker process |
| `reanalyze_incomplete.py` | Re-analyze incomplete papers |
| `check_tier_distribution.py` | Check Tier A/B/C distribution |
| `monitor_progress.py` | Monitor analysis progress |
| `system_diagnose.py` | System health diagnosis |

---

## Monitoring Commands

### Daily Check Commands

```bash
# Check completeness rate
source venv/bin/activate && python -c "
import sqlite3
conn = sqlite3.connect('data/papers.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM papers WHERE LENGTH(analysis_json) >= 500')
complete = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM papers WHERE has_analysis = 1')
total = c.fetchone()[0]
print(f'Complete: {complete}/{total} ({complete/total*100:.1f}%)')
"

# Check for polluted data (empty JSON marked as analyzed)
source venv/bin/activate && python -c "
import sqlite3
conn = sqlite3.connect('data/papers.db')
c = conn.cursor()
c.execute('''
    SELECT COUNT(*) FROM papers
    WHERE has_analysis = 1
    AND (analysis_json IS NULL OR LENGTH(analysis_json) < 500)
''')
print(f'Polluted: {c.fetchone()[0]} papers')
"

# Check Tier distribution
source venv/bin/activate && python scripts/check_tier_distribution.py
```

### Alert Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Empty JSON rate | > 5% | Check validation logic |
| Task failure rate | > 5% | Check API status |
| API 429 errors | > 10/hour | Reduce concurrency |
| Tier A rate | > 20% | Tighten Tier criteria |
| Tier A rate | < 10% | Check Tier evaluation logic |
| Tier B rate | > 50% | May be too loose |
| Tier C rate | < 40% | May be too strict |

### Quality Check Script (每完成500篇执行)

```bash
source venv/bin/activate && python -c "
import sqlite3
import json

conn = sqlite3.connect('data/papers.db')
c = conn.cursor()

# 完整性检查
c.execute('SELECT COUNT(*) FROM papers WHERE has_analysis = 1')
total_analyzed = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM papers WHERE LENGTH(analysis_json) >= 500')
complete = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM papers WHERE has_analysis = 1 AND LENGTH(analysis_json) < 500')
polluted = c.fetchone()[0]

print('【完整性】')
print(f'完整: {complete}/{total_analyzed} ({complete/total_analyzed*100:.1f}%)')
print(f'污染: {polluted} ({polluted/total_analyzed*100:.1f}%)')

# Tier分布检查
c.execute('SELECT tier, COUNT(*) FROM papers WHERE has_analysis=1 AND tier IS NOT NULL GROUP BY tier')
tiers = dict(c.fetchall())
total = sum(tiers.values())
print('【Tier分布】')
for tier, target in [('A',15), ('B',35), ('C',50)]:
    count = tiers.get(tier, 0)
    pct = count/total*100 if total else 0
    status = '✅' if abs(pct-target)<10 else '⚠️'
    print(f'{tier}: {pct:.1f}% (目标{target}%) {status}')

# 内容质量抽样
c.execute('SELECT arxiv_id, analysis_json FROM papers WHERE LENGTH(analysis_json)>=500 ORDER BY RANDOM() LIMIT 3')
for arxiv_id, json_str in c.fetchall():
    data = json.loads(json_str)
    print(f'{arxiv_id}: tier={data.get(\"tier\")}, outline={len(data.get(\"outline\",[]))}项, contrib={len(data.get(\"key_contributions\",[]))}项')

conn.close()
"
```

---

## Common Issues and Fixes

### Issue: API Rate Limiting (429)

```bash
# Stop all workers
pkill -f task_worker.py

# Wait 1 hour for quota reset

# Restart with safe concurrency
python scripts/task_worker.py --concurrent 3
```

### Issue: Polluted Data (empty JSON)

```bash
# Reset polluted papers to not analyzed
sqlite3 data/papers.db "
UPDATE papers
SET has_analysis = 0, analysis_json = NULL, analysis_report = NULL
WHERE LENGTH(analysis_json) < 500
"

# Recreate tasks for reset papers
python scripts/create_analysis_tasks.py
```

### Issue: Worker Stuck

```bash
# Check if worker is processing
tail -f logs/worker*.log

# If no activity for 5+ minutes, restart
pkill -f task_worker.py
python scripts/task_worker.py --concurrent 3
```

### Issue: Tier A Inflation

```bash
# Check distribution
python scripts/check_tier_distribution.py

# Re-evaluate all papers
python scripts/retier_all.py

# Or parallel re-evaluation
python scripts/retier_parallel.py --workers 3
```

---

## Backup and Restore

### Backup

```bash
# Create backup
sqlite3 data/papers.db ".backup 'backups/papers.db.backup_$(date +%Y%m%d_%H%M%S)'"

# Or copy
cp data/papers.db backups/papers.db.backup_$(date +%Y%m%d_%H%M%S)
```

### Restore

```bash
# Restore from backup
sqlite3 data/papers.db ".backup 'backups/papers.db.backup_YYYYMMDD_HHMMSS'"
# Or
cp backups/papers.db.backup_YYYYMMDD_HHMMSS data/papers.db
```

---

## File Locations

| File | Purpose |
|------|---------|
| `app/tasks/analysis_task.py` | Task handler with validation |
| `app/services/ai_service.py` | AI API calls |
| `app/services/guardrails.py` | Analysis validation |
| `app/services/write_service.py` | Database write queue |
| `app/prompts/templates.py` | Prompt templates |
| `scripts/task_worker.py` | Worker process |
| `scripts/daily_workflow.py` | Daily fetch workflow |
| `scripts/create_analysis_tasks.py` | Create analysis tasks |
| `data/papers.db` | Papers database |
| `data/tasks.db` | Task queue |

---

## Key Code Locations

### Validation Function
File: `app/tasks/analysis_task.py:22`
Function: `validate_analysis_result()`

### Task Handler
File: `app/tasks/analysis_task.py:63`
Class: `AnalysisTaskHandler`

### Guardrails
File: `app/services/guardrails.py`
Class: `AnalysisGuardrail`

### Write Service
File: `app/services/write_service.py`
Class: `DatabaseWriteService`

### AI Service
File: `app/services/ai_service.py`
Class: `AIService`

---

## Checklist Before Any Changes

- [ ] Read `docs/ANALYSIS_BUSINESS_LOGIC.md`
- [ ] Ensure failure does NOT write results
- [ ] Ensure validation runs before marking complete
- [ ] Test with API failure scenarios
- [ ] Check Tier criteria not loosened
- [ ] Verify quick mode prompts forbid formulas
- [ ] Update this skill if workflow changes

---

## Monthly Tier Re-evaluation

**目的**: Tier 应反映论文的真实热度，随时间动态调整。

### 自动执行

**定时任务**: `com.arxiv.monthly-retier`
- **执行时间**: 每月 1 日凌晨 3:00
- **脚本**: `scripts/monthly_retier.py`
- **日志**: `~/logs/monthly-retier.log`
- **状态文件**: `data/retier_status.json`

### 重试机制

| 配置 | 值 |
|------|-----|
| 最大重试次数 | 3 次 |
| 重试延迟 | 5 分钟 |
| 状态记录 | 自动保存到 retier_status.json |

### 手动执行

```bash
# 正常执行
python scripts/monthly_retier.py

# 强制重试（忽略重试次数）
python scripts/monthly_retier.py --retry

# 检查状态
cat data/retier_status.json
```

### 为什么需要重新评估

| 时间因素 | 影响 |
|----------|------|
| 引用数增长 | 高引用论文应升级 |
| 技术热度变化 | 热门方向论文价值上升 |
| 方法被后续工作改进 | 原创新性降低，可能降级 |
| 社区验证 | 工具/数据集被广泛使用应升级 |

### 重新评估流程

```
1. 获取所有已分析论文
2. 对每篇论文调用 AI 重新评估 Tier
3. 更新数据库中的 Tier 字段
4. 记录变更统计
5. 保存执行状态
```

### 管理定时任务

```bash
# 查看状态
launchctl list | grep monthly-retier

# 手动触发
launchctl start com.arxiv.monthly-retier

# 停止
launchctl unload ~/Library/LaunchAgents/com.arxiv.monthly-retier.plist

# 启动
launchctl load ~/Library/LaunchAgents/com.arxiv.monthly-retier.plist
```

---

> **核心原则**: Tier 不是静态标签，是论文热度的动态指标。每月自动重新评估确保数据反映真实价值。