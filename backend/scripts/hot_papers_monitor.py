#!/usr/bin/env python3
"""热门论文监控脚本。

定期检查 ArXiv 上热门论文是否被收录，以及检查数据库中论文的引用数变化。
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, desc
from app.database import async_session_maker
from app.models import Paper
from app.services.semantic_scholar_service import s2_service
from app.services.paper_scorer import PaperScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_missing_hot_papers():
    """检查可能遗漏的热门论文。

    检查数据库中论文的引用数，找出高引用但 Tier 低的论文。
    """
    logger.info("=== 检查可能遗漏的热门论文 ===")

    async with async_session_maker() as db:
        # 获取最近 30 天的论文
        recent_date = datetime.now() - timedelta(days=30)
        result = await db.execute(
            select(Paper)
            .where(Paper.publish_date >= recent_date)
            .order_by(desc(Paper.id))
            .limit(100)  # 检查最近 100 篇
        )
        papers = result.scalars().all()

        logger.info(f"检查 {len(papers)} 篇最近论文...")

        upgraded = []
        for paper in papers:
            try:
                # 查询 Semantic Scholar
                info = await s2_service.get_paper_by_arxiv(paper.arxiv_id)

                if info and info.citation_count >= 10:
                    # 更新引用数
                    paper.citation_count = info.citation_count

                    # 如果引用数高但 Tier 低，建议升级
                    if info.citation_count >= 50 and paper.tier in ["B", "C", None]:
                        upgraded.append({
                            "arxiv_id": paper.arxiv_id,
                            "title": paper.title[:50],
                            "citation_count": info.citation_count,
                            "current_tier": paper.tier,
                            "suggested_tier": "A" if info.citation_count >= 100 else "B",
                        })

                    await asyncio.sleep(0.1)  # 避免限流

            except Exception as e:
                logger.warning(f"检查论文 {paper.arxiv_id} 失败: {e}")

        await db.commit()

    # 报告结果
    if upgraded:
        logger.info(f"\n发现 {len(upgraded)} 篇需要升级的论文:")
        for p in upgraded:
            logger.info(f"  [{p['citation_count']} 引用] {p['title']}...")
            logger.info(f"    当前: {p['current_tier']} -> 建议: {p['suggested_tier']}")

    return upgraded


async def check_recent_arxiv_hot():
    """检查 ArXiv 最近的热门论文。

    通过 Semantic Scholar 搜索最近高引用论文，检查是否在数据库中。
    """
    logger.info("\n=== 检查 ArXiv 近期热门论文 ===")

    # 搜索最近热门论文
    hot_papers = await s2_service.get_hot_papers(limit=50)

    if not hot_papers:
        logger.warning("未获取到热门论文")
        return

    async with async_session_maker() as db:
        missing = []
        for paper in hot_papers:
            if paper.citation_count < 20:
                continue

            # 检查是否在数据库中（通过标题匹配）
            result = await db.execute(
                select(Paper).where(Paper.title.ilike(f"%{paper.title[:30]}%"))
            )
            existing = result.scalar_one_or_none()

            if not existing:
                missing.append({
                    "title": paper.title,
                    "citation_count": paper.citation_count,
                    "year": paper.year,
                    "venue": paper.venue,
                })

    # 报告缺失的热门论文
    if missing:
        logger.info(f"\n发现 {len(missing)} 篇缺失的热门论文:")
        for p in missing[:10]:
            logger.info(f"  [{p['citation_count']} 引用] {p['title'][:50]}...")

    return missing


async def update_citation_counts():
    """更新数据库中论文的引用数。

    批量更新最近论文的引用数。
    """
    logger.info("\n=== 更新论文引用数 ===")

    async with async_session_maker() as db:
        # 获取最近 60 天无引用数的论文
        recent_date = datetime.now() - timedelta(days=60)
        result = await db.execute(
            select(Paper)
            .where(Paper.publish_date >= recent_date)
            .where(Paper.citation_count == None)
            .order_by(desc(Paper.id))
            .limit(200)
        )
        papers = result.scalars().all()

        logger.info(f"更新 {len(papers)} 篇论文的引用数...")

        updated = 0
        for paper in papers:
            try:
                info = await s2_service.get_paper_by_arxiv(paper.arxiv_id)
                if info:
                    paper.citation_count = info.citation_count
                    updated += 1

                await asyncio.sleep(0.1)

            except Exception as e:
                logger.warning(f"更新 {paper.arxiv_id} 失败: {e}")

        await db.commit()

    logger.info(f"成功更新 {updated} 篇论文的引用数")
    return updated


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="热门论文监控")
    parser.add_argument(
        "--mode",
        choices=["check-missing", "check-arxiv", "update-citations", "all"],
        default="all",
        help="运行模式",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("热门论文监控脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        if args.mode in ["check-missing", "all"]:
            await check_missing_hot_papers()

        if args.mode in ["check-arxiv", "all"]:
            await check_recent_arxiv_hot()

        if args.mode in ["update-citations", "all"]:
            await update_citation_counts()

        logger.info("\n监控完成!")

    finally:
        await s2_service.close()


if __name__ == "__main__":
    asyncio.run(main())