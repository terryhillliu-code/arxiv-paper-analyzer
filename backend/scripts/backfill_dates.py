#!/usr/bin/env python3
"""回填缺失日期的论文。

针对特定日期范围抓取论文，补充数据库空缺。
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import arxiv
from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper, FetchLog
from app.services.paper_scorer import PaperScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def backfill_date_range(
    date_from: datetime,
    date_to: datetime,
    categories: list[str] = None,
    max_results: int = 500,
    delay: float = 5.0,
):
    """回填指定日期范围的论文。

    Args:
        date_from: 开始日期
        date_to: 结束日期
        categories: 分类列表
        max_results: 最大抓取数
        delay: 请求间隔
    """
    if categories is None:
        categories = ["cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.RO"]

    # 确保时区
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=timezone.utc)
    if date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=timezone.utc)

    query = " OR ".join(f"cat:{cat}" for cat in categories)

    logger.info(f"回填日期范围: {date_from.date()} ~ {date_to.date()}")
    logger.info(f"分类: {categories}")

    try:
        client = arxiv.Client()
        client.delay_seconds = delay

        # 使用提交日期排序
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        def _fetch_sync():
            results = []
            for r in client.results(search):
                results.append(r)
            return results

        all_results = await asyncio.to_thread(_fetch_sync)

        logger.info(f"ArXiv 返回 {len(all_results)} 条结果")

        # 过滤日期范围
        filtered = []
        for result in all_results:
            pub_date = result.published
            if date_from <= pub_date <= date_to:
                filtered.append(result)

        logger.info(f"日期范围内: {len(filtered)} 条")

        if not filtered:
            logger.warning("无符合条件的论文，可能 ArXiv API 不支持历史数据")
            return {"fetched": 0, "added": 0, "message": "无数据"}

        # 存入数据库
        async with async_session_maker() as db:
            added = 0
            seen = set()

            for result in filtered:
                # 解析 arxiv_id
                arxiv_id = result.entry_id.split("/")[-1]
                if "v" in arxiv_id:
                    arxiv_id = arxiv_id.rsplit("v", 1)[0]

                if arxiv_id in seen:
                    continue
                seen.add(arxiv_id)

                # 检查是否已存在
                existing = await db.execute(
                    select(Paper).where(Paper.arxiv_id == arxiv_id)
                )
                if existing.scalar_one_or_none():
                    continue

                # 创建论文
                authors = [a.name for a in result.authors]
                score = PaperScorer.score(result.title, result.summary or "", authors)
                initial_tier = PaperScorer.get_initial_tier(score)

                paper = Paper(
                    arxiv_id=arxiv_id,
                    title=result.title.strip(),
                    authors=authors,
                    abstract=result.summary.strip() if result.summary else None,
                    categories=list(result.categories),
                    publish_date=result.published,
                    pdf_url=result.pdf_url,
                    arxiv_url=result.entry_id,
                    tier=initial_tier,
                )

                db.add(paper)
                added += 1

            await db.commit()

        logger.info(f"新增: {added} 篇")

        return {"fetched": len(filtered), "added": added}

    except Exception as e:
        logger.error(f"回填失败: {e}")
        return {"fetched": 0, "added": 0, "error": str(e)}


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="回填缺失日期的论文")
    parser.add_argument(
        "--from-date",
        default="2026-03-01",
        help="开始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to-date",
        default="2026-03-09",
        help="结束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="请求间隔（秒）",
    )

    args = parser.parse_args()

    date_from = datetime.strptime(args.from_date, "%Y-%m-%d")
    date_to = datetime.strptime(args.to_date, "%Y-%m-%d") + timedelta(days=1)

    logger.info("=" * 60)
    logger.info("论文回填脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    result = await backfill_date_range(
        date_from=date_from,
        date_to=date_to,
        delay=args.delay,
    )

    logger.info(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())