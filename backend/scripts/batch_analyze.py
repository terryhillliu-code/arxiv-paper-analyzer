#!/usr/bin/env python
"""批量分析未处理的论文。

用法:
    python scripts/batch_analyze.py [--date YYYY-MM-DD] [--all] [--parallel N]
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)
logger = logging.getLogger(__name__)

from app.database import async_session_maker
from app.models import Paper
from sqlalchemy import select, func, update
from app.services.ai_service import ai_service
from app.outputs.markdown_generator import MarkdownGenerator


async def get_papers(date_str: str = None):
    """获取未分析的论文"""
    async with async_session_maker() as db:
        query = select(Paper).where(Paper.has_analysis == False)
        if date_str:
            query = query.where(func.date(Paper.publish_date) == date_str)
        query = query.order_by(Paper.publish_date.desc())
        result = await db.execute(query)
        return result.scalars().all()


async def get_date_stats():
    """获取未分析论文的日期分布"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(func.date(Paper.publish_date), func.count(Paper.id))
            .where(Paper.has_analysis == False)
            .group_by(func.date(Paper.publish_date))
            .order_by(func.date(Paper.publish_date).desc())
        )
        return [(str(row[0]), row[1]) for row in result]


async def direct_write(paper_id, report, analysis_json, md_path):
    """直接写入数据库"""
    async with async_session_maker() as db:
        await db.execute(
            update(Paper)
            .where(Paper.id == paper_id)
            .values(
                analysis_report=report,
                analysis_json=analysis_json,
                has_analysis=True,
                tier=analysis_json.get("tier"),
                tags=analysis_json.get("tags"),
                md_output_path=md_path
            )
        )
        await db.commit()


async def analyze_paper(paper, semaphore):
    """分析单篇论文"""
    async with semaphore:
        try:
            result = await ai_service.generate_deep_analysis(
                title=paper.title,
                authors=paper.authors or [],
                institutions=paper.institutions or [],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=paper.categories or [],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=paper.abstract or "",
                quick_mode=True,
            )

            report = result.get("report", "")
            analysis_json = result.get("analysis_json", {})

            generator = MarkdownGenerator()
            export_result = generator._local_generate_paper_md(
                paper_data={
                    "title": paper.title,
                    "authors": paper.authors or [],
                    "institutions": paper.institutions or [],
                    "publish_date": str(paper.publish_date) if paper.publish_date else "",
                    "arxiv_url": paper.arxiv_url or "",
                    "arxiv_id": paper.arxiv_id,
                    "tags": analysis_json.get("tags") or paper.tags,
                },
                analysis_json=analysis_json or {},
                report=report or "",
            )

            await direct_write(paper.id, report, analysis_json, export_result.get("md_path"))
            logger.info(f"✅ {paper.id} tier={analysis_json.get('tier')}")
            return True
        except Exception as e:
            logger.error(f"❌ {paper.id}: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(description="批量论文分析")
    parser.add_argument("--date", type=str, help="指定日期 (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="处理所有未分析论文")
    parser.add_argument("--parallel", type=int, default=6, help="并发数")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("批量论文分析")
    logger.info(f"并发数: {args.parallel}")
    logger.info("=" * 50)

    # 显示日期分布
    stats = await get_date_stats()
    print("\n未分析论文分布:")
    total = 0
    for date, count in stats:
        print(f"  {date}: {count} 篇")
        total += count
    print(f"  总计: {total} 篇\n")

    if not args.date and not args.all:
        print("使用 --date YYYY-MM-DD 处理指定日期")
        print("使用 --all 处理所有未分析论文")
        return

    # 获取论文
    papers = await get_papers(args.date)
    logger.info(f"待分析: {len(papers)} 篇")

    if not papers:
        return

    semaphore = asyncio.Semaphore(args.parallel)
    start = time.time()
    done = 0

    async def process(paper):
        nonlocal done
        ok = await analyze_paper(paper, semaphore)
        done += 1
        elapsed = time.time() - start
        rate = done / (elapsed / 60) if elapsed > 0 else 0
        remaining = (len(papers) - done) / rate if rate > 0 else 0
        logger.info(f"[{done}/{len(papers)}] {rate:.1f}/min | 剩余{remaining:.1f}分钟")
        return ok

    results = await asyncio.gather(*[process(p) for p in papers])
    logger.info(f"完成: OK={sum(1 for r in results if r)}/{len(papers)}")


if __name__ == "__main__":
    asyncio.run(main())