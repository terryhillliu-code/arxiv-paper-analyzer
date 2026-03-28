"""修复剩余 14 篇无 tags 的论文。"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker
from app.models import Paper
from app.services.write_service import db_write_service
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_papers_to_fix():
    """获取需要修复的论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(Paper.analysis_json.isnot(None))
        )
        papers = result.scalars().all()

        to_fix = []
        for paper in papers:
            aj = paper.analysis_json or {}
            tags = aj.get("tags", [])
            if not tags:
                to_fix.append(paper)
        return to_fix


async def fix_paper(paper, ai_service):
    """修复单篇论文"""
    try:
        report_len = len(paper.analysis_report) if paper.analysis_report else 0

        # 如果报告太短，需要重新生成
        if report_len < 1000:
            logger.info(f"论文 {paper.id} 报告不完整({report_len}字符)，重新生成...")
            # 从摘要生成简化报告
            abstract = paper.abstract or ""
            title = paper.title or ""

            # 使用摘要作为内容生成报告
            from app.services.ai_service import AIService
            result = await ai_service.generate_deep_analysis(
                title=title,
                authors=[],
                institutions=[],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=[],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=f"标题: {title}\n\n摘要: {abstract}",
            )

            analysis_report = result.get("report", "")
            analysis_json = result.get("analysis_json", {})
        else:
            # 报告完整，只重新提取 JSON
            logger.info(f"论文 {paper.id} 重新提取 JSON...")
            analysis_json = await ai_service._extract_analysis_json(paper.analysis_report)
            analysis_report = paper.analysis_report

        if analysis_json and analysis_json.get("tags"):
            from app.services.write_service import WriteTask
            write_task = WriteTask(
                paper_id=paper.id,
                analysis_report=analysis_report,
                analysis_json=analysis_json,
                tier=analysis_json.get("tier"),
                action_items=analysis_json.get("action_items"),
                knowledge_links=analysis_json.get("knowledge_links"),
                tags=analysis_json.get("tags"),
                has_analysis=True,
            )

            success = await db_write_service.submit(write_task)
            if success:
                tags = analysis_json.get("tags", [])
                logger.info(f"✅ 论文 {paper.id}: tags={tags}")
                return True

        logger.warning(f"⚠️ 论文 {paper.id} 修复失败")
        return False

    except Exception as e:
        logger.error(f"❌ 论文 {paper.id} 错误: {e}")
        return False


async def main():
    from app.services.ai_service import ai_service

    logger.info("=" * 50)
    logger.info("修复剩余无 tags 论文")
    logger.info("=" * 50)

    await db_write_service.start()

    papers = await get_papers_to_fix()
    logger.info(f"需要修复: {len(papers)} 篇")

    if not papers:
        logger.info("无需修复")
        return

    success = 0
    fail = 0

    for paper in papers:
        result = await fix_paper(paper, ai_service)
        if result:
            success += 1
        else:
            fail += 1

    logger.info("=" * 50)
    logger.info(f"完成: 成功 {success}, 失败 {fail}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())