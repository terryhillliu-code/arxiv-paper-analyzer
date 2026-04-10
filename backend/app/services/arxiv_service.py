"""ArXiv 论文抓取服务模块。

提供从 ArXiv 获取论文并存储到数据库的功能。
支持抓取后自动生成AI摘要。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

import arxiv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FetchLog, Paper
from app.services.paper_scorer import PaperScorer

logger = logging.getLogger(__name__)


class ArxivService:
    """ArXiv 论文抓取服务。

    提供从 ArXiv API 获取论文并存储到数据库的方法。
    """

    # 支持的 ArXiv 分类（使用配置模块）
    # 保持向后兼容，同时支持新的分层优先级系统
    SUPPORTED_CATEGORIES: List[str] = [
        # Tier 1 - 核心
        "cs.AI",  # 人工智能
        "cs.CL",  # 计算语言学
        "cs.LG",  # 机器学习
        "cs.CV",  # 计算机视觉
        "cs.NE",  # 神经与进化计算
        # Tier 2 - 重要扩展
        "cs.RO",  # 机器人
        "cs.DC",  # 分布式计算
        "cs.CR",  # 密码学与安全
        "cs.IR",  # 信息检索
        "cs.SE",  # 软件工程
        # Tier 3 - 关注
        "cs.HC",  # 人机交互
        "stat.ML",  # 机器学习（统计）
        "eess.AS",  # 音频信号处理
        "eess.IV",  # 图像视频处理
    ]

    @staticmethod
    async def fetch_papers(
        db: AsyncSession,
        query: str,
        max_results: int = 50,
    ) -> dict:
        """从 ArXiv 抓取论文并存入数据库。

        Args:
            db: 异步数据库会话
            query: ArXiv 查询语句
            max_results: 最大抓取数量

        Returns:
            包含抓取统计的字典：
            - total_fetched: 总抓取数量
            - new_papers: 新增论文数量
            - message: 结果消息
        """
        fetch_log = FetchLog(
            query=query,
            total_fetched=0,
            new_papers=0,
            fetch_time=datetime.now(),
            status="pending",
        )

        try:
            # 创建 ArXiv 客户端
            client = arxiv.Client()

            # 创建搜索对象
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            # 使用线程池执行同步的 arxiv 调用，避免阻塞事件循环
            def _fetch_sync():
                results = []
                for result in client.results(search):
                    results.append(result)
                return results

            all_results = await asyncio.to_thread(_fetch_sync)

            total_fetched = 0
            new_papers = 0

            # 使用集合跟踪当前批次已处理的 arxiv_id
            seen_ids_in_batch = set()

            # 处理结果
            for result in all_results:
                total_fetched += 1

                # 从 entry_id 中解析 arxiv_id
                # entry_id 格式: "http://arxiv.org/abs/2301.00001v1"
                arxiv_id = result.entry_id.split("/")[-1]
                # 移除版本号 (如 v1)
                if "v" in arxiv_id:
                    arxiv_id = arxiv_id.rsplit("v", 1)[0]

                # 检查当前批次是否已处理过
                if arxiv_id in seen_ids_in_batch:
                    continue
                seen_ids_in_batch.add(arxiv_id)

                # 检查数据库是否已存在
                stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
                existing = await db.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    continue

                # 提取作者列表
                authors = [author.name for author in result.authors]

                # 提取分类列表
                categories = [cat for cat in result.categories]

                # 计算初始 Tier（使用固化规则）
                from app.services.paper_scorer import PaperScorer
                score = PaperScorer.score(result.title, result.summary or "", authors)
                initial_tier = PaperScorer.get_initial_tier(score)

                # 创建 Paper 对象
                paper = Paper(
                    arxiv_id=arxiv_id,
                    title=result.title.strip(),
                    authors=authors,
                    abstract=result.summary.strip() if result.summary else None,
                    categories=categories,
                    publish_date=result.published,
                    pdf_url=result.pdf_url,
                    arxiv_url=result.entry_id,
                    tier=initial_tier,  # 入库时分配初始 Tier
                )

                db.add(paper)
                new_papers += 1

            # 提交事务（批量提交）
            await db.commit()

            # 更新抓取日志
            fetch_log.total_fetched = total_fetched
            fetch_log.new_papers = new_papers
            fetch_log.status = "success"
            db.add(fetch_log)
            await db.commit()

            message = f"成功抓取 {total_fetched} 篇论文，其中 {new_papers} 篇为新论文"
            logger.info(message)

            return {
                "total_fetched": total_fetched,
                "new_papers": new_papers,
                "message": message,
            }

        except Exception as e:
            # 回滚事务
            await db.rollback()

            # 记录错误日志
            error_msg = f"抓取论文失败: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # 更新抓取日志
            fetch_log.status = "failed"
            fetch_log.error_message = error_msg
            db.add(fetch_log)
            await db.commit()

            return {
                "total_fetched": 0,
                "new_papers": 0,
                "message": error_msg,
            }

    @staticmethod
    async def fetch_by_categories(
        db: AsyncSession,
        categories: List[str],
        max_results: int = 50,
    ) -> dict:
        """按分类抓取论文。

        Args:
            db: 异步数据库会话
            categories: ArXiv 分类列表
            max_results: 最大抓取数量

        Returns:
            抓取结果字典
        """
        # 构建查询语句: "cat:cs.AI OR cat:cs.CL"
        query = " OR ".join(f"cat:{cat}" for cat in categories)
        return await ArxivService.fetch_papers(db, query, max_results)

    @staticmethod
    async def fetch_by_relevance(
        db: AsyncSession,
        query: str,
        max_results: int = 10,
    ) -> dict:
        """按相关度排序搜索论文（无日期限制）。

        用于 NotebookLM 2.0 扩展搜索，打破本地库限制。

        Args:
            db: 异步数据库会话
            query: 搜索关键词或短语
            max_results: 最大返回数量

        Returns:
            抓取结果字典，包含：
            - total_fetched: 总抓取数量
            - new_papers: 新增论文数量
            - papers: 新增论文对象列表
            - message: 结果消息
        """
        fetch_log = FetchLog(
            query=f"(relevance) {query}",
            total_fetched=0,
            new_papers=0,
            fetch_time=datetime.now(),
            status="pending",
        )

        try:
            client = arxiv.Client()

            # 使用相关度排序，不设日期限制
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            def _fetch_sync():
                results = []
                for result in client.results(search):
                    results.append(result)
                return results

            all_results = await asyncio.to_thread(_fetch_sync)

            total_fetched = 0
            new_papers = 0
            new_paper_objects = []
            seen_ids_in_batch = set()

            for result in all_results:
                total_fetched += 1

                # 解析 arxiv_id
                arxiv_id = result.entry_id.split("/")[-1]
                if "v" in arxiv_id:
                    arxiv_id = arxiv_id.rsplit("v", 1)[0]

                if arxiv_id in seen_ids_in_batch:
                    continue
                seen_ids_in_batch.add(arxiv_id)

                # 检查数据库是否已存在
                stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
                existing = await db.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    continue

                # 创建 Paper 对象
                authors = [author.name for author in result.authors]
                categories_list = [cat for cat in result.categories]

                # 计算初始 Tier
                from app.services.paper_scorer import PaperScorer
                score = PaperScorer.score(result.title, result.summary or "", authors)
                if score >= 60:
                    initial_tier = "A"
                elif score >= 40:
                    initial_tier = "B"
                else:
                    initial_tier = "C"

                paper = Paper(
                    arxiv_id=arxiv_id,
                    title=result.title.strip(),
                    authors=authors,
                    abstract=result.summary.strip() if result.summary else None,
                    categories=categories_list,
                    publish_date=result.published,
                    pdf_url=result.pdf_url,
                    arxiv_url=result.entry_id,
                    tier=initial_tier,
                )

                db.add(paper)
                new_papers += 1
                new_paper_objects.append(paper)

            await db.commit()

            # 更新日志
            fetch_log.total_fetched = total_fetched
            fetch_log.new_papers = new_papers
            fetch_log.status = "success"
            db.add(fetch_log)
            await db.commit()

            message = f"相关度搜索找到 {total_fetched} 篇，新增 {new_papers} 篇"
            logger.info(message)

            return {
                "total_fetched": total_fetched,
                "new_papers": new_papers,
                "papers": new_paper_objects,
                "message": message,
            }

        except Exception as e:
            await db.rollback()
            error_msg = f"相关度搜索失败: {str(e)}"
            logger.error(error_msg, exc_info=True)

            fetch_log.status = "failed"
            fetch_log.error_message = error_msg
            db.add(fetch_log)
            await db.commit()

            return {
                "total_fetched": 0,
                "new_papers": 0,
                "papers": [],
                "message": error_msg,
            }

    @staticmethod
    async def fetch_by_keywords(
        db: AsyncSession,
        keywords: List[str],
        max_results: int = 50,
    ) -> dict:
        """按关键词抓取论文。

        Args:
            db: 异步数据库会话
            keywords: 关键词列表
            max_results: 最大抓取数量

        Returns:
            抓取结果字典
        """
        # 构建查询语句: 'all:"keyword1" OR all:"keyword2"'
        query = " OR ".join(f'all:"{kw}"' for kw in keywords)
        return await ArxivService.fetch_papers(db, query, max_results)

    @staticmethod
    async def fetch_by_date_range(
        db: AsyncSession,
        categories: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        max_results: int = 200,
        prefilter: bool = True,
    ) -> dict:
        """按日期范围抓取论文。

        ArXiv API 不直接支持日期筛选，此方法通过抓取更多论文后按日期过滤。

        Args:
            db: 异步数据库会话
            categories: 分类列表，默认使用主要AI相关分类
            date_from: 开始日期（包含）
            date_to: 结束日期（包含）
            max_results: 最大抓取数量（建议200-500以保证覆盖）
            prefilter: 是否启用预筛选（默认 True）

        Returns:
            抓取结果字典，包含：
            - total_fetched: 总抓取数量
            - new_papers: 新增论文数量
            - filtered_papers: 日期范围内论文数量
            - skipped_by_score: 因评分过低跳过的论文数
            - message: 结果消息
        """
        # 默认分类（使用核心分类）
        if not categories:
            categories = ["cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.NE"]

        # 处理时区：ArXiv 返回 UTC 时区，确保输入日期也有时区
        if date_from and date_from.tzinfo is None:
            date_from = date_from.replace(tzinfo=timezone.utc)
        if date_to and date_to.tzinfo is None:
            date_to = date_to.replace(tzinfo=timezone.utc)

        # 构建查询
        query = " OR ".join(f"cat:{cat}" for cat in categories)

        fetch_log = FetchLog(
            query=f"{query} (date filter: {date_from} to {date_to})",
            total_fetched=0,
            new_papers=0,
            fetch_time=datetime.now(),
            status="pending",
        )

        try:
            # 配置客户端，增加请求间隔避免限流
            client = arxiv.Client()
            client.delay_seconds = 5.0  # 增加延迟到 5 秒

            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            # 使用线程池执行同步的 arxiv 调用
            def _fetch_sync():
                results = []
                for result in client.results(search):
                    results.append(result)
                return results

            all_results = await asyncio.to_thread(_fetch_sync)

            total_fetched = 0
            new_papers = 0
            filtered_papers = 0
            skipped_by_score = 0
            early_stop = False

            # 使用集合跟踪当前批次已处理的 arxiv_id，避免同一批次重复插入
            seen_ids_in_batch = set()

            for result in all_results:
                total_fetched += 1

                # 日期过滤
                if date_from or date_to:
                    paper_date = result.published

                    # 如果论文日期早于 date_from，停止抓取（因为是降序排列）
                    if date_from and paper_date < date_from:
                        logger.info(f"到达日期边界，停止抓取: {paper_date} < {date_from}")
                        early_stop = True
                        break

                    # 如果论文日期晚于 date_to，跳过
                    if date_to and paper_date > date_to:
                        continue

                filtered_papers += 1

                # 解析 arxiv_id
                arxiv_id = result.entry_id.split("/")[-1]
                if "v" in arxiv_id:
                    arxiv_id = arxiv_id.rsplit("v", 1)[0]

                # 检查当前批次是否已处理过（ArXiv 可能返回同一论文的多个版本）
                if arxiv_id in seen_ids_in_batch:
                    logger.debug(f"跳过重复版本: {arxiv_id}")
                    continue
                seen_ids_in_batch.add(arxiv_id)

                # 检查是否已存在数据库中
                stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
                existing = await db.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    continue

                # 提取作者列表用于预筛选
                authors = [author.name for author in result.authors]
                title = result.title.strip()
                abstract = result.summary.strip() if result.summary else ""

                # 预筛选：评估论文重要性
                if prefilter:
                    if not PaperScorer.should_fetch(title, abstract, authors):
                        skipped_by_score += 1
                        logger.debug(f"跳过低分论文: {title[:40]}...")
                        continue

                # 创建 Paper 对象
                categories_list = [cat for cat in result.categories]

                # 计算初始 Tier
                score = PaperScorer.score(title, abstract, authors)
                if score >= 60:
                    initial_tier = "A"
                elif score >= 40:
                    initial_tier = "B"
                else:
                    initial_tier = "C"

                paper = Paper(
                    arxiv_id=arxiv_id,
                    title=result.title.strip(),
                    authors=authors,
                    abstract=result.summary.strip() if result.summary else None,
                    categories=categories_list,
                    publish_date=result.published,
                    pdf_url=result.pdf_url,
                    arxiv_url=result.entry_id,
                    tier=initial_tier,
                )

                db.add(paper)
                new_papers += 1

            await db.commit()

            # 更新日志
            fetch_log.total_fetched = total_fetched
            fetch_log.new_papers = new_papers
            fetch_log.status = "success"
            db.add(fetch_log)
            await db.commit()

            message = f"抓取 {total_fetched} 篇，日期范围内 {filtered_papers} 篇，新增 {new_papers} 篇"
            if skipped_by_score > 0:
                message += f"，预筛选跳过 {skipped_by_score} 篇"
            if early_stop:
                message += f"（提前终止于日期边界）"

            logger.info(message)

            return {
                "total_fetched": total_fetched,
                "new_papers": new_papers,
                "filtered_papers": filtered_papers,
                "skipped_by_score": skipped_by_score,
                "message": message,
            }

        except Exception as e:
            await db.rollback()
            error_msg = f"按日期抓取失败: {str(e)}"
            logger.error(error_msg, exc_info=True)

            fetch_log.status = "failed"
            fetch_log.error_message = error_msg
            db.add(fetch_log)
            await db.commit()

            return {
                "total_fetched": 0,
                "new_papers": 0,
                "filtered_papers": 0,
                "skipped_by_score": 0,
                "message": error_msg,
            }

    @staticmethod
    async def fetch_by_categories_batch(
        db: AsyncSession,
        categories: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        per_category_limit: int = 150,
        prefilter: bool = True,
        delay_between_categories: float = 10.0,
    ) -> dict:
        """按分类分批抓取论文，避免 ArXiv API 限流。

        每个分类单独抓取，分类之间增加延迟。

        Args:
            db: 异步数据库会话
            categories: 分类列表
            date_from: 开始日期
            date_to: 结束日期
            per_category_limit: 每个分类的最大抓取数量
            prefilter: 是否启用预筛选
            delay_between_categories: 分类之间的延迟（秒）

        Returns:
            汇总的抓取结果
        """
        if not categories:
            categories = ["cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.NE", "cs.RO", "cs.DC"]

        total_stats = {
            "total_fetched": 0,
            "new_papers": 0,
            "filtered_papers": 0,
            "skipped_by_score": 0,
            "categories_processed": 0,
            "errors": [],
        }

        logger.info(f"开始分批抓取，共 {len(categories)} 个分类")

        for i, category in enumerate(categories):
            logger.info(f"抓取分类 [{i+1}/{len(categories)}]: {category}")

            try:
                result = await ArxivService.fetch_by_date_range(
                    db=db,
                    categories=[category],
                    date_from=date_from,
                    date_to=date_to,
                    max_results=per_category_limit,
                    prefilter=prefilter,
                )

                total_stats["total_fetched"] += result.get("total_fetched", 0)
                total_stats["new_papers"] += result.get("new_papers", 0)
                total_stats["filtered_papers"] += result.get("filtered_papers", 0)
                total_stats["skipped_by_score"] += result.get("skipped_by_score", 0)
                total_stats["categories_processed"] += 1

                logger.info(
                    f"分类 {category} 完成: 抓取 {result.get('total_fetched', 0)}, "
                    f"入库 {result.get('new_papers', 0)}"
                )

                # 分类之间延迟，避免限流（最后一个分类不需要）
                if i < len(categories) - 1:
                    logger.info(f"等待 {delay_between_categories} 秒...")
                    await asyncio.sleep(delay_between_categories)

            except Exception as e:
                error_msg = f"分类 {category} 抓取失败: {str(e)}"
                logger.error(error_msg)
                total_stats["errors"].append(error_msg)
                # 继续处理下一个分类

        total_stats["message"] = (
            f"分批抓取完成: {total_stats['categories_processed']}/{len(categories)} 分类, "
            f"总数 {total_stats['total_fetched']}, 入库 {total_stats['new_papers']}"
        )

        return total_stats

    @staticmethod
    async def fetch_by_ids(arxiv_ids: List[str]) -> List[dict]:
        """根据 arXiv ID 批量获取论文信息（不存入数据库）。

        Args:
            arxiv_ids: arXiv ID 列表（支持批量查询）

        Returns:
            论文信息列表
        """
        import arxiv

        client = arxiv.Client()
        results = []

        if not arxiv_ids:
            return results

        try:
            # 批量查询：arXiv API 支持在 id_list 中传入多个 ID
            search = arxiv.Search(
                id_list=arxiv_ids,
                max_results=len(arxiv_ids)
            )

            def _fetch_sync():
                papers = []
                for result in client.results(search):
                    papers.append({
                        "arxiv_id": result.entry_id.split("/")[-1],
                        "title": result.title,
                        "abstract": result.summary,
                        "authors": [a.name for a in result.authors],
                        "categories": [c for c in result.categories],
                        "publish_date": result.published,
                        "arxiv_url": result.entry_id,
                        "pdf_url": result.pdf_url,
                    })
                return papers

            results = await asyncio.to_thread(_fetch_sync)
            logger.info(f"批量获取 {len(arxiv_ids)} 篇论文，返回 {len(results)} 篇")

        except Exception as e:
            logger.error(f"批量获取论文失败: {e}")

        return results