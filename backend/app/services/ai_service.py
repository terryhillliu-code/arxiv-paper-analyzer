"""AI 服务模块。

调用 Anthropic Claude API 进行论文分析。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

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

    封装 Claude API 调用，提供论文摘要生成和深度分析功能。
    """

    def __init__(self):
        """初始化 Anthropic 客户端。"""
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

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

            # 调用 Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            # 解析响应 - 处理不同的 content block 类型
            response_text = ""
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text
                elif hasattr(block, "content"):
                    # ThinkingBlock 可能有 content 属性
                    response_text += str(block.content)

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

            # 调用 Claude API
            logger.info(f"开始生成深度分析: {title[:30]}...")
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            # 处理不同的 content block 类型
            report = ""
            for block in message.content:
                if hasattr(block, "text"):
                    report += block.text
                elif hasattr(block, "content"):
                    report += str(block.content)

            logger.info(f"深度分析报告生成成功: {len(report)} 字符")

            # 提取结构化数据
            analysis_json = await self._extract_analysis_json(report)

            return {
                "report": report,
                "analysis_json": analysis_json,
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
            结构化的分析数据字典
        """
        try:
            # 格式化提示词
            prompt = ANALYSIS_JSON_PROMPT.format(report=report)

            # 调用 Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            # 处理不同的 content block 类型
            response_text = ""
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text
                elif hasattr(block, "content"):
                    response_text += str(block.content)

            result = self._parse_json(response_text)

            logger.info("结构化数据提取成功")
            return result

        except Exception as e:
            logger.error(f"提取结构化数据失败: {e}", exc_info=True)
            return {}

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

        # 策略 1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略 2: 从 ```json ... ``` 代码块中提取
        json_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(json_block_pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # 策略 3: 从文本中找到 { ... } 部分
        brace_pattern = r"\{[\s\S]*\}"
        matches = re.findall(brace_pattern, text)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # 策略 4: 尝试修复常见的 JSON 格式问题
        # 移除可能的注释
        cleaned = re.sub(r"//.*?\n", "", text)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 都失败则返回空字典
        logger.warning(f"JSON 解析失败，返回空字典。原始文本: {text[:200]}...")
        return {}


# 全局实例
ai_service = AIService()