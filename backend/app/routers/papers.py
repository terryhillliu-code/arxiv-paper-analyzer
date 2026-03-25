"""论文相关 API 路由模块。

提供论文查询、抓取、分析等 API 端点。
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import FetchLog, Paper
from app.outputs.markdown_generator import MarkdownGenerator

logger = logging.getLogger(__name__)
from app.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    BatchAnalyzeResponse,
    DailyTrendingPapers,
    DailyTrendingResponse,
    FetchByCategoriesRequest,
    FetchByDateRequest,
    FetchRequest,
    FetchResponse,
    PaperCard,
    PaperDetail,
    PaperFilter,
    PaperListResponse,
    StatsResponse,
    TrendingPaperCard,
    TrendingPapersResponse,
)
from app.services.ai_service import ai_service
from app.services.arxiv_service import ArxivService
from app.services.pdf_service import PDFService, pdf_service

router = APIRouter(prefix="/api", tags=["papers"])


# ==================== 论文列表与详情 ====================


@router.get("/papers", response_model=PaperListResponse)
async def get_papers(
    search: Optional[str] = Query(None, description="搜索关键词"),
    categories: Optional[str] = Query(None, description="分类，逗号分隔"),
    tags: Optional[str] = Query(None, description="标签，逗号分隔"),
    tier: Optional[str] = Query(None, description="Tier等级: A, B, C"),
    date_from: Optional[datetime] = Query(None, description="开始日期"),
    date_to: Optional[datetime] = Query(None, description="结束日期"),
    has_analysis: Optional[bool] = Query(None, description="是否有分析"),
    sort_by: Optional[str] = Query(None, description="排序方式: newest, oldest, views, tier"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
) -> PaperListResponse:
    """获取论文列表。

    支持搜索、筛选、排序和分页。
    """
    # 构建基础查询
    query = select(Paper)

    # 搜索条件：在 title, abstract, summary 中模糊搜索
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Paper.title.ilike(search_pattern),
                Paper.abstract.ilike(search_pattern),
                Paper.summary.ilike(search_pattern),
            )
        )

    # 分类筛选：匹配 JSON 数组中的值
    if categories:
        category_list = [c.strip() for c in categories.split(",")]
        category_conditions = []
        for cat in category_list:
            # SQLite JSON 匹配方式
            category_conditions.append(Paper.categories.like(f'%"{cat}"%'))
        query = query.where(or_(*category_conditions))

    # 标签筛选：匹配 JSON 数组中的值
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        tag_conditions = []
        for tag in tag_list:
            tag_conditions.append(Paper.tags.like(f'%"{tag}"%'))
        query = query.where(or_(*tag_conditions))

    # 日期范围筛选
    # 注意：date_to 需要设置为当天的 23:59:59，因为数据库日期包含时间部分
    if date_from:
        # date_from 设为当天 00:00:00
        date_from_start = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Paper.publish_date >= date_from_start)
    if date_to:
        # date_to 设为当天 23:59:59
        date_to_end = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.where(Paper.publish_date <= date_to_end)

    # 是否有分析
    if has_analysis is not None:
        query = query.where(Paper.has_analysis == has_analysis)

    # Tier 筛选
    if tier:
        query = query.where(Paper.tier == tier.upper())

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 排序：未指定时按 ID 降序（最近添加的在前）
    if sort_by == "oldest":
        query = query.order_by(Paper.publish_date.asc())
    elif sort_by == "views":
        query = query.order_by(Paper.view_count.desc())
    elif sort_by == "newest":
        query = query.order_by(Paper.publish_date.desc())
    elif sort_by == "tier":
        # 按 Tier 排序：A > B > C > NULL
        query = query.order_by(
            func.CASE(
                (Paper.tier == "A", 1),
                (Paper.tier == "B", 2),
                (Paper.tier == "C", 3),
                else_=4
            )
        )
    else:
        # 默认：按 ID 降序
        query = query.order_by(Paper.id.desc())

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # 执行查询
    result = await db.execute(query)
    papers = result.scalars().all()

    # 计算总页数
    total_pages = (total + page_size - 1) // page_size

    return PaperListResponse(
        papers=[PaperCard.model_validate(p) for p in papers],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ==================== 热门度排名（必须在 /papers/{paper_id} 之前）====================


def calculate_popularity_score(
    view_count: int,
    has_analysis: bool,
    has_summary: bool,
    days_since_publish: int,
    is_featured: bool = False,
) -> tuple[float, dict]:
    """计算论文热门度分数。

    热门度 = 浏览量权重 + 分析权重 + 摘要权重 + 时效性权重 + 精选加成

    Args:
        view_count: 浏览量
        has_analysis: 是否有深度分析
        has_summary: 是否有AI摘要
        days_since_publish: 发布距今天数
        is_featured: 是否精选

    Returns:
        (总分, 各项分数字典)
    """
    # 浏览量分数：对数增长，每10次浏览约增加1分
    view_score = min(10.0, (view_count / 10) ** 0.5 * 2) if view_count > 0 else 0

    # 分析分数：有深度分析 +5分
    analysis_score = 5.0 if has_analysis else 0

    # 摘要分数：有AI摘要 +3分
    summary_score = 3.0 if has_summary else 0

    # 时效性分数：7天内发布 +5分，14天内 +3分，30天内 +1分
    if days_since_publish <= 7:
        recency_score = 5.0
    elif days_since_publish <= 14:
        recency_score = 3.0
    elif days_since_publish <= 30:
        recency_score = 1.0
    else:
        recency_score = 0.0

    # 精选加成：+2分
    featured_score = 2.0 if is_featured else 0

    total = view_score + analysis_score + summary_score + recency_score + featured_score

    components = {
        "view_score": round(view_score, 2),
        "analysis_score": analysis_score,
        "summary_score": summary_score,
        "recency_score": recency_score,
        "featured_score": featured_score,
    }

    return round(total, 2), components


async def update_popularity_scores(db: AsyncSession) -> int:
    """更新所有论文的热门度分数。

    Returns:
        更新的论文数量
    """
    from datetime import timezone

    result = await db.execute(select(Paper))
    papers = result.scalars().all()

    now = datetime.now(timezone.utc)
    updated_count = 0

    for paper in papers:
        # 计算发布距今天数
        if paper.publish_date:
            if paper.publish_date.tzinfo is None:
                pub_date = paper.publish_date.replace(tzinfo=timezone.utc)
            else:
                pub_date = paper.publish_date
            days_since = (now - pub_date).days
        else:
            days_since = 999  # 无发布日期视为很旧

        # 计算热门度
        score, _ = calculate_popularity_score(
            view_count=paper.view_count,
            has_analysis=paper.has_analysis,
            has_summary=bool(paper.summary),
            days_since_publish=days_since,
            is_featured=paper.is_featured,
        )

        paper.popularity_score = score
        updated_count += 1

    await db.commit()
    return updated_count


@router.get("/papers/trending", response_model=TrendingPapersResponse)
async def get_trending_papers(
    limit: int = Query(20, ge=1, le=50, description="返回数量"),
    update_scores: bool = Query(False, description="是否更新热门度分数"),
    db: AsyncSession = Depends(get_db),
) -> TrendingPapersResponse:
    """获取热门论文列表。

    按热门度排名返回论文，默认前20篇。
    热门度综合考虑浏览量、分析状态、时效性等因素。
    """
    # 可选：更新热门度分数
    if update_scores:
        await update_popularity_scores(db)

    # 查询热门论文
    query = (
        select(Paper)
        .order_by(Paper.popularity_score.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    # 统计已分析论文数
    analyzed_query = select(func.count()).select_from(Paper).where(
        Paper.has_analysis == True
    )
    analyzed_result = await db.execute(analyzed_query)
    total_analyzed = analyzed_result.scalar() or 0

    # 构建响应
    trending_papers = []
    for rank, paper in enumerate(papers, start=1):
        card = TrendingPaperCard(
            id=paper.id,
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors=paper.authors,
            institutions=paper.institutions,
            categories=paper.categories,
            tags=paper.tags,
            summary=paper.summary,
            publish_date=paper.publish_date,
            pdf_url=paper.pdf_url,
            arxiv_url=paper.arxiv_url,
            content_type=paper.content_type,
            tier=paper.tier,
            action_items=paper.action_items,
            knowledge_links=paper.knowledge_links,
            has_analysis=paper.has_analysis,
            view_count=paper.view_count,
            popularity_score=paper.popularity_score,
            created_at=paper.created_at,
            rank=rank,
            popularity_components=None,  # 可扩展：返回详细分数
        )
        trending_papers.append(card)

    return TrendingPapersResponse(
        papers=trending_papers,
        date=datetime.now().strftime("%Y-%m-%d"),
        total_analyzed=total_analyzed,
    )


@router.post("/papers/trending/analyze", response_model=BatchAnalyzeResponse)
async def analyze_trending_papers(
    limit: int = Query(20, ge=1, le=50, description="分析数量"),
    force_refresh: bool = Query(False, description="是否强制重新分析"),
    use_mineru: bool = Query(True, description="是否使用 MinerU 深度解析"),
    db: AsyncSession = Depends(get_db),
) -> BatchAnalyzeResponse:
    """批量分析热门论文。

    对热门度排名前N的论文进行深度分析。
    默认分析前20篇。
    """
    # 查询热门论文
    query = (
        select(Paper)
        .order_by(Paper.popularity_score.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    success_count = 0
    failed_count = 0
    results = []

    for paper in papers:
        try:
            # 如果已有分析且不强制刷新，跳过
            if paper.has_analysis and paper.analysis_report and not force_refresh:
                results.append({
                    "paper_id": paper.id,
                    "title": paper.title,
                    "status": "skipped",
                    "message": "已有分析",
                })
                continue

            # 下载并解析 PDF
            content = paper.full_text
            if not content and paper.pdf_url and paper.arxiv_id:
                pdf_path = await pdf_service.download_pdf(
                    pdf_url=paper.pdf_url,
                    arxiv_id=paper.arxiv_id,
                )
                paper.pdf_local_path = pdf_path

                if use_mineru:
                    content, _ = await pdf_service.extract_markdown(pdf_path)
                else:
                    content = await PDFService.get_paper_text(
                        pdf_url=paper.pdf_url,
                        arxiv_id=paper.arxiv_id,
                    )

                if content:
                    paper.full_text = content

            # 如果内容不足，使用摘要
            if not content or len(content) < 500:
                content = paper.abstract or ""

            if not content:
                results.append({
                    "paper_id": paper.id,
                    "title": paper.title,
                    "status": "failed",
                    "message": "无内容可分析",
                })
                failed_count += 1
                continue

            # 生成深度分析
            analysis_result = await ai_service.generate_deep_analysis(
                title=paper.title,
                authors=paper.authors or [],
                institutions=paper.institutions or [],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=paper.categories or [],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=content,
            )

            # 更新论文
            paper.analysis_report = analysis_result.get("report", "")
            analysis_json = analysis_result.get("analysis_json", {})
            paper.analysis_json = analysis_json
            paper.has_analysis = True

            if analysis_json:
                paper.tier = analysis_json.get("tier")
                paper.action_items = analysis_json.get("action_items")
                paper.knowledge_links = analysis_json.get("knowledge_links")
                if analysis_json.get("tags"):
                    paper.tags = analysis_json.get("tags")

            # 导出到 Obsidian
            try:
                generator = MarkdownGenerator()
                export_result = generator.generate_paper_md(
                    paper_data={
                        "title": paper.title,
                        "authors": paper.authors,
                        "institutions": paper.institutions,
                        "publish_date": paper.publish_date,
                        "arxiv_url": paper.arxiv_url,
                        "arxiv_id": paper.arxiv_id,
                        "tags": paper.tags,
                        "content_type": paper.content_type or "paper",
                    },
                    analysis_json=analysis_json or {},
                    report=paper.analysis_report or "",
                    pdf_path=paper.pdf_local_path,
                )
                paper.md_output_path = export_result.get("md_path")
            except Exception as e:
                logger.warning(f"导出到 Obsidian 失败: {e}")

            success_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title,
                "status": "success",
                "message": "分析完成",
            })

        except Exception as e:
            failed_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title,
                "status": "failed",
                "message": str(e)[:100],
            })

    await db.commit()

    # 更新热门度分数
    await update_popularity_scores(db)

    return BatchAnalyzeResponse(
        total=len(papers),
        success=success_count,
        failed=failed_count,
        papers=results,
        message=f"批量分析完成: 成功 {success_count}，失败 {failed_count}，跳过 {len(papers) - success_count - failed_count}",
    )


# ==================== 每日热门论文 ====================


@router.get("/papers/trending/daily", response_model=DailyTrendingResponse)
async def get_daily_trending_papers(
    days: int = Query(7, ge=1, le=30, description="返回最近几天的数据"),
    limit_per_day: int = Query(20, ge=1, le=50, description="每天返回数量"),
    update_scores: bool = Query(False, description="是否更新热门度分数"),
    db: AsyncSession = Depends(get_db),
) -> DailyTrendingResponse:
    """获取每日热门论文。

    按日期分组，每天返回热门度 Top N 的论文。

    Args:
        days: 返回最近几天的数据（默认7天）
        limit_per_day: 每天返回的论文数量（默认20篇）
        update_scores: 是否更新热门度分数
        db: 数据库会话

    Returns:
        DailyTrendingResponse: 按日期分组的热门论文列表
    """
    # 可选：更新热门度分数
    if update_scores:
        await update_popularity_scores(db)

    # 计算日期范围
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    # 查询时间范围内的所有论文，按日期和热门度排序
    query = (
        select(Paper)
        .where(Paper.publish_date >= start_date)
        .where(Paper.publish_date <= end_date)
        .order_by(Paper.publish_date.desc(), Paper.popularity_score.desc())
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    # 按日期分组
    papers_by_date = {}
    for paper in papers:
        if paper.publish_date:
            date_str = paper.publish_date.strftime("%Y-%m-%d")
            if date_str not in papers_by_date:
                papers_by_date[date_str] = []
            if len(papers_by_date[date_str]) < limit_per_day:
                papers_by_date[date_str].append(paper)

    # 统计每天的论文总数（按日期部分分组）
    count_query = (
        select(
            func.strftime("%Y-%m-%d", Paper.publish_date).label("date"),
            func.count(Paper.id).label("count")
        )
        .where(Paper.publish_date >= start_date)
        .where(Paper.publish_date <= end_date)
        .group_by(func.strftime("%Y-%m-%d", Paper.publish_date))
        .order_by(func.strftime("%Y-%m-%d", Paper.publish_date).desc())
    )
    count_result = await db.execute(count_query)
    counts_by_date = {
        row.date: row.count
        for row in count_result.all()
        if row.date
    }

    # 构建响应
    daily_papers = []
    total_papers = 0

    for date_str in sorted(papers_by_date.keys(), reverse=True):
        day_papers = papers_by_date[date_str]
        trending_cards = []
        for rank, paper in enumerate(day_papers, 1):
            card = TrendingPaperCard(
                id=paper.id,
                arxiv_id=paper.arxiv_id,
                title=paper.title,
                authors=paper.authors,
                institutions=paper.institutions,
                categories=paper.categories,
                tags=paper.tags,
                summary=paper.summary,
                publish_date=paper.publish_date,
                pdf_url=paper.pdf_url,
                arxiv_url=paper.arxiv_url,
                content_type=paper.content_type,
                tier=paper.tier,
                action_items=paper.action_items,
                knowledge_links=paper.knowledge_links,
                has_analysis=paper.has_analysis,
                view_count=paper.view_count,
                popularity_score=paper.popularity_score,
                created_at=paper.created_at,
                rank=rank,
            )
            trending_cards.append(card)

        daily_papers.append(
            DailyTrendingPapers(
                date=date_str,
                papers=trending_cards,
                total_that_day=counts_by_date.get(date_str, len(day_papers)),
            )
        )
        total_papers += len(day_papers)

    return DailyTrendingResponse(
        days=daily_papers,
        total_days=len(daily_papers),
        total_papers=total_papers,
    )


@router.post("/papers/trending/daily/analyze", response_model=BatchAnalyzeResponse)
async def analyze_daily_trending_papers(
    days: int = Query(1, ge=1, le=7, description="分析最近几天的"),
    limit_per_day: int = Query(20, ge=1, le=50, description="每天分析数量"),
    force_refresh: bool = Query(False, description="是否强制重新分析"),
    use_mineru: bool = Query(True, description="是否使用 MinerU 深度解析"),
    db: AsyncSession = Depends(get_db),
) -> BatchAnalyzeResponse:
    """批量分析每日热门论文。

    对指定天数内每天的热门论文进行深度分析。

    Args:
        days: 分析最近几天的数据（默认1天，即今天）
        limit_per_day: 每天分析的论文数量（默认20篇）
        force_refresh: 是否强制重新分析
        use_mineru: 是否使用 MinerU 深度解析
        db: 数据库会话

    Returns:
        BatchAnalyzeResponse: 批量分析结果
    """
    # 计算日期范围
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    # 查询时间范围内的所有论文，按日期和热门度排序
    query = (
        select(Paper)
        .where(Paper.publish_date >= start_date)
        .where(Paper.publish_date <= end_date)
        .order_by(Paper.publish_date.desc(), Paper.popularity_score.desc())
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    # 按日期分组，取每天 Top N
    papers_by_date = {}
    for paper in papers:
        if paper.publish_date:
            date_str = paper.publish_date.strftime("%Y-%m-%d")
            if date_str not in papers_by_date:
                papers_by_date[date_str] = []
            if len(papers_by_date[date_str]) < limit_per_day:
                papers_by_date[date_str].append(paper)

    # 合并所有待分析的论文
    papers_to_analyze = []
    for date_str in sorted(papers_by_date.keys(), reverse=True):
        papers_to_analyze.extend(papers_by_date[date_str])

    success_count = 0
    failed_count = 0
    skipped_count = 0
    results = []

    for paper in papers_to_analyze:
        try:
            # 如果已有分析且不强制刷新，跳过
            if paper.has_analysis and paper.analysis_report and not force_refresh:
                results.append({
                    "paper_id": paper.id,
                    "title": paper.title,
                    "status": "skipped",
                    "message": "已有分析",
                })
                skipped_count += 1
                continue

            # 下载并解析 PDF
            content = paper.full_text
            if not content and paper.pdf_url and paper.arxiv_id:
                pdf_path = await pdf_service.download_pdf(
                    pdf_url=paper.pdf_url,
                    arxiv_id=paper.arxiv_id,
                )
                paper.pdf_local_path = pdf_path

                if use_mineru:
                    content, _ = await pdf_service.extract_markdown(pdf_path)
                else:
                    content = await PDFService.get_paper_text(
                        pdf_url=paper.pdf_url,
                        arxiv_id=paper.arxiv_id,
                    )

                if content:
                    paper.full_text = content

            # 如果内容不足，使用摘要
            if not content or len(content) < 500:
                content = paper.abstract or ""

            if not content:
                results.append({
                    "paper_id": paper.id,
                    "title": paper.title,
                    "status": "failed",
                    "message": "无内容可分析",
                })
                failed_count += 1
                continue

            # 生成深度分析
            analysis_result = await ai_service.generate_deep_analysis(
                title=paper.title,
                authors=paper.authors or [],
                institutions=paper.institutions or [],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=paper.categories or [],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=content,
            )

            # 更新论文
            paper.analysis_report = analysis_result.get("report", "")
            analysis_json = analysis_result.get("analysis_json", {})
            paper.analysis_json = analysis_json
            paper.has_analysis = True

            if analysis_json:
                paper.tier = analysis_json.get("tier")
                paper.action_items = analysis_json.get("action_items")
                paper.knowledge_links = analysis_json.get("knowledge_links")
                if analysis_json.get("tags"):
                    paper.tags = analysis_json.get("tags")

            # 导出到 Obsidian
            try:
                generator = MarkdownGenerator()
                export_result = generator.generate_paper_md(
                    paper_data={
                        "title": paper.title,
                        "authors": paper.authors,
                        "institutions": paper.institutions,
                        "publish_date": paper.publish_date,
                        "arxiv_url": paper.arxiv_url,
                        "arxiv_id": paper.arxiv_id,
                        "tags": paper.tags,
                        "content_type": paper.content_type or "paper",
                    },
                    analysis_json=analysis_json or {},
                    report=paper.analysis_report or "",
                    pdf_path=paper.pdf_local_path,
                )
                paper.md_output_path = export_result.get("md_path")
            except Exception as e:
                logger.warning(f"导出到 Obsidian 失败: {e}")

            success_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title,
                "status": "success",
                "message": "分析完成",
            })

        except Exception as e:
            failed_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title,
                "status": "failed",
                "message": str(e)[:100],
            })

    await db.commit()

    # 更新热门度分数
    await update_popularity_scores(db)

    return BatchAnalyzeResponse(
        total=len(papers_to_analyze),
        success=success_count,
        failed=failed_count,
        papers=results,
        message=f"批量分析完成: 成功 {success_count}，失败 {failed_count}，跳过 {skipped_count}",
    )


@router.get("/papers/missing-summary")
async def get_papers_missing_summary(
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取缺少AI摘要的论文列表。

    返回 summary 为空的论文，用于批量生成摘要。
    """
    # 查询 summary 为空的论文
    query = (
        select(Paper)
        .where(or_(Paper.summary == None, Paper.summary == ""))
        .order_by(Paper.popularity_score.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    # 统计总数
    count_query = select(func.count()).select_from(Paper).where(
        or_(Paper.summary == None, Paper.summary == "")
    )
    count_result = await db.execute(count_query)
    total_missing = count_result.scalar() or 0

    return {
        "papers": [
            {
                "id": p.id,
                "arxiv_id": p.arxiv_id,
                "title": p.title[:100] if p.title else "",
                "has_abstract": bool(p.abstract),
            }
            for p in papers
        ],
        "total_missing": total_missing,
        "returned": len(papers),
    }


@router.post("/papers/generate-summaries")
async def generate_summaries(
    limit: int = Query(10, ge=1, le=50, description="处理数量限制"),
    process_all: bool = Query(False, description="是否处理所有缺少摘要的论文"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """批量生成论文摘要。

    为没有摘要的论文生成标签和一句话总结。

    Args:
        limit: 每次处理的最大数量（默认10篇）
        process_all: 如果为True，处理所有缺少摘要的论文（最多100篇）
    """
    # 查询 summary 为空的论文
    actual_limit = 100 if process_all else limit
    query = (
        select(Paper)
        .where(or_(Paper.summary == None, Paper.summary == ""))
        .order_by(Paper.popularity_score.desc())
        .limit(actual_limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    if not papers:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "message": "没有需要处理的论文，所有论文都已有AI摘要",
        }

    success_count = 0
    failed_count = 0
    results = []

    for paper in papers:
        try:
            # 调用 AI 生成摘要
            summary_result = await ai_service.generate_summary(
                title=paper.title,
                authors=paper.authors or [],
                abstract=paper.abstract or "",
                categories=paper.categories or [],
            )

            # 更新论文信息
            paper.summary = summary_result.get("summary", "")
            paper.tags = summary_result.get("tags", [])
            paper.institutions = summary_result.get("institutions", [])

            success_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title[:50],
                "status": "success",
            })

        except Exception as e:
            failed_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title[:50],
                "status": "failed",
                "error": str(e)[:50],
            })
            continue

    await db.commit()

    # 更新热门度分数
    await update_popularity_scores(db)

    # 查询剩余未处理的数量
    remaining_query = select(func.count()).select_from(Paper).where(
        or_(Paper.summary == None, Paper.summary == "")
    )
    remaining_result = await db.execute(remaining_query)
    remaining = remaining_result.scalar() or 0

    return {
        "processed": len(papers),
        "success": success_count,
        "failed": failed_count,
        "remaining": remaining,
        "results": results,
        "message": f"处理完成: 成功 {success_count}，失败 {failed_count}，剩余 {remaining} 篇待处理",
    }


# ==================== 论文详情（必须在具体路径之后）====================


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper_detail(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
) -> PaperDetail:
    """获取论文详情。

    增加浏览量并返回详细信息。
    """
    # 查询论文
    query = select(Paper).where(Paper.id == paper_id)
    result = await db.execute(query)
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    # 增加浏览量
    paper.view_count += 1
    await db.commit()
    await db.refresh(paper)

    return PaperDetail.model_validate(paper)


@router.get("/papers/arxiv/{arxiv_id:path}", response_model=PaperDetail)
async def get_paper_by_arxiv_id(
    arxiv_id: str,
    db: AsyncSession = Depends(get_db),
) -> PaperDetail:
    """通过 ArXiv ID 查询论文。

    支持各种格式：2301.00001, cs/0701001 等。
    """
    # 查询论文
    query = select(Paper).where(Paper.arxiv_id == arxiv_id)
    result = await db.execute(query)
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    return PaperDetail.model_validate(paper)


# ==================== 论文抓取 ====================


@router.post("/fetch", response_model=FetchResponse)
async def fetch_papers(
    request: FetchRequest,
    db: AsyncSession = Depends(get_db),
) -> FetchResponse:
    """从 ArXiv 抓取论文。

    使用自定义查询语句抓取。
    支持抓取后自动生成AI摘要。
    """
    result = await ArxivService.fetch_papers(
        db=db,
        query=request.query,
        max_results=request.max_results,
    )

    # 自动生成AI摘要
    summary_message = ""
    if request.auto_summary and result["new_papers"] > 0:
        # 查询新抓取的论文（summary为空）
        new_papers_query = (
            select(Paper)
            .where(or_(Paper.summary == None, Paper.summary == ""))
            .order_by(Paper.created_at.desc())
            .limit(result["new_papers"])
        )
        new_papers_result = await db.execute(new_papers_query)
        new_papers = new_papers_result.scalars().all()

        summary_success = 0
        for paper in new_papers:
            try:
                summary_result = await ai_service.generate_summary(
                    title=paper.title,
                    authors=paper.authors or [],
                    abstract=paper.abstract or "",
                    categories=paper.categories or [],
                )
                paper.summary = summary_result.get("summary", "")
                paper.tags = summary_result.get("tags", [])
                paper.institutions = summary_result.get("institutions", [])
                summary_success += 1
            except Exception as e:
                logger.warning(f"生成摘要失败 {paper.arxiv_id}: {e}")

        await db.commit()
        summary_message = f"，已生成 {summary_success} 篇摘要"

    return FetchResponse(
        total_fetched=result["total_fetched"],
        new_papers=result["new_papers"],
        message=result["message"] + summary_message,
    )


@router.post("/fetch/categories", response_model=FetchResponse)
async def fetch_by_categories(
    request: FetchByCategoriesRequest,
    db: AsyncSession = Depends(get_db),
) -> FetchResponse:
    """按分类抓取论文。

    从指定的 ArXiv 分类抓取最新论文。
    支持抓取后自动生成AI摘要。
    """
    result = await ArxivService.fetch_by_categories(
        db=db,
        categories=request.categories,
        max_results=request.max_results,
    )

    # 自动生成AI摘要
    summary_message = ""
    if request.auto_summary and result["new_papers"] > 0:
        new_papers_query = (
            select(Paper)
            .where(or_(Paper.summary == None, Paper.summary == ""))
            .order_by(Paper.created_at.desc())
            .limit(result["new_papers"])
        )
        new_papers_result = await db.execute(new_papers_query)
        new_papers = new_papers_result.scalars().all()

        summary_success = 0
        for paper in new_papers:
            try:
                summary_result = await ai_service.generate_summary(
                    title=paper.title,
                    authors=paper.authors or [],
                    abstract=paper.abstract or "",
                    categories=paper.categories or [],
                )
                paper.summary = summary_result.get("summary", "")
                paper.tags = summary_result.get("tags", [])
                paper.institutions = summary_result.get("institutions", [])
                summary_success += 1
            except Exception as e:
                logger.warning(f"生成摘要失败 {paper.arxiv_id}: {e}")

        await db.commit()
        summary_message = f"，已生成 {summary_success} 篇摘要"

    return FetchResponse(
        total_fetched=result["total_fetched"],
        new_papers=result["new_papers"],
        message=result["message"] + summary_message,
    )


@router.post("/fetch/date-range", response_model=FetchResponse)
async def fetch_by_date_range(
    request: FetchByDateRequest,
    db: AsyncSession = Depends(get_db),
) -> FetchResponse:
    """按日期范围抓取论文。

    抓取指定日期范围内发布的论文。
    注意：ArXiv API 不直接支持日期筛选，此接口通过抓取更多论文后过滤。
    支持抓取后自动生成AI摘要。
    """
    result = await ArxivService.fetch_by_date_range(
        db=db,
        categories=request.categories,
        date_from=request.date_from,
        date_to=request.date_to,
        max_results=request.max_results,
    )

    # 自动生成AI摘要
    summary_message = ""
    if request.auto_summary and result["new_papers"] > 0:
        new_papers_query = (
            select(Paper)
            .where(or_(Paper.summary == None, Paper.summary == ""))
            .order_by(Paper.created_at.desc())
            .limit(result["new_papers"])
        )
        new_papers_result = await db.execute(new_papers_query)
        new_papers = new_papers_result.scalars().all()

        summary_success = 0
        for paper in new_papers:
            try:
                summary_result = await ai_service.generate_summary(
                    title=paper.title,
                    authors=paper.authors or [],
                    abstract=paper.abstract or "",
                    categories=paper.categories or [],
                )
                paper.summary = summary_result.get("summary", "")
                paper.tags = summary_result.get("tags", [])
                paper.institutions = summary_result.get("institutions", [])
                summary_success += 1
            except Exception as e:
                logger.warning(f"生成摘要失败 {paper.arxiv_id}: {e}")

        await db.commit()
        summary_message = f"，已生成 {summary_success} 篇摘要"

    return FetchResponse(
        total_fetched=result.get("filtered_papers", result["total_fetched"]),
        new_papers=result["new_papers"],
        message=result["message"] + summary_message,
    )


# ==================== 摘要生成 ====================


@router.get("/papers/missing-summary")
async def get_papers_missing_summary(
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取缺少AI摘要的论文列表。

    返回 summary 为空的论文，用于批量生成摘要。
    """
    # 查询 summary 为空的论文
    query = (
        select(Paper)
        .where(or_(Paper.summary == None, Paper.summary == ""))
        .order_by(Paper.popularity_score.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    # 统计总数
    count_query = select(func.count()).select_from(Paper).where(
        or_(Paper.summary == None, Paper.summary == "")
    )
    count_result = await db.execute(count_query)
    total_missing = count_result.scalar() or 0

    return {
        "papers": [
            {
                "id": p.id,
                "arxiv_id": p.arxiv_id,
                "title": p.title[:100] if p.title else "",
                "has_abstract": bool(p.abstract),
            }
            for p in papers
        ],
        "total_missing": total_missing,
        "returned": len(papers),
    }


@router.post("/papers/generate-summaries")
async def generate_summaries(
    limit: int = Query(10, ge=1, le=50, description="处理数量限制"),
    process_all: bool = Query(False, description="是否处理所有缺少摘要的论文"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """批量生成论文摘要。

    为没有摘要的论文生成标签和一句话总结。

    Args:
        limit: 每次处理的最大数量（默认10篇）
        process_all: 如果为True，处理所有缺少摘要的论文（最多100篇）
    """
    # 查询 summary 为空的论文
    actual_limit = 100 if process_all else limit
    query = (
        select(Paper)
        .where(or_(Paper.summary == None, Paper.summary == ""))
        .order_by(Paper.popularity_score.desc())
        .limit(actual_limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    if not papers:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "message": "没有需要处理的论文，所有论文都已有AI摘要",
        }

    success_count = 0
    failed_count = 0
    results = []

    for paper in papers:
        try:
            # 调用 AI 生成摘要
            summary_result = await ai_service.generate_summary(
                title=paper.title,
                authors=paper.authors or [],
                abstract=paper.abstract or "",
                categories=paper.categories or [],
            )

            # 更新论文信息
            paper.summary = summary_result.get("summary", "")
            paper.tags = summary_result.get("tags", [])
            paper.institutions = summary_result.get("institutions", [])

            success_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title[:50],
                "status": "success",
            })

        except Exception as e:
            failed_count += 1
            results.append({
                "paper_id": paper.id,
                "title": paper.title[:50],
                "status": "failed",
                "error": str(e)[:50],
            })
            continue

    await db.commit()

    # 更新热门度分数
    await update_popularity_scores(db)

    # 查询剩余未处理的数量
    remaining_query = select(func.count()).select_from(Paper).where(
        or_(Paper.summary == None, Paper.summary == "")
    )
    remaining_result = await db.execute(remaining_query)
    remaining = remaining_result.scalar() or 0

    return {
        "processed": len(papers),
        "success": success_count,
        "failed": failed_count,
        "remaining": remaining,
        "results": results,
        "message": f"处理完成: 成功 {success_count}，失败 {failed_count}，剩余 {remaining} 篇待处理",
    }


# ==================== 深度分析 ====================


@router.post("/papers/{paper_id}/analyze", response_model=AnalysisResponse)
async def analyze_paper(
    paper_id: int,
    force_refresh: bool = Query(False, description="是否强制重新分析"),
    use_mineru: bool = Query(True, description="是否使用 MinerU 深度解析（保留结构）"),
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    """对论文进行深度分析。

    使用 AI 生成详细的 Markdown 分析报告。

    Args:
        use_mineru: True 使用 MinerU 深度解析（保留表格、公式、结构），
                   False 使用 PyMuPDF 快速提取纯文本。
    """
    # 查询论文
    query = select(Paper).where(Paper.id == paper_id)
    result = await db.execute(query)
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    # 如果已有分析且不强制刷新，直接返回
    if paper.has_analysis and paper.analysis_report and not force_refresh:
        return AnalysisResponse(
            paper_id=paper_id,
            status="completed",
            report=paper.analysis_report,
            message="论文已完成分析，使用 force_refresh=true 重新分析",
        )

    try:
        content = paper.full_text
        content_metadata = {}

        # 如果没有全文，下载 PDF 并解析
        if not content and paper.pdf_url and paper.arxiv_id:
            # 下载 PDF
            pdf_path = await pdf_service.download_pdf(
                pdf_url=paper.pdf_url,
                arxiv_id=paper.arxiv_id,
            )
            paper.pdf_local_path = pdf_path  # 保存本地路径

            # 根据 use_mineru 选择解析方式
            if use_mineru:
                logger.info(f"使用 MinerU 深度解析: {paper.arxiv_id}")
                content, content_metadata = await pdf_service.extract_markdown(pdf_path)
            else:
                logger.info(f"使用 PyMuPDF 快速提取: {paper.arxiv_id}")
                content = await PDFService.get_paper_text(
                    pdf_url=paper.pdf_url,
                    arxiv_id=paper.arxiv_id,
                )
                content_metadata = {"parser": "pymupdf"}

            # 保存全文
            if content:
                paper.full_text = content

        # 如果全文不足，使用摘要
        if not content or len(content) < 500:
            content = paper.abstract or ""
            content_metadata = {"parser": "abstract"}
            if not content:
                raise HTTPException(
                    status_code=400,
                    detail="论文缺少摘要和全文内容，无法分析",
                )

        # 调用 AI 生成深度分析
        analysis_result = await ai_service.generate_deep_analysis(
            title=paper.title,
            authors=paper.authors or [],
            institutions=paper.institutions or [],
            publish_date=str(paper.publish_date) if paper.publish_date else "",
            categories=paper.categories or [],
            arxiv_url=paper.arxiv_url or "",
            pdf_url=paper.pdf_url or "",
            content=content,
        )

        # 更新论文分析结果
        paper.analysis_report = analysis_result.get("report", "")
        analysis_json = analysis_result.get("analysis_json", {})
        paper.analysis_json = analysis_json
        paper.has_analysis = True

        # 保存新增字段
        if analysis_json:
            paper.tier = analysis_json.get("tier")
            paper.action_items = analysis_json.get("action_items")
            paper.knowledge_links = analysis_json.get("knowledge_links")
            # 更新标签（如果有新的）
            if analysis_json.get("tags"):
                paper.tags = analysis_json.get("tags")

        # === 自动导出到 Obsidian ===
        export_result = None
        try:
            generator = MarkdownGenerator()
            export_result = generator.generate_paper_md(
                paper_data={
                    "title": paper.title,
                    "authors": paper.authors,
                    "institutions": paper.institutions,
                    "publish_date": paper.publish_date,
                    "arxiv_url": paper.arxiv_url,
                    "arxiv_id": paper.arxiv_id,
                    "tags": paper.tags,
                    "content_type": paper.content_type or "paper",
                },
                analysis_json=analysis_json or {},
                report=paper.analysis_report or "",
                pdf_path=paper.pdf_local_path,  # 传递本地 PDF 路径
            )
            # 保存导出路径
            paper.md_output_path = export_result.get("md_path")
            logger.info(f"自动导出到 Obsidian 成功: {export_result}")
        except Exception as e:
            logger.warning(f"自动导出到 Obsidian 失败: {e}")
            # 导出失败不影响分析结果保存

        await db.commit()

        # 构建返回消息
        message = "分析完成"
        if export_result:
            message += f"，已导出到 Obsidian"
            if export_result.get("pdf_path"):
                message += "（含 PDF）"

        return AnalysisResponse(
            paper_id=paper_id,
            status="completed",
            report=paper.analysis_report,
            message=message,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ==================== 统计信息 ====================


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """获取论文库统计信息。

    包括总数、分析数、分类分布、标签分布等。
    """
    # 论文总数
    total_query = select(func.count()).select_from(Paper)
    total_result = await db.execute(total_query)
    total_papers = total_result.scalar() or 0

    # 已分析论文数
    analyzed_query = select(func.count()).select_from(Paper).where(
        Paper.has_analysis == True
    )
    analyzed_result = await db.execute(analyzed_query)
    analyzed_papers = analyzed_result.scalar() or 0

    # 近 7 天新增论文数
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_query = select(func.count()).select_from(Paper).where(
        Paper.created_at >= seven_days_ago
    )
    recent_result = await db.execute(recent_query)
    recent_papers_count = recent_result.scalar() or 0

    # 分类分布（需要遍历所有论文统计）
    all_papers_query = select(Paper.categories)
    all_papers_result = await db.execute(all_papers_query)
    all_categories = all_papers_result.scalars().all()

    categories_stats: dict = {}
    for cats in all_categories:
        if cats:
            for cat in cats:
                categories_stats[cat] = categories_stats.get(cat, 0) + 1

    # 标签分布
    all_tags_query = select(Paper.tags)
    all_tags_result = await db.execute(all_tags_query)
    all_tags = all_tags_result.scalars().all()

    tags_stats: dict = {}
    for tags in all_tags:
        if tags:
            for tag in tags:
                tags_stats[tag] = tags_stats.get(tag, 0) + 1

    return StatsResponse(
        total_papers=total_papers,
        analyzed_papers=analyzed_papers,
        categories=categories_stats,
        tags=tags_stats,
        recent_papers_count=recent_papers_count,
    )


# ==================== 标签与分类 ====================


@router.get("/tags")
async def get_tags() -> dict:
    """获取预设标签列表。

    返回所有可用的论文分类标签。
    """
    settings = get_settings()
    return {"tags": settings.predefined_tags}


@router.get("/categories")
async def get_categories() -> dict:
    """获取支持的 ArXiv 学科分类。

    返回分类代码及中文描述。
    """
    categories_info = {
        "cs.AI": {"name": "人工智能", "description": "Artificial Intelligence"},
        "cs.CL": {"name": "计算语言学", "description": "Computation and Language"},
        "cs.LG": {"name": "机器学习", "description": "Machine Learning"},
        "cs.CV": {"name": "计算机视觉", "description": "Computer Vision and Pattern Recognition"},
        "cs.NE": {"name": "神经与进化计算", "description": "Neural and Evolutionary Computing"},
        "cs.IR": {"name": "信息检索", "description": "Information Retrieval"},
        "cs.RO": {"name": "机器人", "description": "Robotics"},
        "cs.SE": {"name": "软件工程", "description": "Software Engineering"},
        "cs.DC": {"name": "分布式计算", "description": "Distributed, Parallel, and Cluster Computing"},
        "cs.CR": {"name": "密码学与安全", "description": "Cryptography and Security"},
        "stat.ML": {"name": "机器学习（统计）", "description": "Machine Learning (Statistics)"},
        "eess.AS": {"name": "音频信号处理", "description": "Audio and Speech Processing"},
        "eess.IV": {"name": "图像视频处理", "description": "Image and Video Processing"},
    }

    return {"categories": categories_info}


# ==================== Markdown 导出 ====================


@router.get("/papers/{paper_id}/markdown", response_class=PlainTextResponse)
async def export_paper_markdown(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
):
    """导出论文的 Markdown 格式。

    直接输出可用于 Obsidian 的 Markdown 内容。
    """
    result = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    if not paper.has_analysis:
        raise HTTPException(status_code=400, detail="论文尚未分析")

    # 生成 Markdown
    generator = MarkdownGenerator()
    md_content = generator._build_paper_content(
        {
            "title": paper.title,
            "authors": paper.authors,
            "institutions": paper.institutions,
            "publish_date": paper.publish_date,
            "arxiv_url": paper.arxiv_url,
            "tags": paper.tags,
        },
        paper.analysis_json or {},
        paper.analysis_report or "",
    )

    return md_content


@router.post("/papers/{paper_id}/export-to-obsidian")
async def export_to_obsidian(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将论文 Markdown 导出到 Obsidian Vault。"""
    result = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    if not paper.has_analysis:
        raise HTTPException(status_code=400, detail="论文尚未分析")

    # 生成并保存 Markdown
    generator = MarkdownGenerator()
    result = generator.generate_paper_md(
        {
            "title": paper.title,
            "authors": paper.authors,
            "institutions": paper.institutions,
            "publish_date": paper.publish_date,
            "arxiv_url": paper.arxiv_url,
            "tags": paper.tags,
            "arxiv_id": paper.arxiv_id,
            "content_type": paper.content_type or "paper",
        },
        paper.analysis_json or {},
        paper.analysis_report or "",
        pdf_path=paper.pdf_local_path,
    )

    # 更新数据库
    paper.md_output_path = result.get("md_path")
    await db.commit()

    return {
        "message": "导出成功",
        "md_path": result.get("md_path"),
        "pdf_path": result.get("pdf_path"),
        "paper_id": paper_id,
    }


# ==================== PDF 解析 (MinerU) ====================


@router.post("/papers/{paper_id}/extract")
async def extract_paper_content(
    paper_id: int,
    force_refresh: bool = Query(False, description="是否强制刷新缓存"),
    db: AsyncSession = Depends(get_db),
):
    """提取论文 PDF 内容（使用 MinerU 深度解析）。

    返回结构化 Markdown，保留表格、公式、标题层级。
    结果会缓存，避免重复解析。
    """
    result = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    if not paper.pdf_url:
        raise HTTPException(status_code=400, detail="论文无 PDF 链接")

    try:
        # 下载 PDF
        pdf_path = await pdf_service.download_pdf(
            pdf_url=paper.pdf_url,
            arxiv_id=paper.arxiv_id or str(paper_id),
        )

        # 使用 MinerU 提取 Markdown
        md_content, metadata = await pdf_service.extract_markdown(
            pdf_path,
            force_refresh=force_refresh,
        )

        # 保存到论文记录
        paper.full_text = md_content
        paper.pdf_local_path = pdf_path
        await db.commit()

        return {
            "paper_id": paper_id,
            "title": paper.title,
            "content_length": len(md_content),
            "metadata": metadata,
            "content_preview": md_content[:2000] if len(md_content) > 2000 else md_content,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 解析失败: {str(e)}")


@router.get("/papers/{paper_id}/cache-info")
async def get_paper_cache_info(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取论文 PDF 解析缓存信息。"""
    result = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    cache_info = {"paper_id": paper_id, "pdf_local_path": paper.pdf_local_path}

    if paper.pdf_local_path:
        cache_info.update(pdf_service.get_cache_info(paper.pdf_local_path))

    return cache_info


@router.delete("/papers/{paper_id}/cache")
async def clear_paper_cache(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
):
    """清理论文 PDF 解析缓存。"""
    result = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    if not paper.pdf_local_path:
        return {"message": "无缓存可清理", "cleared": 0}

    count = await pdf_service.clear_cache(paper.pdf_local_path)
    return {"message": f"已清理 {count} 个缓存文件", "cleared": count}