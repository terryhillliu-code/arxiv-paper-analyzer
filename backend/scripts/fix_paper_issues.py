#!/usr/bin/env python3
"""修复问题论文数据。

修复三类问题：
1. 摘要缺失导致分析无效（2,874 篇）
2. 摘要正常但分析结果不完整（263 篇）
3. 空报告论文（1,590 篇）
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import json
from sqlalchemy import text
from app.database import async_session_maker
from app.services.arxiv_service import ArxivService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def batch_fetch_abstracts(arxiv_ids: list, batch_size: int = 50) -> dict:
    """批量获取摘要"""
    results = {}
    total = len(arxiv_ids)

    for i in range(0, total, batch_size):
        batch = arxiv_ids[i:i + batch_size]
        logger.info(f"获取摘要 [{i+1}-{min(i+batch_size, total)}/{total}]")

        try:
            papers = await ArxivService.fetch_by_ids(batch)
            for paper in papers:
                # 清理版本号（如 2603.09285v1 -> 2603.09285）
                clean_id = paper["arxiv_id"].split("v")[0]
                results[clean_id] = paper.get("abstract", "")
            # 避免 API 限流
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"批量获取失败: {e}")
            await asyncio.sleep(5)

    return results


async def fix_missing_abstracts():
    """修复摘要缺失的论文"""
    # 1. 获取摘要空的论文
    conn = sqlite3.connect('data/papers.db')
    c = conn.cursor()

    c.execute("""
        SELECT id, arxiv_id FROM papers
        WHERE (abstract IS NULL OR LENGTH(abstract) < 100)
        AND has_analysis = 1
    """)
    papers = c.fetchall()
    logger.info(f"找到 {len(papers)} 篇摘要缺失论文")

    if not papers:
        conn.close()
        return

    # 2. 批量获取摘要
    arxiv_ids = [p[1].split("v")[0] for p in papers]  # 清理版本号
    logger.info("开始批量获取摘要...")
    abstracts = await batch_fetch_abstracts(arxiv_ids)
    logger.info(f"获取到 {len(abstracts)} 个摘要")

    # 3. 更新数据库
    updated = 0
    for paper_id, arxiv_id in papers:
        clean_id = arxiv_id.split("v")[0]
        abstract = abstracts.get(clean_id, "")
        if abstract and len(abstract) >= 100:
            c.execute("""
                UPDATE papers SET abstract = ?, has_analysis = 0, analysis_json = NULL, analysis_report = NULL
                WHERE id = ?
            """, (abstract, paper_id))
            updated += 1

    conn.commit()
    conn.close()
    logger.info(f"更新摘要: {updated} 篇")


def reset_invalid_analysis():
    """重置分析结果不完整的论文"""
    conn = sqlite3.connect('data/papers.db')
    c = conn.cursor()

    # 摘要正常但短JSON的论文
    c.execute("""
        UPDATE papers SET has_analysis = 0, analysis_json = NULL, analysis_report = NULL
        WHERE LENGTH(abstract) >= 100 AND LENGTH(analysis_json) < 500 AND has_analysis = 1
    """)
    reset_json = c.rowcount
    logger.info(f"重置短JSON论文: {reset_json} 篇")

    # 空报告论文（historical 类型）
    c.execute("""
        UPDATE papers SET analysis_report = NULL
        WHERE has_analysis = 1 AND analysis_report IS NOT NULL AND LENGTH(analysis_report) < 100 AND analysis_mode = 'historical'
    """)
    reset_report = c.rowcount
    logger.info(f"标记空报告论文: {reset_report} 篇")

    conn.commit()
    conn.close()


async def main():
    logger.info("=" * 60)
    logger.info("开始修复问题论文数据")
    logger.info("=" * 60)

    # Step 1: 修复摘要缺失
    await fix_missing_abstracts()

    # Step 2: 重置无效分析
    reset_invalid_analysis()

    # Step 3: 统计修复结果
    conn = sqlite3.connect('data/papers.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM papers WHERE has_analysis = 0")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND LENGTH(abstract) >= 100")
    has_abstract = c.fetchone()[0]
    conn.close()

    logger.info("=" * 60)
    logger.info(f"修复完成: 待分析 {pending} 篇, 有摘要 {has_abstract} 篇")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())