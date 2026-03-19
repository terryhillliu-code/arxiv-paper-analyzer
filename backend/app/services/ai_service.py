"""AI 服务模块。

支持多种 AI API：
- 阿里百炼 API (glm-5, qwen-plus 等)
- Anthropic Claude API
"""

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

            # 调用 AI API
            response_text = self._call_api(prompt, max_tokens=1024)
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

        Returns:
            包含 report 和 analysis_json 的字典
        """
        try:
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

            # 调用 AI API
            logger.info(f"开始生成深度分析: {title[:30]}...")
            report = self._call_api(prompt, max_tokens=self.max_tokens)

            logger.info(f"深度分析报告生成成功: {len(report)} 字符")

            # 提取结构化数据
            analysis_json = await self._extract_analysis_json(report)

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

    async def _extract_analysis_json(self, report: str) -> Dict[str, Any]:
        """从分析报告中提取结构化数据。

        Args:
            report: Markdown 格式的分析报告

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
            prompt = ANALYSIS_JSON_PROMPT.format(report=report)

            # 调用 AI API（增加 token 限制以容纳完整 JSON）
            response_text = self._call_api(prompt, max_tokens=4096)
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

        # 策略 1: 从 ```json ... ``` 代码块中提取（优先处理）
        # 使用更健壮的正则，支持多行和可选的 json 标签
        json_block_patterns = [
            r"```json\s*([\s\S]*?)\s*```",  # ```json ... ```
            r"```\s*([\s\S]*?)\s*```",       # ``` ... ```
        ]
        for pattern in json_block_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    result = json.loads(match.strip())
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError as e:
                    logger.debug(f"代码块 JSON 解析失败: {e}")
                    continue

        # 策略 2: 直接解析
        try:
            result = json.loads(text.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 策略 3: 从文本中找到第一个完整的 { ... } 对象
        # 使用栈匹配确保提取完整的 JSON 对象
        start = text.find("{")
        if start != -1:
            brace_count = 0
            end = start
            for i, char in enumerate(text[start:], start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end > start:
                try:
                    result = json.loads(text[start:end])
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

        # 策略 4: 尝试修复常见的 JSON 格式问题
        cleaned = re.sub(r"//.*?\n", "", text)  # 移除单行注释
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)  # 移除多行注释
        cleaned = re.sub(r",\s*}", "}", cleaned)  # 移除尾随逗号
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 都失败则返回空字典
        logger.warning(f"JSON 解析失败，返回空字典。原始文本前 500 字符:\n{text[:500]}")
        return {}


# 全局实例
ai_service = AIService()