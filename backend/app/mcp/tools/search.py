"""
搜索论文工具
"""

from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolDefinition, ToolResult


class SearchPapersTool(BaseTool):
    """搜索论文工具"""

    name = "search_papers"
    description = "搜索论文，支持关键词、分类、标签、日期范围筛选"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "分类过滤，如 ['cs.AI', 'cs.CL']",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签过滤",
                    },
                    "date_from": {
                        "type": "string",
                        "format": "date",
                        "description": "起始日期 (YYYY-MM-DD)",
                    },
                    "date_to": {
                        "type": "string",
                        "format": "date",
                        "description": "结束日期 (YYYY-MM-DD)",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["newest", "popularity"],
                        "description": "排序方式",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "返回数量限制",
                    },
                },
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """执行搜索"""
        from sqlalchemy import select, or_
        from app.models import Paper

        try:
            # 构建查询
            query = select(Paper)

            # 关键词搜索
            if arguments.get("query"):
                keyword = f"%{arguments['query']}%"
                query = query.where(
                    or_(
                        Paper.title.ilike(keyword),
                        Paper.abstract.ilike(keyword),
                        Paper.summary.ilike(keyword),
                    )
                )

            # 分类过滤
            if arguments.get("categories"):
                categories = arguments["categories"]
                # JSON 数组查询
                for cat in categories:
                    query = query.where(Paper.categories.contains([cat]))

            # 标签过滤
            if arguments.get("tags"):
                tags = arguments["tags"]
                for tag in tags:
                    query = query.where(Paper.tags.contains([tag]))

            # 日期范围
            if arguments.get("date_from"):
                query = query.where(Paper.publish_date >= arguments["date_from"])
            if arguments.get("date_to"):
                query = query.where(Paper.publish_date <= arguments["date_to"])

            # 排序
            sort_by = arguments.get("sort_by", "newest")
            if sort_by == "newest":
                query = query.order_by(Paper.publish_date.desc())
            elif sort_by == "popularity":
                query = query.order_by(Paper.popularity_score.desc())

            # 限制数量
            limit = arguments.get("limit", 20)
            query = query.limit(limit)

            # 执行查询
            if db_session:
                result = await db_session.execute(query)
                papers = result.scalars().all()
            else:
                # 使用新会话
                from app.database import async_session_maker
                async with async_session_maker() as session:
                    result = await session.execute(query)
                    papers = result.scalars().all()

            # 格式化结果
            papers_data = [self._format_paper(p) for p in papers]

            return ToolResult(
                success=True,
                data={
                    "papers": papers_data,
                    "total": len(papers_data),
                    "query": arguments,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"搜索失败: {str(e)}",
            )

    def _format_paper(self, paper: Any) -> Dict[str, Any]:
        """格式化论文数据"""
        return {
            "id": paper.id,
            "title": paper.title,
            "arxiv_id": paper.arxiv_id,
            "authors": paper.authors or [],
            "publish_date": str(paper.publish_date) if paper.publish_date else None,
            "categories": paper.categories or [],
            "tags": paper.tags or [],
            "tier": paper.tier,
            "summary": paper.summary[:500] if paper.summary else None,
            "arxiv_url": f"https://arxiv.org/abs/{paper.arxiv_id}" if paper.arxiv_id else None,
        }