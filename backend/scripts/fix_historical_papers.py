#!/usr/bin/env python3
"""
修复历史论文的分析数据。

历史导入的论文有 Tier 和 md_output_path，但缺少：
- analysis_json
- analysis_report
- abstract

这个脚本会：
1. 从 arXiv API 获取摘要
2. 运行快速分析
3. 更新数据库
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from app.database import async_session_maker
from app.models import Paper
from app.services.arxiv_service import ArxivService
from app.services.ai_service import ai_service
from app.tasks.task_queue import TaskQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def fetch_abstract(arxiv_id: str) -> str | None:
    """从 arXiv 获取论文摘要"""
    try:
        papers = await ArxivService.fetch_by_ids([arxiv_id])
        if papers and len(papers) > 0:
            return papers[0].get("abstract")
    except Exception as e:
        logger.warning(f"获取摘要失败 {arxiv_id}: {e}")
    return None


async def analyze_paper(paper: Paper) -> dict | None:
    """分析单篇论文"""
    if not paper.abstract:
        # 尝试获取摘要
        abstract = await fetch_abstract(paper.arxiv_id)
        if not abstract:
            logger.warning(f"无法获取摘要: {paper.arxiv_id}")
            return None
        paper.abstract = abstract

    try:
        # 运行快速分析
        result = await ai_service.generate_deep_analysis(
            title=paper.title,
            authors=paper.authors or [],
            institutions=paper.institutions or [],
            publish_date=str(paper.publish_date) if paper.publish_date else "",
            categories=paper.categories or [],
            arxiv_url=paper.arxiv_url or "",
            pdf_url=paper.pdf_url or "",
            content=paper.abstract,
            quick_mode=True,
        )
        return result
    except Exception as e:
        logger.error(f"分析失败 {paper.arxiv_id}: {e}")
        return None


async def fix_historical_papers(batch_size: int = 50, dry_run: bool = False):
    """修复历史论文

    Args:
        batch_size: 每批处理数量
        dry_run: 仅检查不执行
    """
    async with async_session_maker() as db:
        # 查询缺少分析的历史论文
        result = await db.execute(
            select(Paper)
            .where(Paper.analysis_mode == "historical")
            .where(Paper.analysis_json == None)
            .limit(batch_size)
        )
        papers = result.scalars().all()

        logger.info(f"找到 {len(papers)} 篇待修复论文")

        if dry_run:
            for paper in papers[:5]:
                logger.info(f"  [{paper.arxiv_id}] {paper.title[:50]}...")
            return

        fixed = 0
        failed = 0

        for paper in papers:
            logger.info(f"处理: {paper.arxiv_id}")

            # 分析论文
            result = await analyze_paper(paper)

            if result:
                # 更新数据库
                paper.analysis_json = result.get("analysis_json")
                paper.analysis_report = result.get("report")
                paper.one_line_summary = result.get("analysis_json", {}).get("one_line_summary")
                paper.tags = result.get("analysis_json", {}).get("tags")
                paper.tier = result.get("analysis_json", {}).get("tier", "B")
                paper.has_analysis = True

                await db.commit()
                fixed += 1
                logger.info(f"✅ 修复完成: {paper.arxiv_id}")
            else:
                failed += 1

            # 避免过快请求
            await asyncio.sleep(2)

        logger.info(f"修复完成: 成功 {fixed}, 失败 {failed}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=50, help="每批处理数量")
    parser.add_argument("--dry-run", action="store_true", help="仅检查不执行")

    args = parser.parse_args()

    asyncio.run(fix_historical_papers(args.batch, args.dry_run))