"""智能搜索 API 集成测试。"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app


@pytest.fixture
def client():
    """创建测试客户端。"""
    with TestClient(app) as test_client:
        yield test_client


class TestSmartSearchAPI:
    """智能搜索 API 端点测试。"""

    def test_smart_search_basic(self, client):
        """测试基本智能搜索。"""
        response = client.get(
            "/api/papers/smart-search",
            params={"query": "transformer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "papers" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_smart_search_with_semantic_disabled(self, client):
        """测试禁用语义搜索。"""
        response = client.get(
            "/api/papers/smart-search",
            params={"query": "attention", "use_semantic": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert "papers" in data

    def test_smart_search_with_tier_filter(self, client):
        """测试带 Tier 筛选的搜索。"""
        response = client.get(
            "/api/papers/smart-search",
            params={"query": "learning", "tier": "A"},
        )
        assert response.status_code == 200
        data = response.json()
        # 验证返回的论文都是 Tier A
        for paper in data["papers"]:
            if paper.get("tier"):
                assert paper["tier"] == "A"

    def test_smart_search_with_categories(self, client):
        """测试带分类筛选的搜索。"""
        response = client.get(
            "/api/papers/smart-search",
            params={"query": "neural", "categories": "cs.AI"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "papers" in data

    def test_smart_search_pagination(self, client):
        """测试分页功能。"""
        # 第一页
        response1 = client.get(
            "/api/papers/smart-search",
            params={"query": "model", "page": 1, "page_size": 5},
        )
        assert response1.status_code == 200
        data1 = response1.json()

        # 第二页
        response2 = client.get(
            "/api/papers/smart-search",
            params={"query": "model", "page": 2, "page_size": 5},
        )
        assert response2.status_code == 200
        data2 = response2.json()

        # 两页结果不应完全相同
        if data1["total"] > 5:
            ids1 = {p["id"] for p in data1["papers"]}
            ids2 = {p["id"] for p in data2["papers"]}
            assert ids1 != ids2

    def test_smart_search_empty_query(self, client):
        """测试空查询参数。"""
        # 空 query 应该返回 422 错误（缺少必需参数）
        response = client.get("/api/papers/smart-search")
        assert response.status_code == 422

    def test_smart_search_rag_fallback(self, client):
        """测试 RAG 服务不可用时的降级。"""
        # 模拟 RAG 服务返回空结果（内部错误被捕获）
        with patch("app.services.rag_client.RagClient.retrieve") as mock_retrieve:
            mock_retrieve.return_value = []  # RAG 内部错误后返回空列表

            response = client.get(
                "/api/papers/smart-search",
                params={"query": "attention"},
            )
            # 应该降级为 SQL 搜索，仍然返回结果
            assert response.status_code == 200
            data = response.json()
            assert "papers" in data

    def test_smart_search_query_validation(self, client):
        """测试查询输入验证（超长查询截断）。"""
        # 构造超长查询（超过 200 字符）
        long_query = "a" * 500
        response = client.get(
            "/api/papers/smart-search",
            params={"query": long_query},
        )
        # 应该正常处理（内部截断）
        assert response.status_code == 200