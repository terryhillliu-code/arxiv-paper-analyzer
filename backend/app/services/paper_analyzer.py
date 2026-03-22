"""论文分析聚合服务。

提供高层级的分析流水线，整合 PDF 提取、AI 分析、Markdown 生成和数据库写入。
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from app.services.ai_service import ai_service
from app.services.pdf_service import PDFService
from app.services.write_service import db_write_service, WriteTask
from app.outputs.markdown_generator import MarkdownGenerator

logger = logging.getLogger(__name__)


class PaperAnalyzer:
    """论文分析聚合器。"""

    def __init__(self):
        self.generator = MarkdownGenerator()

    async def analyze_paper(
        self, 
        paper: Any, 
        semaphore: asyncio.Semaphore, 
        quick_mode: bool = True
    ) -> bool:
        """分析单篇论文并保存结果。

        Args:
            paper: Paper 模型对象
            semaphore: 控制并发的信号量
            quick_mode: 是否为快速模式（仅分析摘要）

        Returns:
            是否分析成功
        """
        async with semaphore:
            try:
                # 1. 准备内容
                content = paper.abstract or ""
                if not quick_mode:
                    if not paper.pdf_url:
                        logger.warning(f"论文 {paper.id} 无 PDF URL，跳过完整分析")
                        return False
                    
                    # 下载并提取 PDF 文本
                    pdf_text = await PDFService.get_paper_text(paper.pdf_url, paper.arxiv_id or str(paper.id))
                    if pdf_text:
                        content = pdf_text
                    else:
                        logger.warning(f"论文 {paper.id} PDF 提取失败，回退到摘要分析")
                
                # 2. 调用 AI 分析
                result = await ai_service.generate_deep_analysis(
                    title=paper.title,
                    authors=paper.authors or [],
                    institutions=paper.institutions or [],
                    publish_date=str(paper.publish_date) if paper.publish_date else "",
                    categories=paper.categories or [],
                    arxiv_url=paper.arxiv_url or "",
                    pdf_url=paper.pdf_url or "",
                    content=content,
                    quick_mode=quick_mode,
                    citation_count=paper.citation_count,
                )

                report = result.get("report", "")
                analysis_json = result.get("analysis_json", {})
                
                if not report or not analysis_json:
                    logger.error(f"分析失败 {paper.id}: AI 未返回有效结果")
                    return False

                # 3. 生成 Markdown
                export_result = self.generator._local_generate_paper_md(
                    paper_data={
                        "title": paper.title,
                        "authors": paper.authors or [],
                        "institutions": paper.institutions or [],
                        "publish_date": str(paper.publish_date) if paper.publish_date else "",
                        "arxiv_url": paper.arxiv_url or "",
                        "arxiv_id": paper.arxiv_id,
                        "tags": analysis_json.get("tags"),
                    },
                    analysis_json=analysis_json,
                    report=report,
                )

                # 4. 提交数据库写入
                task = WriteTask(
                    paper_id=paper.id,
                    analysis_report=report,
                    analysis_json=analysis_json,
                    tier=analysis_json.get("tier"),
                    tags=analysis_json.get("tags"),
                    md_output_path=export_result.get("md_path"),
                    full_analysis=not quick_mode
                )
                
                success = await db_write_service.submit(task)
                
                if success and not quick_mode:
                    # 额外更新 full_analysis 标记
                    # 由于 db_write_service.submit 只处理 WriteTask 中的字段，
                    # 我们可能需要在这里手动更新或确保 WriteTask 包含此字段。
                    # 检查 models.py 和 write_service.py，我们可以直接在 database 会话中更新。
                    pass

                logger.info(f"✅ {'快速' if quick_mode else '完整'}分析完成: {paper.id} tier={analysis_json.get('tier')}")
                return True

            except Exception as e:
                logger.error(f"❌ 分析异常 {paper.id}: {e}", exc_info=True)
                return False


# 全局实例
paper_analyzer = PaperAnalyzer()
