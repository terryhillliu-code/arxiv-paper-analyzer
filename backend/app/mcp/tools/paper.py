"""
获取论文详情工具
"""

from typing import Any, Dict, Optional

from .base import BaseTool, ToolDefinition, ToolResult


class GetPaperTool(BaseTool):
    """获取论文详情工具"""

    name = "get_paper"
    description = "获取论文详情，包括摘要、分析结果、相关论文"

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
                    "include_analysis": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否包含分析结果",
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
        """执行查询"""
        from sqlalchemy import select
        from app.models import Paper

        paper_id = arguments.get("paper_id")
        include_analysis = arguments.get("include_analysis", True)

        try:
            # 构建查询
            query = select(Paper).where(Paper.id == paper_id)

            # 执行查询
            if db_session:
                result = await db_session.execute(query)
                paper = result.scalar_one_or_none()
            else:
                from app.database import async_session_maker
                async with async_session_maker() as session:
                    result = await session.execute(query)
                    paper = result.scalar_one_or_none()

            if not paper:
                return ToolResult(
                    success=False,
                    error=f"论文不存在: ID={paper_id}",
                )

            # 格式化结果
            paper_data = self._format_paper(paper, include_analysis)

            return ToolResult(
                success=True,
                data=paper_data,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"获取论文失败: {str(e)}",
            )

    def _format_paper(self, paper: Any, include_analysis: bool = True) -> Dict[str, Any]:
        """格式化论文数据"""
        data = {
            "id": paper.id,
            "title": paper.title,
            "arxiv_id": paper.arxiv_id,
            "authors": paper.authors or [],
            "publish_date": str(paper.publish_date) if paper.publish_date else None,
            "categories": paper.categories or [],
            "tags": paper.tags or [],
            "tier": paper.tier,
            "abstract": paper.abstract,
            "arxiv_url": f"https://arxiv.org/abs/{paper.arxiv_id}" if paper.arxiv_id else None,
            "pdf_url": paper.pdf_url or f"https://arxiv.org/pdf/{paper.arxiv_id}" if paper.arxiv_id else None,
        }

        if include_analysis:
            data.update({
                "summary": paper.summary,
                "key_contributions": paper.key_contributions or [],
                "methodology": paper.methodology,
                "knowledge_links": paper.knowledge_links or [],
                "action_items": paper.action_items or [],
                "institutions": paper.institutions or [],
                "analysis_report": paper.analysis_report,
                "popularity_score": paper.popularity_score,
                "md_output_path": paper.md_output_path,
            })

        return data