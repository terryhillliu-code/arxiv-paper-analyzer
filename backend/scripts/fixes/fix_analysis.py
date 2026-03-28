"""修复已分析论文的 tags 和 outline 字段。

重新从 analysis_report 提取结构化数据。
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker
from app.models import Paper
from app.services.write_service import db_write_service
from sqlalchemy import select, func

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_papers_to_fix():
    """获取需要修复的论文列表"""
    async with async_session_maker() as db:
        # 获取所有已分析但 tags 或 outline 为空的论文
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(Paper.analysis_report != None)
            .where(Paper.analysis_report != "")
        )
        papers = result.scalars().all()

        # 过滤出需要修复的
        to_fix = []
        for paper in papers:
            aj = paper.analysis_json or {}
            tags = aj.get("tags", [])
            outline = aj.get("outline", [])
            if not tags or not outline:
                to_fix.append(paper)

        return to_fix


async def fix_paper(paper, ai_service, semaphore):
    """修复单篇论文"""
    async with semaphore:
        try:
            # 从已有报告提取结构化数据
            analysis_json = await ai_service._extract_analysis_json(paper.analysis_report)

            if analysis_json:
                # 提交到写入队列
                from app.services.write_service import WriteTask
                write_task = WriteTask(
                    paper_id=paper.id,
                    analysis_report=paper.analysis_report,
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
                    outline_count = len(analysis_json.get("outline", []))
                    logger.info(f"✅ 论文 {paper.id}: tags={tags}, outline={outline_count}章节")
                    return True
                else:
                    logger.error(f"❌ 论文 {paper.id} 写入失败")
                    return False
            else:
                logger.warning(f"⚠️ 论文 {paper.id} 提取失败")
                return False

        except Exception as e:
            logger.error(f"❌ 论文 {paper.id} 失败: {e}")
            return False


async def main():
    """主函数"""
    from app.services.ai_service import ai_service

    logger.info("=" * 60)
    logger.info("开始修复已分析论文的 tags 和 outline（并行加速版）")
    logger.info("=" * 60)

    # 启动写入服务
    await db_write_service.start()

    # 获取需要修复的论文
    papers = await get_papers_to_fix()
    logger.info(f"需要修复的论文数: {len(papers)}")

    if not papers:
        logger.info("没有需要修复的论文")
        return

    # 并发控制 - 提高到 6 个并发
    semaphore = asyncio.Semaphore(6)

    # 并行处理，每批 20 篇
    batch_size = 20
    success_count = 0
    fail_count = 0

    for i in range(0, len(papers), batch_size):
        batch = papers[i:i+batch_size]
        logger.info(f"\n处理批次 {i//batch_size + 1}/{(len(papers)+batch_size-1)//batch_size} ({len(batch)} 篇)")

        # 并行执行
        tasks = [fix_paper(p, ai_service, semaphore) for p in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        for r in results:
            if r is True:
                success_count += 1
            else:
                fail_count += 1

        logger.info(f"批次完成: 成功 {success_count}，失败 {fail_count}")

        # 写入队列状态
        stats = db_write_service.get_stats()
        logger.info(f"写入队列: {stats}")

    logger.info("\n" + "=" * 60)
    logger.info(f"修复完成: 成功 {success_count}，失败 {fail_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())