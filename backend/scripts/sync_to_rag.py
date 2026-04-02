#!/usr/bin/env python3
"""
Paper Analyzer → RAG 同步工具

将已分析的论文同步到 LanceDB 向量库，使其可被语义检索。

用法:
    # 同步单篇论文
    python scripts/sync_to_rag.py --paper-id 123

    # 批量同步待入库论文
    python scripts/sync_to_rag.py --batch --limit 100

    # 同步所有未入库论文
    python scripts/sync_to_rag.py --all
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# RAG 路径配置
RAG_VENV = Path.home() / "zhiwei-rag" / "venv" / "bin" / "python3"
RAG_INGEST_SCRIPT = Path.home() / "zhiwei-rag" / "scripts" / "ingest_incremental.py"


def sync_paper_to_rag(paper_id: int, md_path: str, arxiv_id: str) -> tuple[bool, str]:
    """同步单篇论文到 RAG

    Args:
        paper_id: 论文 ID
        md_path: Markdown 文件路径
        arxiv_id: arXiv ID

    Returns:
        (success, lancedb_id)
    """
    if not os.path.exists(md_path):
        logger.warning(f"文件不存在: {md_path}")
        return False, ""

    if not RAG_INGEST_SCRIPT.exists():
        logger.warning(f"RAG 入库脚本不存在: {RAG_INGEST_SCRIPT}")
        return False, ""

    try:
        # 调用 RAG 入库脚本
        result = subprocess.run(
            [
                str(RAG_VENV),
                str(RAG_INGEST_SCRIPT),
                "--file", md_path,
                "--prefix", f"arxiv:{arxiv_id}:",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.home() / "zhiwei-rag"),
        )

        if result.returncode == 0:
            # 解析输出获取 lancedb_id（如果有的话）
            output = result.stdout
            logger.info(f"✅ 论文 {paper_id} 入库成功")
            return True, f"arxiv:{arxiv_id}"
        else:
            logger.error(f"入库失败: {result.stderr}")
            return False, ""

    except subprocess.TimeoutExpired:
        logger.error(f"入库超时: paper_id={paper_id}")
        return False, ""
    except Exception as e:
        logger.error(f"入库异常: {e}")
        return False, ""


async def sync_batch(limit: int = 100, tier_filter: str = None):
    """批量同步论文到 RAG

    Args:
        limit: 最大同步数量
        tier_filter: 只同步特定 Tier
    """
    logger.info("=" * 60)
    logger.info("批量同步论文到 RAG")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    async with async_session_maker() as db:
        # 查询待同步论文
        query = select(Paper).where(
            Paper.has_analysis == True,
            Paper.md_output_path != None,
            Paper.rag_indexed == False,
        ).order_by(Paper.tier.desc(), Paper.citation_count.desc().nulls_last())

        if tier_filter:
            query = query.where(Paper.tier == tier_filter)
            logger.info(f"仅同步 Tier {tier_filter} 论文")

        query = query.limit(limit)

        result = await db.execute(query)
        papers = result.scalars().all()

        logger.info(f"找到 {len(papers)} 篇待同步论文")

        if not papers:
            logger.info("没有需要同步的论文")
            return

        success_count = 0
        failed_count = 0

        for paper in papers:
            try:
                success, lancedb_id = sync_paper_to_rag(
                    paper.id,
                    paper.md_output_path,
                    paper.arxiv_id or str(paper.id),
                )

                if success:
                    # 更新数据库
                    paper.rag_indexed = True
                    paper.lancedb_id = lancedb_id
                    await db.commit()
                    success_count += 1
                else:
                    failed_count += 1

                # 避免过快请求
                time.sleep(0.5)

                if (success_count + failed_count) % 20 == 0:
                    logger.info(f"进度: {success_count + failed_count}/{len(papers)}")

            except Exception as e:
                logger.error(f"同步异常 {paper.id}: {e}")
                failed_count += 1

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"同步完成: 成功 {success_count}, 失败 {failed_count}")
        logger.info("=" * 60)


async def sync_single(paper_id: int):
    """同步单篇论文"""
    async with async_session_maker() as db:
        result = await db.execute(select(Paper).where(Paper.id == paper_id))
        paper = result.scalar_one_or_none()

        if not paper:
            logger.error(f"论文不存在: {paper_id}")
            return

        if not paper.md_output_path:
            logger.error(f"论文未导出到 Obsidian: {paper_id}")
            return

        logger.info(f"同步论文 {paper_id}: {paper.title[:50]}...")

        success, lancedb_id = sync_paper_to_rag(
            paper.id,
            paper.md_output_path,
            paper.arxiv_id or str(paper.id),
        )

        if success:
            paper.rag_indexed = True
            paper.lancedb_id = lancedb_id
            await db.commit()
            logger.info(f"✅ 同步成功: {lancedb_id}")
        else:
            logger.error("❌ 同步失败")


async def main():
    parser = argparse.ArgumentParser(description="Paper Analyzer → RAG 同步")
    parser.add_argument("--paper-id", type=int, help="同步单篇论文")
    parser.add_argument("--batch", action="store_true", help="批量同步")
    parser.add_argument("--all", action="store_true", help="同步所有未入库论文")
    parser.add_argument("--limit", type=int, default=100, help="批量同步数量限制")
    parser.add_argument("--tier", type=str, default=None, help="只同步特定 Tier")

    args = parser.parse_args()

    if args.paper_id:
        await sync_single(args.paper_id)
    elif args.all:
        await sync_batch(limit=5000, tier_filter=args.tier)
    elif args.batch:
        await sync_batch(limit=args.limit, tier_filter=args.tier)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())