"""Markdown 输出生成器。

生成符合 Obsidian 格式的 Markdown 文件。
支持同时复制 PDF 到 Obsidian Vault。

优先调用 zhiwei-obsidian 服务，服务不可用时回退到本地实现。
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# 尝试导入 Obsidian 客户端
try:
    from app.services.obsidian_client import obsidian_client
    HAS_OBSIDIAN_CLIENT = True
except ImportError:
    HAS_OBSIDIAN_CLIENT = False
    logger.warning("Obsidian 客户端不可用，使用本地实现")


class MarkdownGenerator:
    """Markdown 文件生成器。

    优先调用 zhiwei-obsidian 服务，服务不可用时回退到本地实现。
    """

    def __init__(self, output_dir: str = None, attachments_dir: str = None, prefer_service: bool = True):
        """初始化生成器。

        Args:
            output_dir: Markdown 输出目录，默认为 Obsidian Vault 的 Inbox
            attachments_dir: PDF 附件目录，默认为 Obsidian Vault 的 attachments
            prefer_service: 是否优先使用 zhiwei-obsidian 服务
        """
        self.vault_path = Path(os.path.expanduser("~/Documents/ZhiweiVault"))
        self.output_dir = Path(output_dir or self.vault_path / "Inbox")
        self.attachments_dir = Path(attachments_dir or self.vault_path / "attachments")
        self.prefer_service = prefer_service and HAS_OBSIDIAN_CLIENT

        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    def generate_paper_md(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_path: str = None,
    ) -> Dict[str, str]:
        """生成论文 Markdown 文件并复制 PDF。

        优先调用 zhiwei-obsidian 服务，服务不可用时回退到本地实现。

        Args:
            paper_data: 论文基础信息
            analysis_json: 分析结果 JSON
            report: 分析报告
            pdf_path: PDF 源文件路径（可选）

        Returns:
            包含 md_path 和 pdf_path 的字典
        """
        # 尝试使用 zhiwei-obsidian 服务
        if self.prefer_service and obsidian_client.is_available():
            logger.info("使用 zhiwei-obsidian 服务导出")
            result = obsidian_client.export_paper(
                paper_data, analysis_json, report, pdf_path
            )
            if "error" not in result:
                logger.info(f"服务导出成功: {result.get('md_path')}")
                return result
            else:
                logger.warning(f"服务导出失败: {result.get('error')}，回退到本地实现")

        # 本地实现
        return self._local_generate_paper_md(paper_data, analysis_json, report, pdf_path)

    def _local_generate_paper_md(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_path: str = None,
    ) -> Dict[str, str]:
        """本地实现：生成论文 Markdown 文件并复制 PDF。"""
        # 提取字段
        title = paper_data.get("title", "未知标题")
        arxiv_id = paper_data.get("arxiv_id", "")
        content_type = paper_data.get("content_type", "paper")

        # 生成文件名（带类型前缀）
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_title = self._sanitize_filename(title)
        type_prefix = self._get_type_prefix(content_type)

        # Markdown 文件
        md_filename = f"{type_prefix}_{date_str}_{safe_title}.md"
        md_filepath = self.output_dir / md_filename

        # 生成 Markdown 内容（包含 PDF 链接）
        content = self._build_paper_content(
            paper_data, analysis_json, report, pdf_filename=None
        )

        # 复制 PDF 并更新链接
        result = {"md_path": str(md_filepath), "pdf_path": None}
        if pdf_path and os.path.exists(pdf_path):
            pdf_filename = f"{date_str}_{safe_title}.pdf"
            pdf_dest = self.attachments_dir / pdf_filename
            try:
                shutil.copy2(pdf_path, pdf_dest)
                result["pdf_path"] = str(pdf_dest)
                logger.info(f"PDF 复制成功: {pdf_dest}")

                # 更新 Markdown 中的 PDF 链接
                content = self._build_paper_content(
                    paper_data, analysis_json, report, pdf_filename=pdf_filename
                )
            except Exception as e:
                logger.warning(f"PDF 复制失败: {e}")

        # 写入 Markdown 文件
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Markdown 生成成功: {md_filepath}")
        return result

    def _build_paper_content(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_filename: str = None,
    ) -> str:
        """构建 Markdown 内容。"""
        # YAML 元数据
        yaml = self._build_yaml(paper_data, analysis_json)

        # 正文
        body = self._build_body(paper_data, analysis_json, report, pdf_filename)

        return yaml + "\n" + body

    def _build_yaml(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
    ) -> str:
        """构建 YAML 元数据。"""
        return f"""---
title: "{paper_data.get('title', '')}"
source_url: "{paper_data.get('arxiv_url', '')}"
date: {paper_data.get('publish_date', '') or '未知'}
type: paper

tags: {analysis_json.get('tags', [])}
tier: {analysis_json.get('tier', 'B')}
ingest_quality: {analysis_json.get('ingest_quality', 'Bronze')}
parser_used: {analysis_json.get('parser_used', 'abstract_only')}
methodology: "{analysis_json.get('methodology', '')}"

related: {analysis_json.get('knowledge_links', [])}
institutions: {paper_data.get('institutions', [])}

overall_rating: {analysis_json.get('overall_rating', 'B')}
---
"""

    def _build_body(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_filename: str = None,
    ) -> str:
        """构建正文内容。"""
        title = paper_data.get("title", "")
        tier = analysis_json.get("tier", "B")
        rating = analysis_json.get("overall_rating", "B")

        tier_text = {"A": "⭐⭐⭐ 深度干货", "B": "⭐⭐ 实用向导", "C": "⭐ 一般参考"}

        # 安全格式化列表字段
        authors = self._safe_join(paper_data.get('authors', []))
        institutions = self._safe_join(paper_data.get('institutions', []))

        # PDF 链接部分
        pdf_section = ""
        if pdf_filename:
            pdf_section = f"""
## 📄 PDF 附件

- [[attachments/{pdf_filename}|打开 PDF]]
"""

        return f"""# {title}

> **内容等级**：{tier_text.get(tier, "⭐⭐ 实用向导")} | **综合评级**：{rating} | **解析质量**：{analysis_json.get('ingest_quality', 'Bronze')} ({analysis_json.get('parser_used', 'abstract_only')})

## 📋 基础信息

| 项目 | 内容 |
|------|------|
| 作者 | {authors or '未知'} |
| 机构 | {institutions or '未知'} |
| 发布日期 | {paper_data.get('publish_date', '') or '未知'} |
| 来源 | [{paper_data.get('arxiv_url', '')}]({paper_data.get('arxiv_url', '')}) |

## 💡 一句话总结

{analysis_json.get('one_line_summary', '待补充')}

{report}
{pdf_section}
## ✅ 行动建议

{self._format_action_items(analysis_json.get('action_items', []))}

## 🔗 知识关联

{self._format_knowledge_links(analysis_json.get('knowledge_links', []))}

## 📚 参考资料

- [{title}]({paper_data.get('arxiv_url', '')})
"""

    def _safe_join(self, items) -> str:
        """安全地将列表或字符串转换为逗分隔的字符串。"""
        if not items:
            return ""
        if isinstance(items, str):
            return items
        return ", ".join(str(item) for item in items)

    def _format_action_items(self, items) -> str:
        """格式化行动建议。"""
        if not items:
            return "- [ ] 待补充"
        # 确保 items 是列表
        if isinstance(items, str):
            items = [items]
        return "\n".join([f"- [ ] {item}" for item in items])

    def _format_knowledge_links(self, links) -> str:
        """格式化知识关联。"""
        if not links:
            return "待补充"
        # 确保 links 是列表
        if isinstance(links, str):
            links = [links]
        return " · ".join([f"[[{link.strip('[]')}]]" for link in links])

    def _sanitize_filename(self, title: str) -> str:
        """清理文件名。"""
        # 移除不允许的字符
        safe = "".join(c for c in title if c.isalnum() or c in " -_")
        # 限制长度
        return safe[:50].strip()

    def _get_type_prefix(self, content_type: str) -> str:
        """根据内容类型获取文件名前缀。

        Args:
            content_type: 内容类型 (paper, video, article, report)

        Returns:
            文件名前缀
        """
        type_prefixes = {
            "paper": "PAPER",
            "video": "VIDEO",
            "article": "NOTE",
            "report": "REPORT",
        }
        return type_prefixes.get(content_type, "NOTE")