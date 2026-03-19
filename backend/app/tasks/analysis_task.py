"""论文分析任务处理器。

处理深度分析任务，避免阻塞 API 响应。
"""

import logging
from typing import Dict, Any

from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from app.services.pdf_service import pdf_service, PDFService
from app.tasks.task_queue import TaskQueue, TaskStatus
from app.outputs.markdown_generator import MarkdownGenerator
from sqlalchemy import select

logger = logging.getLogger(__name__)


class AnalysisTaskHandler:
    """分析任务处理器"""

    @staticmethod
    async def handle(task, queue: TaskQueue) -> Dict[str, Any]:
        """处理分析任务

        Args:
            task: 任务对象
            queue: 任务队列

        Returns:
            处理结果
        """
        payload = task.payload
        paper_id = payload.get("paper_id")
        use_mineru = payload.get("use_mineru", True)
        force_refresh = payload.get("force_refresh", False)

        if not paper_id:
            raise ValueError("缺少 paper_id")

        async with async_session_maker() as db:
            # 查询论文
            result = await db.execute(select(Paper).where(Paper.id == paper_id))
            paper = result.scalar_one_or_none()

            if not paper:
                raise ValueError(f"论文不存在: {paper_id}")

            # 如果已有分析且不强制刷新，跳过
            if paper.has_analysis and paper.analysis_report and not force_refresh:
                return {
                    "paper_id": paper_id,
                    "status": "skipped",
                    "message": "已有分析",
                }

            # 更新进度
            queue.update_task(task.id, progress=10, message="准备 PDF...")

            # 获取内容
            content = paper.full_text
            content_metadata = {}

            # 如果没有全文，下载 PDF 并解析
            if not content and paper.pdf_url and paper.arxiv_id:
                try:
                    pdf_path = await pdf_service.download_pdf(
                        pdf_url=paper.pdf_url,
                        arxiv_id=paper.arxiv_id,
                    )
                    paper.pdf_local_path = pdf_path

                    queue.update_task(task.id, progress=20, message="解析 PDF...")

                    if use_mineru:
                        logger.info(f"使用 MinerU 深度解析: {paper.arxiv_id}")
                        content, content_metadata = await pdf_service.extract_markdown(pdf_path)
                    else:
                        logger.info(f"使用 PyMuPDF 快速提取: {paper.arxiv_id}")
                        content = await PDFService.get_paper_text(
                            pdf_url=paper.pdf_url,
                            arxiv_id=paper.arxiv_id,
                        )

                    if content:
                        paper.full_text = content

                except Exception as e:
                    logger.warning(f"PDF 解析失败，使用摘要: {e}")

            # 如果内容不足，使用摘要
            if not content or len(content) < 500:
                content = paper.abstract or ""

            if not content:
                raise ValueError("论文缺少摘要和全文内容，无法分析")

            # 更新进度
            queue.update_task(task.id, progress=30, message="生成深度分析报告...")

            # 调用 AI 生成深度分析
            analysis_result = await ai_service.generate_deep_analysis(
                title=paper.title,
                authors=paper.authors or [],
                institutions=paper.institutions or [],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=paper.categories or [],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=content,
            )

            # 更新进度
            queue.update_task(task.id, progress=80, message="保存分析结果...")

            # 更新论文分析结果
            paper.analysis_report = analysis_result.get("report", "")
            analysis_json = analysis_result.get("analysis_json", {})
            paper.analysis_json = analysis_json
            paper.has_analysis = True

            # 保存新增字段
            if analysis_json:
                paper.tier = analysis_json.get("tier")
                paper.action_items = analysis_json.get("action_items")
                paper.knowledge_links = analysis_json.get("knowledge_links")
                if analysis_json.get("tags"):
                    paper.tags = analysis_json.get("tags")

            # 导出到 Obsidian
            export_result = None
            try:
                generator = MarkdownGenerator()
                export_result = generator.generate_paper_md(
                    paper_data={
                        "title": paper.title,
                        "authors": paper.authors,
                        "institutions": paper.institutions,
                        "publish_date": paper.publish_date,
                        "arxiv_url": paper.arxiv_url,
                        "arxiv_id": paper.arxiv_id,
                        "tags": paper.tags,
                        "content_type": paper.content_type or "paper",
                    },
                    analysis_json=analysis_json or {},
                    report=paper.analysis_report or "",
                    pdf_path=paper.pdf_local_path,
                )
                paper.md_output_path = export_result.get("md_path")
                logger.info(f"导出到 Obsidian 成功: {export_result}")
            except Exception as e:
                logger.warning(f"导出到 Obsidian 失败: {e}")

            await db.commit()

            return {
                "paper_id": paper_id,
                "status": "completed",
                "has_analysis": True,
                "has_outline": bool(analysis_json.get("outline")),
                "has_contributions": bool(analysis_json.get("key_contributions")),
                "md_path": export_result.get("md_path") if export_result else None,
            }


def register_analysis_handler(queue: TaskQueue):
    """注册分析任务处理器"""
    queue.register_handler("analysis", AnalysisTaskHandler.handle)