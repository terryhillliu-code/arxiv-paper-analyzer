# Tier 通胀与数据捏造防护机制

> 创建日期: 2026-04-01
> 更新日期: 2026-04-01（v2.1 - 收紧 B 类标准）
> 目的: 确保 Tier 分布合理（A≤20%, B≈35%, C≈50%）且不出现数据捏造

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v2.1 | 2026-04-01 | 收紧 B 类标准：从"满足 1 条"改为"满足 2 条" |
| v2.0 | 2026-04-01 | 添加防护层模块 `guardrails.py` |
| v1.0 | 2026-04-01 | 创建基础防护机制文档 |

---

## 一、根因分析

### 1.1 Tier 通胀根因

| 层级 | 问题 | 影响 |
|------|------|------|
| **Prompt 设计** | Tier 标准模糊，缺乏量化指标 | LLM 倾向给高分（AI 行为偏好） |
| **缺少约束** | 没有"目标比例"提示 | LLM 不知道分布约束 |
| **评估流程** | 无决策树引导 | 评估随意，无结构化思考 |
| **监控缺失** | 没有定期检查脚本 | 问题积累后才发现 |

**AI 行为心理学**：
- LLM 有"讨好倾向"——倾向给出正面评价
- 没有"配额"概念时，会过度乐观
- 需要明确的"负面案例"来拉低整体预期

### 1.2 数据捏造根因

| 层级 | 问题 | 影响 |
|------|------|------|
| **Prompt 与输入不匹配** | DEEP_ANALYSIS_PROMPT 要求 outline/公式/数据，但只提供摘要 | LLM 为满足 Prompt 要求而"虚构"内容 |
| **缺少"诚实约束"** | 没有"摘要未提及"的明确指令 | LLM 自动"补充"信息 |
| **Prompt 复杂度** | 过多字段要求 | LLM 困惑，输出格式混乱 |

**Prompt-输入匹配原则**：
- Prompt 要求 ≤ 输入提供的信息量
- 否则必然产生捏造

---

## 二、防护机制（5 重保障）

### 2.1 量化标准机制

**设计原理**：用具体数字替代模糊描述

```python
# ❌ 旧版（模糊）
"A 类：顶尖创新，有重要贡献"

# ✅ 新版（量化）
"A 类（顶尖创新）- 占比应 < 20%
必须同时满足以下至少 2 条：
- 提出全新的方法范式或理论框架（非增量改进）
- 在主流基准上取得显著突破（提升 >10% 或首次解决关键难题）
- 顶级机构（OpenAI/DeepMind/Google/Stanford/MIT）的标志性工作"
```

**防护效果**：
- LLM 需要对照清单逐项检查
- 不满足具体条件时无法给 A
- "量化门槛"自动限制 A 类数量

### 2.2 目标比例约束机制

**设计原理**：在 Prompt 中明确告知期望分布

```python
## Tier 评估标准（非常重要）

⚠️ **严格控制 A 类比例，目标 A:B:C = 15:35:50**

### A 类（顶尖创新）- 占比应 < 20%
### B 类（有价值贡献）- 占比应 30-40%
### C 类（一般参考）- 占比应 40-55%
```

**防护效果**：
- LLM 获得"配额"概念
- 知道"大多数论文应该是 B 或 C"
- 心理预设被拉低，避免过度乐观

### 2.3 决策流程机制

**设计原理**：用结构化思考替代直觉判断

```python
### 评估流程

1. 先问自己：这篇论文是否改变了领域认知？→ 可能是 A
2. 再问：是否有明确的创新点？→ 可能是 B
3. 如果只是增量改进或应用落地 → 给 C

**大多数论文应该是 B 或 C，A 类应该非常少见**
```

**防护效果**：
- 强制 LLM 按顺序思考
- "先排除"逻辑——先确认不是 A/B，再给 C
- 最后的强调句再次拉低预期

### 2.4 Prompt-输入匹配机制

**设计原理**：Prompt 要求必须 ≤ 输入信息量

| 模式 | Prompt | 输入 | 匹配规则 |
|------|--------|------|----------|
| **quick_mode=True** | QUICK_MODE_ANALYSIS_PROMPT | 摘要 | 不要求 outline/公式/实验数据 |
| **quick_mode=False** | DEEP_ANALYSIS_PROMPT | 全文 | 可以要求完整大纲 |

**防护效果**：
- quick_mode 时明确禁止虚构：
  ```
  ⚠️ **你只有论文摘要，没有全文。必须遵守以下规则：**
  1. 不要虚构论文大纲
  2. 不要编造实验数据
  3. 不要推测数学公式
  4. 无法从摘要获知的信息，写"摘要未提及"
  ```
- 消除"信息缺口"，无缺口则无需捏造

### 2.5 定期监控机制

**设计原理**：自动化检测分布异常

```bash
# 每日检查 Tier 分布
python scripts/check_tier_distribution.py

# 输出示例
A: 12.5% ✅ (< 20%)
B: 38.2% ✅ (30-40%)
C: 49.3% ✅ (40-55%)

# 异常时报警
⚠️ Tier A 占比 25% > 20% 预警阈值！
```

**防护效果**：
- 问题早期发现
- 可在积累前干预
- 形成闭环反馈

---

## 三、机制生效验证

### 3.1 验证方法

```bash
# 1. 检查 Prompt 是否包含约束
grep -A 5 "Tier 评估标准" app/prompts/templates.py | grep "占比应"

# 2. 检查 quick_mode 选择逻辑
grep -A 3 "if quick_mode" app/services/ai_service.py

# 3. 运行监控脚本
python scripts/check_tier_distribution.py
```

### 3.2 预期结果

| 指标 | 预期值 | 验证方法 |
|------|--------|----------|
| Tier A 占比 | ≤ 20% | 监控脚本 |
| Tier B 占比 | 30-40% | 监控脚本 |
| Tier C 占比 | 40-55% | 监控脚本 |
| outline 捏造 | 0% | 抽查 quick_mode 报告 |
| 公式捏造 | 0% | 抽查 quick_mode 报告 |

---

## 四、监控脚本

**位置**: `scripts/check_tier_distribution.py`

```python
"""
Tier 分布监控脚本
每日运行，检测异常并报警
"""
import sys
sys.path.insert(0, '/Users/liufang/arxiv-paper-analyzer/backend')

from app.db.database import get_db
from sqlalchemy import text

def check_tier_distribution():
    with get_db() as db:
        result = db.execute(text("""
            SELECT tier, COUNT(*) as count
            FROM paper_analysis
            WHERE tier IS NOT NULL
            GROUP BY tier
            ORDER BY tier
        """))

        tiers = {row.tier: row.count for row in result}
        total = sum(tiers.values())

        print("=== Tier 分布报告 ===")
        alerts = []

        for tier in ['A', 'B', 'C']:
            count = tiers.get(tier, 0)
            pct = count / total * 100 if total > 0 else 0

            # 预期范围
            expected = {'A': (0, 20), 'B': (30, 40), 'C': (40, 55)}
            low, high = expected[tier]

            status = "✅" if low <= pct <= high else "⚠️"
            print(f"{tier}: {pct:.1f}% {status} (预期 {low}-{high}%)")

            if pct > high:
                alerts.append(f"Tier {tier} 占比 {pct:.1f}% > {high}% 预警阈值！")

        if alerts:
            print("\n🚨 异常警报:")
            for alert in alerts:
                print(f"  - {alert}")
            return False
        else:
            print("\n✅ 分布正常")
            return True

if __name__ == "__main__":
    check_tier_distribution()
```

---

## 五、机制维护

### 5.1 Prompt 修改规则

**修改前必须检查**：
1. 是否影响 Tier 量化标准？
2. 是否破坏 Prompt-输入匹配？
3. 是否需要同步更新监控阈值？

**修改流程**：
```
1. 编辑 app/prompts/templates.py
2. 运行语法检查: python -c "import ast; ast.parse(open('app/prompts/templates.py').read())"
3. 小批量测试（10 篇论文）
4. 运行监控脚本验证分布
5. 大批量部署
```

### 5.2 新问题发现流程

```
1. 监控脚本报警 → 人工抽查报告
2. 发现模式性问题 → 分析根因
3. 设计防护机制 → 更新 Prompt
4. 小批量验证 → 大批量部署
5. 更新本文档
```

---

## 六、机制总结

| 问题 | 根因 | 防护机制 | 验证方法 |
|------|------|----------|----------|
| **Tier 通胀** | Prompt 模糊 + AI 讨好倾向 | 量化标准 + 目标比例 + 决策流程 | 监控脚本 |
| **数据捏造** | Prompt 要求 > 输入信息 | Prompt-输入匹配 + 诚实约束 | 抽查报告 |

**核心原则**：
1. **Prompt 要具体**：用数字替代模糊描述
2. **约束要前置**：在 Prompt 中告知期望分布
3. **匹配要精准**：Prompt 要求 ≤ 输入提供
4. **监控要持续**：每日检查，早期发现

---

> 本文档记录了 Tier 通胀和数据捏造问题的根因及防护机制。
> 任何 Prompt 修改前必须检查是否破坏现有机制。

---

## 七、验证结果（2026-04-01）

### 7.1 当前 Tier 分布

| Tier | 当前占比 | 预期范围 | 状态 |
|------|----------|----------|------|
| A | 12.1% | 0-20% | ✅ 符合预期 |
| B | 51.5% | 30-40% | ⚠️ 略高于预期 |
| C | 36.4% | 40-55% | ⚠️ 略低于预期 |

**样本数**: 66 篇（较小，需持续监控）

### 7.2 效果评估

| 机制 | 验证结果 |
|------|----------|
| **量化标准** | ✅ Tier A 从 41% 降到 12.1% |
| **目标比例约束** | ✅ Prompt 中明确告知 15:35:50 分布 |
| **决策流程** | ✅ 强制结构化思考 |
| **Prompt-输入匹配** | ✅ 数据质量抽查通过，无公式捏造 |
| **定期监控** | ✅ 监控脚本正常运行 |

### 7.3 B/C 分布偏差分析

**原因**：B 类标准可能仍然不够严格，部分论文本应给 C 但给了 B

**解决方案**：
1. 继续监控，积累更多样本
2. 如果 B 类持续 > 45%，考虑：
   - 收紧 B 类标准（如要求"有明确创新点且方法合理"）
   - 放宽 C 类描述（如"有一定参考价值即可"）

### 7.4 监控命令

```bash
# 每日运行
source venv/bin/activate && python scripts/check_tier_distribution.py

# 预期输出
A: < 20% ✅
B: 30-40% ✅
C: 40-55% ✅
```

---

## 八、防护层模块（v2.0 新增）

### 8.1 模块概述

**位置**: `app/services/guardrails.py`

**功能**: 提供多层安全检查，防止 Tier 通胀和数据捏造

**核心组件**:
- `AnalysisGuardrail` 类：防护层主类
- `pre_analysis_check`: 分析前检查
- `post_analysis_validate`: 分析后验证
- `tier_distribution_check`: Tier 分布检查
- `detect_fabrication`: 捏造检测

### 8.2 防护流程

```
┌─────────────────────────────────────────────────────────────┐
│                     分析防护流程                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 分析前检查 (pre_analysis_check)                          │
│     ├── 内容长度检查                                         │
│     ├── Prompt-输入匹配检查                                  │
│     ├── 公式符号检测                                         │
│     └── 摘要有效性验证                                       │
│                                                              │
│  2. AI 分析                                                  │
│     ├── 快速模式: QUICK_MODE_ANALYSIS_PROMPT                 │
│     ├── 完整模式: DEEP_ANALYSIS_PROMPT                       │
│     └── JSON 提取                                            │
│                                                              │
│  3. 分析后验证 (post_analysis_validate)                      │
│     ├── Tier 合理性检查                                      │
│     ├── 必要字段检查                                         │
│     ├── 标签数量检查                                         │
│     └── Outline 深度检查                                     │
│                                                              │
│  4. 捏造检测 (detect_fabrication)                           │
│     ├── 公式捏造检测                                         │
│     ├── 虚假数据检测                                         │
│     ├── 虚假章节检测                                         │
│     └── 降级处理                                             │
│                                                              │
│  5. Tier A 二次确认                                          │
│     ├── 日志记录                                             │
│     ├── 详细信息输出                                         │
│     └── 可扩展告警                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 使用方法

```python
from app.services.guardrails import analysis_guardrail

# 分析前检查
pre_check = analysis_guardrail.pre_analysis_check(
    quick_mode=True,
    content=paper_abstract,
    abstract=paper_abstract,
    title=paper_title,
)
if not pre_check.valid:
    logger.warning(f"分析前警告: {pre_check.warnings}")

# 分析后验证
post_check = analysis_guardrail.post_analysis_validate(
    analysis_json=analysis_json,
    quick_mode=True,
    content_used=paper_abstract,
)
if not post_check.valid:
    logger.warning(f"分析后警告: {post_check.warnings}")

# 捏造检测
fabric_check = analysis_guardrail.detect_fabrication(
    analysis_json=analysis_json,
    quick_mode=True,
)
if not fabric_check.valid:
    logger.error(f"检测到捏造: {fabric_check.warnings}")
    analysis_json["outline"] = []  # 清空可疑内容

# Tier 分布检查
tier_check = analysis_guardrail.tier_distribution_check(
    tier_counts={"A": 10, "B": 40, "C": 50},
    total=100,
)
```

### 8.4 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `QUICK_MODE_MAX_CONTENT_LENGTH` | 5000 | 快速模式最大内容长度 |
| `TIER_A_ALERT_THRESHOLD` | 0.20 | Tier A 预警阈值（20%） |
| `MIN_ABSTRACT_LENGTH` | 100 | 最小摘要长度 |

### 8.5 集成位置

| 文件 | 集成方式 |
|------|----------|
| `app/services/ai_service.py` | 分析前检查、分析后验证、捏造检测 |
| `app/tasks/analysis_task.py` | Tier A 二次确认、最终验证 |
| `scripts/check_tier_distribution.py` | Tier 分布检查、告警发送 |

### 8.6 告警机制

**告警日志**: `~/logs/tier_alerts.log`

**告警触发条件**:
- Tier A 占比 > 20%
- Tier 分布偏差 > 10%
- 检测到数据捏造
- Tier A 论文出现

**扩展方式**:
```python
# 在 send_alert 函数中添加飞书通知
def send_alert(message: str, alert_type: str):
    # 现有: 记录到日志文件
    # 扩展: 调用飞书 API
    from app.publishers.feishu import send_message
    send_message(f"⚠️ Tier 告警: {message}")
```

### 8.7 防护效果总结

| 防护层 | 检查项 | 效果 |
|--------|--------|------|
| 分析前 | 内容长度、Prompt匹配 | 防止输入不匹配 |
| 分析后 | Tier合理性、必要字段 | 防止输出不完整 |
| 捏造检测 | 公式、数据、章节 | 防止数据捏造 |
| Tier分布 | 占比、偏差 | 防止 Tier 通胀 |
| 告警 | 日志记录 | 问题及时发现 |

---

## 九、B 类标准收紧（v2.1）

### 9.1 问题发现

**监控结果**：
- Tier A: 8.2% ✅ 符合预期
- Tier B: 67.3% ⚠️ 远超预期（30-40%）
- Tier C: 24.5% ⚠️ 远低于预期（40-55%）

**根因分析**：
B 类标准"满足以下至少 1 条"过于宽松，大多数论文都能满足其中一个条件（如"有明确方法创新"），导致 B 类泛滥。

### 9.2 解决方案

**修改内容**：

```python
# ❌ 旧版（过于宽松）
### B 类（有价值贡献）
满足以下至少 1 条：
- 有明确的方法创新
- 在特定场景下取得良好效果
- 提供有价值的实证研究
- 热门方向的合理改进

# ✅ 新版（收紧标准）
### B 类（有价值贡献）
**需要同时满足以下至少 2 条**（收紧标准）：
- 有明确的方法创新（非简单组合或调参）
- 在特定场景下取得良好效果（有具体数据支撑）
- 提供有价值的实证研究或工具（已被验证）
- 热门方向的合理改进（有创新点）

**注意：只有 1 条满足的应评为 C 类，而非 B 类**
```

### 9.3 评估流程强化

```python
### 评估流程（严格执行）

1. 先问自己：这篇论文是否改变了领域认知？→ 可能是 A（需 2+ 条）
2. 再问：是否满足 2 条以上创新条件？→ 可能是 B（必须 2+ 条）
3. 如果只满足 1 条或都是增量改进 → 给 C

**大多数论文应该是 C 类（50%+），B 类应该是少数（30-40%）**
```

### 9.4 预期效果

| Tier | 旧版占比 | 预期新版占比 |
|------|----------|--------------|
| A | 8.2% | < 20% |
| B | 67.3% | 30-40% |
| C | 24.5% | 40-55% |

**变更要点**：
- B 类门槛从"1 条"提高到"2 条"
- 强调"只有 1 条满足应给 C"
- 明确"C 类应该是多数（50%+）"

---

> 本文档记录了 Tier 通胀和数据捏造问题的根因及防护机制。
> 任何 Prompt 修改前必须检查是否破坏现有机制。
> 防护层模块已集成到 AI 服务和分析任务中，自动执行安全检查。
> B 类标准已收紧，预期分布更接近 15:35:50。