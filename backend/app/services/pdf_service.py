"""PDF 下载与文本提取服务模块。

提供 PDF 文件下载和文本内容提取功能。
"""

import asyncio
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class PDFService:
    """PDF 处理服务。

    提供 PDF 下载和文本提取功能。
    """

    @staticmethod
    async def download_pdf(pdf_url: str, arxiv_id: str) -> str:
        """下载 PDF 文件到本地。

        Args:
            pdf_url: PDF 下载链接
            arxiv_id: arXiv 论文 ID

        Returns:
            本地 PDF 文件路径

        Raises:
            Exception: 下载失败时抛出异常
        """
        settings = get_settings()

        # 确保存储目录存在
        storage_path = Path(settings.pdf_storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        # 将 arxiv_id 中的 / 和 : 替换为 _ 作为文件名
        safe_id = arxiv_id.replace("/", "_").replace(":", "_")
        filename = f"{safe_id}.pdf"
        pdf_path = storage_path / filename

        # 如果本地文件已存在，直接返回路径
        if pdf_path.exists():
            logger.info(f"PDF 已存在: {pdf_path}")
            return str(pdf_path)

        try:
            # 使用 httpx 下载 PDF
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                logger.info(f"开始下载 PDF: {pdf_url}")
                response = await client.get(pdf_url)
                response.raise_for_status()

                # 保存到本地
                pdf_path.write_bytes(response.content)
                logger.info(f"PDF 下载成功: {pdf_path}")

                return str(pdf_path)

        except Exception as e:
            logger.error(f"下载 PDF 失败: {pdf_url}, 错误: {e}", exc_info=True)
            raise

    @staticmethod
    def extract_text(pdf_path: str, max_pages: int = 30) -> str:
        """从 PDF 文件中提取文本内容。

        Args:
            pdf_path: PDF 文件路径
            max_pages: 最大提取页数，默认 30 页

        Returns:
            提取的文本内容
        """
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            page_count = min(len(doc), max_pages)

            # 遍历页面提取文本
            for page_num in range(page_count):
                page = doc[page_num]
                text = page.get_text()

                if text.strip():
                    text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

            doc.close()

            # 合并所有文本
            full_text = "\n\n".join(text_parts)

            # 清理文本
            full_text = PDFService._clean_text(full_text)

            logger.info(f"文本提取成功: {pdf_path}, 共 {page_count} 页")
            return full_text

        except Exception as e:
            logger.error(f"提取文本失败: {pdf_path}, 错误: {e}", exc_info=True)
            return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理提取的文本。

        清理操作：
        - 移除过多空行（4个以上换行合并为3个）
        - 移除孤立的页码行
        - 合并被换行截断的英文单词

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        if not text:
            return text

        # 移除过多空行（4个以上换行合并为3个）
        text = re.sub(r"\n{4,}", "\n\n\n", text)

        # 移除孤立的页码行（单独一行的数字）
        text = re.sub(r"\n\d+\s*\n", "\n", text)

        # 移除页眉页脚式的页码（如 "Page 123" 或 "- 123 -"）
        text = re.sub(r"\n[-–—]?\s*\d+\s*[-–—]?\s*\n", "\n", text)
        text = re.sub(r"\nPage\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)

        # 合并被换行截断的英文单词（如 "algo-\nrithm" → "algorithm"）
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

        # 移除行首行尾多余空白
        lines = text.split("\n")
        lines = [line.strip() for line in lines]
        text = "\n".join(lines)

        # 再次处理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    async def get_paper_text(pdf_url: str, arxiv_id: str) -> str:
        """获取论文文本内容的完整流程。

        流程：下载 PDF → 提取文本 → 返回内容

        Args:
            pdf_url: PDF 下载链接
            arxiv_id: arXiv 论文 ID

        Returns:
            论文文本内容，失败时返回空字符串
        """
        try:
            # 下载 PDF
            pdf_path = await PDFService.download_pdf(pdf_url, arxiv_id)

            # 在线程中提取文本（避免阻塞事件循环）
            text = await asyncio.to_thread(PDFService.extract_text, pdf_path)

            return text

        except Exception as e:
            logger.error(f"获取论文文本失败: {arxiv_id}, 错误: {e}", exc_info=True)
            return ""