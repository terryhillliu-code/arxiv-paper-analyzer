#!/usr/bin/env python3
"""批量论文分析脚本。

将多个论文合并为一次 API 调用，提高效率。

用法:
    python scripts/batch_analysis.py --batch-size 5 --limit 100
"""

import argparse
import asyncio
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from app.outputs.markdown_generator import MarkdownGenerator
from sqlalchemy import select, update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "data" / "papers.db"


async def get_pending_papers(limit: int = 100) -> List[Dict[str, Any]]:
    """获取待分析的论文。"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == False)
            .where(Paper.abstract != None)
            .where(Paper.abstract != "")
            .limit(limit)
        )
        papers = result.scalars().all()

        return [
            {
                "paper_id": p.id,
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "content": p.abstract or p.full_text or "",
            }
            for p in papers
        ]


async def save_batch_results(results: List[Dict[str, Any]]):
    """保存批量分析结果。"""
    generator = MarkdownGenerator()

    for result in results:
        if result["status"] != "completed":
            continue

        paper_id = result["paper_id"]
        analysis_json = result["analysis_json"]

        # 获取论文信息
        async with async_session_maker() as db:
            paper_result = await db.execute(
                select(Paper).where(Paper.id == paper_id)
            )
            paper = paper_result.scalar_one_or_none()
            if not paper:
                continue

            # 生成 Markdown
            try:
                md_result = generator.generate_paper_md(
                    paper_data={
                        "title": paper.title,
                        "arxiv_id": paper.arxiv_id,
                        "arxiv_url": paper.arxiv_url,
                        "authors": paper.authors or [],
                        "institutions": paper.institutions or [],
                        "publish_date": str(paper.publish_date) if paper.publish_date else "",
                    },
                    analysis_json=analysis_json,
                    report="",  # 批量模式不生成详细报告
                )
                md_path = md_result.get("md_path")
            except Exception as e:
                logger.warning(f"Markdown 生成失败: {e}")
                md_path = None

            # 更新数据库
            await db.execute(
                update(Paper).where(Paper.id == paper_id).values(
                    has_analysis=True,
                    analysis_json=analysis_json,
                    tier=analysis_json.get("tier"),
                    tags=analysis_json.get("tags"),
                    md_output_path=md_path,
                )
            )
            await db.commit()

        logger.info(f"✅ 论文 {paper_id} 分析完成")


async def run_batch_analysis(batch_size: int = 5, limit: int = 100):
    """运行批量分析。"""
    logger.info(f"开始批量分析，批量大小: {batch_size}, 上限: {limit}")

    # 获取待分析论文
    papers = await get_pending_papers(limit)
    if not papers:
        logger.info("没有待分析的论文")
        return

    logger.info(f"获取到 {len(papers)} 篇待分析论文")

    # 分批处理
    total_success = 0
    total_failed = 0

    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        logger.info(f"处理批次 {i // batch_size + 1}，包含 {len(batch)} 篇论文")

        # 调用批量分析
        results = await ai_service.generate_batch_analysis(batch, batch_size=len(batch))

        # 统计结果
        success = sum(1 for r in results if r["status"] == "completed")
        failed = sum(1 for r in results if r["status"] == "failed")
        total_success += success
        total_failed += failed

        # 保存结果
        await save_batch_results(results)

        # 避免限流
        if i + batch_size < len(papers):
            await asyncio.sleep(2)

    logger.info(f"批量分析完成: 成功 {total_success}, 失败 {total_failed}")


def main():
    parser = argparse.ArgumentParser(description="批量论文分析")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="每批处理的论文数量",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最大处理论文数量",
    )

    args = parser.parse_args()

    asyncio.run(run_batch_analysis(batch_size=args.batch_size, limit=args.limit))


if __name__ == "__main__":
    main()