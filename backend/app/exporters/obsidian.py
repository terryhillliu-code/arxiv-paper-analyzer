"""
Obsidian 导出器

将论文导出为 Obsidian Markdown 格式。
支持本地生成和通过 zhiwei-obsidian 服务远程导出。
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml

from .base import BaseExporter, ExportResult

logger = logging.getLogger(__name__)


class ObsidianExporter(BaseExporter):
    """Obsidian 格式导出器"""

    name = "obsidian"
    file_extension = ".md"

    def __init__(
        self,
        client: Optional[Any] = None,
        output_dir: Optional[str] = None,
        attachments_dir: Optional[str] = None,
        prefer_service: bool = True,
    ):
        """
        初始化导出器

        Args:
            client: ObsidianClient 实例，用于调用 zhiwei-obsidian 服务
            output_dir: 本地输出目录
            attachments_dir: 本地附件目录
            prefer_service: 是否优先使用远程服务
        """
        self.client = client
        self.prefer_service = prefer_service and client is not None

        # 本地目录（回退时使用）
        from pathlib import Path
        import os
        self.vault_path = Path(os.path.expanduser("~/Documents/ZhiweiVault"))
        self.output_dir = Path(output_dir or self.vault_path / "Inbox")
        self.attachments_dir = Path(attachments_dir or self.vault_path / "attachments")

        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    def export_paper(self, paper: Dict[str, Any]) -> str:
        """
        导出单篇论文为 Obsidian Markdown

        Args:
            paper: 论文数据字典

        Returns:
            Markdown 内容字符串
        """
        frontmatter = self._build_frontmatter(paper)
        body = self._build_body(paper)
        return f"---\n{frontmatter}---\n\n{body}"

    def _build_frontmatter(self, paper: Dict[str, Any]) -> str:
        """
        构建 YAML frontmatter

        Args:
            paper: 论文数据

        Returns:
            YAML 格式字符串
        """
        meta = {
            "title": self._get_field(paper, "title", ""),
            "arxiv_id": self._get_field(paper, "arxiv_id", ""),
            "authors": self._get_field(paper, "authors", []),
            "date": self._get_field(paper, "publish_date", ""),
            "categories": self._get_field(paper, "categories", []),
            "tags": self._get_field(paper, "tags", []),
            "tier": self._get_field(paper, "tier", "C"),
            "url": self._build_arxiv_url(paper),
            "type": "paper",
        }

        # 可选字段
        institutions = self._get_field(paper, "institutions", [])
        if institutions:
            meta["institutions"] = institutions

        methodology = self._get_field(paper, "methodology", "")
        if methodology:
            meta["methodology"] = methodology

        knowledge_links = self._get_field(paper, "knowledge_links", [])
        if knowledge_links:
            meta["related"] = knowledge_links

        return yaml.dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def _build_body(self, paper: Dict[str, Any]) -> str:
        """
        构建正文内容

        Args:
            paper: 论文数据

        Returns:
            Markdown 正文
        """
        title = self._get_field(paper, "title", "未知标题")
        tier = self._get_field(paper, "tier", "C")
        rating = self._get_field(paper, "overall_rating", tier)

        sections = []

        # 标题和评级
        tier_text = {"A": "⭐⭐⭐ 深度干货", "B": "⭐⭐ 实用向导", "C": "⭐ 一般参考"}
        sections.append(f"# {title}\n")
        sections.append(f"> **内容等级**：{tier_text.get(tier, '⭐⭐ 实用向导')} | **综合评级**：{rating}\n")

        # 基础信息表
        sections.append(self._build_info_table(paper))

        # 一句话总结
        one_line = self._get_field(paper, "one_line_summary", "") or self._get_field(paper, "summary", "")
        if one_line:
            sections.append(f"## 💡 一句话总结\n\n{one_line}\n")

        # AI 摘要
        summary = self._get_field(paper, "summary", "")
        if summary and summary != one_line:
            sections.append(f"## 📝 AI 摘要\n\n{summary}\n")

        # 原始摘要
        abstract = self._get_field(paper, "abstract", "")
        if abstract and abstract != summary:
            sections.append(f"## 📄 原始摘要\n\n{abstract[:500]}...\n" if len(abstract) > 500 else f"## 📄 原始摘要\n\n{abstract}\n")

        # 核心贡献
        contributions = self._get_field(paper, "key_contributions", [])
        if contributions:
            sections.append("## 🎯 核心贡献\n")
            for c in contributions:
                sections.append(f"- {c}")
            sections.append("")

        # 分析报告
        report = self._get_field(paper, "analysis_report", "")
        if report:
            sections.append(f"## 📊 深度分析\n\n{report}\n")

        # 行动项
        action_items = self._get_field(paper, "action_items", [])
        if action_items:
            sections.append("## ✅ 行动建议\n")
            for item in action_items:
                sections.append(f"- [ ] {item}")
            sections.append("")

        # 知识链接
        knowledge_links = self._get_field(paper, "knowledge_links", [])
        if knowledge_links:
            sections.append("## 🔗 知识关联\n")
            links_str = " · ".join(f"[[{self._clean_link(link)}]]" for link in knowledge_links)
            sections.append(f"{links_str}\n")

        # 参考资料
        url = self._build_arxiv_url(paper)
        if url:
            sections.append(f"## 📚 参考资料\n\n- [{title}]({url})\n")

        return "\n".join(sections)

    def _build_info_table(self, paper: Dict[str, Any]) -> str:
        """构建基础信息表"""
        authors = self._get_field(paper, "authors", [])
        authors_str = ", ".join(str(a) for a in authors[:5])
        if len(authors) > 5:
            authors_str += f" 等 {len(authors)} 人"

        institutions = self._get_field(paper, "institutions", [])
        institutions_str = ", ".join(str(i) for i in institutions[:3])
        if len(institutions) > 3:
            institutions_str += f" 等 {len(institutions)} 家"

        date = self._get_field(paper, "publish_date", "未知")
        url = self._build_arxiv_url(paper)

        return f"""## 📋 基础信息

| 项目 | 内容 |
|------|------|
| 作者 | {authors_str or '未知'} |
| 机构 | {institutions_str or '未知'} |
| 发布日期 | {date} |
| 来源 | [{url}]({url}) |
"""

    def _build_arxiv_url(self, paper: Dict[str, Any]) -> str:
        """构建 ArXiv URL"""
        arxiv_id = self._get_field(paper, "arxiv_id", "")
        if arxiv_id:
            return f"https://arxiv.org/abs/{arxiv_id}"
        return self._get_field(paper, "arxiv_url", "") or self._get_field(paper, "url", "")

    def _clean_link(self, link: str) -> str:
        """清理链接文本，移除方括号"""
        return link.strip("[]")

    def _sanitize_filename(self, title: str) -> str:
        """
        清理文件名

        Args:
            title: 原始标题

        Returns:
            安全的文件名
        """
        # 移除不允许的字符
        safe = re.sub(r'[<>:"/\\|?*]', "", title)
        # 替换空格为下划线
        safe = re.sub(r"\s+", "_", safe)
        # 限制长度
        return safe[:100].strip()

    def _get_type_prefix(self, content_type: str) -> str:
        """
        根据内容类型获取文件名前缀

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

    async def export_to_vault(
        self,
        paper: Dict[str, Any],
        folder: str = "Inbox",
        pdf_path: Optional[str] = None,
    ) -> ExportResult:
        """
        导出到 Obsidian Vault

        优先使用 zhiwei-obsidian 服务，失败时回退到本地实现。

        Args:
            paper: 论文数据
            folder: 目标文件夹
            pdf_path: PDF 文件路径（可选）

        Returns:
            ExportResult 对象
        """
        # 尝试使用远程服务
        if self.prefer_service and self._check_service_available():
            result = await self._export_via_service(paper, folder, pdf_path)
            if result.success:
                return result
            logger.warning(f"服务导出失败: {result.error}，回退到本地实现")

        # 本地实现
        return self._export_locally(paper, folder, pdf_path)

    def _check_service_available(self) -> bool:
        """检查远程服务是否可用"""
        if not self.client:
            return False
        try:
            return self.client.is_available()
        except Exception:
            return False

    async def _export_via_service(
        self,
        paper: Dict[str, Any],
        folder: str,
        pdf_path: Optional[str],
    ) -> ExportResult:
        """通过 zhiwei-obsidian 服务导出"""
        try:
            result = self.client.export_paper(
                paper_data=paper,
                analysis_json={
                    "tags": self._get_field(paper, "tags", []),
                    "tier": self._get_field(paper, "tier", "C"),
                    "methodology": self._get_field(paper, "methodology", ""),
                    "knowledge_links": self._get_field(paper, "knowledge_links", []),
                    "overall_rating": self._get_field(paper, "overall_rating", "C"),
                    "one_line_summary": self._get_field(paper, "one_line_summary", ""),
                    "action_items": self._get_field(paper, "action_items", []),
                },
                report=self._get_field(paper, "analysis_report", ""),
                pdf_path=pdf_path,
            )

            if result.get("success"):
                return ExportResult(
                    success=True,
                    format=self.name,
                    file_path=result.get("md_path"),
                    content=self.export_paper(paper),
                    metadata={"pdf_path": result.get("pdf_path")}
                )
            else:
                return ExportResult(
                    success=False,
                    format=self.name,
                    error=result.get("error", "导出失败")
                )
        except Exception as e:
            return ExportResult(
                success=False,
                format=self.name,
                error=str(e)
            )

    def _export_locally(
        self,
        paper: Dict[str, Any],
        folder: str,
        pdf_path: Optional[str],
    ) -> ExportResult:
        """本地导出实现"""
        try:
            import shutil

            title = self._get_field(paper, "title", "未命名")
            arxiv_id = self._get_field(paper, "arxiv_id", "unknown")
            content_type = self._get_field(paper, "content_type", "paper")
            date_str = datetime.now().strftime("%Y-%m-%d")
            safe_title = self._sanitize_filename(title)
            type_prefix = self._get_type_prefix(content_type)

            # Markdown 文件（带 arxiv_id 确保唯一性，简化格式避免过长）
            md_filename = f"{type_prefix}_{arxiv_id}_{safe_title[:60]}.md"
            output_dir = self.output_dir if folder == "Inbox" else self.vault_path / folder
            output_dir.mkdir(parents=True, exist_ok=True)
            md_path = output_dir / md_filename

            # 生成内容
            content = self.export_paper(paper)

            # 复制 PDF（也加上 arxiv_id）
            pdf_dest = None
            if pdf_path:
                pdf_filename = f"{arxiv_id}_{safe_title}.pdf"
                pdf_dest = self.attachments_dir / pdf_filename
                try:
                    shutil.copy2(pdf_path, pdf_dest)
                except Exception as e:
                    logger.warning(f"PDF 复制失败: {e}")
                    pdf_dest = None

            # 写入 Markdown
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ExportResult(
                success=True,
                format=self.name,
                content=content,
                file_path=str(md_path),
                metadata={"pdf_path": str(pdf_dest) if pdf_dest else None}
            )
        except Exception as e:
            return ExportResult(
                success=False,
                format=self.name,
                error=str(e)
            )