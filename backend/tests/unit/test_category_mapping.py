"""分类到标签映射模块单元测试。"""

import pytest
from app.config.category_mapping import (
    CATEGORY_TO_TAG_MAP,
    TAG_TO_CATEGORY_MAP,
    get_tags_for_category,
    get_tags_for_categories,
    get_primary_tag_for_category,
    merge_category_tags_with_ai_tags,
    get_categories_for_tag,
)


class TestCategoryToTagMap:
    """分类到标签映射测试。"""

    def test_ai_mapping(self):
        """测试 AI 分类映射。"""
        assert "大模型架构" in CATEGORY_TO_TAG_MAP["cs.AI"]

    def test_ro_mapping(self):
        """测试机器人分类映射。"""
        assert "机器人" in CATEGORY_TO_TAG_MAP["cs.RO"]
        assert "具身智能" in CATEGORY_TO_TAG_MAP["cs.RO"]

    def test_dc_mapping(self):
        """测试分布式计算映射。"""
        assert "AI集群" in CATEGORY_TO_TAG_MAP["cs.DC"]
        assert "分布式训练" in CATEGORY_TO_TAG_MAP["cs.DC"]

    def test_hc_mapping(self):
        """测试人机交互映射。"""
        assert "人机交互" in CATEGORY_TO_TAG_MAP["cs.HC"]


class TestGetTagsForCategory:
    """get_tags_for_category 函数测试。"""

    def test_known_category(self):
        """测试已知分类。"""
        result = get_tags_for_category("cs.AI")
        assert "大模型架构" in result

    def test_unknown_category(self):
        """测试未知分类返回空列表。"""
        result = get_tags_for_category("unknown")
        assert result == []


class TestGetTagsForCategories:
    """get_tags_for_categories 函数测试。"""

    def test_single_category(self):
        """测试单个分类。"""
        result = get_tags_for_categories(["cs.AI"])
        assert "大模型架构" in result

    def test_multiple_categories(self):
        """测试多个分类。"""
        result = get_tags_for_categories(["cs.AI", "cs.RO"])
        assert "大模型架构" in result
        assert "机器人" in result

    def test_deduplication(self):
        """测试去重。"""
        # cs.LG 和 cs.NE 都映射到 "深度学习"
        result = get_tags_for_categories(["cs.LG", "cs.NE"])
        assert result.count("深度学习") == 1

    def test_empty_list(self):
        """测试空列表。"""
        result = get_tags_for_categories([])
        assert result == []


class TestGetPrimaryTagForCategory:
    """get_primary_tag_for_category 函数测试。"""

    def test_known_category(self):
        """测试已知分类返回第一个标签。"""
        assert get_primary_tag_for_category("cs.AI") == "大模型架构"
        assert get_primary_tag_for_category("cs.RO") == "机器人"

    def test_unknown_category(self):
        """测试未知分类返回原值。"""
        assert get_primary_tag_for_category("unknown") == "unknown"


class TestMergeCategoryTagsWithAiTags:
    """merge_category_tags_with_ai_tags 函数测试。"""

    def test_merge_both(self):
        """测试合并分类标签和 AI 标签。"""
        result = merge_category_tags_with_ai_tags(
            categories=["cs.AI", "cs.RO"],
            ai_tags=["深度学习", "强化学习"]
        )
        # 分类标签在前
        assert result[0] == "大模型架构"
        assert "机器人" in result
        # AI 标签在后
        assert "深度学习" in result
        assert "强化学习" in result

    def test_deduplication(self):
        """测试合并时去重。"""
        result = merge_category_tags_with_ai_tags(
            categories=["cs.LG"],
            ai_tags=["深度学习"]  # cs.LG 也映射到 "深度学习"
        )
        assert result.count("深度学习") == 1

    def test_max_five_tags(self):
        """测试最多 5 个标签。"""
        result = merge_category_tags_with_ai_tags(
            categories=["cs.AI", "cs.RO", "cs.DC", "cs.CR"],
            ai_tags=["深度学习", "强化学习", "推荐系统"]
        )
        assert len(result) <= 5

    def test_empty_inputs(self):
        """测试空输入。"""
        result = merge_category_tags_with_ai_tags(
            categories=[],
            ai_tags=[]
        )
        assert result == []


class TestGetCategoriesForTag:
    """get_categories_for_tag 函数测试。"""

    def test_known_tag(self):
        """测试已知标签。"""
        result = get_categories_for_tag("机器人")
        assert "cs.RO" in result

    def test_unknown_tag(self):
        """测试未知标签。"""
        result = get_categories_for_tag("未知标签")
        assert result == []

    def test_multi_category_tag(self):
        """测试映射到多个分类的标签。"""
        result = get_categories_for_tag("深度学习")
        assert "cs.LG" in result
        assert "cs.NE" in result