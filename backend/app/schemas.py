"""Pydantic 数据验证模型模块。

定义 API 请求和响应的数据结构。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 论文相关 Schema ====================


class PaperBase(BaseModel):
    """论文基础字段。

    包含论文的核心信息，用于继承和组合。
    """

    arxiv_id: Optional[str] = None
    title: str
    authors: Optional[List[str]] = None
    institutions: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    publish_date: Optional[datetime] = None
    pdf_url: Optional[str] = None
    arxiv_url: Optional[str] = None

    # 新增字段
    content_type: str = "paper"
    tier: Optional[str] = None
    action_items: Optional[List[str]] = None
    knowledge_links: Optional[List[str]] = None


class PaperCard(PaperBase):
    """列表页卡片数据。

    包含列表展示所需的基本信息和统计字段。
    """

    id: int
    has_analysis: bool = False
    view_count: int = 0
    popularity_score: float = 0.0
    created_at: datetime

    model_config = {"from_attributes": True}


class PaperDetail(PaperCard):
    """详情页数据。

    包含论文的完整信息，包括摘要、全文和分析结果。
    """

    abstract: Optional[str] = None
    full_text: Optional[str] = None
    analysis_report: Optional[str] = None
    analysis_json: Optional[Dict[str, Any]] = None
    updated_at: Optional[datetime] = None

    # 新增：Markdown 输出
    md_output: Optional[str] = None  # 完整的 Markdown 内容
    md_output_path: Optional[str] = None  # 保存路径


class PaperListResponse(BaseModel):
    """分页列表响应。

    包含论文列表和分页信息。
    """

    papers: List[PaperCard]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaperFilter(BaseModel):
    """筛选参数。

    用于论文列表的筛选、排序和分页。
    """

    search: Optional[str] = None
    categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    has_analysis: Optional[bool] = None
    sort_by: str = Field(default="newest", description="排序方式: newest, oldest, views")
    page: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


# ==================== 抓取相关 Schema ====================


class FetchRequest(BaseModel):
    """抓取请求。

    定义从 arXiv 抓取论文的参数。
    """

    query: str = Field(
        default="cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV",
        description="arXiv 查询语句",
    )
    max_results: int = Field(default=50, ge=1, le=100, description="最大抓取数量")
    auto_summary: bool = Field(default=True, description="是否自动生成AI摘要")


class FetchByCategoriesRequest(BaseModel):
    """按分类抓取请求。

    从指定的 ArXiv 分类抓取最新论文。
    """

    categories: List[str] = Field(
        default=["cs.AI", "cs.CL", "cs.LG", "cs.CV"],
        description="ArXiv 分类列表",
    )
    max_results: int = Field(default=50, ge=1, le=100, description="每个分类最大抓取数量")
    auto_summary: bool = Field(default=True, description="是否自动生成AI摘要")


class FetchByDateRequest(BaseModel):
    """按日期范围抓取请求。

    抓取指定日期范围内的论文。
    """

    categories: Optional[List[str]] = Field(
        default=["cs.AI", "cs.CL", "cs.LG", "cs.CV"],
        description="ArXiv 分类列表，默认主要AI相关分类",
    )
    date_from: Optional[datetime] = Field(default=None, description="开始日期（包含）")
    date_to: Optional[datetime] = Field(default=None, description="结束日期（包含）")
    max_results: int = Field(default=200, ge=1, le=500, description="最大抓取数量")
    auto_summary: bool = Field(default=True, description="是否自动生成AI摘要")


class FetchResponse(BaseModel):
    """抓取响应。

    返回抓取操作的统计结果。
    """

    total_fetched: int
    new_papers: int
    message: str


# ==================== 分析相关 Schema ====================


class AnalysisRequest(BaseModel):
    """分析请求。

    定义对论文进行 AI 分析的参数。
    """

    paper_id: int = Field(..., description="论文ID")
    force_refresh: bool = Field(default=False, description="是否强制重新分析")


class AnalysisResponse(BaseModel):
    """分析响应。

    返回分析任务的状态和结果。
    """

    paper_id: int
    status: str = Field(description="状态: pending, processing, completed, failed")
    report: Optional[str] = Field(default=None, description="分析报告（Markdown格式）")
    message: str = Field(default="", description="状态消息或错误信息")


# ==================== 统计相关 Schema ====================


class StatsResponse(BaseModel):
    """统计响应。

    返回论文库的统计信息。
    """

    total_papers: int = Field(description="论文总数")
    analyzed_papers: int = Field(description="已分析论文数")
    categories: Dict[str, int] = Field(default_factory=dict, description="各分类论文数量")
    tags: Dict[str, int] = Field(default_factory=dict, description="各标签论文数量")
    recent_papers_count: int = Field(default=0, description="最近7天新增论文数")


# ==================== 热门度相关 Schema ====================


class TrendingPaperCard(PaperCard):
    """热门论文卡片。

    包含热门度排名信息。
    """

    rank: int = Field(description="排名")
    popularity_components: Optional[Dict[str, Any]] = Field(
        default=None, description="热门度组成详情"
    )


class TrendingPapersResponse(BaseModel):
    """热门论文列表响应。

    按热门度排名返回论文列表。
    """

    papers: List[TrendingPaperCard]
    date: str = Field(description="统计日期")
    total_analyzed: int = Field(description="已分析论文数")


class BatchAnalyzeResponse(BaseModel):
    """批量分析响应。

    返回批量分析操作的结果。
    """

    total: int = Field(description="总处理数量")
    success: int = Field(description="成功数量")
    failed: int = Field(description="失败数量")
    papers: List[Dict[str, Any]] = Field(default_factory=list, description="处理结果列表")
    message: str = Field(default="", description="结果消息")


# ==================== 每日热门论文 Schema ====================


class DailyTrendingPapers(BaseModel):
    """单日热门论文数据。

    包含某一天的热门论文列表和统计信息。
    """

    date: str = Field(description="日期，格式 YYYY-MM-DD")
    papers: List[TrendingPaperCard] = Field(description="该日热门论文列表")
    total_that_day: int = Field(description="该日论文总数")


class DailyTrendingResponse(BaseModel):
    """每日热门论文响应。

    按日期分组返回热门论文。
    """

    days: List[DailyTrendingPapers] = Field(description="每日热门论文列表")
    total_days: int = Field(description="返回的天数")
    total_papers: int = Field(description="论文总数")


# ==================== 视频相关 Schema ====================


class VideoBase(BaseModel):
    """视频基础字段"""

    title: str
    video_id: Optional[str] = None
    platform: Optional[str] = None  # douyin, bilibili, youtube
    video_url: Optional[str] = None
    speaker: Optional[str] = None
    duration: Optional[int] = None  # 秒


class VideoCard(VideoBase):
    """视频列表卡片"""

    id: int
    has_analysis: bool = False
    view_count: Optional[int] = None
    tier: Optional[str] = None
    tags: Optional[List[str]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoDetail(VideoCard):
    """视频详情"""

    cover_url: Optional[str] = None
    speaker_id: Optional[str] = None
    publish_date: Optional[datetime] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    description: Optional[str] = None
    transcript: Optional[str] = None
    analysis_report: Optional[str] = None
    analysis_json: Optional[Dict[str, Any]] = None
    knowledge_links: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    md_output_path: Optional[str] = None


class VideoListResponse(BaseModel):
    """视频列表响应"""

    videos: List[VideoCard]
    total: int
    page: int
    page_size: int
    total_pages: int


class VideoAnalysisRequest(BaseModel):
    """视频分析请求"""

    video_id: int = Field(..., description="视频ID")
    force_refresh: bool = Field(default=False, description="是否强制重新分析")


class VideoAnalysisResponse(BaseModel):
    """视频分析响应"""

    video_id: int
    status: str = Field(description="状态: pending, processing, completed, failed")
    report: Optional[str] = Field(default=None, description="分析报告")
    message: str = Field(default="", description="状态消息或错误信息")


class FetchVideoTranscriptRequest(BaseModel):
    """获取视频转录稿请求"""

    url: str = Field(..., description="视频URL")
    title: Optional[str] = Field(default=None, description="标题（可选）")
    speaker: Optional[str] = Field(default=None, description="创作者（可选）")
    create_record: bool = Field(default=True, description="是否创建数据库记录")