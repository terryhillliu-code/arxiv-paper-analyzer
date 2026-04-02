#!/usr/bin/env python3
"""机构信息补充脚本。

从论文摘要中提取机构信息，补充缺失的 institutions 字段。
"""

import asyncio
import sys
import re
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from app.database import async_session_maker
from app.models import Paper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# 机构别名映射
INSTITUTION_ALIASES = {
    "meta ai": "Meta",
    "meta platforms": "Meta",
    "meta research": "Meta",
    "facebook ai research": "Meta",
    "google research": "Google",
    "google deepmind": "DeepMind",
    "google ai": "Google",
    "deepmind": "DeepMind",
    "microsoft research": "Microsoft",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "nvidia research": "NVIDIA",
    "stanford university": "Stanford",
    "stanford": "Stanford",
    "mit": "MIT",
    "massachusetts institute of technology": "MIT",
    "uc berkeley": "Berkeley",
    "university of california berkeley": "Berkeley",
    "berkeley": "Berkeley",
    "cmu": "CMU",
    "carnegie mellon university": "CMU",
    "carnegie mellon": "CMU",
    "harvard university": "Harvard",
    "harvard": "Harvard",
    "princeton university": "Princeton",
    "princeton": "Princeton",
    "caltech": "Caltech",
    "california institute of technology": "Caltech",
    "oxford university": "Oxford",
    "university of oxford": "Oxford",
    "cambridge university": "Cambridge",
    "university of cambridge": "Cambridge",
    "eth zurich": "ETH Zurich",
    "tsinghua university": "Tsinghua",
    "peking university": "Peking University",
    "pku": "Peking University",
    "nvidia": "NVIDIA",
    "apple": "Apple",
    "amazon": "Amazon",
    "alibaba": "Alibaba",
    "tencent": "Tencent",
    "huawei": "Huawei",
    "baidu": "Baidu",
    "bytedance": "ByteDance",
    "hugging face": "Hugging Face",
    "mistral": "Mistral AI",
}


def extract_institutions_from_text(text: str) -> list[str]:
    """从文本中提取机构信息。

    Args:
        text: 论文摘要或其他文本

    Returns:
        机构列表（去重）
    """
    if not text:
        return []

    text_lower = text.lower()
    found = []

    # 使用别名映射
    for alias, canonical in INSTITUTION_ALIASES.items():
        if alias in text_lower:
            found.append(canonical)

    # 去重
    institutions = list(set(found))

    # 排序（优先显示顶级机构）
    top_order = ["OpenAI", "DeepMind", "Meta", "Google", "Microsoft", "Anthropic", "NVIDIA"]
    others = sorted([i for i in institutions if i not in top_order])

    return [i for i in top_order if i in institutions] + others


async def backfill_institutions(dry_run: bool = False, tier_priority: str = "A"):
    """补充缺失的机构信息。

    Args:
        dry_run: 仅检查不实际更新
        tier_priority: 优先处理的 Tier 等级
    """
    async with async_session_maker() as db:
        # 获取缺机构的论文（按 Tier 优先）
        if tier_priority:
            result = await db.execute(
                select(Paper)
                .where(Paper.institutions == None)
                .where(Paper.tier == tier_priority)
                .where(Paper.abstract != None)
            )
        else:
            result = await db.execute(
                select(Paper)
                .where(Paper.institutions == None)
                .where(Paper.abstract != None)
            )

        papers = result.scalars().all()

        logger.info(f"开始处理 {len(papers)} 篇 Tier {tier_priority} 论文的机构信息...")

        updated = 0
        not_found = 0

        for paper in papers:
            institutions = extract_institutions_from_text(paper.abstract or "")

            if institutions:
                if not dry_run:
                    paper.institutions = institutions
                    logger.debug(f"#{paper.id} | {institutions}")
                else:
                    logger.info(f"[DRY RUN] #{paper.id} | {institutions}")
                updated += 1
            else:
                not_found += 1
                logger.debug(f"#{paper.id} | 未找到机构信息")

        if not dry_run:
            await db.commit()
            logger.info(f"已更新 {updated} 篇论文的机构信息")

        logger.info(f"提取成功: {updated} | 未找到: {not_found}")

        # 统计剩余缺机构论文
        result = await db.execute(
            select(Paper.tier, func.count(Paper.id))
            .where(Paper.institutions == None)
            .group_by(Paper.tier)
        )
        remaining = dict(result.fetchall())

        logger.info("\n=== 剩余缺机构论文 ===")
        for tier, count in sorted(remaining.items(), reverse=True):
            logger.info(f"Tier {tier}: {count} 篇")


from sqlalchemy import func

async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="补充论文机构信息")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检查不实际更新",
    )
    parser.add_argument(
        "--tier",
        default="A",
        choices=["A", "B", "C", "all"],
        help="优先处理的 Tier 等级",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("机构信息补充脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN 模式 - 不实际更新")

    tier = None if args.tier == "all" else args.tier
    await backfill_institutions(dry_run=args.dry_run, tier_priority=tier)

    logger.info("\n处理完成!")


if __name__ == "__main__":
    asyncio.run(main())