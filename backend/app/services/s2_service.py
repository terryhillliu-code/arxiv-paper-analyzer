"""Semantic Scholar API 集成服务。

提供论文引用数和影响力评分查询功能。
API 文档: https://api.semanticscholar.org/api-docs/graph

限流说明：
- 免费限额: 5000 次/月，每 5 分钟 100 次
- 有 API Key 可提高限额
- 建议使用批量查询减少请求次数
"""

import asyncio
import logging
from typing import Dict, List, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class SemanticScholarService:
    """Semantic Scholar API 服务。

    免费限额: 5000 次/月（有 API Key 可提高限额）
    批量查询: 最多 500 个 ID/次
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    BATCH_SIZE = 500  # 每批最大 500
    REQUEST_DELAY = 0.1  # 请求间隔（秒）
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # 重试延迟（秒）

    def __init__(self, api_key: Optional[str] = None):
        """初始化服务。

        Args:
            api_key: Semantic Scholar API Key（可选）
        """
        settings = get_settings()
        self.api_key = api_key or settings.semantic_scholar_api_key
        self.headers = {
            "User-Agent": "ArXivPaperAnalyzer/1.0",
        }
        if self.api_key:
            self.headers["x-api-key"] = self.api_key

    async def get_paper_metrics(self, arxiv_id: str) -> Optional[Dict]:
        """获取单篇论文的引用数和影响力评分。

        Args:
            arxiv_id: ArXiv 论文 ID（如 "2301.00001"）

        Returns:
            包含 citationCount, influenceScore, paperId 的字典，或 None
        """
        url = f"{self.BASE_URL}/paper/arXiv:{arxiv_id}"
        params = {"fields": "paperId,citationCount,referenceCount,influentialCitationCount"}

        for attempt in range(self.MAX_RETRIES):
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    await asyncio.sleep(self.REQUEST_DELAY)
                    response = await client.get(url, headers=self.headers, params=params)

                    if response.status_code == 200:
                        data = response.json()
                        return {
                            "s2_paper_id": data.get("paperId"),
                            "citation_count": data.get("citationCount", 0),
                            "reference_count": data.get("referenceCount", 0),
                            "influential_citation_count": data.get("influentialCitationCount", 0),
                        }
                    elif response.status_code == 404:
                        logger.debug(f"论文未在 Semantic Scholar 找到: {arxiv_id}")
                        return None
                    elif response.status_code == 429:
                        # 限流，等待后重试
                        wait_time = self.RETRY_DELAY * (attempt + 1)
                        logger.warning(f"API 限流，等待 {wait_time}s 后重试 ({attempt + 1}/{self.MAX_RETRIES})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"获取论文评分失败 {arxiv_id}: HTTP {response.status_code}")
                        return None

                except httpx.TimeoutException:
                    logger.warning(f"获取论文评分超时: {arxiv_id}")
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(self.RETRY_DELAY)
                        continue
                    return None
                except Exception as e:
                    logger.error(f"获取论文评分异常 {arxiv_id}: {e}")
                    return None

        return None

    async def batch_get_metrics(
        self,
        arxiv_ids: List[str],
        batch_size: int = BATCH_SIZE,
    ) -> Dict[str, Dict]:
        """批量获取论文引用数和影响力评分。

        Args:
            arxiv_ids: ArXiv 论文 ID 列表
            batch_size: 每批数量（最大 500）

        Returns:
            字典: {arxiv_id: {citation_count, influence_score, s2_paper_id}}
        """
        if not arxiv_ids:
            return {}

        results = {}
        total = len(arxiv_ids)

        logger.info(f"开始批量获取 Semantic Scholar 评分: {total} 篇论文")

        # 使用并发限制的信号量
        semaphore = asyncio.Semaphore(5)  # 最多 5 个并发请求

        async def fetch_with_limit(client: httpx.AsyncClient, arxiv_id: str) -> Optional[tuple]:
            """带并发限制的获取。"""
            async with semaphore:
                await asyncio.sleep(self.REQUEST_DELAY)
                result = await self._get_metrics_single(client, arxiv_id)
                return (arxiv_id, result) if result else None

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 分批处理
            for i in range(0, total, batch_size):
                batch = arxiv_ids[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total + batch_size - 1) // batch_size

                logger.info(f"处理批次 {batch_num}/{total_batches}: {len(batch)} 篇")

                # 并发获取，但有信号量限制
                tasks = [fetch_with_limit(client, aid) for aid in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.warning(f"查询异常: {result}")
                        continue
                    if result:
                        arxiv_id, metrics = result
                        results[arxiv_id] = metrics

                # 批次间延迟，避免限流
                if i + batch_size < total:
                    await asyncio.sleep(1.0)

        logger.info(f"Semantic Scholar 评分获取完成: {len(results)}/{total} 篇")

        return results

    async def _get_metrics_single(
        self,
        client: httpx.AsyncClient,
        arxiv_id: str,
    ) -> Optional[Dict]:
        """使用已有 client 获取单篇论文评分。

        Args:
            client: httpx AsyncClient
            arxiv_id: ArXiv 论文 ID

        Returns:
            评分字典或 None
        """
        url = f"{self.BASE_URL}/paper/arXiv:{arxiv_id}"
        params = {"fields": "paperId,citationCount,referenceCount,influentialCitationCount"}

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.get(url, headers=self.headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "s2_paper_id": data.get("paperId"),
                        "citation_count": data.get("citationCount", 0),
                        "influential_citation_count": data.get("influentialCitationCount", 0),
                        "influence_score": data.get("influenceScore", 0.0),
                    }
                elif response.status_code == 404:
                    return None
                elif response.status_code == 429:
                    # 限流，等待后重试
                    wait_time = self.RETRY_DELAY * (attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.debug(f"获取评分失败 {arxiv_id}: HTTP {response.status_code}")
                    return None

            except Exception as e:
                logger.debug(f"获取评分异常 {arxiv_id}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY)
                    continue
                return None

        return None


# 单例实例
_s2_service: Optional[SemanticScholarService] = None


def get_s2_service() -> SemanticScholarService:
    """获取 Semantic Scholar 服务单例。"""
    global _s2_service
    if _s2_service is None:
        _s2_service = SemanticScholarService()
    return _s2_service