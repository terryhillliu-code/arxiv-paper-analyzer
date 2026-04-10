"""ArXiv 分类关注配置。

定义哪些分类需要关注，控制抓取频率。
注意：分类优先级与论文质量 Tier (A/B/C) 无关。

分类优先级：决定抓取频率和分析资源配置
论文 Tier：根据内容质量评定，任何分类的论文都可能是 A/B/C
"""

from typing import List

# ==================== 分类关注级别 ====================

# 高关注分类（每日抓取，优先分析资源）
# 这些是核心技术领域，需要最高关注度
HIGH_PRIORITY_CATEGORIES: List[str] = [
    "cs.AI",   # 人工智能
    "cs.CL",   # 计算语言学 / 自然语言处理
    "cs.LG",   # 机器学习
    "cs.CV",   # 计算机视觉
    "cs.NE",   # 神经与进化计算
]

# 一般关注分类（每日抓取，标准资源）
# 这些是重要的技术领域，与 AI 有紧密交叉
MEDIUM_PRIORITY_CATEGORIES: List[str] = [
    "cs.RO",   # 机器人
    "cs.DC",   # 分布式、并行和集群计算
    "cs.CR",   # 密码学与安全
    "cs.IR",   # 信息检索
    "cs.SE",   # 软件工程
]

# 低关注分类（每周抓取，基础资源）
# 这些是相关领域，保持关注但降低频率
LOW_PRIORITY_CATEGORIES: List[str] = [
    "cs.HC",   # 人机交互
    "stat.ML", # 统计机器学习（统计学分类）
    "eess.AS", # 音频和语音信号处理
    "eess.IV", # 图像和视频处理
]

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
    return HIGH_PRIORITY_CATEGORIES + MEDIUM_PRIORITY_CATEGORIES + LOW_PRIORITY_CATEGORIES


def get_category_priority(category: str) -> str:
    """获取分类的关注级别。

    Returns:
        "high": 高关注（每日抓取）
        "medium": 一般关注（每日抓取）
        "low": 低关注（每周抓取）
        "none": 未关注
    """
    if category in HIGH_PRIORITY_CATEGORIES:
        return "high"
    elif category in MEDIUM_PRIORITY_CATEGORIES:
        return "medium"
    elif category in LOW_PRIORITY_CATEGORIES:
        return "low"
    return "none"


def get_priority_categories(priority: str) -> List[str]:
    """获取指定关注级别的所有分类。

    Args:
        priority: "high", "medium", "low"

    Returns:
        该级别的分类列表
    """
    if priority == "high":
        return HIGH_PRIORITY_CATEGORIES
    elif priority == "medium":
        return MEDIUM_PRIORITY_CATEGORIES
    elif priority == "low":
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