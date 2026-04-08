"""数据库模型定义模块。

定义 Paper 和 FetchLog 等核心数据模型。
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DeclarativeBase


class Paper(DeclarativeBase):
    """论文数据模型。

    存储从 arXiv 抓取的论文信息及分析结果。
    """

    __tablename__ = "papers"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # arXiv 基本信息
    arxiv_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    institutions: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    categories: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    # 标签与总结
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 时间信息
    publish_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # URL 信息
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    arxiv_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pdf_local_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 全文内容
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 分析结果
    has_analysis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    analysis_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # === 新增字段 ===
    # 内容类型
    content_type: Mapped[str] = mapped_column(
        String(20), default="paper", nullable=False
    )  # paper, article, report

    # 质量等级
    tier: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True
    )  # A, B, C

    # 是否已完整模式分析（仅 Tier A 论文需要）
    full_analysis: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # 分析模式：quick（摘要分析）或 full（全文分析）
    analysis_mode: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )

    # 行动建议（Obsidian 格式）
    action_items: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )

    # 知识关联（双向链接）
    knowledge_links: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )

    # Markdown 输出路径
    md_output_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 热门度分数（综合浏览量、分析状态、时效性）
    popularity_score: Mapped[float] = mapped_column(
        "popularity_score", Float, default=0.0, nullable=False
    )

    # === Semantic Scholar 评分字段 ===
    citation_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    influential_citation_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s2_paper_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # === RAG 同步字段 ===
    rag_indexed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lancedb_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # === Vault 路径追踪字段 ===
    # 记录论文在 Obsidian Vault 的所有位置（支持论文移动后追踪）
    # 示例: ["Inbox/PAPER_xxx.md", "96_Papers_Archive/NLP/PAPER_xxx.md"]
    vault_locations: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Paper(id={self.id}, arxiv_id={self.arxiv_id}, title={self.title[:30]}...)>"


class Video(DeclarativeBase):
    """视频内容数据模型。

    存储抖音/Bilibili等平台的视频信息及分析结果。
    """

    __tablename__ = "videos"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 视频基本信息
    title: Mapped[str] = mapped_column(Text, nullable=False)
    video_id: Mapped[Optional[str]] = mapped_column(
        String(100), index=True, nullable=True
    )  # 平台视频ID（BV号/抖音ID等）
    platform: Mapped[Optional[str]] = mapped_column(
        String(50), index=True, nullable=True
    )  # douyin, bilibili, youtube
    video_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # 原始链接
    cover_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # 封面图

    # 创作者信息
    speaker: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )  # 演讲者/创作者
    speaker_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # 创作者ID

    # 视频元数据
    duration: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 时长（秒）
    publish_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # 发布日期
    view_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 播放量
    like_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 点赞数
    comment_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 评论数

    # 内容
    transcript: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 转录稿
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 简介

    # 分析结果
    has_analysis: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    analysis_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 质量等级
    tier: Mapped[Optional[str]] = mapped_column(
        String(1), index=True, nullable=True
    )  # A, B, C

    # 标签与分类
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # 一级分类

    # 知识关联
    knowledge_links: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    action_items: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    # Markdown 输出
    md_output_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        title_preview = (self.title[:30] + "...") if len(self.title) > 30 else self.title
        return f"<Video(id={self.id}, platform={self.platform}, title={title_preview})>"


class FetchLog(DeclarativeBase):
    """抓取日志模型。

    记录每次 arXiv 抓取操作的详细信息。
    """

    __tablename__ = "fetch_logs"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 抓取参数
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 抓取统计
    total_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_papers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 时间信息
    fetch_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 状态信息
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<FetchLog(id={self.id}, query={self.query}, status={self.status})>"