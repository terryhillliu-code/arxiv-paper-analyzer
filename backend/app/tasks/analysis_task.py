"""论文分析任务处理器。

处理深度分析任务，避免阻塞 API 响应。
使用写入队列服务避免数据库锁竞争。
"""

import logging
from typing import Dict, Any

from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from app.services.pdf_service import pdf_service, PDFService
from app.services.write_service import db_write_service, WriteTask
from app.tasks.task_queue import TaskQueue, TaskStatus
from app.outputs.markdown_generator import MarkdownGenerator
from sqlalchemy import select

logger = logging.getLogger(__name__)


class AnalysisTaskHandler:
    """分析任务处理器"""

    @staticmethod
    async def handle(task, queue: TaskQueue) -> Dict[str, Any]:
        """处理分析任务

        流程：
        1. 读取论文信息（当前 session）
        2. 下载/解析 PDF
        3. 调用 AI 生成分析
        4. 导出到 Obsidian
        5. 提交到写入队列（异步写入数据库）
        """
        payload = task.payload
        paper_id = payload.get("paper_id")
        use_mineru = payload.get("use_mineru", False)
        force_refresh = payload.get("force_refresh", False)

        if not paper_id:
            raise ValueError("缺少 paper_id")

        # ========== 阶段1: 读取论文信息 ==========
        async with async_session_maker() as db:
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

            # 提取论文信息（只读，不修改）
            paper_title = paper.title
            paper_authors = paper.authors or []
            paper_institutions = paper.institutions or []
            paper_publish_date = str(paper.publish_date) if paper.publish_date else ""
            paper_categories = paper.categories or []
            paper_arxiv_url = paper.arxiv_url or ""
            paper_pdf_url = paper.pdf_url or ""
            paper_arxiv_id = paper.arxiv_id
            paper_abstract = paper.abstract or ""
            paper_full_text = paper.full_text
            paper_pdf_local_path = paper.pdf_local_path
            paper_content_type = paper.content_type or "paper"
            paper_tags = paper.tags

        # ========== 阶段2: 获取内容 ==========
        queue.update_task(task.id, progress=10, message="准备 PDF...")

        content = paper_full_text
        content_metadata = {}

        # 如果没有全文，下载 PDF 并解析
        if not content and paper_pdf_url and paper_arxiv_id:
            try:
                pdf_path = await pdf_service.download_pdf(
                    pdf_url=paper_pdf_url,
                    arxiv_id=paper_arxiv_id,
                )
                paper_pdf_local_path = pdf_path

                queue.update_task(task.id, progress=20, message="解析 PDF...")

                if use_mineru:
                    logger.info(f"使用 MinerU 深度解析: {paper_arxiv_id}")
                    content, content_metadata = await pdf_service.extract_markdown(pdf_path)
                else:
                    logger.info(f"使用 PyMuPDF 快速提取: {paper_arxiv_id}")
                    content = await PDFService.get_paper_text(
                        pdf_url=paper_pdf_url,
                        arxiv_id=paper_arxiv_id,
                    )

            except Exception as e:
                logger.warning(f"PDF 解析失败，使用摘要: {e}")
                paper_pdf_local_path = None

        # 如果内容不足，使用摘要
        if not content or len(content) < 500:
            content = paper_abstract

        if not content:
            raise ValueError("论文缺少摘要和全文内容，无法分析")

        # ========== 阶段3: AI 分析（可并行） ==========
        queue.update_task(task.id, progress=30, message="生成深度分析报告...")

        analysis_result = await ai_service.generate_deep_analysis(
            title=paper_title,
            authors=paper_authors,
            institutions=paper_institutions,
            publish_date=paper_publish_date,
            categories=paper_categories,
            arxiv_url=paper_arxiv_url,
            pdf_url=paper_pdf_url,
            content=content,
        )

        queue.update_task(task.id, progress=80, message="保存分析结果...")

        analysis_report = analysis_result.get("report", "")
        analysis_json = analysis_result.get("analysis_json", {})

        logger.info(f"分析结果生成完成，准备保存")

        # ========== 阶段4: 导出到 Obsidian ==========
        export_result = None
        md_output_path = None

        try:
            generator = MarkdownGenerator()
            export_result = generator._local_generate_paper_md(
                paper_data={
                    "title": paper_title,
                    "authors": paper_authors,
                    "institutions": paper_institutions,
                    "publish_date": paper_publish_date,
                    "arxiv_url": paper_arxiv_url,
                    "arxiv_id": paper_arxiv_id,
                    "tags": analysis_json.get("tags") or paper_tags,
                    "content_type": paper_content_type,
                },
                analysis_json=analysis_json or {},
                report=analysis_report or "",
                pdf_path=paper_pdf_local_path,
            )
            md_output_path = export_result.get("md_path")
            logger.info(f"导出到 Obsidian 成功: {md_output_path}")
        except Exception as e:
            logger.warning(f"导出到 Obsidian 失败: {e}")

        # ========== 阶段5: 提交到写入队列 ==========
        write_task = WriteTask(
            paper_id=paper_id,
            analysis_report=analysis_report,
            analysis_json=analysis_json,
            tier=analysis_json.get("tier") if analysis_json else None,
            action_items=analysis_json.get("action_items") if analysis_json else None,
            knowledge_links=analysis_json.get("knowledge_links") if analysis_json else None,
            tags=analysis_json.get("tags") if analysis_json else None,
            md_output_path=md_output_path,
            has_analysis=True,
        )

        success = await db_write_service.submit(write_task)

        if not success:
            raise RuntimeError(f"数据库写入失败: paper_id={paper_id}")

        logger.info(f"✅ 论文 {paper_id} 分析完成")

        return {
            "paper_id": paper_id,
            "status": "completed",
            "has_analysis": True,
            "has_outline": bool(analysis_json.get("outline")),
            "has_contributions": bool(analysis_json.get("key_contributions")),
            "md_path": md_output_path,
        }


def register_analysis_handler(queue: TaskQueue):
    """注册分析任务处理器"""
    queue.register_handler("analysis", AnalysisTaskHandler.handle)