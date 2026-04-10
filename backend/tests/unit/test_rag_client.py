"""RAG 客户端单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag_client import RagClient, get_rag_client


class TestRagClient:
    """RagClient 测试。"""

    def test_singleton_pattern(self):
        """测试单例模式。"""
        instance1 = RagClient.get_instance()
        instance2 = RagClient.get_instance()
        assert instance1 is instance2

    def test_get_rag_client_returns_singleton(self):
        """测试 get_rag_client 返回单例。"""
        client = get_rag_client()
        assert isinstance(client, RagClient)
        assert client is RagClient.get_instance()

    def test_base_url_from_config(self):
        """测试从配置读取 base_url。"""
        client = RagClient()
        # 默认值
        assert client.base_url is not None

    def test_custom_base_url(self):
        """测试自定义 base_url。"""
        client = RagClient(base_url="http://custom:9999")
        assert client.base_url == "http://custom:9999"

    @pytest.mark.asyncio
    async def test_retrieve_success(self):
        """测试成功检索。"""
        client = RagClient()

        # Mock httpx client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"text": "result1", "source": "source1", "score": 0.9},
                {"text": "result2", "source": "source2", "score": 0.8},
            ]
        }

        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            results = await client.retrieve("test query", top_k=10)

            assert len(results) == 2
            assert results[0]["text"] == "result1"

    @pytest.mark.asyncio
    async def test_retrieve_error_status(self):
        """测试非 200 状态码。"""
        client = RagClient()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            results = await client.retrieve("test query")

            assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_timeout(self):
        """测试超时处理。"""
        import httpx
        client = RagClient()

        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_get_client.return_value = mock_client

            results = await client.retrieve("test query")

            assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_connection_error(self):
        """测试连接错误处理。"""
        import httpx
        client = RagClient()

        with patch.object(client, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("connection failed")
            )
            mock_get_client.return_value = mock_client

            results = await client.retrieve("test query")

            assert results == []

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试上下文管理器模式。"""
        async with RagClient(base_url="http://test:8080") as client:
            assert client._client is not None
            assert client.base_url == "http://test:8080"

        # 退出后客户端应关闭
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭方法。"""
        client = RagClient()
        client._get_client()  # 创建客户端
        assert client._client is not None

        await client.close()
        assert client._client is None