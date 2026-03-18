"""Markdown 输出生成器。

生成符合 Obsidian 格式的 Markdown 文件。
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MarkdownGenerator:
    """Markdown 文件生成器。"""

    def __init__(self, output_dir: str = None):
        """初始化生成器。

        Args:
            output_dir: 输出目录，默认为 Obsidian Vault 的 Inbox
        """
        self.output_dir = Path(output_dir or os.path.expanduser(
            "~/Documents/ZhiweiVault/Inbox"
        ))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_paper_md(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
    ) -> str:
        """生成论文 Markdown 文件。

        Args:
            paper_data: 论文基础信息
            analysis_json: 分析结果 JSON
            report: 分析报告

        Returns:
            生成的文件路径
        """
        # 提取字段
        title = paper_data.get("title", "未知标题")
        arxiv_id = paper_data.get("arxiv_id", "")

        # 生成文件名
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_title = self._sanitize_filename(title)
        filename = f"{date_str}_{safe_title}.md"
        filepath = self.output_dir / filename

        # 生成内容
        content = self._build_paper_content(
            paper_data, analysis_json, report
        )

        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return str(filepath)

    def _build_paper_content(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
    ) -> str:
        """构建 Markdown 内容。"""
        # YAML 元数据
        yaml = self._build_yaml(paper_data, analysis_json)

        # 正文
        body = self._build_body(paper_data, analysis_json, report)

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
    ) -> str:
        """构建正文内容。"""
        title = paper_data.get("title", "")
        tier = analysis_json.get("tier", "B")
        rating = analysis_json.get("overall_rating", "B")

        tier_text = {"A": "⭐⭐⭐ 深度干货", "B": "⭐⭐ 实用向导", "C": "⭐ 一般参考"}

        return f"""# {title}

> **内容等级**：{tier_text.get(tier, "⭐⭐ 实用向导")} | **综合评级**：{rating}

## 📋 基础信息

| 项目 | 内容 |
|------|------|
| 作者 | {', '.join(paper_data.get('authors', [])) or '未知'} |
| 机构 | {', '.join(paper_data.get('institutions', [])) or '未知'} |
| 发布日期 | {paper_data.get('publish_date', '') or '未知'} |
| 来源 | [{paper_data.get('arxiv_url', '')}]({paper_data.get('arxiv_url', '')}) |

## 💡 一句话总结

{analysis_json.get('one_line_summary', '待补充')}

{report}

## ✅ 行动建议

{self._format_action_items(analysis_json.get('action_items', []))}

## 🔗 知识关联

{self._format_knowledge_links(analysis_json.get('knowledge_links', []))}

## 📚 参考资料

- [{title}]({paper_data.get('arxiv_url', '')})
"""

    def _format_action_items(self, items: List[str]) -> str:
        """格式化行动建议。"""
        if not items:
            return "- [ ] 待补充"
        return "\n".join([f"- [ ] {item}" for item in items])

    def _format_knowledge_links(self, links: List[str]) -> str:
        """格式化知识关联。"""
        if not links:
            return "待补充"
        return " · ".join([f"[[{link.strip('[]')}]]" for link in links])

    def _sanitize_filename(self, title: str) -> str:
        """清理文件名。"""
        # 移除不允许的字符
        safe = "".join(c for c in title if c.isalnum() or c in " -_")
        # 限制长度
        return safe[:50].strip()