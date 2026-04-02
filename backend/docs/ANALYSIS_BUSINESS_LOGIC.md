# 论文分析系统业务逻辑梳理

> 创建日期: 2026-04-02
> 目的: 彻底梳理分析流程，找出问题根源，防止问题复发

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    论文分析系统架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ arXiv    │───▶│ 抓取服务  │───▶│ 数据库    │              │
│  │ API     │    │          │    │ (papers) │              │
│  └──────────┘    └──────────┘    └────┬─────┘              │
│                                       │                     │
│                                       ▼                     │
│                               ┌──────────┐                 │
│                               │ 任务队列  │                 │
│                               │ (tasks)  │                 │
│                               └────┬─────┘                 │
│                                    │                        │
│                    ┌───────────────┼───────────────┐       │
│                    ▼               ▼               ▼       │
│               ┌────────┐    ┌────────┐    ┌────────┐      │
│               │Worker 1│    │Worker 2│    │Worker N│      │
│               └────┬───┘    └────┬───┘    └────┬───┘      │
│                    │               │               │       │
│                    └───────────────┼───────────────┘       │
│                                    ▼                        │
│                            ┌──────────┐                    │
│                            │ AI 服务   │                    │
│                            │ (API)    │                    │
│                            └────┬─────┘                    │
│                                 │                          │
│                                 ▼                          │
│                          ┌───────────┐                     │
│                          │ 分析结果   │                     │
│                          │ 写入数据库 │                     │
│                          └───────────┘                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、核心流程

### 2.1 正常流程

```
1. 抓取论文 → 存入 papers 表 (has_analysis=False)
2. 创建任务 → 存入 tasks 表 (status=pending)
3. Worker 取任务 → status=running
4. 调用 AI 分析 → 生成 report + JSON
5. 写入结果 → has_analysis=True, 存入 analysis_json
6. 标记完成 → status=completed
```

### 2.2 当前问题流程

```
1. 抓取论文 → 存入 papers 表 (has_analysis=False)
2. 创建任务 → 存入 tasks 表 (status=pending)
3. Worker 取任务 → status=running
4. 调用 AI 分析 → API 限流失败
5. 异常处理 → 写入空结果, has_analysis=True ❌
6. 任务标记完成 → status=completed ❌
```

**问题**: 失败的任务被错误标记为完成，导致数据污染。

---

## 三、问题分类统计

| 类型 | 数量 | 原因 |
|------|------|------|
| 空JSON + 无报告 | 2469 篇 | API限流导致分析完全失败 |
| 部分JSON (<500字节) | 372 篇 | JSON提取失败，写入默认空值 |
| 完整数据 | 4021 篇 | 正常完成 |
| **总计** | **6863 篇** | |

---

## 四、问题根源分析

### 4.1 问题1: API限流处理不当

**现象**:
```
Error code: 429 - hour allocated quota exceeded
```

**根因**:
- 并发数过高（曾设为41）
- 触发API小时配额限制
- 重试3次后直接抛出异常

**代码位置**: `app/services/ai_service.py`

```python
# 问题代码
except RateLimitError as e:
    last_error = e
    delay = RETRY_DELAY * 4  # 等待20秒
    # 但即使重试3次失败后，也没有正确处理
```

### 4.2 问题2: 失败任务标记错误

**现象**: 任务失败后，论文仍被标记为 `has_analysis=True`

**根因**:
- `analysis_task.py` 中的异常处理不完善
- 即使分析失败，仍写入空结果

**代码位置**: `app/tasks/analysis_task.py`

```python
# 问题代码
except Exception as e:
    logger.error(f"分析失败: {e}")
    return {
        "paper_id": paper_id,
        "status": "failed",  # 返回失败状态
        # 但数据库的 has_analysis 可能已被设为 True
    }
```

### 4.3 问题3: JSON提取失败写入默认值

**现象**: 有报告但JSON字段为空

**根因**:
- JSON提取失败时写入默认空值
- 没有验证JSON是否包含实质内容

**代码位置**: `app/services/ai_service.py`

```python
# 问题代码
DEFAULT_VALUES = {
    "one_line_summary": "", "outline": [], ...
}
for key, default in DEFAULT_VALUES.items():
    if key not in analysis_json:
        analysis_json[key] = default  # 写入空默认值
```

### 4.4 问题4: 缺乏完整性验证

**现象**: 不完整的分析被当作完成处理

**根因**:
- 没有检查JSON长度是否合理
- 没有检查关键字段是否有内容
- `has_analysis=True` 的判断标准不严格

---

## 五、正确的数据状态定义

### 5.1 论文状态

| has_analysis | analysis_json | analysis_report | 含义 |
|--------------|---------------|-----------------|------|
| False | NULL | NULL | 未分析 |
| True | NULL | NULL | ❌ 非法状态 |
| True | {} | "" | ❌ 分析失败（应重试） |
| True | {"tier":"B",...} (>=500字节) | "完整报告" (>=500字) | ✅ 分析完成 |

### 5.2 任务状态

| status | 含义 | 后续处理 |
|--------|------|----------|
| pending | 等待处理 | Worker拉取 |
| running | 正在处理 | 等待完成 |
| completed | 成功完成 | 无需处理 |
| failed | 失败 | 需要重试 |

---

## 六、修复方案

### 6.1 短期修复

1. **清理脏数据**: 将空JSON的论文重置为未分析
2. **重新分析**: 对脏数据重新执行分析
3. **控制并发**: 降低并发数避免限流

### 6.2 长期加固

1. **添加完整性验证**
```python
def validate_analysis_result(analysis_json, report):
    """验证分析结果是否完整"""
    if not analysis_json or len(str(analysis_json)) < 500:
        return False
    if not report or len(report) < 500:
        return False
    required = ["tier", "one_line_summary", "outline", "key_contributions"]
    for field in required:
        if not analysis_json.get(field):
            return False
    return True
```

2. **改进错误处理**
```python
async def handle_analysis_task(paper):
    try:
        result = await ai_service.generate_deep_analysis(...)
        if not validate_analysis_result(result["analysis_json"], result["report"]):
            # 验证失败，不标记为完成
            return {"status": "failed", "reason": "验证失败"}
        # 验证通过才写入
        await save_result(paper, result)
        return {"status": "completed"}
    except Exception as e:
        # 异常不写入任何结果
        return {"status": "failed", "reason": str(e)}
```

3. **API限流自动降级**
```python
async def call_api_with_backoff(prompt):
    """带退避的API调用"""
    for attempt in range(MAX_RETRIES):
        try:
            return await api.call(prompt)
        except RateLimitError:
            wait_time = 60 * (attempt + 1)  # 1分钟、2分钟、3分钟
            logger.warning(f"API限流，等待{wait_time}秒...")
            await asyncio.sleep(wait_time)
    raise RateLimitError("超过最大重试次数")
```

---

## 七、监控指标

### 7.1 每日检查

```bash
# 完整率
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN LENGTH(analysis_json) >= 500 THEN 1 ELSE 0 END) as complete,
    SUM(CASE WHEN LENGTH(analysis_json) < 500 THEN 1 ELSE 0 END) as incomplete
FROM papers WHERE has_analysis = 1;
```

### 7.2 告警阈值

| 指标 | 阈值 | 告警 |
|------|------|------|
| 空JSON率 | > 5% | ⚠️ 需检查分析流程 |
| API限流次数 | > 10次/小时 | ⚠️ 降低并发 |
| 任务失败率 | > 5% | ⚠️ 检查错误原因 |

---

## 八、操作指南

### 8.1 发现空JSON时的处理

```bash
# 1. 统计空JSON数量
source venv/bin/activate && python -c "
import sqlite3
conn = sqlite3.connect('data/papers.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM papers WHERE LENGTH(analysis_json) < 500')
print(f'空JSON: {c.fetchone()[0]} 篇')
"

# 2. 重置为未分析
sqlite3 data/papers.db "
UPDATE papers
SET has_analysis = 0, analysis_json = NULL, analysis_report = NULL
WHERE LENGTH(analysis_json) < 500
"

# 3. 重新创建任务
python scripts/create_analysis_tasks.py
```

### 8.2 API限流时的处理

```bash
# 1. 停止所有Worker
pkill -f task_worker.py

# 2. 等待1小时（配额恢复）

# 3. 降低并发重启
python scripts/task_worker.py --concurrent 3
```

---

## 九、总结

### 问题链条

```
并发过高 → API限流 → 分析失败 → 写入空结果 → has_analysis=True
    ↓                                    ↓
数据污染 ← 任务标记完成 ← 未验证完整性 ←
```

### 解决链条

```
控制并发 → 限流重试 → 失败不写入 → 验证完整性 → 只在成功时标记完成
```

### 核心原则

1. **失败不污染**: 分析失败时不写入任何结果
2. **验证后标记**: 只有验证通过才设置 has_analysis=True
3. **数据可恢复**: 状态清晰，支持重新分析
4. **监控先行**: 定期检查完整率，及时发现问题

---

> 本文档记录了论文分析系统的完整业务逻辑和问题修复方案。
> 任何修改分析流程的代码变更前必须阅读本文档。