"""批量论文分析任务处理器。

分层批量处理：
- 阶段1: 批量获取轻量信息（tier, tags, methodology）
- 阶段2: 并行生成详细分析（one_line_summary, key_contributions）
- 阶段3: 合并保存，失败隔离
"""

import asyncio
import logging
from typing import Dict, Any, List

from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from app.tasks.task_queue import TaskQueue, TaskStatus
from app.outputs.markdown_generator import MarkdownGenerator
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


class BatchAnalysisTaskHandler:
    """分层批量分析任务处理器"""

    @staticmethod
    async def handle(task, queue: TaskQueue) -> Dict[str, Any]:
        """处理批量分析任务

        流程：
        1. 批量获取轻量信息（tier, tags, methodology）
        2. 并行生成详细分析（one_line_summary, key_contributions）
        3. 合并保存，失败隔离
        """
        payload = task.payload
        paper_ids = payload.get("paper_ids", [])

        if not paper_ids:
            raise ValueError("缺少 paper_ids")

        batch_size = len(paper_ids)
        logger.info(f"开始分层批量分析: {batch_size} 篇论文")

        # ========== 阶段 1: 批量轻量分析 ==========
        queue.update_task(task.id, progress=10, message="阶段1: 批量获取分类信息...")

        papers = await BatchAnalysisTaskHandler._fetch_papers_batch(paper_ids)
        if not papers:
            return {
                "batch_size": batch_size,
                "success": 0,
                "failed": batch_size,
                "error": "无法获取论文信息",
            }

        # 批量获取轻量结果
        light_results = await ai_service.generate_batch_light(papers)

        queue.update_task(task.id, progress=30, message="阶段1 完成，开始阶段2...")

        # ========== 阶段 2: 并行详细分析 ==========
        detail_tasks = []
        for i, paper in enumerate(papers):
            light = light_results[i]
            detail_tasks.append(
                ai_service.generate_detail(
                    title=paper["title"],
                    abstract=paper["content"][:500],
                    tier=light.get("tier", "B"),
                    tags=light.get("tags", []),
                    methodology=light.get("methodology", ""),
                )
            )

        # 并行执行（最多 5 个并发）
        detail_results = await BatchAnalysisTaskHandler._parallel_gather(
            detail_tasks, max_concurrent=5
        )

        queue.update_task(task.id, progress=70, message="阶段2 完成，开始保存...")

        # ========== 阶段 3: 合并保存 ==========
        success_count = 0
        failed_count = 0

        for i, paper in enumerate(papers):
            light = light_results[i]
            detail = detail_results[i]

            # 检查详细分析是否成功
            if isinstance(detail, Exception):
                logger.error(f"论文 {paper['paper_id']} 详细分析失败: {detail}")
                queue.create_task("force_refresh", {"paper_id": paper["paper_id"]})
                failed_count += 1
                continue

            # 合并结果
            analysis_json = {
                **light,
                **detail,
            }

            # 验证关键字段
            if not analysis_json.get("one_line_summary"):
                logger.warning(f"论文 {paper['paper_id']} 缺少总结，创建重试任务")
                queue.create_task("force_refresh", {"paper_id": paper["paper_id"]})
                failed_count += 1
                continue

            # 保存
            try:
                await BatchAnalysisTaskHandler._save_paper(paper["paper_id"], analysis_json)
                success_count += 1
                logger.info(f"✅ 论文 {paper['paper_id']} 分析完成")
            except Exception as e:
                logger.error(f"保存论文 {paper['paper_id']} 失败: {e}")
                queue.create_task("force_refresh", {"paper_id": paper["paper_id"]})
                failed_count += 1

        logger.info(f"批量分析完成: 成功 {success_count}, 失败 {failed_count}")

        return {
            "batch_size": batch_size,
            "success": success_count,
            "failed": failed_count,
        }

    @staticmethod
    async def _fetch_papers_batch(paper_ids: List[int]) -> List[Dict[str, Any]]:
        """批量获取论文信息"""
        async with async_session_maker() as db:
            result = await db.execute(
                select(Paper).where(Paper.id.in_(paper_ids))
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

    @staticmethod
    async def _parallel_gather(
        tasks: List,
        max_concurrent: int = 5,
    ) -> List:
        """并行执行任务，控制并发数"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(coro):
            async with semaphore:
                try:
                    return await coro
                except Exception as e:
                    return e

        return await asyncio.gather(
            *[run_with_semaphore(t) for t in tasks],
            return_exceptions=True,
        )

    @staticmethod
    async def _save_paper(paper_id: int, analysis_json: Dict[str, Any]):
        """保存单篇论文分析结果（独立事务）"""
        async with async_session_maker() as db:
            # 获取论文
            result = await db.execute(
                select(Paper).where(Paper.id == paper_id)
            )
            paper = result.scalar_one_or_none()

            if not paper:
                raise ValueError(f"论文不存在: {paper_id}")

            # 生成 Markdown
            generator = MarkdownGenerator()
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


def register_batch_analysis_handler(queue: TaskQueue):
    """注册批量分析任务处理器"""
    queue.register_handler("batch_analysis", BatchAnalysisTaskHandler.handle)