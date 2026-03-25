"""论文预筛选评分模块。

在论文入库前评估重要性，过滤低质量论文。
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


class PaperScorer:
    """论文预筛选评分器。

    评分维度（满分 100）：
    - 机构权重 (30分): 作者所属顶级机构
    - 方向热度 (30分): 标题/摘要匹配热门方向
    - 主题相关性 (20分): 与 AI 系统方向匹配度
    - 创新信号 (20分): 标题中的创新关键词

    筛选规则：
    - 总分 >= 35: 入库并分析
    - 总分 < 35: 跳过不入库
    """

    # 顶级科技公司
    TOP_TECH_COMPANIES = [
        "google", "deepmind", "meta", "facebook", "microsoft", "openai",
        "anthropic", "nvidia", "apple", "amazon", "byteDance", "bytedance",
        "alibaba", "tencent", "huawei", "baidu", "xiaomi", "mistral",
        "inflection", "character.ai", "scale ai", "stability ai",
    ]

    # 顶级学术机构
    TOP_ACADEMIC_INSTITUTIONS = [
        "stanford", "mit", "berkeley", "cmu", "princeton", "harvard",
        "caltech", "cornell", "ucla", "ucl", "oxford", "cambridge",
        "eth zurich", "toronto", "waterloo", "tsinghua", "peking university",
        "pku", "ustc", "shanghai jiao tong", "sjtu", "fudan",
        "national university of singapore", "nus", "kaist",
        "max planck", "inria", "epfl",
    ]

    # 热门方向关键词（高权重）
    HOT_KEYWORDS = [
        # 大模型相关
        "llm", "large language model", "gpt", "transformer", "attention",
        "foundation model", "language model",
        # Agent 相关
        "agent", "multi-agent", "autonomous agent", "tool use",
        # 多模态
        "multimodal", "multi-modal", "vision-language", "vlm",
        "video generation", "image generation", "diffusion",
        # RAG 与推理
        "rag", "retrieval-augmented", "reasoning", "chain-of-thought",
        "cot", "o1", "q*",
        # 训练与优化
        "rlhf", "fine-tuning", "peft", "lora", "quantization",
        "distillation", "pruning", "mixture-of-experts", "moe",
        # 应用领域
        "embodied ai", "robot learning", "ai for science",
        "code generation", "mathematical reasoning",
    ]

    # AI 系统方向关键词（相关性）
    AI_SYSTEM_KEYWORDS = [
        "deep learning", "neural network", "machine learning",
        "natural language", "nlp", "computer vision", "speech",
        "reinforcement learning", "generative", "self-supervised",
        "contrastive learning", "representation learning",
        "optimization", "training", "inference", "deployment",
        "efficient", "scaling", "architecture", "benchmark",
        "dataset", "evaluation", "safety", "alignment",
    ]

    # 创新信号关键词
    INNOVATION_KEYWORDS = [
        "novel", "new", "first", "propose", "introduce", "present",
        "uncover", "discover", "demonstrate", "achieve", "breakthrough",
        "state-of-the-art", "sota", "best", "superior", "outperform",
        "significant", "revolutionary", "paradigm",
    ]

    # 低质量信号（降低评分）
    LOW_QUALITY_SIGNALS = [
        "survey", "review", "tutorial", "introduction to",
        "a study of", "an analysis of", "preliminary",
    ]

    @classmethod
    def score(
        cls,
        title: str,
        abstract: str,
        authors: Optional[List[str]] = None,
    ) -> int:
        """计算论文质量评分。

        Args:
            title: 论文标题
            abstract: 论文摘要
            authors: 作者列表（可选，格式如 "John Doe (OpenAI)"）

        Returns:
            质量评分（0-100）
        """
        score = 0

        # 标准化文本
        title_lower = title.lower() if title else ""
        abstract_lower = abstract.lower() if abstract else ""
        combined_text = f"{title_lower} {abstract_lower}"

        # 1. 机构权重 (0-30 分)
        institution_score = cls._check_institutions(authors or [])
        score += institution_score
        if institution_score > 0:
            logger.debug(f"机构得分: {institution_score}")

        # 2. 方向热度 (0-30 分)
        hot_score = cls._check_hot_topics(title_lower, abstract_lower)
        score += hot_score
        if hot_score > 0:
            logger.debug(f"热度得分: {hot_score}")

        # 3. 主题相关性 (0-20 分)
        relevance_score = cls._check_relevance(combined_text)
        score += relevance_score
        if relevance_score > 0:
            logger.debug(f"相关性得分: {relevance_score}")

        # 4. 创新信号 (0-20 分)
        innovation_score = cls._check_innovation(title_lower)
        score += innovation_score
        if innovation_score > 0:
            logger.debug(f"创新得分: {innovation_score}")

        # 5. 低质量信号扣分
        penalty = cls._check_low_quality(title_lower)
        if penalty > 0:
            score -= penalty
            logger.debug(f"低质量扣分: -{penalty}")

        # 确保分数在 0-100 范围内
        score = max(0, min(100, score))

        logger.debug(f"论文评分: {score} | {title[:50]}...")
        return score

    @classmethod
    def should_fetch(
        cls,
        title: str,
        abstract: str,
        authors: Optional[List[str]] = None,
        threshold: int = 35,
    ) -> bool:
        """判断是否应该抓取该论文。

        Args:
            title: 论文标题
            abstract: 论文摘要
            authors: 作者列表
            threshold: 评分阈值，默认 50

        Returns:
            True 表示应入库，False 表示跳过
        """
        score = cls.score(title, abstract, authors)

        # 特殊规则：顶级机构论文自动通过
        if authors and cls._is_top_institution_paper(authors):
            logger.info(f"顶级机构论文自动通过: {title[:50]}")
            return True

        return score >= threshold

    @classmethod
    def _check_institutions(cls, authors: List[str]) -> int:
        """检查作者机构，返回机构得分（0-30）。"""
        if not authors:
            return 0

        # 提取机构信息
        institutions_text = " ".join(authors).lower()

        # 检查顶级科技公司
        for company in cls.TOP_TECH_COMPANIES:
            if company.lower() in institutions_text:
                logger.debug(f"发现顶级科技公司: {company}")
                return 30

        # 检查顶级学术机构
        for inst in cls.TOP_ACADEMIC_INSTITUTIONS:
            if inst.lower() in institutions_text:
                logger.debug(f"发现顶级学术机构: {inst}")
                return 25

        # 部分匹配（如 "Google Research" 但格式不规范）
        top_all = cls.TOP_TECH_COMPANIES + cls.TOP_ACADEMIC_INSTITUTIONS
        matches = sum(1 for inst in top_all if inst.lower() in institutions_text)
        if matches > 0:
            return min(20, matches * 10)

        return 0

    @classmethod
    def _is_top_institution_paper(cls, authors: List[str]) -> bool:
        """检查是否为顶级机构论文。"""
        if not authors:
            return False

        institutions_text = " ".join(authors).lower()

        # 只检查最顶级的机构
        top_tier = cls.TOP_TECH_COMPANIES[:6]  # Google, DeepMind, Meta, Microsoft, OpenAI, Anthropic
        for inst in top_tier:
            if inst.lower() in institutions_text:
                return True

        return False

    @classmethod
    def _check_hot_topics(cls, title: str, abstract: str) -> int:
        """检查热门方向，返回热度得分（0-30）。"""
        combined = f"{title} {abstract}"

        score = 0
        matched_keywords = []

        for keyword in cls.HOT_KEYWORDS:
            if keyword.lower() in combined:
                matched_keywords.append(keyword)
                # 标题匹配权重更高
                if keyword.lower() in title:
                    score += 10
                else:
                    score += 5

        if matched_keywords:
            logger.debug(f"匹配热门关键词: {matched_keywords[:5]}")

        return min(30, score)

    @classmethod
    def _check_relevance(cls, text: str) -> int:
        """检查主题相关性，返回相关性得分（0-20）。"""
        score = 0
        matched = []

        for keyword in cls.AI_SYSTEM_KEYWORDS:
            if keyword.lower() in text:
                matched.append(keyword)
                score += 3

        if matched:
            logger.debug(f"匹配相关关键词: {matched[:5]}")

        return min(20, score)

    @classmethod
    def _check_innovation(cls, title: str) -> int:
        """检查创新信号，返回创新得分（0-20）。"""
        score = 0

        for keyword in cls.INNOVATION_KEYWORDS:
            if keyword.lower() in title:
                score += 5

        return min(20, score)

    @classmethod
    def _check_low_quality(cls, title: str) -> int:
        """检查低质量信号，返回扣分（0-20）。"""
        penalty = 0

        for signal in cls.LOW_QUALITY_SIGNALS:
            if signal.lower() in title:
                penalty += 10

        return min(20, penalty)


# 便捷函数
def score_paper(
    title: str,
    abstract: str,
    authors: Optional[List[str]] = None,
) -> int:
    """计算论文评分的便捷函数。"""
    return PaperScorer.score(title, abstract, authors)


def should_fetch_paper(
    title: str,
    abstract: str,
    authors: Optional[List[str]] = None,
    threshold: int = 35,
) -> bool:
    """判断是否抓取论文的便捷函数。"""
    return PaperScorer.should_fetch(title, abstract, authors, threshold)