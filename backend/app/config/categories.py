"""ArXiv 分类关注配置。

定义哪些分类需要关注，控制抓取频率。
注意：分类优先级与论文质量 Tier (A/B/C) 无关。

分类优先级：决定抓取频率和分析资源配置
论文 Tier：根据内容质量评定，任何分类的论文都可能是 A/B/C
"""

from enum import Enum
from typing import Dict, List

# ==================== 优先级枚举 ====================

class Priority(str, Enum):
    """分类关注级别枚举。"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


# ==================== 分类关注级别 ====================

# 高关注分类（每日抓取，优先分析资源）
HIGH_PRIORITY_CATEGORIES: List[str] = [
    "cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.NE",
]

# 一般关注分类（每日抓取，标准资源）
MEDIUM_PRIORITY_CATEGORIES: List[str] = [
    "cs.RO", "cs.DC", "cs.CR", "cs.IR", "cs.SE",
]

# 低关注分类（每周抓取，基础资源）
LOW_PRIORITY_CATEGORIES: List[str] = [
    "cs.HC", "stat.ML", "eess.AS", "eess.IV",
]

# ==================== 预计算的查找表 ====================

# 缓存的全部分类列表
_ALL_CATEGORIES: List[str] = HIGH_PRIORITY_CATEGORIES + MEDIUM_PRIORITY_CATEGORIES + LOW_PRIORITY_CATEGORIES

# O(1) 优先级查找表
_PRIORITY_MAP: Dict[str, str] = {
    **{c: Priority.HIGH.value for c in HIGH_PRIORITY_CATEGORIES},
    **{c: Priority.MEDIUM.value for c in MEDIUM_PRIORITY_CATEGORIES},
    **{c: Priority.LOW.value for c in LOW_PRIORITY_CATEGORIES},
}

# ==================== 分类元数据 ====================

# 分类的中文名称和描述
CATEGORY_METADATA = {
    # 高关注
    "cs.AI": {"name": "人工智能", "desc": "AI 算法、智能系统、Agent"},
    "cs.CL": {"name": "自然语言处理", "desc": "语言理解、文本生成、翻译"},
    "cs.LG": {"name": "机器学习", "desc": "学习算法、优化、理论"},
    "cs.CV": {"name": "计算机视觉", "desc": "图像理解、视觉感知"},
    "cs.NE": {"name": "神经计算", "desc": "神经网络、进化算法"},

    # 一般关注
    "cs.RO": {"name": "机器人", "desc": "运动规划、控制、具身智能"},
    "cs.DC": {"name": "分布式计算", "desc": "云计算、集群、并行系统"},
    "cs.CR": {"name": "安全", "desc": "密码学、网络安全、隐私保护"},
    "cs.IR": {"name": "信息检索", "desc": "搜索、推荐、知识检索"},
    "cs.SE": {"name": "软件工程", "desc": "软件开发、测试、维护"},

    # 低关注
    "cs.HC": {"name": "人机交互", "desc": "用户体验、界面设计"},
    "stat.ML": {"name": "统计学习", "desc": "统计学视角的机器学习"},
    "eess.AS": {"name": "语音处理", "desc": "语音识别、合成"},
    "eess.IV": {"name": "图像视频处理", "desc": "信号处理视角的视觉"},
}

# ==================== 辅助函数 ====================

def get_all_categories() -> List[str]:
    """获取所有关注的分类列表。"""
    return _ALL_CATEGORIES


def get_category_priority(category: str) -> str:
    """获取分类的关注级别。

    Returns:
        Priority.HIGH/medium/low/none
    """
    return _PRIORITY_MAP.get(category, Priority.NONE.value)


def get_priority_categories(priority: str) -> List[str]:
    """获取指定关注级别的所有分类。"""
    if priority == Priority.HIGH.value:
        return HIGH_PRIORITY_CATEGORIES
    elif priority == Priority.MEDIUM.value:
        return MEDIUM_PRIORITY_CATEGORIES
    elif priority == Priority.LOW.value:
        return LOW_PRIORITY_CATEGORIES
    return []


def get_category_name(category: str) -> str:
    """获取分类的中文名称。"""
    meta = CATEGORY_METADATA.get(category, {})
    return meta.get("name", category)


def get_fetch_frequency(category: str) -> str:
    """获取分类的抓取频率建议。

    Returns:
        "daily" 或 "weekly"
    """
    priority = get_category_priority(category)
    if priority in ["high", "medium"]:
        return "daily"
    elif priority == "low":
        return "weekly"
    return "never"


# ==================== 向后兼容别名 ====================
# 保留旧名称以兼容现有代码，但标记为 deprecated

CORE_CATEGORIES = HIGH_PRIORITY_CATEGORIES  # deprecated: use HIGH_PRIORITY_CATEGORIES
IMPORTANT_CATEGORIES = MEDIUM_PRIORITY_CATEGORIES  # deprecated: use MEDIUM_PRIORITY_CATEGORIES
WATCH_CATEGORIES = LOW_PRIORITY_CATEGORIES  # deprecated: use LOW_PRIORITY_CATEGORIES