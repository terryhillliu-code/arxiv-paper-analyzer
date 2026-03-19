"""
CLI 命令实现

封装 MCP 工具调用逻辑。
"""

from typing import Any, Dict, List, Optional


async def search_papers(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """搜索论文"""
    from sqlalchemy import select, or_
    from app.models import Paper
    from app.database import async_session_maker

    try:
        async with async_session_maker() as session:
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
                for cat in arguments["categories"]:
                    query = query.where(Paper.categories.contains([cat]))

            # 标签过滤
            if arguments.get("tags"):
                for tag in arguments["tags"]:
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

            result = await session.execute(query)
            papers = result.scalars().all()

            papers_data = [_format_paper(p) for p in papers]

            return {
                "success": True,
                "data": {
                    "papers": papers_data,
                    "total": len(papers_data),
                },
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_paper(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """获取论文详情"""
    from sqlalchemy import select
    from app.models import Paper
    from app.database import async_session_maker

    paper_id = arguments.get("paper_id")
    include_analysis = arguments.get("include_analysis", False)

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Paper).where(Paper.id == paper_id)
            )
            paper = result.scalar_one_or_none()

            if not paper:
                return {"success": False, "error": f"论文不存在: ID={paper_id}"}

            data = _format_paper(paper, include_analysis)
            return {"success": True, "data": data}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_trending(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """获取热门论文"""
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.models import Paper
    from app.database import async_session_maker

    days = arguments.get("days", 7)
    limit_per_day = arguments.get("limit_per_day", 20)
    include_analysis = arguments.get("include_analysis", False)

    try:
        async with async_session_maker() as session:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)

            query = (
                select(Paper)
                .where(Paper.publish_date >= start_date)
                .order_by(Paper.publish_date.desc(), Paper.popularity_score.desc())
            )

            result = await session.execute(query)
            papers = result.scalars().all()

            # 按日期分组
            papers_by_date = defaultdict(list)
            for paper in papers:
                if paper.publish_date:
                    date_str = str(paper.publish_date)[:10]
                    if len(papers_by_date[date_str]) < limit_per_day:
                        papers_by_date[date_str].append(
                            _format_paper(paper, include_analysis)
                        )

            days_data = []
            for date_str in sorted(papers_by_date.keys(), reverse=True):
                days_data.append({
                    "date": date_str,
                    "papers": papers_by_date[date_str],
                    "total_that_day": len(papers_by_date[date_str]),
                })

            return {
                "success": True,
                "data": {
                    "days": days_data,
                    "total_days": len(days_data),
                },
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def analyze_paper(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """深度分析论文"""
    import httpx

    paper_id = arguments.get("paper_id")
    force = arguments.get("force", False)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/api/papers/{paper_id}/analyze",
                params={"force": force},
                timeout=300.0,
            )

            if response.status_code == 200:
                data = response.json()
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": response.text}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def generate_summary(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """生成 AI 摘要"""
    import httpx

    paper_id = arguments.get("paper_id")
    style = arguments.get("style", "brief")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:8000/api/papers/{paper_id}/summary",
                params={"style": style},
                timeout=120.0,
            )

            if response.status_code == 200:
                data = response.json()
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": response.text}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def export_papers(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """导出论文"""
    from sqlalchemy import select
    from app.models import Paper
    from app.database import async_session_maker
    from app.exporters import BibTeXExporter, ObsidianExporter

    paper_ids = arguments.get("paper_ids", [])
    format = arguments.get("format", "bibtex")
    output_file = arguments.get("output_file")
    folder = arguments.get("folder", "Inbox")

    if not paper_ids:
        return {"success": False, "error": "请提供论文 ID"}

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Paper).where(Paper.id.in_(paper_ids))
            )
            papers = result.scalars().all()

            if not papers:
                return {"success": False, "error": "未找到任何论文"}

            papers_data = [_format_paper_full(p) for p in papers]

            if format == "bibtex":
                exporter = BibTeXExporter()
                content = exporter.export_papers(papers_data)

                if output_file:
                    exporter.export_to_file(papers_data, output_file)

                return {
                    "success": True,
                    "data": {
                        "content": content,
                        "paper_count": len(papers),
                        "file_path": output_file,
                    },
                }

            elif format == "obsidian":
                from app.services.obsidian_client import ObsidianClient

                client = ObsidianClient()
                exporter = ObsidianExporter(client=client, prefer_service=True)

                exported_count = 0
                for paper_data in papers_data:
                    result = await exporter.export_to_vault(paper_data, folder=folder)
                    if result.success:
                        exported_count += 1

                return {
                    "success": True,
                    "data": {
                        "paper_count": exported_count,
                    },
                }

            else:
                return {"success": False, "error": f"不支持的格式: {format}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def publish_papers(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """发布论文"""
    import httpx

    paper_ids = arguments.get("paper_ids", [])
    platform = arguments.get("platform")
    config_file = arguments.get("config_file")

    if not paper_ids:
        return {"success": False, "error": "请提供论文 ID"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/api/publish",
                json={
                    "paper_ids": paper_ids,
                    "platform": platform,
                    "config_file": config_file,
                },
                timeout=60.0,
            )

            if response.status_code == 200:
                data = response.json()
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": response.text}

    except Exception as e:
        return {"success": False, "error": str(e)}


def _format_paper(paper: Any, include_analysis: bool = False) -> Dict[str, Any]:
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
            "one_line_summary": paper.one_line_summary,
            "overall_rating": paper.overall_rating,
        })

    return data


def _format_paper_full(paper: Any) -> Dict[str, Any]:
    """格式化完整论文数据（用于导出）"""
    return {
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
        "pdf_url": paper.pdf_url,
    }