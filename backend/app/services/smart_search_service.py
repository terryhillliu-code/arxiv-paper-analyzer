"""智能搜索服务。

提供语义搜索能力，结合 SQL 模糊搜索和 RAG 向量检索。
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper

logger = logging.getLogger(__name__)

# 预编译正则表达式
_ARXIV_PREFIX_PATTERN = re.compile(r"arxiv:([0-9.]+):")
_ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})")

# 常量定义
QUERY_MAX_LENGTH = 200
MAX_CATEGORIES = 10
DEFAULT_TOP_K = 20
VALID_TIERS = ("A", "B", "C")


class SmartSearchService:
    """智能搜索服务类。

    支持两种搜索模式:
    1. SQL 模糊搜索：传统的 ILIKE 模式匹配
    2. 语义搜索：RAG 向量检索 + 数据库匹配

    混合搜索策略:
    - SQL 结果在前（精确匹配优先）
    - 向量结果补充（语义相关）
    - 去重合并
    """

    async def sql_search(
        self,
        db: AsyncSession,
        query: str,
        categories: Optional[List[str]] = None,
        tier: Optional[str] = None,
        limit: int = 50,
    ) -> List[int]:
        """SQL 模糊搜索。

        Args:
            db: 数据库会话
            query: 搜索关键词
            categories: 分类筛选列表
            tier: Tier 筛选
            limit: 返回数量限制

        Returns:
            匹配的论文 ID 列表
        """
        # 输入验证：限制查询长度防止滥用
        query = query[:QUERY_MAX_LENGTH]

        search_pattern = f"%{query}%"
        sql_query = select(Paper.id).where(
            or_(
                Paper.title.ilike(search_pattern),
                Paper.abstract.ilike(search_pattern),
                Paper.summary.ilike(search_pattern),
                Paper.authors.like(search_pattern),
            )
        )

        # 分类筛选
        if categories:
            # 输入验证：限制分类数量
            categories = categories[:MAX_CATEGORIES]
            cat_conditions = [
                Paper.categories.like(f'%"{cat}"%') for cat in categories
            ]
            sql_query = sql_query.where(or_(*cat_conditions))

        # Tier 筛选
        if tier:
            # 输入验证：只允许有效 Tier 值
            if tier.upper() in VALID_TIERS:
                sql_query = sql_query.where(Paper.tier == tier.upper())

        sql_query = sql_query.limit(limit)
        result = await db.execute(sql_query)
        return [row[0] for row in result.fetchall()]

    def _extract_arxiv_ids_from_rag_results(
        self, rag_results: List[Dict[str, Any]]
    ) -> List[str]:
        """从 RAG 结果中提取 arxiv_id。

        RAG source 格式: "arxiv:2301.12345:..."
        或 Markdown 文件路径可能包含 arxiv_id

        Args:
            rag_results: RAG 搜索结果列表

        Returns:
            提取的 arxiv_id 列表
        """
        arxiv_ids: List[str] = []

        for item in rag_results:
            source = item.get("source", "")

            # 格式1: "arxiv:2301.12345:..."
            match = _ARXIV_PREFIX_PATTERN.search(source)
            if match:
                arxiv_ids.append(match.group(1))
                continue

            # 格式2: 从文件名提取 (如 "PAPER_2301.12345.md")
            match = _ARXIV_ID_PATTERN.search(source)
            if match:
                arxiv_ids.append(match.group(1))

        return arxiv_ids

    async def match_papers_by_arxiv_ids(
        self,
        db: AsyncSession,
        arxiv_ids: List[str],
    ) -> List[int]:
        """根据 arxiv_id 匹配数据库论文。

        Args:
            db: 数据库会话
            arxiv_ids: arxiv_id 列表

        Returns:
            匹配的论文 ID 列表
        """
        if not arxiv_ids:
            return []

        query = select(Paper.id).where(Paper.arxiv_id.in_(arxiv_ids))
        result = await db.execute(query)
        return [row[0] for row in result.fetchall()]

    async def hybrid_search(
        self,
        db: AsyncSession,
        query: str,
        rag_results: List[Dict[str, Any]],
        categories: Optional[List[str]] = None,
        tier: Optional[str] = None,
        top_k: int = 20,
    ) -> List[int]:
        """混合搜索：SQL + 向量。

        Args:
            db: 数据库会话
            query: 搜索关键词
            rag_results: RAG 向量搜索结果
            categories: 分类筛选
            tier: Tier 筛选
            top_k: 返回数量

        Returns:
            合并后的论文 ID 列表（SQL 结果优先）
        """
        # 1. SQL 模糊搜索
        sql_ids = await self.sql_search(db, query, categories, tier, limit=top_k)

        # 2. 从 RAG 结果提取 arxiv_id，匹配数据库
        arxiv_ids = self._extract_arxiv_ids_from_rag_results(rag_results)
        vector_ids = await self.match_papers_by_arxiv_ids(db, arxiv_ids)

        # 3. 合并去重，SQL 结果在前
        seen: Set[int] = set(sql_ids)
        merged: List[int] = list(sql_ids)

        for paper_id in vector_ids:
            if paper_id not in seen:
                seen.add(paper_id)
                merged.append(paper_id)

        return merged[:top_k]