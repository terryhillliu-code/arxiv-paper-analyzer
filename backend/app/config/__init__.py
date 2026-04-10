"""应用配置模块。

包含分类优先级、标签映射、Settings 等配置。

注意区分两个概念：
- 分类优先级 (priority): 决定哪些分类值得关注，控制抓取频率
- 论文质量 Tier (A/B/C): 根据论文内容质量评定，与分类无关
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==================== Settings 配置类 ====================


class Settings(BaseSettings):
    """应用配置类。

    所有配置项都可以通过环境变量或 .env 文件设置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API 配置
    anthropic_api_key: str = ""
    dashscope_api_key: str = ""  # 阿里百炼 API Key
    coding_plan_api_key: str = ""  # Coding Plan API Key
    zhipu_api_key: str = ""  # 智谱直连 API Key（支持 glm-5.1 推理模型）
    semantic_scholar_api_key: str = ""  # Semantic Scholar API Key (可选，提高限额)

    # 数据库配置
    database_url: str = "sqlite+aiosqlite:///./data/papers.db"

    # arXiv 抓取配置
    arxiv_fetch_max: int = 50

    # PDF 存储配置
    pdf_storage_path: str = "./data/pdfs"

    # AI 模型配置
    ai_model: str = "qwen3.5-plus"  # 后台任务使用 qwen3.5-plus（快速稳定）
    ai_max_tokens: int = 8000

    # 预定义标签
    predefined_tags: List[str] = [
        "大模型基础架构",
        "GPU硬件架构",
        "AI集群",
        "训练推理框架",
        "代码生成",
        "图像&视频生成",
        "多模态",
        "自然语言处理",
        "计算机视觉",
        "强化学习",
        "知识图谱",
        "推荐系统",
        "语音处理",
        "机器人",
        "自动驾驶",
        "医疗AI",
        "科学计算",
        "数据挖掘",
        "计算机存储故障诊断",
        "安全与隐私",
    ]

    # Obsidian 配置
    obsidian_vault_path: str = Field(
        default="~/Documents/ZhiweiVault",
        description="Obsidian Vault 根目录"
    )
    obsidian_inbox_path: str = Field(
        default="Inbox",
        description="Markdown 输出的 Inbox 子目录"
    )

    # PDF 解析配置
    pdf_parser: str = Field(
        default="auto",
        description="PDF 解析器: pymupdf(快速) | mineru(深度) | auto(智能选择)"
    )
    mineru_cache_dir: str = Field(
        default="./data/mineru_cache",
        description="MinerU 解析结果缓存目录"
    )
    mineru_timeout: int = Field(
        default=1200,
        description="MinerU 解析超时时间(秒)"
    )
    mineru_path: str = Field(
        default="/Users/liufang/zhiwei-rag/mineru-venv/bin/mineru",
        description="MinerU CLI 路径"
    )

    # 外部服务集成配置 (Phase 3)
    rag_python_path: str = Field(
        default="/Users/liufang/zhiwei-rag/venv/bin/python3",
        description="RAG 虚拟环境 Python 路径"
    )
    rag_bridge_path: str = Field(
        default="/Users/liufang/zhiwei-rag/bridge.py",
        description="RAG bridge 脚本路径"
    )
    obsidian_service_url: str = Field(
        default="http://127.0.0.1:8766",
        description="Obsidian 导出服务地址"
    )


@lru_cache
def get_settings() -> Settings:
    """获取配置单例。

    使用 lru_cache 确保配置只加载一次。

    Returns:
        Settings: 应用配置实例
    """
    return Settings()


# ==================== 分类配置 ====================

from app.config.categories import (
    # 新名称
    HIGH_PRIORITY_CATEGORIES,
    MEDIUM_PRIORITY_CATEGORIES,
    LOW_PRIORITY_CATEGORIES,
    get_all_categories,
    get_category_priority,
    get_category_name,
    get_priority_categories,
    get_fetch_frequency,
    CATEGORY_METADATA,
    # 向后兼容
    CORE_CATEGORIES,
    IMPORTANT_CATEGORIES,
    WATCH_CATEGORIES,
)

from app.config.category_mapping import (
    CATEGORY_TO_TAG_MAP,
    get_tags_for_category,
    get_tags_for_categories,
    get_primary_tag_for_category,
    merge_category_tags_with_ai_tags,
    get_categories_for_tag,
)

__all__ = [
    # Settings
    "Settings",
    "get_settings",
    # 分类优先级（新名称）
    "HIGH_PRIORITY_CATEGORIES",
    "MEDIUM_PRIORITY_CATEGORIES",
    "LOW_PRIORITY_CATEGORIES",
    "get_all_categories",
    "get_category_priority",
    "get_category_name",
    "get_priority_categories",
    "get_fetch_frequency",
    "CATEGORY_METADATA",
    # 向后兼容
    "CORE_CATEGORIES",
    "IMPORTANT_CATEGORIES",
    "WATCH_CATEGORIES",
    # 标签映射
    "CATEGORY_TO_TAG_MAP",
    "get_tags_for_category",
    "get_tags_for_categories",
    "get_primary_tag_for_category",
    "merge_category_tags_with_ai_tags",
    "get_categories_for_tag",
]