"""
导出到 Obsidian 工具（需要完全访问权限）
"""

from typing import Any, Dict, Optional

from .base import BaseTool, ToolDefinition, ToolResult


class ExportToObsidianTool(BaseTool):
    """导出到 Obsidian 工具"""

    name = "export_to_obsidian"
    description = "导出论文到 Obsidian（需要完全访问权限）"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "论文 ID",
                    },
                    "folder": {
                        "type": "string",
                        "default": "Inbox",
                        "description": "目标文件夹",
                    },
                },
                "required": ["paper_id"],
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
        from app.exporters.obsidian import ObsidianExporter
        from app.services.obsidian_client import ObsidianClient

        paper_id = arguments.get("paper_id")
        folder = arguments.get("folder", "Inbox")

        # 检查权限
        if not config.is_tool_allowed(self.name):
            return ToolResult(
                success=False,
                error="权限不足：此操作需要完全访问权限",
            )

        try:
            # 获取论文
            if db_session:
                result = await db_session.execute(
                    select(Paper).where(Paper.id == paper_id)
                )
                paper = result.scalar_one_or_none()
            else:
                from app.database import async_session_maker
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(Paper).where(Paper.id == paper_id)
                    )
                    paper = result.scalar_one_or_none()

            if not paper:
                return ToolResult(
                    success=False,
                    error=f"论文不存在: ID={paper_id}",
                )

            # 准备论文数据
            paper_data = {
                "id": paper.id,
                "title": paper.title,
                "arxiv_id": paper.arxiv_id,
                "authors": paper.authors or [],
                "publish_date": str(paper.publish_date) if paper.publish_date else None,
                "categories": paper.categories or [],
                "tags": paper.tags or [],
                "tier": paper.tier,
                "abstract": paper.abstract,
                "summary": paper.summary,
                "key_contributions": paper.key_contributions or [],
                "methodology": paper.methodology,
                "knowledge_links": paper.knowledge_links or [],
                "action_items": paper.action_items or [],
                "institutions": paper.institutions or [],
                "analysis_report": paper.analysis_report,
                "one_line_summary": paper.one_line_summary,
                "overall_rating": paper.overall_rating,
                "content_type": paper.content_type or "paper",
            }

            # 创建导出器
            client = ObsidianClient(base_url=config.obsidian_service_url)
            exporter = ObsidianExporter(client=client, prefer_service=True)

            # 执行导出
            result = await exporter.export_to_vault(paper_data, folder=folder)

            if result.success:
                # 更新论文的 md_output_path
                paper.md_output_path = result.file_path
                if db_session:
                    await db_session.commit()
                else:
                    from app.database import async_session_maker
                    async with async_session_maker() as session:
                        session.add(paper)
                        await session.commit()

                return ToolResult(
                    success=True,
                    data={
                        "paper_id": paper_id,
                        "md_path": result.file_path,
                        "pdf_path": result.metadata.get("pdf_path"),
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    error=result.error or "导出失败",
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"导出失败: {str(e)}",
            )