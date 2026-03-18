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
from app.services.pdf_service import PDFService, pdf_service

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