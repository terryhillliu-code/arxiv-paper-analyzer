#!/usr/bin/env python3
"""导出缺失 md 文件的论文到 Obsidian。

处理已分析但未导出到 Obsidian 的论文。
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.outputs.markdown_generator import MarkdownGenerator
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def export_papers(batch_size: int = 100):
    """导出缺失 md 文件的论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(Paper.md_output_path == None)
            .where(Paper.analysis_json != None)
            .limit(batch_size)
        )
        papers = result.scalars().all()

        logger.info(f"找到 {len(papers)} 篇待导出论文")

        if not papers:
            return

        generator = MarkdownGenerator()
        exported = 0
        failed = 0

        for paper in papers:
            try:
                # analysis_json 可能是字符串或已经是 dict
                if isinstance(paper.analysis_json, str):
                    analysis_json = json.loads(paper.analysis_json)
                else:
                    analysis_json = paper.analysis_json or {}

                export_result = generator._local_generate_paper_md(
                    paper_data={
                        "title": paper.title,
                        "authors": paper.authors or [],
                        "institutions": paper.institutions or [],
                        "publish_date": str(paper.publish_date) if paper.publish_date else "",
                        "arxiv_url": paper.arxiv_url or "",
                        "arxiv_id": paper.arxiv_id,
                        "tags": analysis_json.get("tags") or paper.tags,
                        "content_type": paper.content_type or "paper",
                        "paper_id": paper.id,
                        "has_analysis": True,
                        "rag_indexed": paper.rag_indexed,
                        "analysis_mode": paper.analysis_mode,
                        "pdf_local_path": paper.pdf_local_path,
                    },
                    analysis_json=analysis_json,
                    report=paper.analysis_report or "",
                    pdf_path=paper.pdf_local_path,
                )

                if export_result:
                    paper.md_output_path = export_result.get("md_path")
                    await db.commit()
                    exported += 1
                    logger.info(f"✅ 导出: {paper.arxiv_id}")
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"导出失败 {paper.arxiv_id}: {e}")
                failed += 1

        logger.info(f"完成: 导出 {exported}, 失败 {failed}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=100)

    args = parser.parse_args()
    asyncio.run(export_papers(args.batch))