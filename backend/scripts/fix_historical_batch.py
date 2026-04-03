#!/usr/bin/env python3
"""批量修复历史论文分析数据。

优化版本：
1. 批量获取摘要（每批 50 个 ID）
2. 并发分析（5 个并发）
3. 进度跟踪和断点续传
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
import json as json_module

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.services.arxiv_service import ArxivService
from app.services.ai_service import ai_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def batch_fetch_abstracts(arxiv_ids: List[str], batch_size: int = 50) -> Dict[str, str]:
    """批量获取摘要

    Args:
        arxiv_ids: arXiv ID 列表
        batch_size: 每批数量

    Returns:
        {arxiv_id: abstract} 字典
    """
    results = {}
    total = len(arxiv_ids)

    for i in range(0, total, batch_size):
        batch = arxiv_ids[i:i + batch_size]
        logger.info(f"获取摘要 [{i+1}-{min(i+batch_size, total)}/{total}]")

        try:
            papers = await ArxivService.fetch_by_ids(batch)
            for paper in papers:
                results[paper["arxiv_id"]] = paper.get("abstract", "")

            # 避免 API 限流
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"批量获取失败: {e}")
            await asyncio.sleep(5)

    return results


async def analyze_paper(paper: Paper, abstract: str) -> Dict[str, Any] | None:
    """分析单篇论文"""
    try:
        result = await ai_service.generate_deep_analysis(
            title=paper.title,
            authors=paper.authors or [],
            institutions=paper.institutions or [],
            publish_date=str(paper.publish_date) if paper.publish_date else "",
            categories=paper.categories or [],
            arxiv_url=paper.arxiv_url or "",
            pdf_url=paper.pdf_url or "",
            content=abstract,
            quick_mode=True,
        )
        return result
    except Exception as e:
        logger.error(f"分析失败 {paper.arxiv_id}: {e}")
        return None


async def process_batch(
    papers: List[Paper],
    abstracts: Dict[str, str],
    concurrency: int = 5
) -> int:
    """并发处理一批论文

    Returns:
        成功处理数量
    """
    semaphore = asyncio.Semaphore(concurrency)
    success_count = 0

    async def process_one(paper: Paper):
        nonlocal success_count

        async with semaphore:
            abstract = abstracts.get(paper.arxiv_id, "")

            if not abstract or len(abstract) < 100:
                logger.warning(f"跳过 {paper.arxiv_id}: 摘要不足")
                return

            result = await analyze_paper(paper, abstract)

            if result:
                async with async_session_maker() as db:
                    paper.abstract = abstract
                    paper.analysis_json = result.get("analysis_json")
                    paper.analysis_report = result.get("report")
                    paper.one_line_summary = result.get("analysis_json", {}).get("one_line_summary")
                    paper.tags = result.get("analysis_json", {}).get("tags")
                    paper.tier = result.get("analysis_json", {}).get("tier", "B")
                    paper.has_analysis = True
                    await db.commit()

                success_count += 1
                logger.info(f"✅ [{success_count}] {paper.arxiv_id}")

            # 避免过快请求
            await asyncio.sleep(0.5)

    await asyncio.gather(*[process_one(p) for p in papers])
    return success_count


async def fix_all_historical(
    batch_size: int = 100,
    concurrency: int = 5,
    max_papers: int = 0
):
    """修复所有历史论文

    Args:
        batch_size: 每批处理数量
        concurrency: 并发数
        max_papers: 最大处理数量（0 = 全部）
    """
    logger.info("=" * 60)
    logger.info("批量修复历史论文")
    logger.info(f"批大小: {batch_size}, 并发: {concurrency}")
    logger.info("=" * 60)

    # 1. 获取待处理论文
    async with async_session_maker() as db:
        query = select(Paper).where(
            Paper.analysis_mode == "historical",
            Paper.analysis_json == None
        ).order_by(Paper.id)

        if max_papers > 0:
            query = query.limit(max_papers)

        result = await db.execute(query)
        papers = result.scalars().all()

    total = len(papers)
    logger.info(f"待处理论文: {total}")

    if total == 0:
        logger.info("没有需要处理的论文")
        return

    # 2. 批量获取摘要
    arxiv_ids = [p.arxiv_id for p in papers]
    logger.info("开始批量获取摘要...")
    abstracts = await batch_fetch_abstracts(arxiv_ids)
    logger.info(f"获取到 {len(abstracts)} 个摘要")

    # 3. 分批处理
    total_success = 0
    start_time = time.time()

    for i in range(0, total, batch_size):
        batch = papers[i:i + batch_size]
        logger.info(f"\n处理批次 [{i+1}-{min(i+batch_size, total)}/{total}]")

        success = await process_batch(batch, abstracts, concurrency)
        total_success += success

        # 进度报告
        elapsed = time.time() - start_time
        rate = total_success / elapsed if elapsed > 0 else 0
        remaining = (total - i - batch_size) / rate / 60 if rate > 0 else 0

        logger.info(f"进度: {total_success}/{total} ({total_success/total*100:.1f}%)")
        logger.info(f"速度: {rate:.1f} 篇/秒, 预计剩余: {remaining:.0f} 分钟")

    # 4. 最终报告
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info(f"完成! 成功: {total_success}/{total}")
    logger.info(f"耗时: {elapsed/60:.1f} 分钟")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=100, help="每批处理数量")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--max", type=int, default=0, help="最大处理数量（0=全部）")

    args = parser.parse_args()

    asyncio.run(fix_all_historical(
        batch_size=args.batch,
        concurrency=args.concurrency,
        max_papers=args.max
    ))