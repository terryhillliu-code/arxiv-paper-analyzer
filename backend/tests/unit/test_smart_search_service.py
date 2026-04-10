"""智能搜索服务单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.smart_search_service import SmartSearchService


class TestSmartSearchService:
    """SmartSearchService 测试。"""

    def test_extract_arxiv_ids_from_rag_results_with_prefix(self):
        """测试从 RAG 结果中提取 arxiv_id（带前缀格式）。"""
        service = SmartSearchService()
        rag_results = [
            {"source": "arxiv:2301.12345:chunk_1", "text": "some text"},
            {"source": "arxiv:2402.56789:chunk_2", "text": "other text"},
        ]
        arxiv_ids = service._extract_arxiv_ids_from_rag_results(rag_results)
        assert "2301.12345" in arxiv_ids
        assert "2402.56789" in arxiv_ids

    def test_extract_arxiv_ids_from_rag_results_from_filename(self):
        """测试从文件名中提取 arxiv_id。"""
        service = SmartSearchService()
        rag_results = [
            {"source": "/path/to/PAPER_2301.12345.md", "text": "some text"},
            {"source": "/path/to/2402.56789_summary.md", "text": "other text"},
        ]
        arxiv_ids = service._extract_arxiv_ids_from_rag_results(rag_results)
        assert "2301.12345" in arxiv_ids
        assert "2402.56789" in arxiv_ids

    def test_extract_arxiv_ids_empty_results(self):
        """测试空 RAG 结果。"""
        service = SmartSearchService()
        arxiv_ids = service._extract_arxiv_ids_from_rag_results([])
        assert arxiv_ids == []

    def test_extract_arxiv_ids_no_match(self):
        """测试无匹配的 RAG 结果。"""
        service = SmartSearchService()
        rag_results = [
            {"source": "/path/to/random_file.md", "text": "some text"},
        ]
        arxiv_ids = service._extract_arxiv_ids_from_rag_results(rag_results)
        assert arxiv_ids == []


class TestSqlSearch:
    """SQL 搜索测试。"""

    @pytest.mark.asyncio
    async def test_sql_search_basic(self):
        """测试基本 SQL 搜索。"""
        service = SmartSearchService()

        # Mock 数据库会话
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(1,), (2,), (3,)]
        mock_db.execute.return_value = mock_result

        paper_ids = await service.sql_search(mock_db, "transformer", limit=10)

        assert len(paper_ids) == 3
        assert paper_ids == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_sql_search_with_categories(self):
        """测试带分类筛选的 SQL 搜索。"""
        service = SmartSearchService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(1,)]
        mock_db.execute.return_value = mock_result

        paper_ids = await service.sql_search(
            mock_db, "attention", categories=["cs.AI", "cs.LG"], limit=10
        )

        assert len(paper_ids) == 1

    @pytest.mark.asyncio
    async def test_sql_search_with_tier(self):
        """测试带 Tier 筛选的 SQL 搜索。"""
        service = SmartSearchService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(5,)]
        mock_db.execute.return_value = mock_result

        paper_ids = await service.sql_search(mock_db, "RLHF", tier="A", limit=10)

        assert len(paper_ids) == 1


class TestMatchPapersByArxivIds:
    """arxiv_id 匹配测试。"""

    @pytest.mark.asyncio
    async def test_match_papers_found(self):
        """测试成功匹配论文。"""
        service = SmartSearchService()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(10,), (20,)]
        mock_db.execute.return_value = mock_result

        paper_ids = await service.match_papers_by_arxiv_ids(
            mock_db, ["2301.12345", "2402.56789"]
        )

        assert len(paper_ids) == 2

    @pytest.mark.asyncio
    async def test_match_papers_empty_list(self):
        """测试空 arxiv_id 列表。"""
        service = SmartSearchService()

        mock_db = AsyncMock()
        paper_ids = await service.match_papers_by_arxiv_ids(mock_db, [])

        assert paper_ids == []


class TestHybridSearch:
    """混合搜索测试。"""

    @pytest.mark.asyncio
    async def test_hybrid_search_merges_results(self):
        """测试混合搜索合并结果。"""
        service = SmartSearchService()

        mock_db = AsyncMock()

        # SQL 搜索返回 [1, 2, 3]
        sql_result = MagicMock()
        sql_result.fetchall.return_value = [(1,), (2,), (3,)]

        # arxiv_id 匹配返回 [4, 5]
        arxiv_result = MagicMock()
        arxiv_result.fetchall.return_value = [(4,), (5,)]

        # 设置 mock 执行顺序
        mock_db.execute.side_effect = [sql_result, arxiv_result]

        rag_results = [
            {"source": "arxiv:2301.12345:chunk_1", "text": "some text"},
        ]

        paper_ids = await service.hybrid_search(
            mock_db, "transformer", rag_results, top_k=10
        )

        # SQL 结果在前，向量结果补充
        assert 1 in paper_ids
        assert 2 in paper_ids
        assert 3 in paper_ids

    @pytest.mark.asyncio
    async def test_hybrid_search_deduplicates(self):
        """测试混合搜索去重。"""
        service = SmartSearchService()

        mock_db = AsyncMock()

        # SQL 搜索返回 [1, 2]
        sql_result = MagicMock()
        sql_result.fetchall.return_value = [(1,), (2,)]

        # arxiv_id 匹配也返回 [2]（重复）
        arxiv_result = MagicMock()
        arxiv_result.fetchall.return_value = [(2,), (3,)]

        mock_db.execute.side_effect = [sql_result, arxiv_result]

        rag_results = [
            {"source": "arxiv:2301.12345:chunk_1", "text": "some text"},
        ]

        paper_ids = await service.hybrid_search(
            mock_db, "test", rag_results, top_k=10
        )

        # 确保去重
        assert paper_ids.count(2) == 1

    @pytest.mark.asyncio
    async def test_hybrid_search_respects_top_k(self):
        """测试混合搜索限制返回数量。"""
        service = SmartSearchService()

        mock_db = AsyncMock()

        # SQL 搜索返回很多结果
        sql_result = MagicMock()
        sql_result.fetchall.return_value = [(i,) for i in range(1, 21)]

        # arxiv_id 匹配返回更多
        arxiv_result = MagicMock()
        arxiv_result.fetchall.return_value = [(i,) for i in range(21, 41)]

        mock_db.execute.side_effect = [sql_result, arxiv_result]

        rag_results = [
            {"source": f"arxiv:2301.{i}:chunk", "text": "text"} for i in range(12345, 12365)
        ]

        paper_ids = await service.hybrid_search(
            mock_db, "test", rag_results, top_k=5
        )

        # 限制返回数量
        assert len(paper_ids) <= 5