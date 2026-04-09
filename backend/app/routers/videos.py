"""视频相关 API 路由模块。

提供视频查询、转录稿获取、分析等 API 端点。
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Video
from app.schemas import (
    VideoAnalysisRequest,
    VideoAnalysisResponse,
    VideoCard,
    VideoDetail,
    VideoListResponse,
    FetchVideoTranscriptRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])


# ==================== 视频列表与详情 ====================


@router.get("", response_model=VideoListResponse)
async def get_videos(
    search: Optional[str] = Query(None, description="搜索关键词"),
    platform: Optional[str] = Query(None, description="平台: douyin, bilibili"),
    tier: Optional[str] = Query(None, description="Tier等级: A, B, C"),
    has_analysis: Optional[bool] = Query(None, description="是否有分析"),
    sort_by: Optional[str] = Query(None, description="排序方式: newest, oldest"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    """获取视频列表。"""
    query = select(Video)

    # 搜索
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Video.title.ilike(search_pattern),
                Video.transcript.ilike(search_pattern),
                Video.speaker.ilike(search_pattern),
            )
        )

    # 平台筛选
    if platform:
        query = query.where(Video.platform == platform)

    # Tier 筛选
    if tier:
        query = query.where(Video.tier == tier.upper())

    # 是否有分析
    if has_analysis is not None:
        query = query.where(Video.has_analysis == has_analysis)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 排序
    if sort_by == "oldest":
        query = query.order_by(Video.created_at.asc())
    else:
        query = query.order_by(Video.created_at.desc())

    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    videos = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return VideoListResponse(
        videos=[VideoCard.model_validate(v) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{video_id}", response_model=VideoDetail)
async def get_video(
    video_id: int,
    db: AsyncSession = Depends(get_db),
) -> VideoDetail:
    """获取视频详情。"""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    # 增加浏览量（可选）
    # video.view_count = (video.view_count or 0) + 1
    # await db.commit()

    return VideoDetail.model_validate(video)


# ==================== 视频分析 ====================


@router.post("/{video_id}/analyze", response_model=VideoAnalysisResponse)
async def analyze_video(
    video_id: int,
    force_refresh: bool = Query(False, description="是否强制重新分析"),
    db: AsyncSession = Depends(get_db),
) -> VideoAnalysisResponse:
    """触发视频分析。"""
    # 检查视频是否存在
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    # 创建分析任务
    from app.tasks.task_queue import task_queue

    task = task_queue.create_task(
        task_type="video_analysis",
        payload={
            "video_id": video_id,
            "force_refresh": force_refresh,
        },
    )

    logger.info(f"创建视频分析任务: video_id={video_id}, task_id={task.id}")

    return VideoAnalysisResponse(
        video_id=video_id,
        status="pending",
        message=f"任务已创建: {task.id}",
    )


# ==================== 转录稿获取 ====================


@router.post("/fetch-transcript")
async def fetch_video_transcript(
    request: FetchVideoTranscriptRequest,
    db: AsyncSession = Depends(get_db),
):
    """获取视频转录稿并创建记录。"""
    from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool
    from app.mcp.config import MCPConfig

    tool = FetchVideoTranscriptTool()
    config = MCPConfig()  # 使用默认配置

    result = await tool.execute(
        arguments={
            "url": request.url,
            "title": request.title,
            "speaker": request.speaker,
            "create_record": request.create_record,
        },
        config=config,
        db_session=db,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result.data


# ==================== 统计 ====================


@router.get("/stats/overview")
async def get_video_stats(
    db: AsyncSession = Depends(get_db),
):
    """获取视频统计信息。"""
    # 总数
    total_result = await db.execute(select(func.count()).select_from(Video))
    total = total_result.scalar() or 0

    # 已分析数
    analyzed_result = await db.execute(
        select(func.count()).select_from(Video).where(Video.has_analysis == True)
    )
    analyzed = analyzed_result.scalar() or 0

    # 各平台数量
    platform_result = await db.execute(
        select(Video.platform, func.count()).group_by(Video.platform)
    )
    platforms = {row[0] or "unknown": row[1] for row in platform_result.fetchall()}

    # 各 Tier 数量
    tier_result = await db.execute(
        select(Video.tier, func.count()).group_by(Video.tier)
    )
    tiers = {row[0] or "unrated": row[1] for row in tier_result.fetchall()}

    return {
        "total": total,
        "analyzed": analyzed,
        "platforms": platforms,
        "tiers": tiers,
    }