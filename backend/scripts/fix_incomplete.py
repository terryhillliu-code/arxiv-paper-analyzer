#!/usr/bin/env python3
"""修复不完整的分析结果。

重新处理缺少summary或tags的论文。
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


async def fix_incomplete_analysis():
    """修复不完整的分析"""
    async with async_session_maker() as db:
        # 查找不完整的论文
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(
                (Paper.summary == None) |
                (Paper.summary == '') |
                (Paper.tags == None)
            )
            .order_by(Paper.id)
        )
        papers = result.scalars().all()

        total = len(papers)
        logger.info(f"找到 {total} 篇需要修复的论文")

        fixed = 0
        failed = 0

        for i, paper in enumerate(papers):
            try:
                # 检查是否有摘要
                if not paper.abstract or len(paper.abstract) < 100:
                    logger.warning(f"ID={paper.id}: 摘要太短，跳过")
                    continue

                # 重新生成摘要信息
                logger.info(f"处理 {i+1}/{total}: ID={paper.id}")

                summary_result = await ai_service.generate_summary(
                    title=paper.title,
                    authors=paper.authors or [],
                    abstract=paper.abstract,
                    categories=paper.categories or [],
                )

                # 更新字段
                if summary_result.get("summary"):
                    paper.summary = summary_result["summary"]
                if summary_result.get("tags"):
                    paper.tags = summary_result["tags"]
                if summary_result.get("institutions"):
                    paper.institutions = summary_result["institutions"]

                await db.commit()
                fixed += 1

                # 避免API限流
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"修复失败 ID={paper.id}: {e}")
                failed += 1

        logger.info(f"修复完成: 成功 {fixed}, 失败 {failed}")


if __name__ == "__main__":
    asyncio.run(fix_incomplete_analysis())