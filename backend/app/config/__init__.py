"""应用配置模块。

包含分类优先级、标签映射等配置。
"""

from app.config.categories import (
    CORE_CATEGORIES,
    IMPORTANT_CATEGORIES,
    WATCH_CATEGORIES,
    get_all_categories,
    get_category_tier,
    get_category_name,
    get_tier_categories,
    should_deep_analyze,
    get_fetch_frequency,
    CATEGORY_METADATA,
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
    # 分类优先级
    "CORE_CATEGORIES",
    "IMPORTANT_CATEGORIES",
    "WATCH_CATEGORIES",
    "get_all_categories",
    "get_category_tier",
    "get_category_name",
    "get_tier_categories",
    "should_deep_analyze",
    "get_fetch_frequency",
    "CATEGORY_METADATA",
    # 标签映射
    "CATEGORY_TO_TAG_MAP",
    "get_tags_for_category",
    "get_tags_for_categories",
    "get_primary_tag_for_category",
    "merge_category_tags_with_ai_tags",
    "get_categories_for_tag",
]