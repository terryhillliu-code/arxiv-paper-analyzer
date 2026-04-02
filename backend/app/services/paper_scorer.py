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
    - 机构权重 (30分): 作者所属顶级机构（从作者名或摘要提取）
    - 方向热度 (35分): 标题/摘要匹配热门方向（权重提高）
    - 主题相关性 (20分): 与 AI 系统方向匹配度
    - 创新信号 (15分): 标题中的创新关键词

    筛选规则：
    - 总分 >= 25: 入库并分析（阈值降低）
    - 热门关键词匹配 >= 3 个: 自动入库
    """

    # 顶级科技公司
    TOP_TECH_COMPANIES = [
        "google", "deepmind", "meta", "facebook", "microsoft", "openai",
        "anthropic", "nvidia", "apple", "amazon", "byteDance", "bytedance",
        "alibaba", "tencent", "huawei", "baidu", "xiaomi", "mistral",
        "inflection", "character.ai", "scale ai", "stability ai",
        "databricks", "cohere", "ai21", "hugging face",
    ]

    # 顶级学术机构
    TOP_ACADEMIC_INSTITUTIONS = [
        "stanford", "mit", "berkeley", "cmu", "princeton", "harvard",
        "caltech", "cornell", "ucla", "ucl", "oxford", "cambridge",
        "eth zurich", "toronto", "waterloo", "tsinghua", "peking university",
        "pku", "ustc", "shanghai jiao tong", "sjtu", "fudan",
        "national university of singapore", "nus", "kaist",
        "max planck", "inria", "epfl", "uw madison", "uiuc", "gatech",
        "uchicago", "upenn", "columbia", "nyu", "uva",
    ]

    # 热门方向关键词（高权重）- 扩展列表
    HOT_KEYWORDS = [
        # 大模型核心
        "llm", "large language model", "gpt", "transformer", "attention",
        "foundation model", "language model", "gemma", "llama", "mistral",
        "claude", "chatgpt", "palm", "gemini",
        # Agent 相关（高热度）
        "agent", "multi-agent", "autonomous agent", "tool use", "tool calling",
        "function calling", "agentic", "ai agent", "llm agent",
        # 多模态
        "multimodal", "multi-modal", "vision-language", "vlm",
        "video generation", "image generation", "diffusion", "stable diffusion",
        "dall-e", "midjourney", "sora",
        # RAG 与推理（高热度）
        "rag", "retrieval-augmented", "reasoning", "chain-of-thought",
        "cot", "o1", "q*", "inference-time", "test-time compute",
        "search", "retrieval",
        # 训练与优化
        "rlhf", "fine-tuning", "peft", "lora", "quantization",
        "distillation", "pruning", "mixture-of-experts", "moe",
        "training", "optimization", "scaling law",
        # 系统与效率
        "inference", "serving", "deployment", "efficient", "acceleration",
        "harness", "orchestration", "pipeline",
        # 应用领域
        "embodied ai", "robot learning", "ai for science",
        "code generation", "mathematical reasoning", "programming",
        # 新兴热点
        "long context", "context window", "kv cache",
        "speculative decoding", "flash attention",
    ]

    # 超高热度关键词（自动加分）
    SUPER_HOT_KEYWORDS = [
        "llm", "agent", "rag", "multimodal", "diffusion",
        "chain-of-thought", "reasoning", "fine-tuning", "quantization",
        "moe", "mixture-of-experts", "inference", "harness",
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
        "end-to-end", "framework", "system",
    ]

    # 创新信号关键词
    INNOVATION_KEYWORDS = [
        "novel", "new", "first", "propose", "introduce", "present",
        "uncover", "discover", "demonstrate", "achieve", "breakthrough",
        "state-of-the-art", "sota", "best", "superior", "outperform",
        "significant", "revolutionary", "paradigm",
    ]

    # 低质量信号（降低评分）- 更精确的模式
    LOW_QUALITY_SIGNALS = [
        "survey",  # 综述文章
        "a survey",
        "literature review",
        "review paper",
        "a review of",
        "tutorial",
        "introduction to",
        "a study of",
        "an analysis of",
        "preliminary",
        "overview",
        "comprehensive review",
    ]

    # 机构别名映射（从摘要中识别）
    INSTITUTION_ALIASES = {
        "meta ai": "meta",
        "meta platforms": "meta",
        "meta research": "meta",
        "google research": "google",
        "google deepmind": "deepmind",
        "google ai": "google",
        "microsoft research": "microsoft",
        "openai": "openai",
        "anthropic": "anthropic",
        "nvidia research": "nvidia",
        "stanford university": "stanford",
        "mit": "mit",
        "uc berkeley": "berkeley",
        "cmu": "cmu",
        "carnege mellon": "cmu",
    }

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

        # 1. 机构权重 (0-15 分) - 降低权重因为 ArXiv 不返回机构
        institution_score = cls._check_institutions(authors or [], abstract_lower)
        score += institution_score
        if institution_score > 0:
            logger.debug(f"机构得分: {institution_score}")

        # 2. 方向热度 (0-40 分) - 提高权重
        hot_score, matched_hot = cls._check_hot_topics(title_lower, abstract_lower)
        score += hot_score
        if hot_score > 0:
            logger.debug(f"热度得分: {hot_score}")

        # 3. 主题相关性 (0-20 分)
        relevance_score = cls._check_relevance(combined_text)
        score += relevance_score
        if relevance_score > 0:
            logger.debug(f"相关性得分: {relevance_score}")

        # 4. 创新信号 (0-15 分) - 降低权重
        innovation_score = cls._check_innovation(title_lower, abstract_lower)
        score += innovation_score
        if innovation_score > 0:
            logger.debug(f"创新得分: {innovation_score}")

        # 5. 低质量信号扣分
        penalty = cls._check_low_quality(title_lower)
        if penalty > 0:
            score -= penalty
            logger.debug(f"低质量扣分: -{penalty}")

        # 6. 热门关键词数量加分
        hot_count = len(matched_hot)
        if hot_count >= 5:
            score += 10  # 匹配 5+ 热门关键词额外加分
            logger.debug(f"热门关键词数量加分: +10 ({hot_count} 个)")
        elif hot_count >= 3:
            score += 5  # 匹配 3+ 热门关键词额外加分
            logger.debug(f"热门关键词数量加分: +5 ({hot_count} 个)")

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
        threshold: int = 25,  # 降低阈值到 25
    ) -> bool:
        """判断是否应该抓取该论文。

        Args:
            title: 论文标题
            abstract: 论文摘要
            authors: 作者列表
            threshold: 评分阈值，默认 25

        Returns:
            True 表示应入库，False 表示跳过
        """
        # 计算热门关键词匹配
        title_lower = title.lower() if title else ""
        abstract_lower = abstract.lower() if abstract else ""
        _, matched_hot = cls._check_hot_topics(title_lower, abstract_lower)

        # 快速通道：热门关键词匹配 >= 3 个，直接入库
        if len(matched_hot) >= 3:
            logger.info(f"热门关键词快速通道: {title[:50]}... (匹配 {len(matched_hot)} 个)")
            return True

        # 快速通道：超高热度关键词匹配
        for kw in cls.SUPER_HOT_KEYWORDS:
            if kw in title_lower:
                logger.info(f"超高热度关键词快速通道: {title[:50]}... (关键词: {kw})")
                return True

        # 计算完整评分
        score = cls.score(title, abstract, authors)

        # 特殊规则：顶级机构论文自动通过
        if authors and cls._is_top_institution_paper(authors, abstract_lower):
            logger.info(f"顶级机构论文自动通过: {title[:50]}")
            return True

        return score >= threshold

    @classmethod
    def get_initial_tier(cls, score: int) -> str:
        """获取初始 Tier（入库时使用）。

        仅基于内容评分，不考虑引用数（新论文无引用）。

        Args:
            score: 论文评分（0-100）

        Returns:
            Tier 等级 ('A', 'B', 'C')
        """
        if score >= 80:
            return 'A'
        elif score >= 50:
            return 'B'
        else:
            return 'C'

    @classmethod
    def get_dynamic_tier(
        cls,
        score: int,
        citation_count: int = 0,
        days_since_publish: int = 0,
    ) -> str:
        """获取动态 Tier（定期更新时使用）。

        考虑内容评分、引用数和时效性。
        新论文（30天内）保持初始评估，避免频繁变动。
        高分论文（>=85）有保底机制，不会因时效衰减降级。

        Args:
            score: 论文评分（0-100）
            citation_count: 引用数
            days_since_publish: 发布天数

        Returns:
            Tier 等级 ('A', 'B', 'C')
        """
        # 新论文保持初始评估
        if days_since_publish <= 30:
            return cls.get_initial_tier(score)

        # 高分论文保底机制：评分>=85的论文永远保持 Tier A
        # 这类论文即使时效衰减也是高质量研究
        if score >= 85:
            # 只有在没有引用且发布超过1年时，才可能降级到 B
            if citation_count == 0 and days_since_publish > 365:
                return 'B'
            return 'A'

        # 高引用论文保护：引用>=50的论文至少是 Tier B
        if citation_count >= 50 and score >= 40:
            return 'B'

        # 时效衰减
        if days_since_publish <= 90:
            time_factor = 0.95
        elif days_since_publish <= 180:
            time_factor = 0.90
        else:
            time_factor = 0.85

        # 引用加成
        citation_bonus = 0
        if citation_count >= 100:
            citation_bonus = 20
        elif citation_count >= 50:
            citation_bonus = 10
        elif citation_count >= 20:
            citation_bonus = 5
        elif citation_count >= 10:
            citation_bonus = 2

        # 计算最终分数
        final_score = score * time_factor + citation_bonus
        final_score = min(100, final_score)  # 不超过 100

        return cls.get_initial_tier(int(final_score))

    @classmethod
    def _check_institutions(cls, authors: List[str], abstract: str = "") -> int:
        """检查作者机构，返回机构得分（0-15）。

        Args:
            authors: 作者列表
            abstract: 摘要文本（用于提取机构信息）
        """
        if not authors and not abstract:
            return 0

        # 从作者列表和摘要中提取机构信息
        institutions_text = " ".join(authors).lower() if authors else ""

        # 尝试从摘要中提取机构（格式如 "Google Research" 或 "Stanford University"）
        if abstract:
            abstract_lower = abstract.lower()
            # 检查摘要中是否提到机构
            for alias, canonical in cls.INSTITUTION_ALIASES.items():
                if alias in abstract_lower:
                    institutions_text += f" {canonical}"

        # 检查顶级科技公司
        for company in cls.TOP_TECH_COMPANIES:
            if company.lower() in institutions_text:
                logger.debug(f"发现顶级科技公司: {company}")
                return 15

        # 检查顶级学术机构
        for inst in cls.TOP_ACADEMIC_INSTITUTIONS:
            if inst.lower() in institutions_text:
                logger.debug(f"发现顶级学术机构: {inst}")
                return 12

        # 部分匹配
        top_all = cls.TOP_TECH_COMPANIES + cls.TOP_ACADEMIC_INSTITUTIONS
        matches = sum(1 for inst in top_all if inst.lower() in institutions_text)
        if matches > 0:
            return min(10, matches * 5)

        return 0

    @classmethod
    def _is_top_institution_paper(cls, authors: List[str], abstract: str = "") -> bool:
        """检查是否为顶级机构论文。"""
        if not authors and not abstract:
            return False

        # 从作者和摘要中提取机构信息
        institutions_text = " ".join(authors).lower() if authors else ""

        # 从摘要中提取机构
        if abstract:
            abstract_lower = abstract.lower()
            for alias, canonical in cls.INSTITUTION_ALIASES.items():
                if alias in abstract_lower:
                    institutions_text += f" {canonical}"

        # 只检查最顶级的机构
        top_tier = cls.TOP_TECH_COMPANIES[:6]  # Google, DeepMind, Meta, Microsoft, OpenAI, Anthropic
        for inst in top_tier:
            if inst.lower() in institutions_text:
                return True

        return False

    @classmethod
    def _check_hot_topics(cls, title: str, abstract: str) -> tuple:
        """检查热门方向，返回 (热度得分, 匹配的关键词列表)。

        Args:
            title: 标题
            abstract: 摘要

        Returns:
            (得分, 匹配的关键词列表)
        """
        combined = f"{title} {abstract}"

        score = 0
        matched_keywords = []

        for keyword in cls.HOT_KEYWORDS:
            if keyword.lower() in combined:
                matched_keywords.append(keyword)
                # 标题匹配权重更高
                if keyword.lower() in title:
                    score += 12
                else:
                    score += 6

        if matched_keywords:
            logger.debug(f"匹配热门关键词: {matched_keywords[:5]}")

        return min(40, score), matched_keywords

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
    def _check_innovation(cls, title: str, abstract: str = "") -> int:
        """检查创新信号，返回创新得分（0-15）。"""
        score = 0
        combined = f"{title} {abstract}".lower()

        for keyword in cls.INNOVATION_KEYWORDS:
            if keyword.lower() in combined:
                score += 4

        return min(15, score)

    @classmethod
    def _check_low_quality(cls, title: str) -> int:
        """检查低质量信号，返回扣分（0-20）。"""
        penalty = 0
        title_lower = title.lower() if title else ""

        for signal in cls.LOW_QUALITY_SIGNALS:
            if signal.lower() in title_lower:
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
    threshold: int = 25,  # 降低阈值
) -> bool:
    """判断是否抓取论文的便捷函数。"""
    return PaperScorer.should_fetch(title, abstract, authors, threshold)


async def score_with_s2(
    title: str,
    abstract: str,
    authors: Optional[List[str]] = None,
    arxiv_id: str = None,
) -> tuple[int, dict]:
    """使用 Semantic Scholar 数据增强评分。

    Args:
        title: 论文标题
        abstract: 论文摘要
        authors: 作者列表
        arxiv_id: ArXiv ID（用于查询 S2）

    Returns:
        (评分, S2 信息字典)
    """
    # 基础评分
    base_score = PaperScorer.score(title, abstract, authors)

    s2_info = {}
    citation_bonus = 0

    # 如果有 ArXiv ID，查询 Semantic Scholar
    if arxiv_id:
        try:
            from app.services.semantic_scholar_service import s2_service
            info = await s2_service.get_paper_by_arxiv(arxiv_id)

            if info:
                s2_info = {
                    "citation_count": info.citation_count,
                    "influential_citations": info.influential_citation_count,
                    "year": info.year,
                    "venue": info.venue,
                    "authors_with_affiliation": info.authors,
                    "tldr": info.tldr,
                }

                # 引用数加分
                if info.citation_count >= 100:
                    citation_bonus = 15
                elif info.citation_count >= 50:
                    citation_bonus = 10
                elif info.citation_count >= 20:
                    citation_bonus = 5
                elif info.citation_count >= 10:
                    citation_bonus = 3

                # 从 S2 获取机构信息，重新计算机构分
                if info.authors:
                    affiliations = [a.get("affiliation", "") for a in info.authors if a.get("affiliation")]
                    if affiliations:
                        aff_text = " ".join(affiliations).lower()
                        for company in PaperScorer.TOP_TECH_COMPANIES:
                            if company in aff_text:
                                citation_bonus += 10
                                break
                        for inst in PaperScorer.TOP_ACADEMIC_INSTITUTIONS:
                            if inst in aff_text:
                                citation_bonus += 8
                                break

        except Exception as e:
            logger.warning(f"Semantic Scholar 查询失败: {e}")

    final_score = min(100, base_score + citation_bonus)

    return final_score, s2_info