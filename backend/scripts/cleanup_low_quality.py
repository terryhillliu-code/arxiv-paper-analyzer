#!/usr/bin/env python3
"""清理低质量论文。

删除 Tier C 且未分析的论文，减少数据冗余。
"""

import asyncio
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from app.database import async_session_maker
from app.models import Paper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def cleanup_low_quality(dry_run: bool = True):
    """清理 Tier C 且未分析的论文。

    Args:
        dry_run: 仅统计不实际删除
    """
    async with async_session_maker() as db:
        # 统计待删除论文
        result = await db.execute(
            select(Paper)
            .where(Paper.tier == "C")
            .where(Paper.has_analysis == False)
        )
        papers = result.scalars().all()

        logger.info(f"找到 {len(papers)} 篇 Tier C 未分析论文")

        if not papers:
            logger.info("无需清理")
            return {"deleted": 0}

        # 按分类统计
        from collections import Counter
        cat_counter = Counter()
        for p in papers:
            for cat in p.categories or []:
                cat_counter[cat] += 1

        logger.info("\n=== 待删除论文分类分布 ===")
        for cat, count in cat_counter.most_common(10):
            logger.info(f"  {cat}: {count}")

        if dry_run:
            logger.info("\n[DRY RUN] 不实际删除")
            return {"would_delete": len(papers)}

        # 实际删除
        result = await db.execute(
            delete(Paper)
            .where(Paper.tier == "C")
            .where(Paper.has_analysis == False)
        )
        deleted = result.rowcount

        await db.commit()

        logger.info(f"已删除 {deleted} 篇论文")
        return {"deleted": deleted}


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="清理低质量论文")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除（默认仅统计）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("低质量论文清理")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    await cleanup_low_quality(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())