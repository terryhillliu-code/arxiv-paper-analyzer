"""分类配置模块单元测试。"""

import pytest
from app.config.categories import (
    Priority,
    HIGH_PRIORITY_CATEGORIES,
    MEDIUM_PRIORITY_CATEGORIES,
    LOW_PRIORITY_CATEGORIES,
    get_all_categories,
    get_category_priority,
    get_priority_categories,
    get_category_name,
    get_fetch_frequency,
    CATEGORY_METADATA,
)


class TestPriorityEnum:
    """Priority 枚举测试。"""

    def test_priority_values(self):
        """测试枚举值。"""
        assert Priority.HIGH.value == "high"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.LOW.value == "low"
        assert Priority.NONE.value == "none"

    def test_priority_is_string(self):
        """测试枚举是字符串类型。"""
        assert isinstance(Priority.HIGH.value, str)


class TestCategoryLists:
    """分类列表测试。"""

    def test_high_priority_categories(self):
        """测试高关注分类列表。"""
        assert "cs.AI" in HIGH_PRIORITY_CATEGORIES
        assert "cs.CL" in HIGH_PRIORITY_CATEGORIES
        assert "cs.LG" in HIGH_PRIORITY_CATEGORIES
        assert "cs.CV" in HIGH_PRIORITY_CATEGORIES
        assert "cs.NE" in HIGH_PRIORITY_CATEGORIES
        assert len(HIGH_PRIORITY_CATEGORIES) == 5

    def test_medium_priority_categories(self):
        """测试一般关注分类列表。"""
        assert "cs.RO" in MEDIUM_PRIORITY_CATEGORIES
        assert "cs.DC" in MEDIUM_PRIORITY_CATEGORIES
        assert "cs.CR" in MEDIUM_PRIORITY_CATEGORIES
        assert "cs.IR" in MEDIUM_PRIORITY_CATEGORIES
        assert "cs.SE" in MEDIUM_PRIORITY_CATEGORIES
        assert len(MEDIUM_PRIORITY_CATEGORIES) == 5

    def test_low_priority_categories(self):
        """测试低关注分类列表。"""
        assert "cs.HC" in LOW_PRIORITY_CATEGORIES
        assert "stat.ML" in LOW_PRIORITY_CATEGORIES
        assert len(LOW_PRIORITY_CATEGORIES) == 4

    def test_no_overlap(self):
        """测试分类列表无重叠。"""
        all_cats = HIGH_PRIORITY_CATEGORIES + MEDIUM_PRIORITY_CATEGORIES + LOW_PRIORITY_CATEGORIES
        assert len(all_cats) == len(set(all_cats))


class TestGetAllCategories:
    """get_all_categories 函数测试。"""

    def test_returns_all_categories(self):
        """测试返回所有分类。"""
        result = get_all_categories()
        assert len(result) == 14
        assert "cs.AI" in result
        assert "cs.RO" in result
        assert "cs.HC" in result

    def test_returns_same_object(self):
        """测试返回缓存对象（性能优化）。"""
        result1 = get_all_categories()
        result2 = get_all_categories()
        assert result1 is result2  # 应该是同一个对象


class TestGetCategoryPriority:
    """get_category_priority 函数测试。"""

    def test_high_priority(self):
        """测试高关注分类。"""
        assert get_category_priority("cs.AI") == "high"
        assert get_category_priority("cs.CV") == "high"

    def test_medium_priority(self):
        """测试一般关注分类。"""
        assert get_category_priority("cs.RO") == "medium"
        assert get_category_priority("cs.DC") == "medium"

    def test_low_priority(self):
        """测试低关注分类。"""
        assert get_category_priority("cs.HC") == "low"
        assert get_category_priority("stat.ML") == "low"

    def test_unknown_category(self):
        """测试未知分类。"""
        assert get_category_priority("cs.UNKNOWN") == "none"
        assert get_category_priority("invalid") == "none"


class TestGetPriorityCategories:
    """get_priority_categories 函数测试。"""

    def test_get_high_categories(self):
        """测试获取高关注分类。"""
        result = get_priority_categories("high")
        assert result == HIGH_PRIORITY_CATEGORIES

    def test_get_medium_categories(self):
        """测试获取一般关注分类。"""
        result = get_priority_categories("medium")
        assert result == MEDIUM_PRIORITY_CATEGORIES

    def test_get_low_categories(self):
        """测试获取低关注分类。"""
        result = get_priority_categories("low")
        assert result == LOW_PRIORITY_CATEGORIES

    def test_invalid_priority(self):
        """测试无效优先级。"""
        result = get_priority_categories("invalid")
        assert result == []


class TestGetCategoryName:
    """get_category_name 函数测试。"""

    def test_known_category(self):
        """测试已知分类。"""
        assert get_category_name("cs.AI") == "人工智能"
        assert get_category_name("cs.RO") == "机器人"

    def test_unknown_category(self):
        """测试未知分类返回原值。"""
        assert get_category_name("unknown") == "unknown"


class TestGetFetchFrequency:
    """get_fetch_frequency 函数测试。"""

    def test_high_priority_daily(self):
        """测试高关注分类每日抓取。"""
        assert get_fetch_frequency("cs.AI") == "daily"

    def test_medium_priority_daily(self):
        """测试一般关注分类每日抓取。"""
        assert get_fetch_frequency("cs.RO") == "daily"

    def test_low_priority_weekly(self):
        """测试低关注分类每周抓取。"""
        assert get_fetch_frequency("cs.HC") == "weekly"

    def test_unknown_never(self):
        """测试未知分类不抓取。"""
        assert get_fetch_frequency("unknown") == "never"


class TestCategoryMetadata:
    """分类元数据测试。"""

    def test_metadata_completeness(self):
        """测试元数据完整性。"""
        all_cats = get_all_categories()
        for cat in all_cats:
            assert cat in CATEGORY_METADATA, f"Missing metadata for {cat}"
            assert "name" in CATEGORY_METADATA[cat]
            assert "desc" in CATEGORY_METADATA[cat]