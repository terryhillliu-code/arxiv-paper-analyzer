"""ArXiv 分类到主题标签的映射配置。

定义每个 ArXiv 分类自动映射的主题标签。
"""

from typing import List, Dict, Set

# ==================== 分类→标签映射表 ====================

# ArXiv 分类到主题标签的自动映射
# 当论文抓取时，根据分类自动添加这些标签
CATEGORY_TO_TAG_MAP: Dict[str, List[str]] = {
    # Tier 1 - 核心 AI 分类
    "cs.AI": ["大模型架构"],
    "cs.CL": ["NLP与语言处理"],
    "cs.LG": ["深度学习"],
    "cs.CV": ["计算机视觉"],
    "cs.NE": ["深度学习"],

    # Tier 2 - 重要扩展分类
    "cs.RO": ["机器人", "具身智能"],
    "cs.DC": ["AI集群", "分布式训练"],
    "cs.CR": ["安全与隐私"],
    "cs.IR": ["推荐系统", "RAG与知识系统"],
    "cs.SE": ["软件工程"],

    # Tier 3 - 关注分类
    "cs.HC": ["人机交互"],
    "stat.ML": ["深度学习"],
    "eess.AS": ["语音处理"],
    "eess.IV": ["计算机视觉"],

    # 其他相关分类（偶尔出现）
    "cs.AR": ["GPU硬件架构"],      # 硬件架构
    "cs.NI": ["网络架构"],         # 网络与互联网架构
    "cs.SY": ["计算平台"],         # 系统与控制
    "cs.MM": ["多模态智能体"],     # 多媒体
    "cs.MA": ["AI集群"],           # 多智能体系统
    "cs.GR": ["计算机视觉"],       # 图形学
    "math.NA": ["科学计算"],       # 数值分析
}

# ==================== 辅助函数 ====================

def get_tags_for_category(category: str) -> List[str]:
    """获取单个分类对应的标签列表。

    Args:
        category: ArXiv 分类代码（如 "cs.AI"）

    Returns:
        标签列表，如果无映射则返回空列表
    """
    return CATEGORY_TO_TAG_MAP.get(category, [])


def get_tags_for_categories(categories: List[str]) -> List[str]:
    """获取多个分类对应的合并标签列表（去重）。

    Args:
        categories: ArXiv 分类代码列表

    Returns:
        合并后的标签列表（去重，保持顺序）
    """
    seen: Set[str] = set()
    result: List[str] = []

    for cat in categories:
        tags = get_tags_for_category(cat)
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                result.append(tag)

    return result


def get_primary_tag_for_category(category: str) -> str:
    """获取分类的主要标签（第一个）。

    Args:
        category: ArXiv 分类代码

    Returns:
        主要标签，若无映射则返回分类本身
    """
    tags = get_tags_for_category(category)
    if tags:
        return tags[0]
    return category


def merge_category_tags_with_ai_tags(
    categories: List[str],
    ai_tags: List[str]
) -> List[str]:
    """合并分类映射标签和 AI 推断标签（去重）。

    Args:
        categories: 论文的 ArXiv 分类列表
        ai_tags: AI 推断的标签列表

    Returns:
        合并后的标签列表（分类标签在前，AI 标签在后，去重）
    """
    category_tags = get_tags_for_categories(categories)

    seen: Set[str] = set(category_tags)
    result: List[str] = list(category_tags)

    for tag in ai_tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)

    # 限制最多 5 个标签
    return result[:5]


# ==================== 反向映射（标签→分类） ====================

# 标签到可能分类的反向映射（用于推荐）
TAG_TO_CATEGORY_MAP: Dict[str, List[str]] = {
    "大模型架构": ["cs.AI", "cs.CL"],
    "NLP与语言处理": ["cs.CL"],
    "深度学习": ["cs.LG", "cs.NE", "stat.ML"],
    "计算机视觉": ["cs.CV", "eess.IV", "cs.GR"],
    "机器人": ["cs.RO"],
    "具身智能": ["cs.RO", "cs.AI"],
    "AI集群": ["cs.DC", "cs.MA"],
    "分布式训练": ["cs.DC", "cs.LG"],
    "安全与隐私": ["cs.CR"],
    "推荐系统": ["cs.IR"],
    "RAG与知识系统": ["cs.IR", "cs.AI"],
    "软件工程": ["cs.SE"],
    "人机交互": ["cs.HC"],
    "语音处理": ["eess.AS"],
}


def get_categories_for_tag(tag: str) -> List[str]:
    """获取标签可能对应的分类列表。

    Args:
        tag: 主题标签

    Returns:
        可能的分类列表
    """
    return TAG_TO_CATEGORY_MAP.get(tag, [])