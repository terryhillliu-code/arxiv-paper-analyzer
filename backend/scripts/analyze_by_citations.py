#!/usr/bin/env python3
"""按引用数优先分析高影响力论文。

用法:
    # 获取 S2 评分
    python scripts/analyze_by_citations.py --fetch-s2

    # 分析 Top 50 高引用论文
    python scripts/analyze_by_citations.py --analyze --top-n 50

    # 分析引用数 >= 100 的论文
    python scripts/analyze_by_citations.py --analyze --min-citations 100
"""

import argparse
import asyncio
import logging
import sys
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
from app.services.s2_service import get_s2_service
from app.outputs.markdown_generator import MarkdownGenerator


async def fetch_s2_scores(batch_size: int = 100):
    """获取论文的 Semantic Scholar 评分。"""
    s2 = get_s2_service()
    s2.REQUEST_DELAY = 0.5

    async with async_session_maker() as db:
        # 查询没有评分的论文
        result = await db.execute(
            select(Paper)
            .where(Paper.arxiv_id != None)
            .where(Paper.citation_count == None)
            .order_by(Paper.publish_date.desc())
        )
        papers = result.scalars().all()

        if not papers:
            logger.info("所有论文已有评分")
            return

        logger.info(f"需要获取评分: {len(papers)} 篇论文")

        total_updated = 0
        for i in range(0, len(papers), batch_size):
            batch = papers[i:i + batch_size]
            ids = [p.arxiv_id for p in batch if p.arxiv_id]

            logger.info(f"批次 {i // batch_size + 1}/{(len(papers) + batch_size - 1) // batch_size}")

            metrics = await s2.batch_get_metrics(ids)

            for p in batch:
                if p.arxiv_id in metrics:
                    m = metrics[p.arxiv_id]
                    p.citation_count = m['citation_count']
                    p.influential_citation_count = m['influential_citation_count']
                    p.s2_paper_id = m['s2_paper_id']
                    total_updated += 1

            await db.commit()
            logger.info(f"  已更新: {total_updated} 篇")

            if i + batch_size < len(papers):
                await asyncio.sleep(2)

        logger.info(f"完成! 共更新 {total_updated} 篇论文的评分")


async def analyze_by_citations(top_n: int = 0, min_citations: int = 0, parallel: int = 4, sort_by_date: bool = False):
    """按引用数优先分析论文。

    Args:
        top_n: 只分析 Top N 篇
        min_citations: 最小引用数阈值
        parallel: 并发数
        sort_by_date: 按日期排序（而非引用数）
    """
    async with async_session_maker() as db:
        if sort_by_date:
            # 按日期排序（最新论文优先）
            query = (
                select(Paper)
                .where(Paper.has_analysis == False)
                .order_by(Paper.publish_date.desc())
            )
        else:
            # 按引用数排序（高影响力论文优先）
            query = (
                select(Paper)
                .where(Paper.has_analysis == False)
                .order_by(Paper.citation_count.desc().nulls_last())
            )

        result = await db.execute(query)
        papers = result.scalars().all()

        # 应用引用数过滤
        if min_citations > 0:
            papers = [p for p in papers if (p.citation_count or 0) >= min_citations]

        # 应用 Top N 限制
        if top_n > 0:
            papers = papers[:top_n]

    if not papers:
        logger.info("没有需要分析的论文")
        return

    logger.info(f"准备分析 {len(papers)} 篇论文")

    # 显示 Top 5
    if papers[0].citation_count:
        logger.info("引用数 Top 5:")
        for i, p in enumerate(papers[:5], 1):
            logger.info(f"  {i}. [{p.citation_count or 'N/A':6}] {p.title[:45]}...")

    semaphore = asyncio.Semaphore(parallel)

    async def analyze_one(paper):
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
                    citation_count=paper.citation_count,
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
                        "tags": analysis_json.get("tags"),
                    },
                    analysis_json=analysis_json or {},
                    report=report or "",
                )

                async with async_session_maker() as db:
                    await db.execute(
                        update(Paper)
                        .where(Paper.id == paper.id)
                        .values(
                            analysis_report=report,
                            analysis_json=analysis_json,
                            has_analysis=True,
                            tier=analysis_json.get("tier"),
                            tags=analysis_json.get("tags"),
                            md_output_path=export_result.get("md_path"),
                        )
                    )
                    await db.commit()

                tier = analysis_json.get("tier", "B")
                citations = paper.citation_count or "N/A"
                logger.info(f"✅ [{citations:6}] tier={tier} {paper.title[:35]}...")
                return tier
            except Exception as e:
                logger.error(f"❌ {paper.id}: {e}")
                return None

    done = 0
    tier_a = 0

    async def process(paper):
        nonlocal done, tier_a
        tier = await analyze_one(paper)
        done += 1
        if tier == 'A':
            tier_a += 1
        logger.info(f"进度: {done}/{len(papers)} | Tier A: {tier_a}")
        return tier

    await asyncio.gather(*[process(p) for p in papers])
    logger.info(f"分析完成! Tier A: {tier_a}, 其他: {len(papers) - tier_a}")


async def show_stats():
    """显示论文统计。"""
    async with async_session_maker() as db:
        total = await db.execute(select(func.count(Paper.id)))
        total_count = total.scalar()

        with_s2 = await db.execute(select(func.count(Paper.id)).where(Paper.citation_count != None))
        s2_count = with_s2.scalar()

        unanalyzed = await db.execute(select(func.count(Paper.id)).where(Paper.has_analysis == False))
        unanalyzed_count = unanalyzed.scalar()

        high_cite = await db.execute(
            select(func.count(Paper.id))
            .where(Paper.has_analysis == False)
            .where(Paper.citation_count >= 100)
        )
        high_cite_count = high_cite.scalar()

        print(f"总论文数: {total_count}")
        print(f"有 S2 评分: {s2_count}")
        print(f"未分析: {unanalyzed_count}")
        print(f"高引用(>=100)未分析: {high_cite_count}")

        # Top 10
        result = await db.execute(
            select(Paper)
            .where(Paper.citation_count != None)
            .order_by(Paper.citation_count.desc())
            .limit(10)
        )
        papers = result.scalars().all()

        print("\n引用数 Top 10:")
        for i, p in enumerate(papers, 1):
            status = '✅' if p.has_analysis else '⏳'
            print(f"  {i}. [{p.citation_count:6}] {status} {p.title[:40]}...")


def main():
    parser = argparse.ArgumentParser(description="按引用数优先分析论文")
    parser.add_argument("--fetch-s2", action="store_true", help="获取 S2 评分")
    parser.add_argument("--analyze", action="store_true", help="执行分析")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    parser.add_argument("--top-n", type=int, default=0, help="分析 Top N 篇 (0=全部)")
    parser.add_argument("--min-citations", type=int, default=0, help="最小引用数")
    parser.add_argument("--parallel", type=int, default=4, help="并发数")
    parser.add_argument("--sort-by-date", action="store_true", help="按日期排序（默认按引用数）")
    args = parser.parse_args()

    if args.fetch_s2:
        asyncio.run(fetch_s2_scores())
    elif args.analyze:
        asyncio.run(analyze_by_citations(
            args.top_n, args.min_citations, args.parallel, args.sort_by_date
        ))
    elif args.stats:
        asyncio.run(show_stats())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()