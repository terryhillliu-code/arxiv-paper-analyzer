"""
CLI 单元测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typer.testing import CliRunner

from app.cli.main import app
from app.cli import commands


runner = CliRunner()


class TestSearchCommand:
    """测试搜索命令"""

    @pytest.mark.asyncio
    async def test_search_papers_success(self):
        """测试搜索成功"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_papers = [
            MagicMock(
                id=1,
                title="Test Paper",
                arxiv_id="2401.00001",
                authors=["Author"],
                summary="Summary",
                categories=["cs.AI"],
                tags=[],
                tier="A",
                publish_date=None,
                popularity_score=0.5,
            )
        ]
        mock_result.scalars.return_value.all.return_value = mock_papers
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            result = await commands.search_papers({"query": "test"})

        assert result["success"] is True
        assert result["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_search_papers_with_filters(self):
        """测试带过滤条件搜索"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_papers = []
        mock_result.scalars.return_value.all.return_value = mock_papers
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            result = await commands.search_papers({
                "query": "test",
                "categories": ["cs.AI"],
                "tags": ["important"],
                "sort_by": "popularity",
            })

        assert result["success"] is True


class TestGetCommand:
    """测试获取命令"""

    @pytest.mark.asyncio
    async def test_get_paper_success(self):
        """测试获取成功"""
        mock_paper = MagicMock(
            id=1,
            title="Test Paper",
            arxiv_id="2401.00001",
            authors=["Author"],
            summary="Summary",
            categories=["cs.AI"],
            tags=[],
            tier="A",
            publish_date=None,
            popularity_score=0.5,
            key_contributions=[],
            methodology=None,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            result = await commands.get_paper({"paper_id": 1})

        assert result["success"] is True
        assert result["data"]["id"] == 1

    @pytest.mark.asyncio
    async def test_get_paper_not_found(self):
        """测试论文不存在"""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            result = await commands.get_paper({"paper_id": 999})

        assert result["success"] is False
        assert "不存在" in result["error"]


class TestTrendingCommand:
    """测试热门命令"""

    @pytest.mark.asyncio
    async def test_get_trending_success(self):
        """测试获取热门成功"""
        from datetime import datetime, timezone

        mock_paper = MagicMock(
            id=1,
            title="Trending Paper",
            arxiv_id="2401.00001",
            authors=["Author"],
            summary="Summary",
            categories=["cs.AI"],
            tags=[],
            tier="S",
            publish_date=datetime.now(timezone.utc),
            popularity_score=0.9,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            result = await commands.get_trending({"days": 7})

        assert result["success"] is True
        assert "days" in result["data"]


class TestExportCommand:
    """测试导出命令"""

    @pytest.mark.asyncio
    async def test_export_bibtex(self):
        """测试 BibTeX 导出"""
        mock_paper = MagicMock(
            id=1,
            title="Test Paper",
            arxiv_id="2401.00001",
            authors=["Author One", "Author Two"],
            summary="Summary",
            categories=["cs.AI"],
            tags=[],
            tier="A",
            publish_date=None,
            key_contributions=[],
            methodology=None,
            knowledge_links=[],
            action_items=[],
            institutions=[],
            analysis_report=None,
            one_line_summary=None,
            overall_rating=None,
            pdf_url="http://example.com/pdf",
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_session.execute.return_value = mock_result

        with patch("app.database.async_session_maker") as maker:
            maker.return_value.__aenter__.return_value = mock_session

            result = await commands.export_papers({
                "paper_ids": [1],
                "format": "bibtex",
            })

        assert result["success"] is True
        assert "content" in result["data"]

    @pytest.mark.asyncio
    async def test_export_empty_ids(self):
        """测试空 ID 列表"""
        result = await commands.export_papers({
            "paper_ids": [],
            "format": "bibtex",
        })

        assert result["success"] is False


class TestPublishCommand:
    """测试发布命令"""

    @pytest.mark.asyncio
    async def test_publish_success(self):
        """测试发布成功"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Published 1 papers"}

        with patch("httpx.AsyncClient") as client_mock:
            client_instance = AsyncMock()
            client_instance.__aenter__.return_value = client_instance
            client_instance.post.return_value = mock_response
            client_mock.return_value = client_instance

            result = await commands.publish_papers({
                "paper_ids": [1],
                "platform": "feishu",
            })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_publish_empty_ids(self):
        """测试空 ID 列表"""
        result = await commands.publish_papers({
            "paper_ids": [],
            "platform": "feishu",
        })

        assert result["success"] is False


class TestCLIApp:
    """测试 CLI 应用"""

    def test_app_help(self):
        """测试帮助信息"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "arxiv-cli" in result.output

    def test_search_help(self):
        """测试搜索帮助"""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "搜索论文" in result.output

    def test_get_help(self):
        """测试获取帮助"""
        result = runner.invoke(app, ["get", "--help"])
        assert result.exit_code == 0
        assert "论文 ID" in result.output

    def test_trending_help(self):
        """测试热门帮助"""
        result = runner.invoke(app, ["trending", "--help"])
        assert result.exit_code == 0
        assert "热门论文" in result.output

    def test_analyze_help(self):
        """测试分析帮助"""
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "深度分析" in result.output

    def test_summary_help(self):
        """测试摘要帮助"""
        result = runner.invoke(app, ["summary", "--help"])
        assert result.exit_code == 0
        assert "AI 摘要" in result.output

    def test_export_help(self):
        """测试导出帮助"""
        result = runner.invoke(app, ["export", "--help"])
        assert result.exit_code == 0
        assert "导出论文" in result.output

    def test_publish_help(self):
        """测试发布帮助"""
        result = runner.invoke(app, ["publish", "--help"])
        assert result.exit_code == 0
        assert "发布论文" in result.output

    def test_list_platforms(self):
        """测试列出平台"""
        result = runner.invoke(app, ["list-platforms"])
        assert result.exit_code == 0
        # 检查是否有表格输出
        assert "可用发布平台" in result.output or "平台" in result.output