#!/usr/bin/env python3
"""
ArXiv 论文定时抓取脚本

功能：
1. 抓取今天和昨天的论文
2. 自动生成 AI 摘要
3. 网络错误重试机制
4. 发送通知（可选）

使用方法：
    python scheduled_fetch.py              # 抓取今天和昨天
    python scheduled_fetch.py --date 2026-03-15  # 抓取指定日期
    python scheduled_fetch.py --dry-run    # 试运行，不实际写入

定时任务建议：
    ArXiv 使用美国东部时间（ET）发布论文，北京时间比 ET 早 12-13 小时。
    建议在北京时间晚上 22:00 或 23:00 运行，确保获取当天最新论文。

    # 添加到 crontab（北京时间 22:00）
    0 22 * * * cd /path/to/backend && /path/to/venv/bin/python scheduled_fetch.py >> /path/to/logs/fetch.log 2>&1
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker
from app.services.ai_service import ai_service
from app.services.arxiv_service import ArxivService
from app.services.s2_service import get_s2_service
from sqlalchemy import select, or_
from app.models import Paper

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class ScheduledFetcher:
    """定时抓取器"""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: int = 60,
        categories: Optional[list] = None,
        max_results: int = 300,
        max_concurrent_ai: int = 3,
    ):
        """
        Args:
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            categories: 要抓取的分类
            max_results: 每次最大抓取数量
            max_concurrent_ai: AI 摘要生成并发数限制
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.categories = categories or ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]
        self.max_results = max_results
        self.max_concurrent_ai = max_concurrent_ai
        # 并发控制信号量
        self._semaphore = asyncio.Semaphore(max_concurrent_ai)

    async def fetch_papers_with_retry(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> dict:
        """带重试的论文抓取"""
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"开始抓取 (尝试 {attempt}/{self.max_retries}): "
                    f"{date_from.date()} 至 {date_to.date()}"
                )

                async with async_session_maker() as db:
                    result = await ArxivService.fetch_by_date_range(
                        db=db,
                        categories=self.categories,
                        date_from=date_from,
                        date_to=date_to,
                        max_results=self.max_results,
                    )

                logger.info(
                    f"抓取成功: 总数 {result['total_fetched']}, "
                    f"日期范围内 {result.get('filtered_papers', 0)}, "
                    f"新增 {result['new_papers']}"
                )
                return result

            except Exception as e:
                last_error = e
                logger.error(f"抓取失败 (尝试 {attempt}/{self.max_retries}): {e}")

                if attempt < self.max_retries:
                    logger.info(f"{self.retry_delay} 秒后重试...")
                    await asyncio.sleep(self.retry_delay)

        raise Exception(f"抓取失败，已重试 {self.max_retries} 次: {last_error}")

    async def generate_summaries_with_retry(self, limit: int = 20) -> dict:
        """带重试的 AI 摘要生成

        Args:
            limit: 每次处理的最大论文数（默认 20，减少资源占用）
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"开始生成 AI 摘要 (尝试 {attempt}/{self.max_retries})")

                async with async_session_maker() as db:
                    # 查询没有摘要的论文
                    query = (
                        select(Paper)
                        .where(or_(Paper.summary == None, Paper.summary == ""))
                        .limit(limit)
                    )
                    result = await db.execute(query)
                    papers = result.scalars().all()

                    if not papers:
                        logger.info("没有需要生成摘要的论文")
                        return {"processed": 0, "success": 0, "failed": 0}

                    logger.info(f"找到 {len(papers)} 篇论文需要生成摘要")

                    success_count = 0
                    failed_count = 0

                    for i, paper in enumerate(papers):
                        try:
                            # 使用信号量控制并发
                            async with self._semaphore:
                                # 添加短暂延迟，让出事件循环
                                await asyncio.sleep(0.05)

                                # 调用 AI 生成摘要
                                summary_result = await ai_service.generate_summary(
                                    title=paper.title,
                                    authors=paper.authors or [],
                                    abstract=paper.abstract or "",
                                    categories=paper.categories or [],
                                )

                                paper.summary = summary_result.get("summary", "")
                                paper.tags = summary_result.get("tags", [])
                                paper.institutions = summary_result.get("institutions", [])
                                success_count += 1

                                logger.info(f"摘要生成成功: {paper.title[:50]}...")

                                # 每 5 篇论文让出控制权并提交一次
                                if (i + 1) % 5 == 0:
                                    await db.commit()
                                    logger.info(f"已处理 {i + 1} 篇论文，中间提交完成")
                                    # 让出控制权
                                    await asyncio.sleep(0)

                        except Exception as e:
                            failed_count += 1
                            logger.error(f"摘要生成失败: {paper.title[:50]}... - {e}")
                            continue

                    await db.commit()

                logger.info(
                    f"摘要生成完成: 处理 {len(papers)} 篇, "
                    f"成功 {success_count} 篇, 失败 {failed_count} 篇"
                )

                return {
                    "processed": len(papers),
                    "success": success_count,
                    "failed": failed_count,
                }

            except Exception as e:
                last_error = e
                logger.error(f"摘要生成失败 (尝试 {attempt}/{self.max_retries}): {e}")

                if attempt < self.max_retries:
                    logger.info(f"{self.retry_delay} 秒后重试...")
                    await asyncio.sleep(self.retry_delay)

        raise Exception(f"摘要生成失败，已重试 {self.max_retries} 次: {last_error}")

    async def fetch_s2_metrics(self, limit: int = 100) -> dict:
        """获取论文的 Semantic Scholar 评分。

        Args:
            limit: 每次处理的最大论文数（默认 100）

        Returns:
            处理结果统计
        """
        logger.info("开始获取 Semantic Scholar 评分...")

        async with async_session_maker() as db:
            # 查询没有评分的论文
            query = (
                select(Paper)
                .where(Paper.arxiv_id != None)
                .where(or_(Paper.citation_count == None, Paper.influential_citation_count == None))
                .limit(limit)
            )
            result = await db.execute(query)
            papers = result.scalars().all()

            if not papers:
                logger.info("没有需要获取评分的论文")
                return {"processed": 0, "updated": 0, "not_found": 0}

            logger.info(f"找到 {len(papers)} 篇论文需要获取评分")

            # 提取 arxiv_ids
            arxiv_ids = [p.arxiv_id for p in papers]

            # 批量获取评分
            s2_service = get_s2_service()
            metrics = await s2_service.batch_get_metrics(arxiv_ids)

            updated_count = 0
            not_found_count = 0

            for paper in papers:
                if paper.arxiv_id in metrics:
                    m = metrics[paper.arxiv_id]
                    paper.citation_count = m.get("citation_count", 0)
                    paper.influential_citation_count = m.get("influential_citation_count", 0)
                    paper.s2_paper_id = m.get("s2_paper_id")
                    updated_count += 1
                else:
                    not_found_count += 1

            await db.commit()

        logger.info(
            f"Semantic Scholar 评分获取完成: "
            f"处理 {len(papers)} 篇, 更新 {updated_count} 篇, 未找到 {not_found_count} 篇"
        )

        return {
            "processed": len(papers),
            "updated": updated_count,
            "not_found": not_found_count,
        }

    async def run(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        skip_ai: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """执行抓取任务

        Args:
            date_from: 开始日期，默认昨天
            date_to: 结束日期，默认今天
            skip_ai: 是否跳过 AI 摘要生成
            dry_run: 试运行模式

        Returns:
            执行结果
        """
        # 设置日期范围（默认昨天和今天）
        # 注意：ArXiv 使用美国东部时间发布，存在时差
        # 北京时间早上时，ArXiv 可能还未发布当天的论文
        today = datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
        # 正确计算昨天：先设置为今天 00:00，再减一天
        yesterday = today.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)

        if not date_from:
            date_from = yesterday
        if not date_to:
            date_to = today

        logger.info(f"{'='*60}")
        logger.info(f"ArXiv 论文定时抓取任务开始")
        logger.info(f"时间范围: {date_from.date()} 至 {date_to.date()}")
        logger.info(f"分类: {', '.join(self.categories)}")
        logger.info(f"{'='*60}")

        results = {
            "fetch": None,
            "summary": None,
            "s2_metrics": None,
            "errors": [],
        }

        if dry_run:
            logger.info("试运行模式，不实际执行")
            return results

        try:
            # 1. 抓取论文
            fetch_result = await self.fetch_papers_with_retry(date_from, date_to)
            results["fetch"] = fetch_result

            # 2. 获取 Semantic Scholar 评分
            if fetch_result.get("new_papers", 0) > 0:
                logger.info("开始获取 Semantic Scholar 评分...")
                s2_result = await self.fetch_s2_metrics(limit=200)
                results["s2_metrics"] = s2_result

            # 3. 生成 AI 摘要
            if not skip_ai and fetch_result.get("new_papers", 0) > 0:
                logger.info("开始生成 AI 摘要...")
                summary_result = await self.generate_summaries_with_retry()
                results["summary"] = summary_result

            logger.info(f"{'='*60}")
            logger.info("任务完成！")
            logger.info(f"{'='*60}")

        except Exception as e:
            logger.error(f"任务失败: {e}")
            results["errors"].append(str(e))

        return results


def main():
    parser = argparse.ArgumentParser(description="ArXiv 论文定时抓取")
    parser.add_argument(
        "--date",
        type=str,
        help="指定抓取日期 (YYYY-MM-DD)，默认昨天和今天",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        help="开始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        help="结束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="跳过 AI 摘要生成",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="最大重试次数 (默认: 3)",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="cs.AI,cs.CL,cs.LG,cs.CV",
        help="要抓取的分类 (逗号分隔)",
    )

    args = parser.parse_args()

    # 解析日期
    date_from = None
    date_to = None

    if args.date:
        # 单日期模式：只抓取这一天
        dt = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        date_from = dt.replace(hour=0, minute=0, second=0)
        date_to = dt.replace(hour=23, minute=59, second=59)
    else:
        if args.from_date:
            date_from = datetime.strptime(args.from_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc, hour=0, minute=0, second=0
            )
        if args.to_date:
            date_to = datetime.strptime(args.to_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc, hour=23, minute=59, second=59
            )

    # 解析分类
    categories = [c.strip() for c in args.categories.split(",")]

    # 创建抓取器
    fetcher = ScheduledFetcher(
        max_retries=args.max_retries,
        categories=categories,
    )

    # 执行
    results = asyncio.run(
        fetcher.run(
            date_from=date_from,
            date_to=date_to,
            skip_ai=args.skip_ai,
            dry_run=args.dry_run,
        )
    )

    # 返回退出码
    if results.get("errors"):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()