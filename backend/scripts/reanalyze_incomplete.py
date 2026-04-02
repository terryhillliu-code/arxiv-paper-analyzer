#!/usr/bin/env python3
"""重新分析不完整的论文。

对JSON几乎空的论文重新生成深度分析。
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def reanalyze_papers(start_id: int = 0, end_id: int = 99999):
    """重新分析指定ID范围的论文"""
    async with async_session_maker() as db:
        # 查找JSON几乎空的论文
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(Paper.id >= start_id)
            .where(Paper.id <= end_id)
            .order_by(Paper.id)
        )
        all_papers = result.scalars().all()

        # 筛选JSON不完整的（小于500字节说明缺少outline等关键字段）
        papers = [p for p in all_papers if not p.analysis_json or len(p.analysis_json) < 500]

        total = len(papers)
        logger.info(f"找到 {total} 篇需要重新分析的论文 (ID {start_id}-{end_id})")

        done = 0
        failed = 0

        for i, paper in enumerate(papers):
            try:
                if not paper.abstract or len(paper.abstract) < 100:
                    logger.warning(f"ID={paper.id}: 摘要太短，跳过")
                    continue

                logger.info(f"处理 {i+1}/{total}: ID={paper.id}")

                # 调用深度分析（快速模式）
                result = await ai_service.generate_deep_analysis(
                    title=paper.title,
                    authors=paper.authors or [],
                    institutions=paper.institutions or [],
                    publish_date=str(paper.publish_date) if paper.publish_date else "",
                    categories=paper.categories or [],
                    arxiv_url=paper.arxiv_url or "",
                    pdf_url=paper.pdf_url or "",
                    content=paper.abstract,  # 使用摘要
                    quick_mode=True,
                    citation_count=paper.citation_count,
                )

                # 更新字段
                paper.analysis_report = result.get("report", "")
                paper.analysis_json = result.get("analysis_json", {})

                if result.get("analysis_json"):
                    aj = result["analysis_json"]
                    if aj.get("tier"):
                        paper.tier = aj["tier"]
                    if aj.get("one_line_summary"):
                        paper.summary = aj["one_line_summary"]
                    if aj.get("tags"):
                        paper.tags = aj["tags"]
                    if aj.get("action_items"):
                        paper.action_items = aj["action_items"]
                    if aj.get("knowledge_links"):
                        paper.knowledge_links = aj["knowledge_links"]

                await db.commit()
                done += 1

                # 避免API限流
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"失败 ID={paper.id}: {e}")
                failed += 1
                await asyncio.sleep(2)

        logger.info(f"完成: 成功 {done}, 失败 {failed}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=99999)
    args = parser.parse_args()

    asyncio.run(reanalyze_papers(args.start, args.end))