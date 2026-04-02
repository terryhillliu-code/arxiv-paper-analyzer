#!/usr/bin/env python3
"""历史论文补抓调度器。

定期检查并补抓缺失的历史论文。
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_missing_dates() -> list:
    """检查缺失的日期。

    Returns:
        缺失日期列表
    """
    async with async_session_maker() as db:
        # 只检查最近 30 天的日期
        cutoff_date = datetime.now() - timedelta(days=30)

        # 获取数据库中最近 30 天的论文日期及数量
        result = await db.execute(
            select(func.date(Paper.publish_date), func.count(Paper.id))
            .where(Paper.publish_date >= cutoff_date)
            .group_by(func.date(Paper.publish_date))
        )
        # func.date() 返回字符串，转为 date 对象
        from datetime import date as date_type
        date_counts = {}
        for row in result.fetchall():
            if isinstance(row[0], str):
                date_counts[date_type.fromisoformat(row[0])] = row[1]
            elif isinstance(row[0], date_type):
                date_counts[row[0]] = row[1]

        logger.info(f"最近 30 天已有论文日期: {len(date_counts)} 个")

        # 找出缺失或数据不完整的日期
        missing_dates = []
        incomplete_dates = []
        current = cutoff_date.replace(hour=0, minute=0, second=0)
        end_date = datetime.now()

        while current <= end_date:
            current_date = current.date()

            # 跳过周末（ArXiv 不在周末发布论文）
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            count = date_counts.get(current_date, 0)

            if count == 0:
                missing_dates.append(current)
            elif count < 50:  # 正常工作日应该有 50+ 篇论文
                incomplete_dates.append((current, count))

            current += timedelta(days=1)

        logger.info(f"完全缺失: {len(missing_dates)} 个工作日")
        if missing_dates:
            logger.info("缺失日期:")
            for d in missing_dates:
                logger.info(f"  {d.strftime('%Y-%m-%d')} ({d.strftime('%A')})")

        logger.info(f"数据不完整: {len(incomplete_dates)} 个工作日")
        if incomplete_dates:
            logger.info("不完整日期:")
            for d, c in incomplete_dates:
                logger.info(f"  {d.strftime('%Y-%m-%d')} ({d.strftime('%A')}): {c} 篇")

        return missing_dates


async def fetch_missing_papers(missing_dates: list, max_days: int = 7) -> dict:
    """补抓缺失日期的论文。

    Args:
        missing_dates: 缺失日期列表
        max_days: 最多补抓天数（避免一次抓太多）

    Returns:
        抓取统计
    """
    if not missing_dates:
        return {"message": "无缺失日期"}

    # 只处理最近 max_days 天
    dates_to_fetch = missing_dates[:max_days]

    logger.info(f"准备补抓 {len(dates_to_fetch)} 天的论文")

    results = {
        "total_dates": len(missing_dates),
        "fetched_dates": len(dates_to_fetch),
        "total_papers": 0,
        "details": [],
    }

    async with async_session_maker() as db:
        for date in dates_to_fetch:
            try:
                logger.info(f"\n补抓日期: {date.strftime('%Y-%m-%d')}")

                # 使用日期范围抓取
                result = await ArxivService.fetch_by_date_range(
                    db=db,
                    categories=["cs.AI", "cs.CL", "cs.LG", "cs.CV"],
                    date_from=date,
                    date_to=date + timedelta(days=1),
                    max_results=200,
                    prefilter=True,
                )

                papers_count = result.get("new_papers", 0)
                results["total_papers"] += papers_count
                results["details"].append({
                    "date": date.strftime("%Y-%m-%d"),
                    "papers": papers_count,
                })

                logger.info(f"  抓取到 {papers_count} 篇新论文")

                # 避免限流
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"补抓失败: {date.strftime('%Y-%m-%d')}, 错误: {e}")

    return results


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="历史论文补抓")
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查缺失日期",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=7,
        help="最多补抓天数",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="实际补抓（默认仅检查）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("历史论文补抓调度器")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 检查缺失日期
    missing_dates = await check_missing_dates()

    if args.check or not args.commit:
        logger.info("\n检查完成，使用 --commit 参数执行补抓")
        return

    # 执行补抓
    if missing_dates:
        results = await fetch_missing_papers(missing_dates, max_days=args.max_days)

        logger.info("\n=== 补抓结果 ===")
        logger.info(f"总缺失日期: {results['total_dates']}")
        logger.info(f"本次处理: {results['fetched_dates']}")
        logger.info(f"抓取论文: {results['total_papers']}")

        for detail in results["details"]:
            logger.info(f"  {detail['date']}: {detail['papers']} 篇")


if __name__ == "__main__":
    asyncio.run(main())