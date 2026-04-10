"""通用工具函数模块。"""

from typing import Optional, List


def parse_csv_param(value: Optional[str]) -> Optional[List[str]]:
    """解析逗号分隔的字符串参数。

    Args:
        value: 逗号分隔的字符串，如 "cs.AI,cs.LG"

    Returns:
        去除空白后的列表，如 ["cs.AI", "cs.LG"]，输入为空返回 None
    """
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def calculate_total_pages(total: int, page_size: int) -> int:
    """计算总页数。

    Args:
        total: 总记录数
        page_size: 每页数量

    Returns:
        总页数
    """
    if page_size <= 0:
        return 0
    return (total + page_size - 1) // page_size


def calculate_offset(page: int, page_size: int) -> int:
    """计算分页偏移量。

    Args:
        page: 当前页码（从 1 开始）
        page_size: 每页数量

    Returns:
        偏移量
    """
    return (page - 1) * page_size