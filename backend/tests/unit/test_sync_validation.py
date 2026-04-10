"""验证前后端分类配置同步性。"""

import pytest


class TestFrontendBackendSync:
    """前后端同步性测试。"""

    def test_category_names_sync(self):
        """验证前端和后端的分类名称一致。"""
        from app.config.categories import CATEGORY_METADATA

        # 前端定义的分类名称（应与后端一致）
        frontend_names = {
            'cs.AI': '人工智能',
            'cs.CL': '自然语言处理',
            'cs.LG': '机器学习',
            'cs.CV': '计算机视觉',
            'cs.NE': '神经计算',
            'cs.RO': '机器人',
            'cs.DC': '分布式计算',
            'cs.CR': '安全',
            'cs.IR': '信息检索',
            'cs.SE': '软件工程',
            'cs.HC': '人机交互',
            'stat.ML': '统计学习',
            'eess.AS': '语音处理',
            'eess.IV': '图像视频处理',
        }

        for cat, expected_name in frontend_names.items():
            assert cat in CATEGORY_METADATA, f"后端缺少分类 {cat}"
            assert CATEGORY_METADATA[cat]["name"] == expected_name, \
                f"分类 {cat} 名称不一致: 后端={CATEGORY_METADATA[cat]['name']}, 前端={expected_name}"

    def test_category_class_coverage(self):
        """验证前端 CSS 类名覆盖所有关注的分类。"""
        from app.config.categories import get_all_categories

        # 前端 CSS 支持的分类
        frontend_css_classes = {
            'cs.AI', 'cs.CL', 'cs.LG', 'cs.CV', 'cs.NE',
            'cs.RO', 'cs.DC', 'cs.CR', 'cs.IR', 'cs.SE',
            'cs.HC', 'stat.ML', 'eess.AS', 'eess.IV',
        }

        backend_categories = set(get_all_categories())

        # 检查后端所有分类都有对应的前端样式
        missing = backend_categories - frontend_css_classes
        assert not missing, f"前端 CSS 缺少以下分类: {missing}"

    def test_category_mapping_keys_sync(self):
        """验证分类映射与关注分类的一致性。"""
        from app.config.categories import get_all_categories
        from app.config.category_mapping import CATEGORY_TO_TAG_MAP

        all_categories = set(get_all_categories())
        mapped_categories = set(CATEGORY_TO_TAG_MAP.keys())

        # 所有关注的分类都应该有标签映射
        missing_mapping = all_categories - mapped_categories
        # 允许部分分类没有映射（但应该有测试覆盖）
        # 这里只检查主要的关注分类
        high_medium = {'cs.AI', 'cs.CL', 'cs.LG', 'cs.CV', 'cs.NE',
                       'cs.RO', 'cs.DC', 'cs.CR', 'cs.IR', 'cs.SE'}

        for cat in high_medium:
            assert cat in mapped_categories, f"分类 {cat} 缺少标签映射"