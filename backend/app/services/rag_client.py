"""RAG 服务客户端。

封装 RAG 服务调用，支持连接池复用。
"""

import logging
from typing import List, Dict, Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_CONNECTIONS = 10
DEFAULT_MAX_KEEPALIVE = 5


class RagClient:
    """RAG 服务客户端类。

    封装 RAG 服务的 HTTP 调用，支持：
    - 连接池复用（应用级单例）
    - 统一错误处理
    - 超时配置

    用法:
        # 推荐方式：依赖注入
        client = get_rag_client()
        results = await client.retrieve("query")

        # 或上下文管理器（适用于测试）
        async with RagClient() as client:
            results = await client.retrieve("query")
    """

    _instance: "RagClient | None" = None

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url or getattr(
            get_settings(), 'rag_service_url', 'http://127.0.0.1:8765'
        )
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def get_instance(cls) -> "RagClient":
        """获取全局单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def __aenter__(self) -> "RagClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(
                max_keepalive_connections=DEFAULT_MAX_KEEPALIVE,
                max_connections=DEFAULT_MAX_CONNECTIONS,
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=DEFAULT_MAX_KEEPALIVE,
                    max_connections=DEFAULT_MAX_CONNECTIONS,
                ),
            )
        return self._client

    async def close(self):
        """关闭 HTTP 客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def retrieve(
        self,
        query: str,
        top_k: int = 30,
    ) -> List[Dict[str, Any]]:
        """执行语义检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            检索结果列表（失败返回空列表）
        """
        try:
            client = self._get_client()
            response = await client.post(
                "/retrieve",
                json={"query": query, "top_k": top_k},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            else:
                logger.warning(f"RAG retrieve 返回错误: {response.status_code}")
                return []
        except httpx.TimeoutException:
            logger.warning("RAG retrieve 超时")
            return []
        except httpx.RequestError as e:
            logger.warning(f"RAG retrieve 请求失败: {e}")
            return []
        except Exception as e:
            logger.warning(f"RAG retrieve 异常: {e}")
            return []


# 全局获取函数（依赖注入用）
def get_rag_client() -> RagClient:
    """获取 RAG 客户端实例。

    推荐在 FastAPI 依赖中使用此函数。
    返回单例实例，连接池在整个应用生命周期内复用。
    """
    return RagClient.get_instance()