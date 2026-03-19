"""
Exporter 集成测试
"""

import pytest
from datetime import datetime

from app.exporters import BibTeXExporter, ObsidianExporter
from app.exporters.base import ExportResult


class TestBibTeXExporterIntegration:
    """BibTeX 导出器集成测试"""

    def test_export_real_paper(self):
        """测试导出真实论文数据"""
        exporter = BibTeXExporter()

        papers = [
            {
                "id": 1,
                "title": "Attention Is All You Need",
                "arxiv_id": "1706.03762",
                "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
                "publish_date": "2017-06-12",
                "primary_category": "cs.LG",
                "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
            }
        ]

        result = exporter.export_papers(papers)

        assert result is not None
        assert "@article" in result
        assert "Vaswani2017Attention" in result or "vaswani2017attention" in result.lower()
        assert "1706.03762" in result

    def test_export_multiple_papers(self):
        """测试导出多篇论文"""
        exporter = BibTeXExporter()

        papers = [
            {
                "id": 1,
                "title": "Paper One",
                "arxiv_id": "2401.00001",
                "authors": ["Author A"],
                "publish_date": "2024-01-01",
                "primary_category": "cs.AI",
            },
            {
                "id": 2,
                "title": "Paper Two",
                "arxiv_id": "2401.00002",
                "authors": ["Author B"],
                "publish_date": "2024-01-02",
                "primary_category": "cs.CL",
            }
        ]

        result = exporter.export_papers(papers)

        assert result is not None
        assert result.count("@article") == 2
        assert "2401.00001" in result
        assert "2401.00002" in result

    def test_latex_escaping(self):
        """测试 LaTeX 特殊字符转义"""
        exporter = BibTeXExporter()

        papers = [
            {
                "id": 1,
                "title": "Test & Analysis of AI/ML Systems",
                "arxiv_id": "2401.00001",
                "authors": ["John O'Brien", "Mary-Kate"],
                "publish_date": "2024-01-01",
                "primary_category": "cs.AI",
            }
        ]

        result = exporter.export_papers(papers)

        assert "\\&" in result
        assert "O'Brien" in result or "O{'}Brien" in result


class TestObsidianExporterIntegration:
    """Obsidian 导出器集成测试"""

    def test_export_to_markdown(self):
        """测试导出为 Markdown"""
        exporter = ObsidianExporter(prefer_service=False)

        paper = {
            "id": 1,
            "title": "Test Paper",
            "arxiv_id": "2401.00001",
            "authors": ["Author One", "Author Two"],
            "publish_date": "2024-01-15",
            "categories": ["cs.AI", "cs.LG"],
            "tags": ["transformer", "attention"],
            "tier": "A",
            "abstract": "This is a test abstract.",
            "summary": "Key summary of the paper.",
            "key_contributions": ["Contribution 1", "Contribution 2"],
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
        }

        result = exporter.export_paper(paper)

        assert result is not None
        assert "---" in result  # YAML frontmatter
        assert "title: Test Paper" in result
        assert "2401.00001" in result
        assert "Author One" in result
        assert "核心贡献" in result or "Contributions" in result

    def test_export_with_analysis(self):
        """测试导出包含分析结果"""
        exporter = ObsidianExporter(prefer_service=False)

        paper = {
            "id": 1,
            "title": "Paper with Analysis",
            "arxiv_id": "2401.00002",
            "authors": ["Author"],
            "publish_date": "2024-01-01",
            "categories": ["cs.AI"],
            "tags": [],
            "tier": "S",
            "abstract": "Abstract text",
            "key_contributions": ["Main contribution"],
            "methodology": "The methodology used is...",
            "one_line_summary": "One line summary",
            "overall_rating": 9,
        }

        result = exporter.export_paper(paper)

        # methodology 在 frontmatter 中
        assert "methodology" in result
        assert "The methodology used is..." in result
        assert "9" in result  # 评分