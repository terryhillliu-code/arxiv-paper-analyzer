"""
导出 BibTeX 工具
"""

from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolDefinition, ToolResult


class ExportToBibtexTool(BaseTool):
    """导出 BibTeX 工具"""

    name = "export_to_bibtex"
    description = "导出论文引用为 BibTeX 格式"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "论文 ID 列表",
                    },
                    "output_file": {
                        "type": "string",
                        "description": "输出文件路径（可选）",
                    },
                },
                "required": ["paper_ids"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """执行导出"""
        from sqlalchemy import select
        from app.models import Paper
        from app.exporters.bibtex import BibTeXExporter

        paper_ids = arguments.get("paper_ids", [])
        output_file = arguments.get("output_file")

        if not paper_ids:
            return ToolResult(
                success=False,
                error="请提供论文 ID 列表",
            )

        try:
            # 获取论文
            if db_session:
                result = await db_session.execute(
                    select(Paper).where(Paper.id.in_(paper_ids))
                )
                papers = result.scalars().all()
            else:
                from app.database import async_session_maker
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(Paper).where(Paper.id.in_(paper_ids))
                    )
                    papers = result.scalars().all()

            if not papers:
                return ToolResult(
                    success=False,
                    error="未找到任何论文",
                )

            # 准备论文数据
            papers_data = []
            for paper in papers:
                papers_data.append({
                    "id": paper.id,
                    "title": paper.title,
                    "arxiv_id": paper.arxiv_id,
                    "authors": paper.authors or [],
                    "publish_date": str(paper.publish_date) if paper.publish_date else None,
                    "primary_category": paper.categories[0] if paper.categories else None,
                    "pdf_url": paper.pdf_url,
                    "abstract": paper.abstract,
                })

            # 创建导出器
            exporter = BibTeXExporter()

            # 导出
            bibtex_content = exporter.export_papers(papers_data)

            # 写入文件（如果指定）
            if output_file:
                result = exporter.export_to_file(papers_data, output_file)
                if not result.success:
                    return ToolResult(
                        success=False,
                        error=f"写入文件失败: {result.error}",
                    )

                return ToolResult(
                    success=True,
                    data={
                        "content": bibtex_content,
                        "file_path": output_file,
                        "paper_count": len(papers),
                    },
                )

            return ToolResult(
                success=True,
                data={
                    "content": bibtex_content,
                    "paper_count": len(papers),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"导出失败: {str(e)}",
            )