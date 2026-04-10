"""ArXiv 分类优先级配置。

定义三层分类优先级，控制抓取频率和分析深度。
"""

from typing import List

# ==================== 分类优先级系统 ====================

# Tier 1 - 核心分类（每日抓取，深度分析）
# 这些是 AI 领域最核心的分类，需要最高关注度
CORE_CATEGORIES: List[str] = [
    "cs.AI",   # 人工智能
    "cs.CL",   # 计算语言学 / 自然语言处理
    "cs.LG",   # 机器学习
    "cs.CV",   # 计算机视觉
    "cs.NE",   # 神经与进化计算
]

# Tier 2 - 重要分类（每日抓取，标准分析）
# 这些是重要的技术领域，与 AI 有紧密交叉
IMPORTANT_CATEGORIES: List[str] = [
    "cs.RO",   # 机器人
    "cs.DC",   # 分布式、并行和集群计算
    "cs.CR",   # 密码学与安全
    "cs.IR",   # 信息检索
    "cs.SE",   # 软件工程
]

# Tier 3 - 关注分类（每周抓取，快速分析）
# 这些是相关领域，保持关注但降低频率
WATCH_CATEGORIES: List[str] = [
    "cs.HC",   # 人机交互
    "stat.ML", # 统计机器学习（统计学分类）
    "eess.AS", # 音频和语音信号处理
    "eess.IV", # 图像和视频处理
]

# ==================== 分类元数据 ====================

# 分类的中文名称和描述
CATEGORY_METADATA = {
    # Tier 1
    "cs.AI": {"name": "人工智能", "desc": "AI 算法、智能系统、Agent"},
    "cs.CL": {"name": "自然语言处理", "desc": "语言理解、文本生成、翻译"},
    "cs.LG": {"name": "机器学习", "desc": "学习算法、优化、理论"},
    "cs.CV": {"name": "计算机视觉", "desc": "图像理解、视觉感知"},
    "cs.NE": {"name": "神经计算", "desc": "神经网络、进化算法"},

    # Tier 2
    "cs.RO": {"name": "机器人", "desc": "运动规划、控制、具身智能"},
    "cs.DC": {"name": "分布式计算", "desc": "云计算、集群、并行系统"},
    "cs.CR": {"name": "安全", "desc": "密码学、网络安全、隐私保护"},
    "cs.IR": {"name": "信息检索", "desc": "搜索、推荐、知识检索"},
    "cs.SE": {"name": "软件工程", "desc": "软件开发、测试、维护"},

    # Tier 3
    "cs.HC": {"name": "人机交互", "desc": "用户体验、界面设计"},
    "stat.ML": {"name": "统计学习", "desc": "统计学视角的机器学习"},
    "eess.AS": {"name": "语音处理", "desc": "语音识别、合成"},
    "eess.IV": {"name": "图像视频处理", "desc": "信号处理视角的视觉"},
}

# ==================== 辅助函数 ====================

def get_all_categories() -> List[str]:
    """获取所有关注的分类列表。"""
    return CORE_CATEGORIES + IMPORTANT_CATEGORIES + WATCH_CATEGORIES


def get_category_tier(category: str) -> int:
    """获取分类的优先级层级。

    Returns:
        1: 核心分类
        2: 重要分类
        3: 关注分类
        0: 未关注
    """
    if category in CORE_CATEGORIES:
        return 1
    elif category in IMPORTANT_CATEGORIES:
        return 2
    elif category in WATCH_CATEGORIES:
        return 3
    return 0


def get_tier_categories(tier: int) -> List[str]:
    """获取指定层级的所有分类。

    Args:
        tier: 层级 (1, 2, 3)

    Returns:
        该层级的分类列表
    """
    if tier == 1:
        return CORE_CATEGORIES
    elif tier == 2:
        return IMPORTANT_CATEGORIES
    elif tier == 3:
        return WATCH_CATEGORIES
    return []


def get_category_name(category: str) -> str:
    """获取分类的中文名称。"""
    meta = CATEGORY_METADATA.get(category, {})
    return meta.get("name", category)


def should_deep_analyze(category: str) -> bool:
    """判断是否需要深度分析（全文分析）。

    Tier 1 分类使用深度分析，其他使用快速分析。
    """
    return get_category_tier(category) == 1


def get_fetch_frequency(category: str) -> str:
    """获取分类的抓取频率建议。

    Returns:
        "daily" 或 "weekly"
    """
    tier = get_category_tier(category)
    if tier in [1, 2]:
        return "daily"
    elif tier == 3:
        return "weekly"
    return "never"