"""论文相关 API 路由模块。

提供论文查询、抓取、分析等 API 端点。
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import FetchLog, Paper
from app.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    FetchByCategoriesRequest,
    FetchByDateRequest,
    FetchRequest,
    FetchResponse,
    PaperCard,
    PaperDetail,
    PaperFilter,
    PaperListResponse,
    StatsResponse,
)
from app.services.ai_service import ai_service
from app.services.arxiv_service import ArxivService
from app.services.pdf_service import PDFService

router = APIRouter(prefix="/api", tags=["papers"])


# ==================== 论文列表与详情 ====================


@router.get("/papers", response_model=PaperListResponse)
async def get_papers(
    search: Optional[str] = Query(None, description="搜索关键词"),
    categories: Optional[str] = Query(None, description="分类，逗号分隔"),
    tags: Optional[str] = Query(None, description="标签，逗号分隔"),
    date_from: Optional[datetime] = Query(None, description="开始日期"),
    date_to: Optional[datetime] = Query(None, description="结束日期"),
    has_analysis: Optional[bool] = Query(None, description="是否有分析"),
    sort_by: str = Query("newest", description="排序方式: newest, oldest, views"),
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

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 排序
    if sort_by == "oldest":
        query = query.order_by(Paper.publish_date.asc())
    elif sort_by == "views":
        query = query.order_by(Paper.view_count.desc())
    else:  # newest
        query = query.order_by(Paper.publish_date.desc())

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
    """
    result = await ArxivService.fetch_papers(
        db=db,
        query=request.query,
        max_results=request.max_results,
    )

    return FetchResponse(
        total_fetched=result["total_fetched"],
        new_papers=result["new_papers"],
        message=result["message"],
    )


@router.post("/fetch/categories", response_model=FetchResponse)
async def fetch_by_categories(
    request: FetchByCategoriesRequest,
    db: AsyncSession = Depends(get_db),
) -> FetchResponse:
    """按分类抓取论文。

    从指定的 ArXiv 分类抓取最新论文。
    """
    result = await ArxivService.fetch_by_categories(
        db=db,
        categories=request.categories,
        max_results=request.max_results,
    )

    return FetchResponse(
        total_fetched=result["total_fetched"],
        new_papers=result["new_papers"],
        message=result["message"],
    )


@router.post("/fetch/date-range", response_model=FetchResponse)
async def fetch_by_date_range(
    request: FetchByDateRequest,
    db: AsyncSession = Depends(get_db),
) -> FetchResponse:
    """按日期范围抓取论文。

    抓取指定日期范围内发布的论文。
    注意：ArXiv API 不直接支持日期筛选，此接口通过抓取更多论文后过滤。
    """
    result = await ArxivService.fetch_by_date_range(
        db=db,
        categories=request.categories,
        date_from=request.date_from,
        date_to=request.date_to,
        max_results=request.max_results,
    )

    return FetchResponse(
        total_fetched=result.get("filtered_papers", result["total_fetched"]),
        new_papers=result["new_papers"],
        message=result["message"],
    )


# ==================== 摘要生成 ====================


@router.post("/papers/generate-summaries")
async def generate_summaries(
    limit: int = Query(10, ge=1, le=50, description="处理数量限制"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """批量生成论文摘要。

    为没有摘要的论文生成标签和一句话总结。
    """
    # 查询 summary 为空的论文
    query = (
        select(Paper)
        .where(or_(Paper.summary == None, Paper.summary == ""))
        .limit(limit)
    )
    result = await db.execute(query)
    papers = result.scalars().all()

    if not papers:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "message": "没有需要处理的论文",
        }

    success_count = 0
    failed_count = 0

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

        except Exception as e:
            failed_count += 1
            continue

    await db.commit()

    return {
        "processed": len(papers),
        "success": success_count,
        "failed": failed_count,
        "message": f"处理完成: 成功 {success_count} 篇，失败 {failed_count} 篇",
    }


# ==================== 深度分析 ====================


@router.post("/papers/{paper_id}/analyze", response_model=AnalysisResponse)
async def analyze_paper(
    paper_id: int,
    force_refresh: bool = Query(False, description="是否强制重新分析"),
    db: AsyncSession = Depends(get_db),
) -> AnalysisResponse:
    """对论文进行深度分析。

    使用 AI 生成详细的 Markdown 分析报告。
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
        # 获取论文全文
        content = paper.full_text

        # 如果没有全文，尝试下载 PDF 提取
        if not content and paper.pdf_url and paper.arxiv_id:
            content = await PDFService.get_paper_text(
                pdf_url=paper.pdf_url,
                arxiv_id=paper.arxiv_id,
            )
            # 保存全文
            if content:
                paper.full_text = content

        # 如果全文不足，使用摘要
        if not content or len(content) < 500:
            content = paper.abstract or ""
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
        paper.analysis_json = analysis_result.get("analysis_json", {})
        paper.has_analysis = True

        await db.commit()

        return AnalysisResponse(
            paper_id=paper_id,
            status="completed",
            report=paper.analysis_report,
            message="分析完成",
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