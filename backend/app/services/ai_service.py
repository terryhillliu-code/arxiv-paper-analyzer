"""AI 服务模块。

支持多种 AI API：
- 阿里百炼 API (glm-5, qwen-plus 等)
- 智谱直连 API (glm-5.1, glm-5 等)
- Anthropic Claude API
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI, APIError, APIConnectionError, RateLimitError
import anthropic
import httpx

from app.config import get_settings
from app.prompts.templates import (
    ANALYSIS_JSON_PROMPT,
    QUICK_MODE_JSON_PROMPT,
    DEEP_ANALYSIS_PROMPT,
    QUICK_MODE_ANALYSIS_PROMPT,
    PREDEFINED_TAGS,
    SUMMARY_PROMPT,
    TIER_REEVALUATION_PROMPT,
    VIDEO_ANALYSIS_PROMPT,
    VIDEO_JSON_PROMPT,
    BATCH_LIGHT_PROMPT,
    DETAIL_PROMPT,
)
from app.services.guardrails import analysis_guardrail, CheckResult

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5.0  # 秒
RETRY_BACKOFF = 2.0  # 指数退避因子


class AIService:
    """AI 分析服务。

    支持 Coding Plan API (OpenAI 兼容)、智谱直连 API 和 Anthropic Claude API。
    """

    # Coding Plan API 支持的模型（阿里百炼代理）
    CODING_PLAN_MODELS = ["qwen3.5-plus", "glm-5", "kimi-k2.5", "qwen3-max-2026-01-23", "MiniMax-M2.5"]

    # 百炼 API 支持的模型 (备用)
    DASHSCOPE_MODELS = ["qwen-plus", "qwen-turbo", "qwen-max"]

    # 智谱直连 API 支持的模型（推理模型）
    ZHIPU_MODELS = ["glm-5.1", "glm-5-turbo", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5"]

    # 推理模型（返回 reasoning_content）
    REASONING_MODELS = ["glm-5.1", "glm-5-turbo", "glm-5"]

    def __init__(self):
        """初始化 AI 客户端。"""
        settings = get_settings()
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

        # 推理模型需要更长超时
        if self.model in self.REASONING_MODELS:
            self.timeout = 300  # 推理模型 5 分钟超时
        else:
            self.timeout = 180  # 默认 3 分钟超时（阶段2需要更长）

        # 根据模型选择客户端
        if self.model in self.ZHIPU_MODELS:
            # 使用智谱直连 API（支持推理模型）
            self.client_type = "zhipu"
            # 从环境变量或配置获取智谱 API Key
            zhipu_api_key = os.environ.get("ZHIPU_API_KEY", settings.zhipu_api_key or "")
            self.client = OpenAI(
                api_key=zhipu_api_key,
                base_url="https://open.bigmodel.cn/api/paas/v4",
                timeout=self.timeout,
            )
            logger.info(f"使用智谱直连 API，模型: {self.model}, 超时: {self.timeout}s")
        elif self.model in self.CODING_PLAN_MODELS:
            # 使用 Coding Plan API (OpenAI 兼容格式)
            self.client_type = "coding_plan"
            self.client = OpenAI(
                api_key=settings.coding_plan_api_key,
                base_url="https://coding.dashscope.aliyuncs.com/v1",
                timeout=self.timeout,
            )
            logger.info(f"使用 Coding Plan API，模型: {self.model}")
        elif self.model in self.DASHSCOPE_MODELS:
            # 使用百炼 API (OpenAI 兼容格式)
            self.client_type = "dashscope"
            self.client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=self.timeout,
            )
            logger.info(f"使用百炼 API，模型: {self.model}")
        else:
            # 使用 Anthropic API
            self.client_type = "anthropic"
            self.client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key,
                timeout=self.timeout,
            )
            logger.info(f"使用 Anthropic API，模型: {self.model}")

    def _call_api(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """统一调用 AI API，带重试机制。

        Args:
            prompt: 输入提示词
            max_tokens: 最大输出 token 数

        Returns:
            模型响应文本

        Raises:
            最后一次重试失败后抛出异常
        """
        max_tokens = max_tokens or self.max_tokens
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                if self.client_type in ["zhipu", "coding_plan", "dashscope"]:
                    # 智谱、Coding Plan、百炼 API 都使用 OpenAI 兼容格式
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                    # 推理模型可能返回 reasoning_content
                    content = response.choices[0].message.content or ""
                    # 检查是否有 reasoning_content（智谱推理模型）
                    if hasattr(response.choices[0].message, 'reasoning_content'):
                        reasoning = response.choices[0].message.reasoning_content or ""
                        if reasoning:
                            logger.debug(f"推理内容长度: {len(reasoning)} 字符")
                    return content
                else:
                    # Anthropic API
                    message = self.client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    # 处理不同的 content block 类型
                    response_text = ""
                    for block in message.content:
                        if hasattr(block, "text"):
                            response_text += block.text
                        elif hasattr(block, "content"):
                            response_text += str(block.content)
                    return response_text

            except (APIConnectionError, APIError) as e:
                last_error = e
                delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(f"API 调用失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"等待 {delay:.1f} 秒后重试...")
                    time.sleep(delay)

            except RateLimitError as e:
                last_error = e
                delay = RETRY_DELAY * 4  # 限流时等待更长时间
                logger.warning(f"API 限流: {e}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"等待 {delay:.1f} 秒后重试...")
                    time.sleep(delay)

            except Exception as e:
                last_error = e
                logger.error(f"API 调用未知错误: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)

        # 所有重试都失败
        raise RuntimeError(f"API 调用失败，已重试 {MAX_RETRIES} 次: {last_error}")

    async def generate_summary(
        self,
        title: str,
        authors: List[str],
        abstract: str,
        categories: List[str],
    ) -> Dict[str, Any]:
        """生成论文摘要信息。

        包括标签匹配、机构推断和一句话总结。

        Args:
            title: 论文标题
            authors: 作者列表
            abstract: 摘要
            categories: arXiv 分类列表

        Returns:
            包含 tags, institutions, summary 的字典
        """
        try:
            # 格式化提示词
            prompt = SUMMARY_PROMPT.format(
                title=title,
                authors=", ".join(authors) if authors else "未知",
                abstract=abstract or "无摘要",
                categories=", ".join(categories) if categories else "未分类",
                tags_library=", ".join(PREDEFINED_TAGS),
            )

            # 调用 AI API (在线程池中运行，避免阻塞事件循环)
            response_text = await asyncio.to_thread(self._call_api, prompt, max_tokens=1024)
            result = self._parse_json(response_text)

            # 验证 tags 是否在预设列表中
            if "tags" in result:
                valid_tags = [tag for tag in result["tags"] if tag in PREDEFINED_TAGS]
                result["tags"] = valid_tags
            else:
                result["tags"] = []

            # 确保其他字段存在
            if "institutions" not in result:
                result["institutions"] = []
            if "summary" not in result:
                result["summary"] = ""

            logger.info(f"摘要生成成功: {title[:30]}...")
            return result

        except Exception as e:
            logger.error(f"生成摘要失败: {e}", exc_info=True)
            return {
                "tags": [],
                "institutions": [],
                "summary": "",
            }

    async def generate_deep_analysis(
        self,
        title: str,
        authors: List[str],
        institutions: List[str],
        publish_date: str,
        categories: List[str],
        arxiv_url: str,
        pdf_url: str,
        content: str,
        quick_mode: bool = False,
        citation_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """生成论文深度分析报告。

        Args:
            title: 论文标题
            authors: 作者列表
            institutions: 机构列表
            publish_date: 发布日期
            categories: arXiv 分类列表
            arxiv_url: arXiv 链接
            pdf_url: PDF 链接
            content: 论文全文内容
            quick_mode: 是否快速模式
            citation_count: 引用数（用于 tier 评估）

        Returns:
            包含 report 和 analysis_json 的字典
        """
        try:
            # ========== 防护层：分析前检查 ==========
            pre_check = analysis_guardrail.pre_analysis_check(
                quick_mode=quick_mode,
                content=content,
                abstract="",  # 摘要已在调用前处理
                title=title,
            )
            if not pre_check.valid:
                logger.warning(f"分析前检查警告: {pre_check.warnings}")
                # 如果有警告但不是致命错误，继续执行
                for warning in pre_check.warnings:
                    logger.warning(warning)

            # 判断是否是新论文（三个月内）
            from datetime import datetime, timedelta
            is_new_paper = False
            if publish_date and publish_date != "未知":
                try:
                    pub_dt = datetime.fromisoformat(publish_date.replace('Z', '+00:00').replace('+00:00', ''))
                    if (datetime.now(pub_dt.tzinfo) - pub_dt) < timedelta(days=90):
                        is_new_paper = True
                except:
                    pass

            # 如果内容超过 60000 字符则截断
            max_content_length = 60000
            if len(content) > max_content_length:
                content = content[:max_content_length]
                logger.warning(f"内容已截断至 {max_content_length} 字符")

            # 格式化提示词（快速模式使用专门的 prompt）
            if quick_mode:
                prompt = QUICK_MODE_ANALYSIS_PROMPT.format(
                    title=title,
                    authors=", ".join(authors) if authors else "未知",
                    institutions=", ".join(institutions) if institutions else "未知",
                    publish_date=publish_date or "未知",
                    categories=", ".join(categories) if categories else "未分类",
                    arxiv_url=arxiv_url or "",
                    content=content,
                )
            else:
                prompt = DEEP_ANALYSIS_PROMPT.format(
                    title=title,
                    authors=", ".join(authors) if authors else "未知",
                    institutions=", ".join(institutions) if institutions else "未知",
                    publish_date=publish_date or "未知",
                    categories=", ".join(categories) if categories else "未分类",
                    arxiv_url=arxiv_url or "",
                    pdf_url=pdf_url or "",
                    content=content,
                )

            # 调用 AI API (在线程池中运行，避免阻塞事件循环)
            logger.info(f"开始生成深度分析: {title[:30]}...")
            # 快速模式使用更少的 token
            max_tokens = 4000 if quick_mode else self.max_tokens
            report = await asyncio.to_thread(self._call_api, prompt, max_tokens=max_tokens)

            # 移除 AI 自动生成的论文大纲章节（大纲信息从 analysis_json.outline 获取）
            report = self._strip_outline_section(report)

            logger.info(f"深度分析报告生成成功: {len(report)} 字符")

            # 快速模式：用推理模型异步提取 JSON（带重试）
            if quick_mode:
                from openai import OpenAI as OpenAIClient
                settings = get_settings()

                try:
                    # 使用 Coding Plan API (qwen3.5-plus)，统一限流管理
                    quick_model = "qwen3.5-plus"
                    quick_client = OpenAIClient(
                        api_key=settings.coding_plan_api_key,
                        base_url="https://coding.dashscope.aliyuncs.com/v1",
                        timeout=120,  # Coding Plan 响应更快
                    )
                    prompt_json = QUICK_MODE_JSON_PROMPT.format(
                        report=report,
                        citation_count=citation_count if citation_count else "未知（新论文）",
                        institutions=", ".join(institutions) if institutions else "未知",
                        publish_date=publish_date or "未知",
                        is_new_paper="是（忽略引用数维度）" if is_new_paper else "否",
                    )

                    # 重试机制：最多 3 次
                    MAX_RETRIES = 3
                    analysis_json = {}
                    for attempt in range(MAX_RETRIES):
                        def _sync_json_call():
                            return quick_client.chat.completions.create(
                                model=quick_model,
                                messages=[{"role": "user", "content": prompt_json}],
                                max_tokens=8192,  # 增加以避免截断
                            )

                        response = await asyncio.to_thread(_sync_json_call)
                        response_text = response.choices[0].message.content or ""
                        analysis_json = self._parse_json(response_text)

                        # 验证关键字段（快速模式检查长度）
                        is_valid, missing = self.validate_analysis_json(analysis_json, check_length=True)
                        if is_valid:
                            break
                        logger.warning(f"JSON 验证失败 (尝试 {attempt+1}/{MAX_RETRIES})，缺失: {missing}")

                        # 如果是长度问题，尝试扩展总结（最后一次尝试时）
                        if attempt == MAX_RETRIES - 1 and "one_line_summary太短" in str(missing):
                            logger.warning("总结太短，尝试扩展...")
                            expand_prompt = f"""请将以下论文总结扩展到80-150字（中文字符），必须包含：研究问题、方法思路、具体结论。

原始总结：{analysis_json.get('one_line_summary', '')}

要求：展开描述每个要素，用完整句子，不要过于精简。直接输出扩展后的总结文本，不要输出JSON。"""
                            try:
                                expand_response = quick_client.chat.completions.create(
                                    model=quick_model,
                                    messages=[{"role": "user", "content": expand_prompt}],
                                    max_tokens=300,
                                )
                                expanded = expand_response.choices[0].message.content or ""
                                if len(expanded) >= 80:
                                    analysis_json["one_line_summary"] = expanded.strip()
                                    logger.info(f"总结扩展成功: {len(expanded)}字")
                            except Exception as e:
                                logger.warning(f"总结扩展失败: {e}")

                    # 补充默认值
                    DEFAULT_VALUES = {
                        "one_line_summary": "", "outline": [], "key_contributions": [],
                        "strengths": [], "weaknesses": [], "methodology": "",
                        "datasets": [], "metrics": [], "future_directions": [],
                        "overall_rating": "B", "recommendation": "",
                        "related_work": {"key_references": [], "similar_papers": []},
                        "action_items": [], "knowledge_links": [], "tier": "B", "tags": [],
                    }
                    for key, default in DEFAULT_VALUES.items():
                        if key not in analysis_json:
                            analysis_json[key] = default

                    # ========== 防护层：分析后验证 ==========
                    post_check = analysis_guardrail.post_analysis_validate(
                        analysis_json=analysis_json,
                        quick_mode=quick_mode,
                        content_used=content,
                    )
                    if not post_check.valid:
                        logger.warning(f"分析后验证警告: {post_check.warnings}")
                        for warning in post_check.warnings:
                            logger.warning(warning)

                    # ========== 防护层：捏造检测 ==========
                    fabric_check = analysis_guardrail.detect_fabrication(
                        analysis_json=analysis_json,
                        quick_mode=quick_mode,
                    )
                    if not fabric_check.valid:
                        logger.error(f"⚠️ 检测到疑似捏造: {fabric_check.warnings}")
                        # 如果检测到捏造，降级处理
                        if fabric_check.warnings:
                            logger.warning("降级处理：简化 outline，移除公式符号")
                            analysis_json["outline"] = []  # 清空可疑 outline

                    logger.info(f"快速模式: JSON提取完成 tier={analysis_json.get('tier', 'B')}")
                except Exception as e:
                    logger.warning(f"JSON提取失败: {e}")
                    analysis_json = {"tier": "B", "tags": [], "one_line_summary": "", "outline": []}
            else:
                # 提取结构化数据
                analysis_json = await self._extract_analysis_json(
                    report,
                    institutions=institutions,
                    publish_date=publish_date,
                    citation_count=citation_count,
                    is_new_paper=is_new_paper,
                )

            # === 新增：生成 Markdown 输出 ===
            md_output = self._generate_markdown_output(
                title=title,
                authors=authors,
                institutions=institutions,
                publish_date=publish_date,
                categories=categories,
                arxiv_url=arxiv_url,
                pdf_url=pdf_url,
                report=report,
                analysis_json=analysis_json,
            )

            return {
                "report": report,
                "analysis_json": analysis_json,
                "md_output": md_output,  # 新增
            }

        except Exception as e:
            logger.error(f"生成深度分析失败: {e}", exc_info=True)
            return {
                "report": "",
                "analysis_json": {},
            }

    async def reevaluate_tier(
        self,
        title: str,
        abstract: str,
        citation_count: Optional[int] = None,
        publish_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """重新评估论文的 tier 等级。

        Args:
            title: 论文标题
            abstract: 摘要
            citation_count: 引用数
            publish_date: 发布日期文本

        Returns:
            包含 tier 和 reason 的字典
        """
        try:
            # 判断是否新论文（三个月内）
            from datetime import datetime, timedelta
            is_new_paper = False
            if publish_date and publish_date != "未知":
                try:
                    # 尝试多种日期格式
                    pub_dt = None
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
                        try:
                            pub_dt = datetime.strptime(publish_date.split(' ')[0].split('T')[0], "%Y-%m-%d")
                            break
                        except:
                            continue
                    
                    if pub_dt and (datetime.now() - pub_dt) < timedelta(days=90):
                        is_new_paper = True
                except:
                    pass

            prompt = TIER_REEVALUATION_PROMPT.format(
                title=title,
                abstract=abstract[:1000] if abstract else "无",
                citation_count=citation_count if citation_count is not None else "未知",
                publish_date=publish_date or "未知",
                is_new_paper="是" if is_new_paper else "否",
            )

            # 使用 AI 调用
            response_text = await asyncio.to_thread(self._call_api, prompt, max_tokens=200)
            result = self._parse_json(response_text)

            return {
                "tier": result.get("tier", "B"),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.error(f"重新评估 tier 失败: {e}")
            return {"tier": "B", "reason": str(e)}

    async def _extract_analysis_json(
        self,
        report: str,
        institutions: List[str] = None,
        publish_date: str = None,
        citation_count: int = None,
        is_new_paper: bool = False,
    ) -> Dict[str, Any]:
        """从分析报告中提取结构化数据。

        Args:
            report: Markdown 格式的分析报告
            institutions: 机构列表（用于 tier 评估）
            publish_date: 发布日期（用于 tier 评估）
            citation_count: 引用数（用于 tier 评估）
            is_new_paper: 是否是新论文（三个月内）

        Returns:
            结构化的分析数据字典，确保关键字段存在
        """
        # 定义默认值
        DEFAULT_VALUES = {
            "one_line_summary": "",
            "outline": [],
            "key_contributions": [],
            "strengths": [],
            "weaknesses": [],
            "methodology": "",
            "datasets": [],
            "metrics": [],
            "future_directions": [],
            "overall_rating": "B",
            "recommendation": "",
            "related_work": {"key_references": [], "similar_papers": []},
            "action_items": [],
            "knowledge_links": [],
            "tier": "B",
            "tags": [],
        }

        try:
            # 格式化提示词
            prompt = ANALYSIS_JSON_PROMPT.format(
                report=report,
                citation_count=citation_count if citation_count else "未知（新论文）",
                institutions=", ".join(institutions) if institutions else "未知",
                publish_date=publish_date or "未知",
                is_new_paper="是（忽略引用数维度）" if is_new_paper else "否",
            )

            # 调用 AI API（增加 token 限制以容纳完整 JSON）(在线程池中运行)
            response_text = await asyncio.to_thread(self._call_api, prompt, max_tokens=4096)
            result = self._parse_json(response_text)

            # 合并默认值，确保所有字段存在
            for key, default_value in DEFAULT_VALUES.items():
                if key not in result or result[key] is None:
                    result[key] = default_value
                    logger.warning(f"字段 '{key}' 缺失，使用默认值")
                elif isinstance(default_value, list) and not isinstance(result[key], list):
                    # 如果期望是列表但返回不是，转换为列表
                    result[key] = [result[key]] if result[key] else default_value

            # 验证 outline 格式
            if result.get("outline"):
                outline_valid = self._validate_outline(result["outline"])
                if not outline_valid:
                    logger.warning("outline 格式无效，使用空列表")
                    result["outline"] = []

            # 验证 related_work 格式
            if not isinstance(result.get("related_work"), dict):
                result["related_work"] = {"key_references": [], "similar_papers": []}
            else:
                if "key_references" not in result["related_work"]:
                    result["related_work"]["key_references"] = []
                if "similar_papers" not in result["related_work"]:
                    result["related_work"]["similar_papers"] = []

            # ========== 防护层：分析后验证（完整模式） ==========
            post_check = analysis_guardrail.post_analysis_validate(
                analysis_json=result,
                quick_mode=False,  # 完整模式
                content_used=report,
            )
            if not post_check.valid:
                logger.warning(f"完整模式分析后验证警告: {post_check.warnings}")
                for warning in post_check.warnings:
                    logger.warning(warning)

            logger.info(f"结构化数据提取成功: outline={len(result.get('outline', []))} 章节, "
                       f"contributions={len(result.get('key_contributions', []))} 条")
            return result

        except Exception as e:
            logger.error(f"提取结构化数据失败: {e}", exc_info=True)
            return DEFAULT_VALUES.copy()

    def _generate_markdown_output(
        self,
        title: str,
        authors: List[str],
        institutions: List[str],
        publish_date: str,
        categories: List[str],
        arxiv_url: str,
        pdf_url: str,
        report: str,
        analysis_json: Dict[str, Any],
    ) -> str:
        """生成 Obsidian 格式的 Markdown 输出。

        Args:
            各参数来自分析结果

        Returns:
            完整的 Markdown 内容
        """
        # 提取字段
        one_line_summary = analysis_json.get("one_line_summary", "")
        key_contributions = analysis_json.get("key_contributions", [])
        strengths = analysis_json.get("strengths", [])
        weaknesses = analysis_json.get("weaknesses", [])
        future_directions = analysis_json.get("future_directions", [])
        action_items = analysis_json.get("action_items", [])
        knowledge_links = analysis_json.get("knowledge_links", [])
        tier = analysis_json.get("tier", "B")
        tags = analysis_json.get("tags", [])
        outline = analysis_json.get("outline", [])

        # 构建 YAML 元数据
        yaml_front = f"""---
title: "{title}"
source_url: "{arxiv_url}"
date: {publish_date or "未知"}
type: paper

tags: {tags}
tier: {tier}
methodology: "{analysis_json.get('methodology', '')}"

related: {knowledge_links}
institutions: {institutions}

overall_rating: {analysis_json.get("overall_rating", "B")}
---
"""
        # 构建正文
        content = f"""# {title}

> **内容等级**：{"⭐⭐⭐ 深度干货" if tier == "A" else "⭐⭐ 实用向导" if tier == "B" else "⭐ 一般参考"} | **综合评级**：{analysis_json.get("overall_rating", "B")}

## 📋 基础信息

| 项目 | 内容 |
|------|------|
| 作者 | {", ".join(authors) if authors else "未知"} |
| 机构 | {", ".join(institutions) if institutions else "未知"} |
| 发布日期 | {publish_date or "未知"} |
| 来源 | [{arxiv_url}]({arxiv_url}) |

## 💡 一句话总结

{one_line_summary}

{report}

## ✅ 行动建议

{self._render_action_items(action_items)}

## 🔗 知识关联

{self._render_knowledge_links(knowledge_links)}

## 📚 参考资料

- [{title}]({arxiv_url})
"""
        return yaml_front + "\n" + content

    def _render_outline(self, outline: List[Dict], level: int = 0) -> str:
        """递归渲染大纲为 Markdown 列表。"""
        if not outline:
            return "待补充"

        lines = []
        indent = "    " * level  # 每层缩进4空格
        for item in outline:
            title = item.get('title', '')
            if title:
                lines.append(f"{indent}- {title}")
            children = item.get('children', [])
            if children:
                lines.append(self._render_outline(children, level + 1))
        return "\n".join(lines)

    def _strip_outline_section(self, report: str) -> str:
        """移除报告中的论文大纲章节。

        AI 可能会自动生成 "### 📑 论文大纲" 章节，
        但大纲信息应该从 analysis_json.outline 结构化数据中获取。
        """
        original_len = len(report)

        # 匹配并移除 "### 📑 论文大纲" 到下一个 "###" 之间的内容
        pattern = r'### 📑 论文大纲\s*\n.*?(?=###)'
        report = re.sub(pattern, '', report, flags=re.DOTALL)

        # 也移除其他可能的大纲格式
        other_patterns = [
            r'### 论文大纲\s*\n.*?(?=###)',
            r'## 论文大纲\s*\n.*?(?=##|###)',
            r'# 论文大纲\s*\n.*?(?=#)',
        ]
        for p in other_patterns:
            report = re.sub(p, '', report, flags=re.DOTALL)

        new_len = len(report.strip())
        if original_len != new_len:
            logger.info(f"已移除论文大纲章节，报告长度从 {original_len} 减少到 {new_len}")

        return report.strip()

    def _render_action_items(self, items: List[str]) -> str:
        """渲染行动建议为 checkbox 列表。"""
        if not items:
            return "- [ ] 待补充"
        # 确保 items 是列表
        if isinstance(items, str):
            items = [items]
        return "\n".join([f"- [ ] {item}" for item in items])

    def _render_knowledge_links(self, links) -> str:
        """渲染知识关联。"""
        if not links:
            return "待补充"
        # 确保 links 是列表
        if isinstance(links, str):
            links = [links]
        # 处理可能的嵌套列表
        flattened = []
        for link in links:
            if isinstance(link, list):
                flattened.extend(link)
            elif isinstance(link, str):
                flattened.append(link)
        return " · ".join([f"[[{link.strip('[]')}]]" for link in flattened if isinstance(link, str)])

    def _validate_outline(self, outline: List[Dict]) -> bool:
        """验证 outline 格式是否正确。

        Args:
            outline: 大纲数据

        Returns:
            是否有效
        """
        if not outline or not isinstance(outline, list):
            return False

        for item in outline:
            if not isinstance(item, dict):
                return False
            if "title" not in item:
                return False
            # 递归验证 children
            if "children" in item and item["children"]:
                if not self._validate_outline(item["children"]):
                    return False

        return True

    def _quick_extract_json(self, report: str, title: str, categories: List[str]) -> Dict[str, Any]:
        """快速提取 JSON（无需二次 AI 调用）。

        使用正则从报告中提取基本信息。
        """
        # 默认值
        result = {
            "one_line_summary": "",
            "tier": "B",
            "tags": [],
            "key_contributions": [],
            "outline": [],
        }

        # 尝试提取一句话总结
        summary_match = re.search(r'(?:一句话总结|One-line Summary)[:：]\s*(.+?)(?:\n|$)', report)
        if summary_match:
            result["one_line_summary"] = summary_match.group(1).strip()

        # 尝试提取 tier
        tier_match = re.search(r'(?:内容等级|Tier)[:：]\s*([ABC])', report)
        if tier_match:
            result["tier"] = tier_match.group(1)

        # 根据 categories 推断 tags
        category_tags = {
            "cs.CV": "计算机视觉",
            "cs.LG": "机器学习",
            "cs.CL": "自然语言处理",
            "cs.AI": "人工智能",
            "cs.RO": "机器人",
            "cs.NE": "神经网络",
        }
        result["tags"] = [category_tags.get(c, c) for c in (categories or [])][:3]

        return result

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """多策略 JSON 解析。

        尝试多种方式从文本中提取 JSON 对象。

        Args:
            text: 可能包含 JSON 的文本

        Returns:
            解析出的字典，失败时返回空字典
        """
        if not text:
            return {}

        # 预处理：移除 markdown 代码块标记
        cleaned_text = text.strip()
        if cleaned_text.startswith("```"):
            # 移除开头的 ```json 或 ```
            lines = cleaned_text.split("\n")
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            # 移除结尾的 ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_text = "\n".join(lines)

        # 预处理：修复字符串值中未转义的双引号
        # 使用状态机方法修复 JSON 中的非法引号
        def fix_json_quotes(json_str: str) -> str:
            result = []
            i = 0
            in_string = False
            current_key = None

            while i < len(json_str):
                char = json_str[i]

                if char == '"' and (i == 0 or json_str[i-1] != '\\'):
                    if not in_string:
                        # 开始字符串
                        in_string = True
                        result.append(char)
                    else:
                        # 检查这是字符串结束还是内部引号
                        # 向前看：如果后面是 : , } ] 或行尾，则是结束
                        rest = json_str[i+1:].lstrip()
                        if rest and rest[0] in ':,}]':
                            # 这是字符串结束
                            in_string = False
                            result.append(char)
                        elif not rest or rest[0] == '\n':
                            # 行尾，可能是字符串结束
                            in_string = False
                            result.append(char)
                        else:
                            # 这是字符串内部的引号，需要转义
                            result.append('\\"')
                    i += 1
                else:
                    result.append(char)
                    i += 1

            return ''.join(result)

        cleaned_text = fix_json_quotes(cleaned_text)

        # 策略 1: 从清理后的文本中提取代码块
        json_block_patterns = [
            r"```json\s*([\s\S]*?)\s*```",  # ```json ... ```
            r"```\s*([\s\S]*?)\s*```",       # ``` ... ```
        ]
        for pattern in json_block_patterns:
            matches = re.findall(pattern, cleaned_text, re.DOTALL)
            for match in matches:
                try:
                    result = json.loads(match.strip())
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError as e:
                    logger.debug(f"代码块 JSON 解析失败: {e}")
                    continue

        # 策略 2: 直接解析清理后的文本
        try:
            result = json.loads(cleaned_text.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 策略 3: 从文本中找到第一个完整的 { ... } 对象
        # 使用栈匹配确保提取完整的 JSON 对象
        start = cleaned_text.find("{")
        if start != -1:
            brace_count = 0
            end = start
            for i, char in enumerate(cleaned_text[start:], start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end > start:
                try:
                    result = json.loads(cleaned_text[start:end])
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

        # 策略 4: 尝试修复常见的 JSON 格式问题
        repaired = re.sub(r"//.*?\n", "", cleaned_text)  # 移除单行注释
        repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)  # 移除多行注释
        repaired = re.sub(r",\s*}", "}", repaired)  # 移除尾随逗号
        repaired = re.sub(r",\s*]", "]", repaired)
        try:
            result = json.loads(repaired)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 都失败则返回空字典
        logger.warning(f"JSON 解析失败，返回空字典。原始文本前 500 字符:\n{text[:500]}")
        return {}

    @staticmethod
    def validate_analysis_json(analysis_json: Dict[str, Any], check_length: bool = False) -> tuple[bool, List[str]]:
        """验证分析 JSON 是否包含必要字段。

        Args:
            analysis_json: 待验证的 JSON 字典
            check_length: 是否检查 one_line_summary 长度（快速模式需要）

        Returns:
            (是否有效, 缺失字段列表)
        """
        REQUIRED_FIELDS = ["tags", "one_line_summary", "tier"]

        missing = []
        for field in REQUIRED_FIELDS:
            value = analysis_json.get(field)
            if not value:
                missing.append(field)
            elif field == "tags" and isinstance(value, list) and len(value) == 0:
                missing.append(field)
            elif field == "one_line_summary" and isinstance(value, str) and value.strip() == "":
                missing.append(field)

        # 快速模式额外检查总结长度（必须80-150字）
        if check_length and "one_line_summary" in analysis_json:
            summary = analysis_json.get("one_line_summary", "")
            if summary:
                summary_len = len(summary)
                if summary_len < 80:
                    missing.append(f"one_line_summary太短({summary_len}字，需80-150字)")
                elif summary_len > 150:
                    missing.append(f"one_line_summary太长({summary_len}字，需80-150字)")

        return len(missing) == 0, missing

    async def generate_batch_light(
        self,
        papers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """批量生成论文轻量分析结果（tier, tags, methodology）。

        阶段1：批量处理，容忍少量误差。

        Args:
            papers: 论文列表，每项包含 {paper_id, title, content, arxiv_id}

        Returns:
            轻量结果列表，每项包含 {paper_id, tier, tags, methodology}
        """
        if not papers:
            return []

        logger.info(f"阶段1: 批量轻量分析 {len(papers)} 篇论文")

        # 构建批量内容（每篇限制 300 字）
        papers_content = []
        for paper in papers:
            content = paper.get("content", "")[:300]
            papers_content.append(f"""
### 论文 ID: {paper.get('paper_id', '未知')}

标题: {paper.get('title', '未知标题')}

摘要: {content}

---""")

        # 格式化 Prompt
        prompt = BATCH_LIGHT_PROMPT.format(
            batch_size=len(papers),
            papers_content="\n".join(papers_content),
        )

        try:
            # 调用 API
            response_text = await asyncio.to_thread(
                self._call_api, prompt, max_tokens=4096
            )

            # 解析 JSON 数组
            results = self._parse_json_array(response_text)

            if not results:
                logger.error("批量轻量分析返回空结果")
                return [self._default_light_result(p["paper_id"]) for p in papers]

            # 按 paper_id 匹配
            matched = self._match_results_by_paper_id(papers, results)

            logger.info(f"阶段1完成: {len([m for m in matched if m.get('tier')])}/{len(papers)} 成功")
            return matched

        except Exception as e:
            logger.error(f"批量轻量分析失败: {e}")
            return [self._default_light_result(p["paper_id"]) for p in papers]

    def _default_light_result(self, paper_id: int) -> Dict[str, Any]:
        """默认轻量结果"""
        return {
            "paper_id": paper_id,
            "tier": "B",
            "tags": [],
            "methodology": "未知",
        }

    def _match_results_by_paper_id(
        self,
        papers: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """按 paper_id 匹配结果，确保对应正确。"""
        paper_id_to_idx = {p["paper_id"]: i for i, p in enumerate(papers)}
        matched = [None] * len(papers)

        for result in results:
            paper_id = result.get("paper_id")
            # 尝试转换为 int
            if isinstance(paper_id, str):
                try:
                    paper_id = int(paper_id)
                except:
                    pass

            if paper_id in paper_id_to_idx:
                idx = paper_id_to_idx[paper_id]
                matched[idx] = {
                    "paper_id": papers[idx]["paper_id"],
                    "tier": result.get("tier", "B"),
                    "tags": result.get("tags", []),
                    "methodology": result.get("methodology", "未知"),
                }

        # 未匹配的使用默认值
        for i, m in enumerate(matched):
            if m is None:
                matched[i] = self._default_light_result(papers[i]["paper_id"])
                logger.warning(f"论文 {papers[i]['paper_id']} 未匹配到结果，使用默认值")

        return matched

    async def generate_detail(
        self,
        title: str,
        abstract: str,
        tier: str = "B",
        tags: List[str] = None,
        methodology: str = "",
    ) -> Dict[str, Any]:
        """生成单篇论文详细分析结果（one_line_summary, key_contributions）。

        阶段2：独立处理，必须准确。使用真正的异步 HTTP 调用。

        Args:
            title: 论文标题
            abstract: 论文摘要
            tier: 已确定的 tier
            tags: 已确定的标签
            methodology: 已确定的方法类型

        Returns:
            详细结果，包含 one_line_summary 和 key_contributions
        """
        logger.info(f"阶段2: 详细分析 - {title[:30]}...")

        tags_str = ", ".join(tags) if tags else "未分类"

        prompt = DETAIL_PROMPT.format(
            title=title,
            abstract=abstract[:1000],
            tier=tier,
            tags=tags_str,
            methodology=methodology,
        )

        try:
            # 使用真正的异步 HTTP 调用
            response_text = await self._call_api_async(prompt, max_tokens=2048)

            # 解析 JSON
            result = self._parse_json(response_text)

            if not result:
                logger.error("详细分析返回空结果")
                return {
                    "one_line_summary": "",
                    "key_contributions": [],
                }

            # 验证 one_line_summary 长度
            summary = result.get("one_line_summary", "")
            if len(summary) < 80:
                logger.warning(f"总结太短 ({len(summary)}字): {title[:30]}")

            return {
                "one_line_summary": summary,
                "key_contributions": result.get("key_contributions", []),
            }

        except Exception as e:
            logger.error(f"详细分析失败: {e}")
            return {
                "one_line_summary": "",
                "key_contributions": [],
            }

    async def _call_api_async(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """异步调用 AI API（使用 httpx.AsyncClient 实现真正的异步）。

        Args:
            prompt: 输入提示词
            max_tokens: 最大输出 token 数

        Returns:
            模型响应文本
        """
        max_tokens = max_tokens or self.max_tokens
        settings = get_settings()

        # 构建 API 配置
        if self.client_type == "coding_plan":
            base_url = "https://coding.dashscope.aliyuncs.com/v1"
            api_key = settings.coding_plan_api_key
        elif self.client_type == "zhipu":
            base_url = "https://open.bigmodel.cn/api/paas/v4"
            api_key = os.environ.get("ZHIPU_API_KEY", settings.zhipu_api_key or "")
        elif self.client_type == "dashscope":
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            api_key = settings.dashscope_api_key
        else:
            # Anthropic: 回退到线程池
            return await asyncio.to_thread(self._call_api, prompt, max_tokens)

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }

        # 带重试的异步调用
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()

                    # 安全解析 JSON
                    try:
                        data = response.json()
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON 解析失败: {e}, body={response.text[:100]}")
                        raise

                    # 安全获取内容
                    choices = data.get("choices", [])
                    if not choices:
                        logger.warning(f"API 返回空 choices: model={self.model}")
                        return ""

                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        logger.warning(f"API 返回空内容: model={self.model}, id={data.get('id', 'unknown')}")

                    return content or ""

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"API 超时 (attempt {attempt+1}/{MAX_RETRIES}, {self.timeout}s): {e}")
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                    logger.info(f"等待 {delay}s 后重试...")
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as e:
                # 429 限流错误需要重试
                if e.response.status_code == 429:
                    last_error = e
                    logger.warning(f"API 限流 (attempt {attempt+1}/{MAX_RETRIES}): 429")
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt) * 2  # 限流加倍等待
                        logger.info(f"限流，等待 {delay}s 后重试...")
                        await asyncio.sleep(delay)
                else:
                    # 其他 HTTP 错误不重试
                    logger.error(f"HTTP 错误: {e.response.status_code}, body={e.response.text[:200]}")
                    raise

            except Exception as e:
                last_error = e
                logger.error(f"API 调用异常 (attempt {attempt+1}): type={type(e).__name__}, msg={e}")
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (RETRY_BACKOFF ** attempt)
                    await asyncio.sleep(delay)

        # 所有重试失败
        logger.error(f"API 调用失败，已重试 {MAX_RETRIES} 次: {last_error}")
        raise last_error

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """从文本中解析 JSON 对象。"""
        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except:
            pass

        # 尝试提取 JSON 对象
        import re
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass

        return {}

    def _parse_json_array(self, text: str) -> List[Dict]:
        """从文本中解析 JSON 数组。"""
        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except:
            pass

        # 尝试提取 JSON 数组
        import re
        match = re.search(r'\[\s*\{.*?\}\s*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass

        return []

    async def generate_video_analysis(
        self,
        title: str,
        transcript: str,
        duration: Optional[int] = None,
        speaker: Optional[str] = None,
        platform: Optional[str] = None,
        publish_date: Optional[str] = None,
        video_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成视频内容分析报告。

        Args:
            title: 视频标题
            transcript: 视频转录稿
            duration: 视频时长（秒）
            speaker: 演讲者/创作者
            platform: 平台（youtube/bilibili等）
            publish_date: 发布日期
            video_url: 视频链接

        Returns:
            包含 report 和 analysis_json 的字典
        """
        try:
            # 格式化时长显示
            duration_str = "未知"
            if duration:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                if hours > 0:
                    duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = f"{minutes}:{seconds:02d}"

            # 格式化视频分析 prompt
            prompt = VIDEO_ANALYSIS_PROMPT.format(
                title=title,
                duration=duration_str,
                speaker=speaker or "未知",
                platform=platform or "未知",
                publish_date=publish_date or "未知",
                video_url=video_url or "",
                transcript=transcript[:60000] if len(transcript) > 60000 else transcript,
            )

            logger.info(f"开始生成视频分析: {title[:30]}...")
            report = await asyncio.to_thread(self._call_api, prompt, max_tokens=self.max_tokens)

            logger.info(f"视频分析报告生成成功: {len(report)} 字符")

            # 提取结构化数据
            prompt_json = VIDEO_JSON_PROMPT.format(
                duration=duration_str,
                speaker=speaker or "未知",
                platform=platform or "未知",
                publish_date=publish_date or "未知",
                report=report,
            )

            response_text = await asyncio.to_thread(
                self._call_api, prompt_json, max_tokens=4096
            )
            analysis_json = self._parse_json(response_text)

            # 补充默认值
            DEFAULT_VALUES = {
                "tier": "B",
                "tags": [],
                "one_line_summary": "",
                "chapters": [],
                "key_points": [],
                "tools_mentioned": [],
                "resources": [],
                "code_snippets": [],
                "target_audience": [],
                "prerequisites": [],
                "action_items": [],
                "knowledge_links": [],
                "overall_rating": "B",
                "content_quality": {
                    "information_density": "medium",
                    "clarity": "good",
                    "practical_value": "medium"
                }
            }
            for key, default in DEFAULT_VALUES.items():
                if key not in analysis_json:
                    analysis_json[key] = default

            # 存储视频元数据到 analysis_json
            analysis_json["video_metadata"] = {
                "duration": duration,
                "speaker": speaker,
                "platform": platform,
                "video_url": video_url,
            }

            logger.info(f"视频分析完成: tier={analysis_json.get('tier', 'B')}")
            return {
                "report": report,
                "analysis_json": analysis_json,
            }

        except Exception as e:
            logger.error(f"生成视频分析失败: {e}", exc_info=True)
            return {
                "report": "",
                "analysis_json": {},
            }


# 全局实例
ai_service = AIService()