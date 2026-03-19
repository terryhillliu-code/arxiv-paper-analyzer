"""
BibTeX 导出器

将论文导出为 BibTeX 引用格式。
"""

from typing import Any, Dict, List

from .base import BaseExporter


class BibTeXExporter(BaseExporter):
    """BibTeX 格式导出器"""

    name = "bibtex"
    file_extension = ".bib"

    def _generate_key(self, paper: Dict[str, Any]) -> str:
        """
        生成引用键

        格式: FirstAuthorYear + 首词
        例如: smith2023attention

        Args:
            paper: 论文数据

        Returns:
            引用键字符串
        """
        # 获取第一作者姓氏
        authors = self._get_field(paper, "authors", [])
        if authors:
            first_author = str(authors[0]).split()[-1]
            # 清理非字母字符
            first_author = "".join(c for c in first_author if c.isalpha())
        else:
            first_author = "Unknown"

        # 获取年份
        date = self._get_field(paper, "publish_date", "")
        year = str(date)[:4] if date else "XXXX"

        # 获取标题首词
        title = self._get_field(paper, "title", "")
        if title:
            first_word = title.split()[0] if title.split() else "Paper"
            # 清理非字母字符
            first_word = "".join(c for c in first_word if c.isalpha())
        else:
            first_word = "Paper"

        key = f"{first_author}{year}{first_word}".lower()
        return key

    def _escape_latex(self, text: str) -> str:
        """
        转义 LaTeX 特殊字符

        Args:
            text: 原始文本

        Returns:
            转义后的文本
        """
        if not text:
            return ""

        replacements = {
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _format_authors(self, authors: List[str]) -> str:
        """
        格式化作者列表

        Args:
            authors: 作者名列表

        Returns:
            BibTeX 格式的作者字符串
        """
        if not authors:
            return ""

        # 用 " and " 连接作者
        return " and ".join(str(a) for a in authors)

    def export_paper(self, paper: Dict[str, Any]) -> str:
        """
        导出单篇论文为 BibTeX 格式

        Args:
            paper: 论文数据

        Returns:
            BibTeX 条目字符串
        """
        key = self._generate_key(paper)

        # 基本信息
        title = self._escape_latex(self._get_field(paper, "title", ""))
        authors = self._format_authors(self._get_field(paper, "authors", []))
        date = self._get_field(paper, "publish_date", "")
        year = str(date)[:4] if date else ""

        # ArXiv 信息
        arxiv_id = self._get_field(paper, "arxiv_id", "")
        primary_category = self._get_field(paper, "primary_category", "")

        # URL
        pdf_url = self._get_field(paper, "pdf_url", "")
        if pdf_url:
            url = pdf_url
        elif arxiv_id:
            url = f"https://arxiv.org/abs/{arxiv_id}"
        else:
            url = ""

        # 摘要
        abstract = self._escape_latex(self._get_field(paper, "abstract", ""))

        # 确定条目类型
        # arXiv 论文通常用 @article 或 @misc
        entry_type = "@article" if arxiv_id else "@misc"

        # 构建 BibTeX 条目
        lines = [f"{entry_type}{{{key},"]

        if authors:
            lines.append(f"  author = {{{authors}}},")

        if title:
            lines.append(f"  title = {{{title}}},")

        if year:
            lines.append(f"  year = {{{year}}},")

        if arxiv_id:
            lines.append(f"  eprint = {{{arxiv_id}}},")
            lines.append(f"  archiveprefix = {{arXiv}},")

        if primary_category:
            lines.append(f"  primaryclass = {{{primary_category}}},")

        if url:
            lines.append(f"  url = {{{url}}},")

        if abstract:
            # 长摘要放在多行
            lines.append(f"  abstract = {{{abstract}}},")

        # 移除最后一个逗号
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]

        lines.append("}")

        return "\n".join(lines)

    def export_papers(self, papers: List[Dict[str, Any]]) -> str:
        """
        导出多篇论文

        覆盖基类方法，确保条目之间有适当的空行。

        Args:
            papers: 论文列表

        Returns:
            BibTeX 文件内容
        """
        entries = [self.export_paper(p) for p in papers]
        return "\n\n".join(entries)