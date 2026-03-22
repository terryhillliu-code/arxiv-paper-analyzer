"""AI 服务模块。

支持多种 AI API：
- 阿里百炼 API (glm-5, qwen-plus 等)
- Anthropic Claude API
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
import anthropic

from app.config import get_settings
from app.prompts.templates import (
    ANALYSIS_JSON_PROMPT,
    DEEP_ANALYSIS_PROMPT,
    PREDEFINED_TAGS,
    SUMMARY_PROMPT,
    TIER_REEVALUATION_PROMPT,
)

logger = logging.getLogger(__name__)


class AIService:
    """AI 分析服务。

    支持 Coding Plan API (OpenAI 兼容) 和 Anthropic Claude API。
    """

    # Coding Plan API 支持的模型
    CODING_PLAN_MODELS = ["qwen3.5-plus", "glm-5", "kimi-k2.5", "qwen3-max-2026-01-23", "MiniMax-M2.5"]

    # 百炼 API 支持的模型 (备用)
    DASHSCOPE_MODELS = ["qwen-plus", "qwen-turbo", "qwen-max"]

    def __init__(self):
        """初始化 AI 客户端。"""
        settings = get_settings()
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

        # 根据模型选择客户端
        if self.model in self.CODING_PLAN_MODELS:
            # 使用 Coding Plan API (OpenAI 兼容格式)
            self.client_type = "coding_plan"
            self.client = OpenAI(
                api_key=settings.coding_plan_api_key,
                base_url="https://coding.dashscope.aliyuncs.com/v1",
            )
            logger.info(f"使用 Coding Plan API，模型: {self.model}")
        elif self.model in self.DASHSCOPE_MODELS:
            # 使用百炼 API (OpenAI 兼容格式)
            self.client_type = "dashscope"
            self.client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            logger.info(f"使用百炼 API，模型: {self.model}")
        else:
            # 使用 Anthropic API
            self.client_type = "anthropic"
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            logger.info(f"使用 Anthropic API，模型: {self.model}")

    def _call_api(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """统一调用 AI API。

        Args:
            prompt: 输入提示词
            max_tokens: 最大输出 token 数

        Returns:
            模型响应文本
        """
        max_tokens = max_tokens or self.max_tokens

        if self.client_type in ["coding_plan", "dashscope"]:
            # Coding Plan API 和百炼 API 都使用 OpenAI 兼容格式
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
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

            # 格式化提示词
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

            logger.info(f"深度分析报告生成成功: {len(report)} 字符")

            # 快速模式：用 glm-5 异步提取 JSON（带重试）
            if quick_mode:
                from openai import OpenAI as OpenAIClient
                settings = get_settings()

                try:
                    quick_model = "glm-5"
                    quick_client = OpenAIClient(
                        api_key=settings.coding_plan_api_key,
                        base_url="https://coding.dashscope.aliyuncs.com/v1",
                    )
                    prompt_json = ANALYSIS_JSON_PROMPT.format(
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

                        # 验证关键字段
                        is_valid, missing = self.validate_analysis_json(analysis_json)
                        if is_valid:
                            break
                        logger.warning(f"JSON 验证失败 (尝试 {attempt+1}/{MAX_RETRIES})，缺失: {missing}")

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

## 📑 论文大纲

{self._render_outline(outline)}

{report}

## ✅ 行动建议

{self._render_action_items(action_items)}

## 🔗 知识关联

{self._render_knowledge_links(knowledge_links)}

## 📚 参考资料

- [{title}]({arxiv_url})
"""
        return yaml_front + "\n" + content

    def _render_outline(self, outline: List[Dict]) -> str:
        """渲染大纲为 Markdown 列表。"""
        if not outline:
            return "待补充"

        lines = []
        for item in outline:
            lines.append(f"- {item.get('title', '')}")
            for child in item.get('children', []):
                lines.append(f"  - {child.get('title', '')}")
        return "\n".join(lines)

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
        return " · ".join([f"[[{link.strip('[]')}]]" for link in links])

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
        # 尝试从报告中直接提取 JSON（如果有）
        import re

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
    def validate_analysis_json(analysis_json: Dict[str, Any]) -> tuple[bool, List[str]]:
        """验证分析 JSON 是否包含必要字段。

        Args:
            analysis_json: 待验证的 JSON 字典

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

        return len(missing) == 0, missing


# 全局实例
ai_service = AIService()