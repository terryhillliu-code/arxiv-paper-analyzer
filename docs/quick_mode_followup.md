# 快速模式后续任务清单

> 创建时间: 2026-03-20 18:00
> 快速模式预计完成: 明早 ~7:30

---

## 一、完成后检查

```bash
# 查看最终状态
tail -20 /tmp/quick_analysis.log

# 统计完成数量
ls ~/Documents/ZhiweiVault/Inbox/PAPER_2026-03-20*.md | wc -l

# Tier A/B/C 分布
grep -l "tier: A" ~/Documents/ZhiweiVault/Inbox/PAPER_2026-03-20*.md | wc -l
grep -l "tier: B" ~/Documents/ZhiweiVault/Inbox/PAPER_2026-03-20*.md | wc -l
grep -l "tier: C" ~/Documents/ZhiweiVault/Inbox/PAPER_2026-03-20*.md | wc -l
```

---

## 二、Tier A 论文完整模式重分析

**共 36 篇 Tier A 论文需要重分析**

### 执行命令

```bash
# 获取 Tier A 论文 arxiv_id 列表
grep -l "tier: A" ~/Documents/ZhiweiVault/Inbox/PAPER_2026-03-20*.md | \
  xargs grep -h "source_url:" | \
  sed 's/.*abs\/\([^"]*\).*/\1/' > /tmp/tier_a_papers.txt

# 用完整模式重新分析 (示例)
cd ~/arxiv-paper-analyzer/backend
source venv/bin/activate
python -c "
import asyncio
from app.tasks.batch_analyzer import BatchAnalyzer

async def main():
    with open('/tmp/tier_a_papers.txt') as f:
        arxiv_ids = [line.strip() for line in f]

    analyzer = BatchAnalyzer(quick_mode=False, max_concurrent=3)
    await analyzer.run(arxiv_ids)

asyncio.run(main())
"
```

---

## 三、重点论文清单

以下 Tier A 论文建议优先深入研究：

| arxiv_id | 标题 | 领域 | 优先级 |
|----------|------|------|--------|
| 2603.19234 | Matryoshka Gaussian Splatting | 3D渲染 | P0 |
| 2603.19222 | Spectrally-Guided Diffusion Noise | 扩散模型 | P0 |
| 待补充 | Bootstrapping Coding Agents | AI Agent | P1 |
| 待补充 | DriveTok: 3D Driving Scene | 自动驾驶 | P1 |
| 待补充 | The Phasor Transformer | Transformer | P1 |

---

## 四、监控命令

```bash
# 实时进度
tail -f /tmp/quick_analysis.log

# 每5分钟汇总
watch -n 300 'tail -1 /tmp/quick_analysis.log | grep -oE "[0-9]+/300"'

# 检查进程是否存活
ps aux | grep batch_analyzer
```

---

## 五、对比报告

详见: `docs/analysis_mode_comparison.md`