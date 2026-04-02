# ArXiv Paper Analyzer - Claude Code Instructions

## Project Overview

This is an academic paper analysis system that:
1. Fetches papers from arXiv
2. Analyzes papers using AI (generates summaries, tags, tier ratings)
3. Exports results to Obsidian vault

## Critical Rules

### 1. Data Integrity (MOST IMPORTANT)

> **Failure must not pollute data**

When analysis fails:
- ❌ DO NOT write empty results
- ❌ DO NOT set has_analysis=True
- ✅ Return {"status": "failed"}
- ✅ Leave paper available for retry

### 2. Validation Before Save

Always validate before marking complete:
```python
# Required: JSON >= 500 bytes, report >= 500 chars
# Required fields: tier, one_line_summary, outline, key_contributions
is_valid, missing = validate_analysis_result(analysis_json, report)
if not is_valid:
    return {"status": "failed"}  # Do NOT save
```

### 3. API Rate Limiting

- Safe concurrency: 3-5 workers
- If 429 error: wait 60s, retry max 3 times
- If still fails: return failed, wait 1 hour

## Key Files

| File | Purpose |
|------|---------|
| `app/tasks/analysis_task.py` | Task handler + validation |
| `app/services/ai_service.py` | AI API calls |
| `app/services/guardrails.py` | Quality checks |
| `docs/ANALYSIS_BUSINESS_LOGIC.md` | Full workflow documentation |

## Skills

- **paper-analysis**: Analysis workflow and validation rules

## Common Commands

```bash
# Check analysis progress
source venv/bin/activate && python -c "
import sqlite3
conn = sqlite3.connect('data/papers.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM papers WHERE LENGTH(analysis_json) >= 500')
print(f'Complete: {c.fetchone()[0]}/6863')
"

# Start worker (safe concurrency)
python scripts/task_worker.py --concurrent 3

# Check for polluted data
source venv/bin/activate && python scripts/check_tier_distribution.py
```

## Before Modifying Analysis Code

1. Read `docs/ANALYSIS_BUSINESS_LOGIC.md`
2. Run syntax check: `python -c "import ast; ast.parse(open('file.py').read())"`
3. Test validation logic
4. Ensure failures don't pollute data