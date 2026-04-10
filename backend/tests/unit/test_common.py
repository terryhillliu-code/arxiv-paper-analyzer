"""通用工具函数测试。"""

import pytest

from app.utils.common import (
    parse_csv_param,
    calculate_total_pages,
    calculate_offset,
)


class TestParseCsvParam:
    """parse_csv_param 测试。"""

    def test_normal_input(self):
        """测试正常输入。"""
        result = parse_csv_param("cs.AI, cs.LG, cs.CL")
        assert result == ["cs.AI", "cs.LG", "cs.CL"]

    def test_with_extra_spaces(self):
        """测试多余空格。"""
        result = parse_csv_param("  cs.AI  ,  cs.LG  ")
        assert result == ["cs.AI", "cs.LG"]

    def test_empty_string(self):
        """测试空字符串。"""
        result = parse_csv_param("")
        assert result is None

    def test_none_input(self):
        """测试 None 输入。"""
        result = parse_csv_param(None)
        assert result is None

    def test_whitespace_only(self):
        """测试仅空白字符（返回空列表，因为输入非空）。"""
        result = parse_csv_param("   ,  ,  ")
        assert result == []  # 非空输入，但过滤后为空列表

    def test_single_value(self):
        """测试单个值。"""
        result = parse_csv_param("cs.AI")
        assert result == ["cs.AI"]

    def test_filters_empty_parts(self):
        """测试过滤空部分。"""
        result = parse_csv_param("cs.AI,,cs.LG,")
        assert result == ["cs.AI", "cs.LG"]


class TestCalculateTotalPages:
    """calculate_total_pages 测试。"""

    def test_exact_multiple(self):
        """测试恰好整除。"""
        assert calculate_total_pages(100, 20) == 5
        assert calculate_total_pages(50, 10) == 5

    def test_not_exact_multiple(self):
        """测试非整除（向上取整）。"""
        assert calculate_total_pages(101, 20) == 6
        assert calculate_total_pages(51, 10) == 6
        assert calculate_total_pages(1, 10) == 1

    def test_zero_total(self):
        """测试总数为零。"""
        assert calculate_total_pages(0, 20) == 0

    def test_zero_page_size(self):
        """测试 page_size 为零。"""
        assert calculate_total_pages(100, 0) == 0
        assert calculate_total_pages(0, 0) == 0

    def test_negative_page_size(self):
        """测试负 page_size。"""
        assert calculate_total_pages(100, -10) == 0

    def test_large_numbers(self):
        """测试大数。"""
        assert calculate_total_pages(10000, 100) == 100
        assert calculate_total_pages(9999, 100) == 100


class TestCalculateOffset:
    """calculate_offset 测试。"""

    def test_first_page(self):
        """测试第一页。"""
        assert calculate_offset(1, 20) == 0

    def test_second_page(self):
        """测试第二页。"""
        assert calculate_offset(2, 20) == 20

    def test_third_page(self):
        """测试第三页。"""
        assert calculate_offset(3, 20) == 40

    def test_large_page_number(self):
        """测试大页码。"""
        assert calculate_offset(100, 10) == 990

    def test_different_page_sizes(self):
        """测试不同 page_size。"""
        assert calculate_offset(1, 50) == 0
        assert calculate_offset(2, 50) == 50
        assert calculate_offset(3, 15) == 30