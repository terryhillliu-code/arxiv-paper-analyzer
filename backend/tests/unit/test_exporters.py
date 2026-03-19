"""
导出器单元测试
"""

import json
import pytest
from pathlib import Path

from app.exporters.base import BaseExporter, ExportResult
from app.exporters.bibtex import BibTeXExporter
from app.exporters.obsidian import ObsidianExporter


# 加载测试数据
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
with open(FIXTURES_DIR / "papers.json") as f:
    TEST_DATA = json.load(f)
    TEST_PAPERS = TEST_DATA["papers"]
    TEST_PAPER = TEST_PAPERS[0]


class TestBibTeXExporter:
    """BibTeX 导出器测试"""

    def test_export_single_paper(self):
        """测试导出单篇论文"""
        exporter = BibTeXExporter()
        result = exporter.export_paper(TEST_PAPER)

        # 验证基本结构
        assert "@article{" in result or "@misc{" in result
        assert "vaswani2017attention" in result.lower()  # 引用键（小写）
        assert "Attention Is All You Need" in result  # 标题
        assert "Vaswani" in result  # 作者
        assert "1706.03762" in result  # arXiv ID

    def test_export_multiple_papers(self):
        """测试导出多篇论文"""
        exporter = BibTeXExporter()
        result = exporter.export_papers(TEST_PAPERS)

        # 验证两篇论文都被导出
        assert "vaswani2017attention" in result.lower()
        assert "devlin2018bert" in result.lower()
        assert result.count("@") == 2  # 两个条目

    def test_generate_key(self):
        """测试引用键生成"""
        exporter = BibTeXExporter()

        key = exporter._generate_key(TEST_PAPER)
        assert "vaswani" in key.lower()
        assert "2017" in key
        assert "attention" in key.lower()

    def test_escape_latex(self):
        """测试 LaTeX 特殊字符转义"""
        exporter = BibTeXExporter()

        # 测试各种特殊字符
        assert exporter._escape_latex("a & b") == r"a \& b"
        assert exporter._escape_latex("100%") == r"100\%"
        assert exporter._escape_latex("x_y") == r"x\_y"

    def test_export_to_file(self, tmp_path):
        """测试导出到文件"""
        exporter = BibTeXExporter()
        file_path = tmp_path / "test.bib"

        result = exporter.export_to_file(TEST_PAPERS, str(file_path))

        assert result.success
        assert file_path.exists()
        assert "@article" in file_path.read_text()

    def test_paper_without_arxiv_id(self):
        """测试没有 arXiv ID 的论文"""
        paper = {
            "title": "Test Paper",
            "authors": ["Author One"],
            "publish_date": "2023-01-01",
            "abstract": "Abstract here"
        }

        exporter = BibTeXExporter()
        result = exporter.export_paper(paper)

        # 应该使用 @misc 类型
        assert "@misc{" in result
        assert "Test Paper" in result


class TestObsidianExporter:
    """Obsidian 导出器测试"""

    def test_export_single_paper(self):
        """测试导出单篇论文"""
        exporter = ObsidianExporter()
        result = exporter.export_paper(TEST_PAPER)

        # 验证 YAML frontmatter
        assert result.startswith("---")
        assert "title:" in result
        assert "arxiv_id:" in result
        assert "tags:" in result

        # 验证正文
        assert "# Attention Is All You Need" in result
        assert "## 📋 基础信息" in result

    def test_build_frontmatter(self):
        """测试 YAML frontmatter 构建"""
        exporter = ObsidianExporter()
        frontmatter = exporter._build_frontmatter(TEST_PAPER)

        assert "title:" in frontmatter
        assert "Attention Is All You Need" in frontmatter
        assert "Transformer" in frontmatter  # 标签

    def test_build_body(self):
        """测试正文构建"""
        exporter = ObsidianExporter()
        body = exporter._build_body(TEST_PAPER)

        assert "# Attention Is All You Need" in body
        assert "## 📋 基础信息" in body
        assert "## 💡 一句话总结" in body

    def test_sanitize_filename(self):
        """测试文件名清理"""
        exporter = ObsidianExporter()

        # 测试特殊字符
        assert "/" not in exporter._sanitize_filename("a/b/c")
        assert ":" not in exporter._sanitize_filename("a:b")

        # 测试长度限制
        long_title = "a" * 200
        assert len(exporter._sanitize_filename(long_title)) <= 100

    def test_export_paper_with_knowledge_links(self):
        """测试带知识链接的论文"""
        exporter = ObsidianExporter()
        result = exporter.export_paper(TEST_PAPER)

        # 验证知识链接部分
        if TEST_PAPER.get("knowledge_links"):
            assert "## 🔗 知识关联" in result
            assert "[[" in result  # Obsidian 链接格式

    def test_export_paper_without_summary(self):
        """测试没有摘要的论文"""
        paper = {
            "title": "Test Paper",
            "authors": ["Author"],
            "arxiv_id": "1234.5678",
            "publish_date": "2023-01-01"
        }

        exporter = ObsidianExporter()
        result = exporter.export_paper(paper)

        assert "Test Paper" in result
        assert "---" in result  # YAML frontmatter


class TestBaseExporter:
    """导出器基类测试"""

    def test_get_field_from_dict(self):
        """测试从字典获取字段"""
        class DummyExporter(BaseExporter):
            name = "dummy"
            def export_paper(self, paper):
                return ""

        exporter = DummyExporter()
        paper = {"title": "Test", "authors": ["A", "B"]}

        assert exporter._get_field(paper, "title") == "Test"
        assert exporter._get_field(paper, "missing", "default") == "default"

    def test_get_field_from_object(self):
        """测试从对象获取字段"""
        class DummyExporter(BaseExporter):
            name = "dummy"
            def export_paper(self, paper):
                return ""

        class PaperObj:
            title = "Object Title"
            authors = ["X"]

        exporter = DummyExporter()
        paper = PaperObj()

        assert exporter._get_field(paper, "title") == "Object Title"
        assert exporter._get_field(paper, "missing", "default") == "default"


class TestExportResult:
    """导出结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        result = ExportResult(
            success=True,
            format="bibtex",
            content="@article{test}",
            file_path="/tmp/test.bib"
        )

        assert result.success
        assert result.format == "bibtex"
        assert result.error is None

    def test_failure_result(self):
        """测试失败结果"""
        result = ExportResult(
            success=False,
            format="obsidian",
            error="File not found"
        )

        assert not result.success
        assert result.error == "File not found"