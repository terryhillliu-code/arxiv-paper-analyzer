"""
生成摘要工具（需要完全访问权限）
"""

from typing import Any, Dict, Optional

import httpx

from .base import BaseTool, ToolDefinition, ToolResult


class GenerateSummaryTool(BaseTool):
    """生成摘要工具"""

    name = "generate_summary"
    description = "为论文生成 AI 摘要（需要完全访问权限）"

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
                    "regenerate": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否重新生成（即使已有摘要）",
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
        """执行摘要生成"""
        from sqlalchemy import select
        from app.models import Paper
        from app.services.ai_service import ai_service

        paper_id = arguments.get("paper_id")
        regenerate = arguments.get("regenerate", False)

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

            # 检查是否已有摘要
            if paper.summary and not regenerate:
                return ToolResult(
                    success=True,
                    data={
                        "paper_id": paper_id,
                        "summary": paper.summary,
                        "tags": paper.tags,
                        "institutions": paper.institutions,
                        "existed": True,
                    },
                    metadata={"message": "使用已有摘要"},
                )

            # 生成摘要
            summary_result = await ai_service.generate_summary(
                title=paper.title,
                authors=paper.authors or [],
                abstract=paper.abstract or "",
                categories=paper.categories or [],
            )

            # 更新论文
            paper.summary = summary_result.get("summary", "")
            paper.tags = summary_result.get("tags", [])
            paper.institutions = summary_result.get("institutions", [])

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
                    "summary": paper.summary,
                    "tags": paper.tags,
                    "institutions": paper.institutions,
                    "existed": False,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"生成摘要失败: {str(e)}",
            )