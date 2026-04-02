#!/usr/bin/env python3
"""Tier 定期更新脚本。

根据论文的发布时间、引用数动态调整 Tier。
建议每周运行一次。
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.database import async_session_maker
from app.models import Paper
from app.services.paper_scorer import PaperScorer

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def update_tiers(dry_run: bool = False):
    """更新所有论文的 Tier。"""
    async with async_session_maker() as db:
        # 获取所有论文
        result = await db.execute(select(Paper))
        papers = result.scalars().all()

        logger.info(f"开始更新 {len(papers)} 篇论文的 Tier...")

        now = datetime.now()
        changes = {'A_to_B': 0, 'B_to_A': 0, 'B_to_C': 0, 'C_to_B': 0, 'unchanged': 0}

        for paper in papers:
            # 计算内容评分
            score = PaperScorer.score(
                paper.title,
                paper.abstract or "",
                paper.authors
            )

            # 计算发布天数
            days_since_publish = 0
            if paper.publish_date:
                delta = now - paper.publish_date
                days_since_publish = delta.days

            # 获取引用数
            citation_count = paper.citation_count or 0

            # 计算新 Tier
            old_tier = paper.tier
            new_tier = PaperScorer.get_dynamic_tier(
                score,
                citation_count,
                days_since_publish
            )

            if new_tier != old_tier:
                change_key = f"{old_tier}_to_{new_tier}"
                if change_key in changes:
                    changes[change_key] += 1
                if not dry_run:
                    paper.tier = new_tier
                logger.debug(f"#{paper.id} | {old_tier} -> {new_tier} | {paper.title[:40]}")
            else:
                changes['unchanged'] += 1

        if dry_run:
            logger.info("DRY RUN - 跳过数据库提交")
        else:
            await db.commit()

        # 统计结果
        result = await db.execute(
            select(Paper.tier, func.count(Paper.id))
            .group_by(Paper.tier)
        )
        tiers = dict(result.fetchall())

        logger.info("\n=== Tier 更新结果 ===")
        logger.info(f"A -> B: {changes['A_to_B']} 篇")
        logger.info(f"B -> A: {changes['B_to_A']} 篇")
        logger.info(f"B -> C: {changes['B_to_C']} 篇")
        logger.info(f"C -> B: {changes['C_to_B']} 篇")
        logger.info(f"保持不变: {changes['unchanged']} 篇")

        logger.info("\n=== 当前 Tier 分布 ===")
        total = sum(tiers.values())
        for tier in ['A', 'B', 'C']:
            count = tiers.get(tier, 0)
            pct = count / total * 100 if total > 0 else 0
            logger.info(f"Tier {tier}: {count} ({pct:.1f}%)")


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="更新论文 Tier")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检查不实际更新",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Tier 定期更新脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN 模式 - 不实际更新")

    await update_tiers(dry_run=args.dry_run)

    logger.info("\n更新完成!")


if __name__ == "__main__":
    asyncio.run(main())