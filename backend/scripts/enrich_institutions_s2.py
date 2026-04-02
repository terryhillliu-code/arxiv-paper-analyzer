#!/usr/bin/env python3
"""使用 Semantic Scholar API 补充机构信息。

处理缺机构的论文，从 S2 获取作者机构信息。
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.services.semantic_scholar_service import s2_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 机构别名映射
INSTITUTION_ALIASES = {
    "google": "Google",
    "deepmind": "DeepMind",
    "meta": "Meta",
    "facebook": "Meta",
    "microsoft": "Microsoft",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "nvidia": "NVIDIA",
    "stanford": "Stanford",
    "mit": "MIT",
    "massachusetts institute of technology": "MIT",
    "berkeley": "Berkeley",
    "uc berkeley": "Berkeley",
    "cmu": "CMU",
    "carnegie mellon": "CMU",
    "harvard": "Harvard",
    "princeton": "Princeton",
    "caltech": "Caltech",
    "oxford": "Oxford",
    "cambridge": "Cambridge",
    "tsinghua": "Tsinghua",
    "peking university": "Peking University",
    "alibaba": "Alibaba",
    "tencent": "Tencent",
    "huawei": "Huawei",
    "baidu": "Baidu",
    "bytedance": "ByteDance",
    "apple": "Apple",
    "amazon": "Amazon",
}


def normalize_institution(affiliation: str) -> str | None:
    """标准化机构名称。"""
    if not affiliation:
        return None

    aff_lower = affiliation.lower()

    for alias, canonical in INSTITUTION_ALIASES.items():
        if alias in aff_lower:
            return canonical

    # 如果不在映射中，返回原文（首字母大写）
    return affiliation.title() if len(affiliation) < 50 else None


async def enrich_institutions(
    tier_priority: str = "A",
    limit: int = 50,
    delay: float = 2.0,
):
    """从 Semantic Scholar 补充机构信息。

    Args:
        tier_priority: 优先处理的 Tier
        limit: 最大处理数量
        delay: 请求间隔（秒）
    """
    async with async_session_maker() as db:
        # 获取缺机构的论文
        query = (
            select(Paper)
            .where(Paper.institutions == None)
            .where(Paper.tier == tier_priority)
            .where(Paper.arxiv_id != None)
            .order_by(Paper.tier.desc(), Paper.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(query)
        papers = result.scalars().all()

        logger.info(f"待处理: {len(papers)} 篇 Tier {tier_priority} 论文")

        enriched = 0
        failed = 0
        no_data = 0

        for i, paper in enumerate(papers):
            logger.info(f"[{i+1}/{len(papers)}] #{paper.id} | {paper.title[:40]}...")

            try:
                # 查询 Semantic Scholar
                s2_paper = await s2_service.get_paper_by_arxiv(paper.arxiv_id)

                if s2_paper and s2_paper.authors:
                    institutions = []

                    for author in s2_paper.authors:
                        aff = author.get("affiliation")
                        if aff:
                            normalized = normalize_institution(aff)
                            if normalized and normalized not in institutions:
                                institutions.append(normalized)

                    if institutions:
                        paper.institutions = institutions[:5]
                        enriched += 1
                        logger.info(f"  → 机构: {institutions[:3]}")
                    else:
                        no_data += 1
                        logger.info(f"  → 无机构信息")
                else:
                    no_data += 1
                    logger.info(f"  → S2 无数据")

                # 延迟避免限流
                if i < len(papers) - 1:
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"  → 错误: {e}")
                failed += 1
                # 遇到限流时增加延迟
                if "limit" in str(e).lower() or "rate" in str(e).lower():
                    logger.info("  等待 10 秒后继续...")
                    await asyncio.sleep(10)

        await db.commit()

        logger.info("")
        logger.info("=== 补充结果 ===")
        logger.info(f"成功: {enriched}")
        logger.info(f"无数据: {no_data}")
        logger.info(f"失败: {failed}")

        # 统计剩余
        result = await db.execute(
            select(Paper.tier, func.count(Paper.id))
            .where(Paper.institutions == None)
            .group_by(Paper.tier)
        )
        remaining = dict(result.fetchall())

        logger.info("")
        logger.info("=== 剩余缺机构论文 ===")
        for tier, count in sorted(remaining.items(), reverse=True):
            logger.info(f"Tier {tier}: {count}")


from sqlalchemy import func


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="从 Semantic Scholar 补充机构信息")
    parser.add_argument(
        "--tier",
        default="A",
        choices=["A", "B", "C"],
        help="优先处理的 Tier 等级",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="最大处理数量",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="请求间隔（秒）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("机构信息补充脚本（Semantic Scholar）")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Tier: {args.tier}, Limit: {args.limit}, Delay: {args.delay}s")
    logger.info("=" * 60)

    await enrich_institutions(
        tier_priority=args.tier,
        limit=args.limit,
        delay=args.delay,
    )

    logger.info("\n处理完成!")


if __name__ == "__main__":
    asyncio.run(main())