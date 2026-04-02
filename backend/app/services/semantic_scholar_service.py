"""Semantic Scholar API 集成服务。

提供论文引用数、机构信息等数据获取功能。
API 文档: https://api.semanticscholar.org/
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)

# Semantic Scholar API 基础 URL
S2_API_BASE = "https://api.semanticscholar.org/graph/v1"

# API 请求超时
REQUEST_TIMEOUT = 30


@dataclass
class S2PaperInfo:
    """Semantic Scholar 论文信息"""

    paper_id: Optional[str] = None
    title: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    reference_count: int = 0
    authors: List[Dict[str, str]] = None  # [{name, affiliation}]
    year: Optional[int] = None
    venue: Optional[str] = None
    fields_of_study: List[str] = None
    tldr: Optional[str] = None

    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.fields_of_study is None:
            self.fields_of_study = []


class SemanticScholarService:
    """Semantic Scholar 服务类。

    提供论文信息查询功能，包括：
    - 引用数查询
    - 作者机构信息
    - 论文影响力指标
    """

    # API 请求间隔（避免限流）
    REQUEST_DELAY = 0.1  # 100ms

    def __init__(self, api_key: Optional[str] = None):
        """初始化服务。

        Args:
            api_key: Semantic Scholar API Key（可选，有 Key 可以提高速率限制）
        """
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话。"""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            )
        return self._session

    async def close(self):
        """关闭 HTTP 会话。"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """发送 API 请求。

        Args:
            endpoint: API 端点
            params: 查询参数

        Returns:
            JSON 响应数据，失败返回 None
        """
        session = await self._get_session()
        url = f"{S2_API_BASE}/{endpoint}"

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    logger.debug(f"论文未找到: {endpoint}")
                    return None
                elif response.status == 429:
                    logger.warning("Semantic Scholar API 限流，等待后重试")
                    await asyncio.sleep(1.0)
                    return await self._make_request(endpoint, params)
                else:
                    logger.warning(f"API 请求失败: {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"API 请求超时: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"API 请求错误: {e}")
            return None

    async def get_paper_by_arxiv(self, arxiv_id: str) -> Optional[S2PaperInfo]:
        """通过 ArXiv ID 获取论文信息。

        Args:
            arxiv_id: ArXiv 论文 ID（如 "2301.00001"）

        Returns:
            论文信息，未找到返回 None
        """
        # 使用 ARXIV: 前缀查询
        result = await self._make_request(
            f"paper/ARXIV:{arxiv_id}",
            params={
                "fields": "paperId,title,citationCount,influentialCitationCount,referenceCount,year,venue,authors,fieldsOfStudy,tldr"
            }
        )

        if result:
            return self._parse_paper_result(result)
        return None

    async def get_paper_by_title(self, title: str) -> Optional[S2PaperInfo]:
        """通过标题搜索论文。

        Args:
            title: 论文标题

        Returns:
            论文信息，未找到返回 None
        """
        # 搜索论文
        search_result = await self._make_request(
            "paper/search",
            params={
                "query": title,
                "limit": 1,
                "fields": "paperId,title,citationCount,influentialCitationCount,referenceCount,year,venue,authors,fieldsOfStudy,tldr"
            }
        )

        if search_result and search_result.get("data"):
            return self._parse_paper_result(search_result["data"][0])
        return None

    async def get_paper_batch(self, arxiv_ids: List[str]) -> Dict[str, S2PaperInfo]:
        """批量获取论文信息。

        Args:
            arxiv_ids: ArXiv ID 列表

        Returns:
            {arxiv_id: S2PaperInfo} 字典
        """
        results = {}

        # 并发请求（限制并发数）
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(arxiv_id: str):
            async with semaphore:
                info = await self.get_paper_by_arxiv(arxiv_id)
                return arxiv_id, info

        tasks = [fetch_one(aid) for aid in arxiv_ids]
        for coro in asyncio.as_completed(tasks):
            arxiv_id, info = await coro
            if info:
                results[arxiv_id] = info
            # 添加延迟避免限流
            await asyncio.sleep(self.REQUEST_DELAY)

        return results

    def _parse_paper_result(self, data: Dict) -> S2PaperInfo:
        """解析 API 响应数据。

        Args:
            data: API 返回的论文数据

        Returns:
            S2PaperInfo 对象
        """
        authors = []
        for author in data.get("authors", []):
            authors.append({
                "name": author.get("name", ""),
                "affiliation": author.get("affiliations", [None])[0] if author.get("affiliations") else None,
            })

        tldr = None
        if data.get("tldr"):
            tldr = data["tldr"].get("text")

        return S2PaperInfo(
            paper_id=data.get("paperId"),
            title=data.get("title"),
            citation_count=data.get("citationCount", 0) or 0,
            influential_citation_count=data.get("influentialCitationCount", 0) or 0,
            reference_count=data.get("referenceCount", 0) or 0,
            authors=authors,
            year=data.get("year"),
            venue=data.get("venue"),
            fields_of_study=data.get("fieldsOfStudy", []) or [],
            tldr=tldr,
        )

    async def get_hot_papers(self, category: str = "Computer Science", limit: int = 100) -> List[S2PaperInfo]:
        """获取热门论文（按引用数排序）。

        注意：这需要 API Key，否则可能受限。

        Args:
            category: 学科分类
            limit: 返回数量

        Returns:
            热门论文列表
        """
        # Semantic Scholar 没有直接的"热门论文"API
        # 这里使用搜索功能获取高引用论文
        search_result = await self._make_request(
            "paper/search",
            params={
                "query": category,
                "limit": limit,
                "fields": "paperId,title,citationCount,year,authors,venue",
                "sortBy": "citationCount",
            }
        )

        papers = []
        if search_result and search_result.get("data"):
            for item in search_result["data"]:
                papers.append(self._parse_paper_result(item))

        return papers

    async def check_if_hot(self, arxiv_id: str, threshold: int = 50) -> tuple[bool, int]:
        """检查论文是否为热门论文。

        Args:
            arxiv_id: ArXiv ID
            threshold: 引用数阈值

        Returns:
            (是否热门, 引用数)
        """
        info = await self.get_paper_by_arxiv(arxiv_id)
        if info:
            return info.citation_count >= threshold, info.citation_count
        return False, 0


# 全局实例
s2_service = SemanticScholarService()