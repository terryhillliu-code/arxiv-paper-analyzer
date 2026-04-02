#!/usr/bin/env python3
"""批量重新评估 Tier。

根据新的严格标准重新评估已分析论文的Tier。
B类标准从"满足1条"收紧为"满足2条"。

用法：
    python scripts/retier_all.py
    python scripts/retier_all.py --dry-run  # 预览不执行
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 新的Tier评估标准
TIER_PROMPT = """你是一位学术论文评审专家。根据以下严格标准重新评估论文的Tier。

## 论文信息
标题: {title}
摘要: {abstract}
当前Tier: {current_tier}
引用数: {citation_count}
发布日期: {publish_date}
机构: {institutions}

## Tier 评估标准（严格执行）

⚠️ **目标分布: A=15%, B=35%, C=50%**

### A 类（顶尖创新）- 占比应 < 20%
必须同时满足以下至少 2 条：
- 提出全新的方法范式或理论框架（非增量改进）
- 在主流基准上取得显著突破（提升 >10% 或首次解决关键难题）
- 顶级机构（OpenAI/DeepMind/Google/Stanford/MIT）的标志性工作
- 开创全新研究方向或解决长期未解决的难题

### B 类（有价值贡献）- 占比应 30-40%
**需要同时满足以下至少 2 条**：
- 有明确的方法创新（非简单组合或调参）
- 在特定场景下取得良好效果（有具体数据支撑）
- 提供有价值的实证研究或工具（已被验证）
- 热门方向的合理改进（有创新点）

**注意：只有 1 条满足的应评为 C 类**

### C 类（一般参考）- 占比应 40-55%
- 增量式改进（方法组合、参数调优、小范围应用）
- 应用导向研究（场景适配、系统集成）
- 初步探索或概念验证
- 工具/数据集构建
- 只有 1 条满足 B 类条件

## 评估流程
1. 这篇论文是否改变了领域认知？→ 可能是 A（需满足2+条）
2. 是否满足 2 条以上创新条件？→ 可能是 B（必须2+条）
3. 只满足1条或都是增量改进 → 给 C

**大多数论文应该是 C 类**

## 输出格式
直接输出 JSON:
{{"tier": "A/B/C", "reason": "简短理由（20字内）"}}
"""


async def retier_paper(paper: Paper, dry_run: bool = False) -> str:
    """重新评估单篇论文的Tier"""
    try:
        # 获取必要信息
        title = paper.title or ""
        abstract = paper.abstract or ""
        current_tier = paper.tier or "B"
        citation_count = paper.citation_count or "未知"
        publish_date = str(paper.publish_date) if paper.publish_date else "未知"
        institutions = ", ".join(paper.institutions) if paper.institutions else "未知"

        # 如果摘要太短，跳过
        if len(abstract) < 100:
            return current_tier

        # 调用AI评估
        prompt = TIER_PROMPT.format(
            title=title[:200],
            abstract=abstract[:1500],
            current_tier=current_tier,
            citation_count=citation_count,
            publish_date=publish_date,
            institutions=institutions,
        )

        response = await asyncio.to_thread(
            ai_service._call_api, prompt, 200
        )
        result = ai_service._parse_json(response)

        new_tier = result.get("tier", current_tier)
        reason = result.get("reason", "")

        # 验证Tier有效性
        if new_tier not in ["A", "B", "C"]:
            new_tier = current_tier

        if new_tier != current_tier:
            logger.info(f"Tier 变更: {current_tier} → {new_tier} | {title[:40]}... | {reason}")

        return new_tier

    except Exception as e:
        logger.warning(f"评估失败: {e}")
        return paper.tier or "B"


async def retier_all(dry_run: bool = False, batch_size: int = 50):
    """批量重新评估所有已分析论文"""
    async with async_session_maker() as db:
        # 获取所有已分析且有Tier的论文
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(Paper.tier != None)
            .where(Paper.abstract != None)
            .order_by(Paper.id)
        )
        papers = result.scalars().all()

        total = len(papers)
        logger.info(f"找到 {total} 篇已分析论文需要重新评估")

        if dry_run:
            logger.info("=== DRY RUN 模式 ===")

        # 统计变更
        changes = {"A": 0, "B": 0, "C": 0}
        new_tiers = {"A": 0, "B": 0, "C": 0}

        # 分批处理
        for i in range(0, total, batch_size):
            batch = papers[i:i+batch_size]

            for paper in batch:
                old_tier = paper.tier
                new_tier = await retier_paper(paper, dry_run)

                if new_tier != old_tier:
                    changes[old_tier] = changes.get(old_tier, 0) - 1
                    changes[new_tier] = changes.get(new_tier, 0) + 1

                new_tiers[new_tier] = new_tiers.get(new_tier, 0) + 1

                # 更新数据库
                if not dry_run and new_tier != old_tier:
                    paper.tier = new_tier

            # 提交批次
            if not dry_run:
                await db.commit()

            logger.info(f"进度: {min(i+batch_size, total)}/{total} | "
                       f"A:{new_tiers['A']} B:{new_tiers['B']} C:{new_tiers['C']}")

            # 避免API限流
            await asyncio.sleep(1)

        # 最终统计
        logger.info("=" * 50)
        logger.info("重新评估完成")
        logger.info(f"新分布: A={new_tiers['A']} ({new_tiers['A']/total*100:.1f}%), "
                   f"B={new_tiers['B']} ({new_tiers['B']/total*100:.1f}%), "
                   f"C={new_tiers['C']} ({new_tiers['C']/total*100:.1f}%)")
        logger.info(f"变更: A{changes['A']:+d}, B{changes['B']:+d}, C{changes['C']:+d}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="批量重新评估Tier")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不修改数据")
    parser.add_argument("--batch-size", type=int, default=50, help="批处理大小")
    args = parser.parse_args()

    await retier_all(dry_run=args.dry_run, batch_size=args.batch_size)


if __name__ == "__main__":
    asyncio.run(main())