#!/usr/bin/env python3
"""批量导出已分析论文到 Obsidian。

将已完成分析但尚未导出的论文重新生成 Markdown 文件。
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.outputs.markdown_generator import MarkdownGenerator
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def batch_export(limit: int = 1000, tier_filter: str = None):
    """批量导出论文到 Obsidian。

    Args:
        limit: 最大导出数量
        tier_filter: 只导出特定 Tier 的论文 (A, B, C)
    """
    logger.info("=" * 60)
    logger.info("批量导出已分析论文到 Obsidian")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    generator = MarkdownGenerator()

    async with async_session_maker() as db:
        # 查询待导出论文
        query = select(Paper).where(
            Paper.has_analysis == True,
            Paper.md_output_path == None,
            Paper.analysis_json != None,
        ).order_by(Paper.tier.desc(), Paper.citation_count.desc().nulls_last())

        if tier_filter:
            query = query.where(Paper.tier == tier_filter)
            logger.info(f"仅导出 Tier {tier_filter} 论文")

        query = query.limit(limit)

        result = await db.execute(query)
        papers = result.scalars().all()

        logger.info(f"找到 {len(papers)} 篇待导出论文")

        if not papers:
            logger.info("没有需要导出的论文")
            return

        success_count = 0
        failed_count = 0

        for paper in papers:
            try:
                # 准备数据
                analysis_json = paper.analysis_json or {}
                paper_data = {
                    "title": paper.title,
                    "authors": paper.authors or [],
                    "institutions": paper.institutions or [],
                    "publish_date": str(paper.publish_date) if paper.publish_date else "",
                    "arxiv_url": paper.arxiv_url or "",
                    "arxiv_id": paper.arxiv_id,
                    "tags": analysis_json.get("tags") or paper.tags,
                    "content_type": paper.content_type or "paper",
                    # ⭐ v1.1 联动字段
                    "paper_id": paper.id,
                    "has_analysis": paper.has_analysis,
                    "rag_indexed": paper.rag_indexed,
                    "analysis_mode": paper.analysis_mode or "",
                    "pdf_local_path": paper.pdf_local_path,
                }

                # 生成 Markdown
                export_result = generator._local_generate_paper_md(
                    paper_data=paper_data,
                    analysis_json=analysis_json,
                    report=paper.analysis_report or "",
                    pdf_path=paper.pdf_local_path,
                )

                md_path = export_result.get("md_path")

                if md_path and os.path.exists(md_path):
                    # 更新数据库
                    paper.md_output_path = md_path
                    await db.commit()
                    success_count += 1

                    if success_count % 50 == 0:
                        logger.info(f"进度: {success_count}/{len(papers)} 已完成")
                else:
                    failed_count += 1
                    logger.warning(f"导出失败 {paper.id}: {paper.title[:50]}")

            except Exception as e:
                failed_count += 1
                logger.error(f"导出异常 {paper.id}: {e}")

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"导出完成: 成功 {success_count}, 失败 {failed_count}")
        logger.info("=" * 60)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="批量导出论文到 Obsidian")
    parser.add_argument("--limit", type=int, default=1000, help="最大导出数量")
    parser.add_argument("--tier", type=str, default=None, help="只导出特定 Tier")
    args = parser.parse_args()

    await batch_export(limit=args.limit, tier_filter=args.tier)


if __name__ == "__main__":
    asyncio.run(main())