#!/usr/bin/env python3
"""批量创建分析任务。

为未分析的论文创建任务队列。
"""

import asyncio
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.database import async_session_maker
from app.models import Paper
from app.tasks.task_queue import task_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def create_analysis_tasks(
    tier_priority: str = None,
    limit: int = 100,
    quick_mode: bool = True,
):
    """创建分析任务。

    Args:
        tier_priority: 优先处理的 Tier（A, B, C），None 表示全部
        limit: 最大创建数量
        quick_mode: 快速模式（只用摘要）
    """
    async with async_session_maker() as db:
        # 查询未分析的论文
        query = (
            select(Paper)
            .where(Paper.has_analysis == False)
            .where(Paper.abstract != None)  # 必须有摘要
            .order_by(Paper.tier.desc(), Paper.publish_date.desc())
        )

        if tier_priority:
            query = query.where(Paper.tier == tier_priority)

        query = query.limit(limit)

        result = await db.execute(query)
        papers = result.scalars().all()

        logger.info(f"找到 {len(papers)} 篇未分析论文")

        if not papers:
            logger.info("没有需要处理的论文")
            return {"created": 0, "skipped": 0}

        # 获取已有的任务（包括 pending 和 running）
        import sqlite3
        conn = sqlite3.connect(task_queue.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT payload FROM tasks WHERE status IN ("pending", "running")')
        existing_paper_ids = set()
        for row in cursor.fetchall():
            import json
            payload = json.loads(row[0])
            if payload and "paper_id" in payload:
                existing_paper_ids.add(payload["paper_id"])
        conn.close()

        created = 0
        skipped = 0

        for paper in papers:
            if paper.id in existing_paper_ids:
                skipped += 1
                continue

            # 创建任务
            task = task_queue.create_task(
                task_type="analysis",
                payload={
                    "paper_id": paper.id,
                    "quick_mode": quick_mode,
                },
            )

            if task:
                created += 1
                if created % 50 == 0:
                    logger.info(f"已创建 {created} 个任务...")

        logger.info(f"创建完成: {created} 个任务，跳过 {skipped} 个已存在")

        # 统计任务队列
        pending = task_queue.get_pending_tasks(limit=1000)

        return {"created": created, "skipped": skipped, "pending_total": len(pending)}


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="批量创建分析任务")
    parser.add_argument(
        "--tier",
        choices=["A", "B", "C"],
        help="优先处理的 Tier 等级",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="最大创建数量",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=True,
        help="快速模式（只用摘要）",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="完整模式（解析 PDF）",
    )

    args = parser.parse_args()

    quick_mode = not args.full

    logger.info("=" * 60)
    logger.info("批量创建分析任务")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Tier 过滤: {args.tier or '全部'}")
    logger.info(f"模式: {'快速' if quick_mode else '完整'}")
    logger.info(f"限制: {args.limit}")
    logger.info("=" * 60)

    result = await create_analysis_tasks(
        tier_priority=args.tier,
        limit=args.limit,
        quick_mode=quick_mode,
    )

    logger.info(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())