#!/usr/bin/env python3
"""每日论文工作流。

完整流程：
1. 从 arXiv 抓取新论文
2. 预筛选评分
3. 自动创建分析任务
4. 发送通知

用法：
    python scripts/daily_workflow.py
    python scripts/daily_workflow.py --categories cs.AI,cs.CL
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.database import async_session_maker
from app.models import Paper
from app.services.arxiv_service import ArxivService
from app.services.paper_scorer import PaperScorer
from app.tasks.task_queue import TaskQueue, TASK_DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 默认分类
DEFAULT_CATEGORIES = [
    "cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.RO",
    "cs.NE", "cs.SE", "cs.DC", "cs.CR", "cs.HC"
]


async def fetch_new_papers(categories: list, days: int = 1) -> int:
    """抓取新论文。

    Args:
        categories: 分类列表
        days: 抓取最近几天的论文

    Returns:
        新增论文数
    """
    logger.info("=" * 60)
    logger.info("第一步：抓取新论文")
    logger.info("=" * 60)

    arxiv_service = ArxivService()

    try:
        async with async_session_maker() as db:
            # 使用 fetch_by_categories_batch 批量抓取
            from datetime import datetime, timedelta
            date_from = datetime.now() - timedelta(days=days)

            result = await arxiv_service.fetch_by_categories_batch(
                db=db,
                categories=categories,
                date_from=date_from,
                per_category_limit=100,
                prefilter=True,
                delay_between_categories=5.0,
            )

            total_added = result.get("added", 0)
            logger.info(f"抓取完成: 总数 {result.get('total', 0)}, 新增 {total_added}")
            return total_added

    except Exception as e:
        logger.error(f"抓取失败: {e}", exc_info=True)
        return 0


async def create_analysis_tasks_for_new_papers(limit: int = 500, days: int = 1) -> int:
    """为新论文创建分析任务。

    Args:
        limit: 最大创建数量
        days: 处理最近几天的论文

    Returns:
        创建任务数
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("第二步：创建分析任务")
    logger.info("=" * 60)

    # 查询最近 N 天新增且未分析的论文
    async with async_session_maker() as db:
        since = datetime.now().date() - timedelta(days=days)
        result = await db.execute(
            select(Paper)
            .where(Paper.created_at >= since)
            .where(Paper.has_analysis == False)
            .where(Paper.abstract != None)
            .order_by(Paper.tier.desc(), Paper.publish_date.desc())
            .limit(limit)
        )
        papers = result.scalars().all()

        if not papers:
            logger.info("没有需要分析的新论文")
            return 0

        logger.info(f"找到 {len(papers)} 篇待分析新论文")

        # 创建任务队列
        task_queue = TaskQueue(db_path=TASK_DB_PATH, max_concurrent=6)

        # 获取已有任务
        import sqlite3
        import json
        conn = sqlite3.connect(task_queue.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT payload FROM tasks WHERE status IN ("pending", "running")')
        existing_paper_ids = set()
        for row in cursor.fetchall():
            payload = json.loads(row[0])
            if payload and "paper_id" in payload:
                existing_paper_ids.add(payload["paper_id"])
        conn.close()

        # 创建任务
        created = 0
        for paper in papers:
            if paper.id in existing_paper_ids:
                continue

            task = task_queue.create_task(
                task_type="analysis",
                payload={
                    "paper_id": paper.id,
                    "quick_mode": True,
                },
            )
            if task:
                created += 1
                if created % 50 == 0:
                    logger.info(f"已创建 {created} 个任务...")

        logger.info(f"创建完成: {created} 个新任务")
        return created


async def get_stats() -> dict:
    """获取当前统计"""
    async with async_session_maker() as db:
        # 总体
        total = await db.execute(select(func.count(Paper.id)))
        total_count = total.scalar()

        analyzed = await db.execute(
            select(func.count(Paper.id)).where(Paper.has_analysis == True)
        )
        analyzed_count = analyzed.scalar()

        # 今日
        today = datetime.now().date()
        today_papers = await db.execute(
            select(func.count(Paper.id)).where(Paper.created_at >= today)
        )
        today_count = today_papers.scalar()

        today_analyzed = await db.execute(
            select(func.count(Paper.id))
            .where(Paper.created_at >= today)
            .where(Paper.has_analysis == True)
        )
        today_analyzed_count = today_analyzed.scalar()

        # 待处理
        pending = await db.execute(
            select(func.count(Paper.id))
            .where(Paper.has_analysis == False)
            .where(Paper.abstract != None)
        )
        pending_count = pending.scalar()

        return {
            "total": total_count,
            "analyzed": analyzed_count,
            "analyzed_percent": analyzed_count / total_count * 100 if total_count > 0 else 0,
            "today_new": today_count,
            "today_analyzed": today_analyzed_count,
            "pending": pending_count,
        }


async def send_notification(stats: dict, new_papers: int, new_tasks: int):
    """发送通知（可选）"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("第三步：状态汇总")
    logger.info("=" * 60)

    logger.info(f"本次新增论文: {new_papers}")
    logger.info(f"本次创建任务: {new_tasks}")
    logger.info("")
    logger.info(f"总论文数: {stats['total']}")
    logger.info(f"已分析: {stats['analyzed']} ({stats['analyzed_percent']:.1f}%)")
    logger.info(f"今日新增: {stats['today_new']}")
    logger.info(f"今日已分析: {stats['today_analyzed']}")
    logger.info(f"待处理: {stats['pending']}")

    # 可以添加飞书通知
    # from app.services.feishu import send_message
    # await send_message(...)


async def main():
    """主流程"""
    import argparse

    parser = argparse.ArgumentParser(description="每日论文工作流")
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="分类列表，逗号分隔",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="抓取最近几天的论文",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="跳过抓取，只创建任务",
    )
    parser.add_argument(
        "--task-limit",
        type=int,
        default=500,
        help="最大创建任务数",
    )

    args = parser.parse_args()
    categories = args.categories.split(",")

    logger.info("=" * 60)
    logger.info("每日论文工作流")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 第一步：抓取
    new_papers = 0
    if not args.skip_fetch:
        new_papers = await fetch_new_papers(categories, args.days)

    # 第二步：创建任务
    new_tasks = await create_analysis_tasks_for_new_papers(args.task_limit, args.days)

    # 第三步：统计通知
    stats = await get_stats()
    await send_notification(stats, new_papers, new_tasks)

    logger.info("")
    logger.info("=" * 60)
    logger.info("工作流完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())