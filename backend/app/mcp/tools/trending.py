"""
获取热门论文工具
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolDefinition, ToolResult


class GetTrendingTool(BaseTool):
    """获取热门论文工具"""

    name = "get_trending"
    description = "获取热门论文列表（按日期分组）"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "最近几天",
                    },
                    "limit_per_day": {
                        "type": "integer",
                        "default": 20,
                        "description": "每天返回数量",
                    },
                    "include_analysis": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否包含分析结果",
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
        """执行查询"""
        from sqlalchemy import select
        from app.models import Paper

        days = arguments.get("days", 7)
        limit_per_day = arguments.get("limit_per_day", 20)
        include_analysis = arguments.get("include_analysis", False)

        try:
            # 计算日期范围
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)

            # 构建查询
            query = (
                select(Paper)
                .where(Paper.publish_date >= start_date)
                .order_by(Paper.publish_date.desc(), Paper.popularity_score.desc())
            )

            # 执行查询
            if db_session:
                result = await db_session.execute(query)
                papers = result.scalars().all()
            else:
                from app.database import async_session_maker
                async with async_session_maker() as session:
                    result = await session.execute(query)
                    papers = result.scalars().all()

            # 按日期分组
            papers_by_date = defaultdict(list)
            for paper in papers:
                if paper.publish_date:
                    date_str = str(paper.publish_date)[:10]  # YYYY-MM-DD
                    if len(papers_by_date[date_str]) < limit_per_day:
                        papers_by_date[date_str].append(
                            self._format_paper(paper, include_analysis)
                        )

            # 构建响应
            days_data = []
            for date_str in sorted(papers_by_date.keys(), reverse=True):
                days_data.append({
                    "date": date_str,
                    "papers": papers_by_date[date_str],
                    "total_that_day": len(papers_by_date[date_str]),
                })

            return ToolResult(
                success=True,
                data={
                    "days": days_data,
                    "total_days": len(days_data),
                    "limit_per_day": limit_per_day,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"获取热门论文失败: {str(e)}",
            )

    def _format_paper(self, paper: Any, include_analysis: bool = False) -> Dict[str, Any]:
        """格式化论文数据"""
        data = {
            "id": paper.id,
            "title": paper.title,
            "arxiv_id": paper.arxiv_id,
            "authors": paper.authors[:5] if paper.authors else [],
            "publish_date": str(paper.publish_date)[:10] if paper.publish_date else None,
            "categories": paper.categories or [],
            "tags": paper.tags or [],
            "tier": paper.tier,
            "popularity_score": paper.popularity_score,
            "arxiv_url": f"https://arxiv.org/abs/{paper.arxiv_id}" if paper.arxiv_id else None,
        }

        if paper.summary:
            data["summary"] = paper.summary[:300]

        if include_analysis:
            data.update({
                "key_contributions": paper.key_contributions or [],
                "methodology": paper.methodology,
                "institutions": paper.institutions or [],
            })

        return data