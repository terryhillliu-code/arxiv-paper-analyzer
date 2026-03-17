"""ArXiv 论文抓取服务模块。

提供从 ArXiv 获取论文并存储到数据库的功能。
"""

import logging
from datetime import datetime
from typing import List, Optional

import arxiv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FetchLog, Paper

logger = logging.getLogger(__name__)


class ArxivService:
    """ArXiv 论文抓取服务。

    提供从 ArXiv API 获取论文并存储到数据库的方法。
    """

    # 支持的 ArXiv 分类
    SUPPORTED_CATEGORIES: List[str] = [
        "cs.AI",  # 人工智能
        "cs.CL",  # 计算语言学
        "cs.LG",  # 机器学习
        "cs.CV",  # 计算机视觉
        "cs.NE",  # 神经与进化计算
        "cs.IR",  # 信息检索
        "cs.RO",  # 机器人
        "cs.SE",  # 软件工程
        "cs.DC",  # 分布式计算
        "cs.CR",  # 密码学与安全
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

            total_fetched = 0
            new_papers = 0

            # 遍历搜索结果
            for result in client.results(search):
                total_fetched += 1

                # 从 entry_id 中解析 arxiv_id
                # entry_id 格式: "http://arxiv.org/abs/2301.00001v1"
                arxiv_id = result.entry_id.split("/")[-1]
                # 移除版本号 (如 v1)
                if "v" in arxiv_id:
                    arxiv_id = arxiv_id.rsplit("v", 1)[0]

                # 检查数据库是否已存在
                stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
                existing = await db.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    continue

                # 提取作者列表
                authors = [author.name for author in result.authors]

                # 提取分类列表
                categories = [cat for cat in result.categories]

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
                )

                db.add(paper)
                new_papers += 1

            # 提交事务
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