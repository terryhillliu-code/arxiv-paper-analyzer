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

from app.adapters.obsidian_adapter import ObsidianAdapter

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
    支持根据 Tier 动态选择输出目录。
    """

    # Tier 对应的输出目录配置
    TIER_FOLDERS = {
        "A": "90-99_系统与归档_System/96_Papers_Archive/重要论文",
        "B": "Inbox",
        "C": "Inbox",
    }

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

    def get_output_folder(self, tier: str = None, paper_data: Dict[str, Any] = None) -> Path:
        """根据 Tier 获取输出目录

        Args:
            tier: 论文等级（A/B/C）
            paper_data: 论文数据（可用于更复杂的路由逻辑）

        Returns:
            输出目录路径
        """
        if tier and tier in self.TIER_FOLDERS:
            folder = self.TIER_FOLDERS[tier]
            output_path = self.vault_path / folder
            output_path.mkdir(parents=True, exist_ok=True)
            return output_path
        return self.output_dir

    def generate_paper_md(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_path: str = None,
        images_dir: str = None,
    ) -> Dict[str, str]:
        """生成论文 Markdown 文件并复制 PDF。

        优先调用 zhiwei-obsidian 服务，服务不可用时回退到本地实现。

        Args:
            paper_data: 论文基础信息
            analysis_json: 分析结果 JSON
            report: 分析报告
            pdf_path: PDF 源文件路径（可选）
            images_dir: 图片源目录（MinerU 提取的图片目录）

        Returns:
            包含 md_path、pdf_path、images_copied 的字典
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
        return self._local_generate_paper_md(paper_data, analysis_json, report, pdf_path, images_dir)

    def _local_generate_paper_md(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_path: str = None,
        images_dir: str = None,
    ) -> Dict[str, str]:
        """本地实现：生成论文 Markdown 文件并复制 PDF。"""
        # 提取字段
        title = paper_data.get("title", "未知标题")
        arxiv_id = paper_data.get("arxiv_id", "")
        content_type = paper_data.get("content_type", "paper")
        tier = analysis_json.get("tier", "B") if analysis_json else "B"

        # 生成文件名（带类型前缀）
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_title = self._sanitize_filename(title)
        type_prefix = self._get_type_prefix(content_type)

        # 根据Tier选择输出目录
        output_dir = self.get_output_folder(tier, paper_data)

        # Markdown 文件
        md_filename = f"{type_prefix}_{date_str}_{safe_title}.md"
        md_filepath = output_dir / md_filename

        # 处理图片（使用 ObsidianAdapter）
        images_copied = 0
        if images_dir and Path(images_dir).exists():
            adapter = ObsidianAdapter(self.vault_path)
            report, conversions = adapter.adapt_images(
                report, Path(images_dir), arxiv_id=arxiv_id
            )
            images_copied = sum(1 for c in conversions if c.success)
            if images_copied > 0:
                logger.info(f"图片复制成功: {images_copied} 张")

        # 生成 Markdown 内容（包含 PDF 链接）
        content = self._build_paper_content(
            paper_data, analysis_json, report, pdf_filename=None
        )

        # 复制 PDF 并更新链接
        result = {"md_path": str(md_filepath), "pdf_path": None, "images_copied": images_copied}
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
        """构建 YAML 元数据（包含 Paper Analyzer 联动字段）。"""
        # 基础元数据
        title = paper_data.get('title', '')
        source_url = paper_data.get('arxiv_url', '')
        publish_date = paper_data.get('publish_date', '') or '未知'
        tags = analysis_json.get('tags', [])
        tier = analysis_json.get('tier', 'B')
        ingest_quality = analysis_json.get('ingest_quality', 'Bronze')
        parser_used = analysis_json.get('parser_used', 'abstract_only')
        methodology = analysis_json.get('methodology', '')
        related = analysis_json.get('knowledge_links', [])
        institutions = paper_data.get('institutions', [])
        overall_rating = analysis_json.get('overall_rating', 'B')

        # 联动字段（v1.1 状态同步）
        paper_id = paper_data.get('paper_id', '')
        arxiv_id = paper_data.get('arxiv_id', '')
        analyzed = paper_data.get('has_analysis', True)
        rag_indexed = paper_data.get('rag_indexed', False)
        analysis_mode = paper_data.get('analysis_mode', '')
        has_pdf = paper_data.get('pdf_local_path') is not None

        # 构建联动字段块（仅在有关联数据时显示）
        linkage_block = ""
        if paper_id or arxiv_id:
            linkage_lines = []
            if paper_id:
                linkage_lines.append(f"paper_id: {paper_id}")
            if arxiv_id:
                linkage_lines.append(f"arxiv_id: \"{arxiv_id}\"")
            linkage_lines.append(f"analyzed: {str(analyzed).lower()}")
            linkage_lines.append(f"rag_indexed: {str(rag_indexed).lower()}")
            if analysis_mode:
                linkage_lines.append(f"analysis_mode: \"{analysis_mode}\"")
            linkage_lines.append(f"has_pdf: {str(has_pdf).lower()}")
            linkage_block = "\n# === Paper Analyzer 联动字段 ===\n" + "\n".join(linkage_lines)

        return f"""---
title: "{title}"
source_url: "{source_url}"
date: {publish_date}
type: paper

tags: {tags}
tier: {tier}
ingest_quality: {ingest_quality}
parser_used: {parser_used}
methodology: "{methodology}"

related: {related}
institutions: {institutions}

overall_rating: {overall_rating}
{linkage_block}
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

    def generate_video_md(
        self,
        video_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
    ) -> Dict[str, str]:
        """生成视频 Markdown 文件。

        公开方法，用于生成视频内容的 Markdown 输出。

        Args:
            video_data: 视频基础信息
            analysis_json: 分析结果 JSON
            report: 分析报告

        Returns:
            包含 md_path 的字典
        """
        title = video_data.get("title", "未命名视频")
        platform = video_data.get("platform", "")
        video_id = video_data.get("video_id", "")
        speaker = video_data.get("speaker", "")
        video_url = video_data.get("video_url", "")

        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_title = self._sanitize_filename(title)

        # 文件名
        if video_id:
            md_filename = f"VIDEO_{video_id}_{date_str}_{safe_title}.md"
        else:
            md_filename = f"VIDEO_{date_str}_{safe_title}.md"

        md_filepath = self.output_dir / md_filename

        # 生成内容
        content = self._build_video_content(
            video_data=video_data,
            analysis_json=analysis_json,
            report=report,
        )

        # 写入文件
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"视频 Markdown 生成成功: {md_filepath}")
        return {"md_path": str(md_filepath)}

    def _build_video_content(
        self,
        video_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
    ) -> str:
        """构建视频 Markdown 内容。"""
        title = video_data.get("title", "未命名视频")
        platform = video_data.get("platform", "")
        speaker = video_data.get("speaker", "")
        duration = video_data.get("duration", 0)
        video_url = video_data.get("video_url", "")
        publish_date = video_data.get("publish_date", "") or "未知"

        tier = analysis_json.get("tier", "B")
        tags = analysis_json.get("tags", [])
        knowledge_links = analysis_json.get("knowledge_links", [])
        action_items = analysis_json.get("action_items", [])

        # 格式化时长
        if duration:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60
            if hours > 0:
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes}:{seconds:02d}"
        else:
            duration_str = "未知"

        # YAML 元数据
        yaml_content = f"""---
title: "{title}"
type: video
platform: "{platform}"
speaker: "{speaker}"
duration: "{duration_str}"
date: {publish_date}
video_url: "{video_url}"
tags: {tags}
tier: {tier}
---
"""

        # 正文
        tier_text = {"A": "⭐⭐⭐ 深度干货", "B": "⭐⭐ 实用向导", "C": "⭐ 一般参考"}

        body = f"""# {title}

> **内容等级**：{tier_text.get(tier, "⭐⭐ 实用向导")} | **平台**：{platform} | **时长**：{duration_str}

## 📋 视频信息

| 项目 | 内容 |
|------|------|
| 创作者 | {speaker or '未知'} |
| 平台 | {platform or '未知'} |
| 时长 | {duration_str} |
| 链接 | [{video_url}]({video_url}) |

{report}

## ✅ 行动建议

{self._format_action_items(action_items)}

## 🔗 知识关联

{self._format_knowledge_links(knowledge_links)}
"""

        return yaml_content + "\n" + body