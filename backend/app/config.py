"""应用配置管理模块。

使用 pydantic-settings 管理 application 配置，支持从 .env 文件读取。
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # 数据库配置
    database_url: str = "sqlite+aiosqlite:///./data/papers.db"

    # arXiv 抓取配置
    arxiv_fetch_max: int = 50

    # PDF 存储配置
    pdf_storage_path: str = "./data/pdfs"

    # AI 模型配置
    ai_model: str = "qwen3.5-plus"  # 可选: qwen3.5-plus, glm-5, kimi-k2.5, qwen3-max-2026-01-23, MiniMax-M2.5
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
        default=600,
        description="MinerU 解析超时时间(秒)"
    )
    mineru_path: str = Field(
        default="/Users/liufang/zhiwei-rag/mineru-venv/bin/mineru",
        description="MinerU CLI 路径"
    )


@lru_cache
def get_settings() -> Settings:
    """获取配置单例。

    使用 lru_cache 确保配置只加载一次。

    Returns:
        Settings: 应用配置实例
    """
    return Settings()