#!/usr/bin/env python3
"""PDF下载任务处理器。

独立于分析任务，后台下载PDF用于：
1. 存档备用
2. 深度分析（可选）
3. RAG索引
"""

import logging
from typing import Any, Dict

from app.services.pdf_service import pdf_service
from app.database import async_session_maker
from app.models import Paper
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


class PDFDownloadTaskHandler:
    """PDF下载任务处理器"""

    @staticmethod
    async def handle(task, queue) -> Dict[str, Any]:
        """处理PDF下载任务

        Args:
            task: 任务对象
            queue: 任务队列

        Returns:
            处理结果
        """
        payload = task.payload
        paper_id = payload.get("paper_id")
        arxiv_id = payload.get("arxiv_id")
        pdf_url = payload.get("pdf_url")
        trigger_deep_analysis = payload.get("trigger_deep_analysis", False)

        if not paper_id or not pdf_url:
            raise ValueError("缺少 paper_id 或 pdf_url")

        logger.info(f"开始下载PDF: {arxiv_id}")

        try:
            # 1. 下载PDF
            pdf_path = await pdf_service.download_pdf(
                pdf_url=pdf_url,
                arxiv_id=arxiv_id,
            )
            logger.info(f"PDF下载完成: {pdf_path}")

            # 2. 更新数据库
            async with async_session_maker() as db:
                await db.execute(
                    update(Paper)
                    .where(Paper.id == paper_id)
                    .values(pdf_local_path=pdf_path)
                )
                await db.commit()
            logger.info(f"数据库已更新: paper_id={paper_id}")

            # 3. 可选：触发深度分析
            if trigger_deep_analysis:
                queue.create_task("deep_analysis", {
                    "paper_id": paper_id,
                    "quick_mode": False,
                })
                logger.info(f"已创建深度分析任务: paper_id={paper_id}")

            return {
                "status": "completed",
                "paper_id": paper_id,
                "pdf_path": pdf_path,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"PDF下载失败: {arxiv_id}, 错误: {e}")

            # 检查是否为不可重试的错误（文件过大）
            if "PDF_TOO_LARGE" in error_msg:
                logger.warning(f"PDF文件过大，跳过下载: {arxiv_id}")
                # 标记为completed，但记录原因
                return {
                    "status": "skipped",
                    "reason": "file_too_large",
                    "paper_id": paper_id,
                    "detail": error_msg,
                }

            # 其他错误抛出异常让任务队列标记为failed，这样才能重试
            raise Exception(f"PDF下载失败: {e}")


def register_pdf_download_handler(queue):
    """注册PDF下载任务处理器"""
    queue.register_handler("pdf_download", PDFDownloadTaskHandler.handle)