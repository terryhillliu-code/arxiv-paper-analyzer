#!/usr/bin/env python3
"""历史论文重评估脚本。

使用新的评分逻辑重新评估可能被遗漏的论文。
从 ArXiv 抓取近期论文，检查是否应该入库。
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import arxiv
from sqlalchemy import select, func
from app.database import async_session_maker
from app.models import Paper, FetchLog
from app.services.paper_scorer import PaperScorer, score_with_s2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 默认抓取的分类
DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]


async def check_date_range(
    date_from: datetime,
    date_to: datetime,
    categories: list = None,
    dry_run: bool = True,
):
    """检查指定日期范围内遗漏的论文。

    Args:
        date_from: 开始日期 (timezone-aware)
        date_to: 结束日期 (timezone-aware)
        categories: 分类列表
        dry_run: 是否只检查不实际入库
    """
    categories = categories or DEFAULT_CATEGORIES

    logger.info(f"检查日期范围: {date_from.strftime('%Y-%m-%d')} 到 {date_to.strftime('%Y-%m-%d')}")
    logger.info(f"分类: {categories}")
    logger.info(f"模式: {'仅检查' if dry_run else '实际入库'}")

    # 计算需要抓取的论文数量
    # 假设每天约 150 篇论文，计算需要抓取的最大结果数
    days_diff = (datetime.now(timezone.utc) - date_from).days + 7
    max_results = min(5000, days_diff * 200)  # 增加上限到 5000

    logger.info(f"预计需要抓取 {max_results} 篇论文")

    # 构建基础查询（不使用日期范围）
    query = " OR ".join(f"cat:{cat}" for cat in categories)

    client = arxiv.Client()
    client.delay_seconds = 3.0

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    # 获取结果
    logger.info("正在获取 ArXiv 论文...")
    all_results = []
    try:
        all_results = list(client.results(search))
        logger.info(f"获取到 {len(all_results)} 篇论文")
    except Exception as e:
        logger.error(f"获取论文失败: {e}")
        return []

    # 筛选日期范围内的论文
    filtered_results = []
    for r in all_results:
        if date_from <= r.published <= date_to:
            filtered_results.append(r)

    logger.info(f"日期范围内论文: {len(filtered_results)} 篇")

    # 检查数据库中已有论文（使用 timezone-naive datetime）
    async with async_session_maker() as db:
        date_from_naive = date_from.replace(tzinfo=None)
        date_to_naive = date_to.replace(tzinfo=None)
        result = await db.execute(
            select(Paper.arxiv_id)
            .where(Paper.publish_date >= date_from_naive)
            .where(Paper.publish_date <= date_to_naive)
        )
        existing_ids = set(row[0] for row in result.fetchall())

    logger.info(f"数据库已有: {len(existing_ids)} 篇")

    # 检查遗漏的论文
    missing_high_quality = []
    missing_total = 0

    for r in filtered_results:
        arxiv_id = r.entry_id.split("/")[-1]
        if "v" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("v", 1)[0]

        if arxiv_id in existing_ids:
            continue

        missing_total += 1

        # 评估论文质量
        authors = [a.name for a in r.authors]
        score = PaperScorer.score(r.title, r.summary, authors)
        should_fetch = PaperScorer.should_fetch(r.title, r.summary, authors)

        if should_fetch:
            missing_high_quality.append({
                "arxiv_id": arxiv_id,
                "title": r.title,
                "score": score,
                "categories": r.categories,
                "published": r.published,
            })

    logger.info(f"\n=== 检查结果 ===")
    logger.info(f"遗漏论文总数: {missing_total}")
    logger.info(f"高质量遗漏: {len(missing_high_quality)}")

    if missing_high_quality:
        logger.info("\n高质量遗漏论文:")
        for p in missing_high_quality[:20]:
            logger.info(f"  [{p['score']}分] {p['title'][:50]}...")
            logger.info(f"    ArXiv: {p['arxiv_id']} | 分类: {p['categories'][:2]}")

    # 如果不是 dry_run，实际入库
    if not dry_run and missing_high_quality:
        logger.info(f"\n开始入库 {len(missing_high_quality)} 篇论文...")

        async with async_session_maker() as db:
            added = 0
            for p in missing_high_quality:
                # 查找对应的 arxiv 结果
                for r in filtered_results:
                    arxiv_id = r.entry_id.split("/")[-1]
                    if "v" in arxiv_id:
                        arxiv_id = arxiv_id.rsplit("v", 1)[0]

                    if arxiv_id == p["arxiv_id"]:
                        paper = Paper(
                            arxiv_id=arxiv_id,
                            title=r.title.strip(),
                            authors=[a.name for a in r.authors],
                            abstract=r.summary.strip() if r.summary else None,
                            categories=list(r.categories),
                            publish_date=r.published,
                            pdf_url=r.pdf_url,
                            arxiv_url=r.entry_id,
                        )
                        db.add(paper)
                        added += 1
                        break

            await db.commit()
            logger.info(f"成功入库 {added} 篇论文")

            # 记录日志
            log = FetchLog(
                query=f"历史补抓: {date_from.strftime('%Y-%m-%d')} 到 {date_to.strftime('%Y-%m-%d')}",
                total_fetched=missing_total,
                new_papers=added,
                fetch_time=datetime.now(),
                status="success",
            )
            db.add(log)
            await db.commit()

    return missing_high_quality


async def reevaluate_by_date(date_str: str, dry_run: bool = True):
    """重新评估指定日期的论文。

    Args:
        date_str: 日期字符串 (YYYY-MM-DD)
        dry_run: 是否只检查
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")
    date_from = date.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
    date_to = date.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    return await check_date_range(date_from, date_to, dry_run=dry_run)


async def reevaluate_recent_days(days: int = 7, dry_run: bool = True):
    """重新评估最近 N 天的论文。

    Args:
        days: 天数
        dry_run: 是否只检查
    """
    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0)
    date_to = now

    return await check_date_range(date_from, date_to, dry_run=dry_run)


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="历史论文重评估")
    parser.add_argument(
        "--mode",
        choices=["recent", "date", "range"],
        default="recent",
        help="运行模式: recent=最近N天, date=指定日期, range=日期范围",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="最近天数 (recent 模式)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="指定日期 (date 模式, YYYY-MM-DD)",
    )
    parser.add_argument(
        "--date-from",
        type=str,
        help="开始日期 (range 模式)",
    )
    parser.add_argument(
        "--date-to",
        type=str,
        help="结束日期 (range 模式)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="实际入库（默认只检查）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("历史论文重评估脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    dry_run = not args.commit

    if args.mode == "recent":
        await reevaluate_recent_days(args.days, dry_run=dry_run)

    elif args.mode == "date":
        if not args.date:
            logger.error("--date 参数必须指定")
            return
        await reevaluate_by_date(args.date, dry_run=dry_run)

    elif args.mode == "range":
        if not args.date_from or not args.date_to:
            logger.error("--date-from 和 --date-to 参数必须指定")
            return
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, tzinfo=timezone.utc
        )
        date_to = datetime.strptime(args.date_to, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
        await check_date_range(date_from, date_to, dry_run=dry_run)

    logger.info("\n评估完成!")


if __name__ == "__main__":
    asyncio.run(main())