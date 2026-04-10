"""应用配置模块。

包含分类优先级、标签映射等配置。

注意区分两个概念：
- 分类优先级 (priority): 决定哪些分类值得关注，控制抓取频率
- 论文质量 Tier (A/B/C): 根据论文内容质量评定，与分类无关
"""

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