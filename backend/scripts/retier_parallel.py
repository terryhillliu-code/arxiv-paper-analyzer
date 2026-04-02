#!/usr/bin/env python3
"""并行Tier重新评估 - 处理后半部分。"""
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

TIER_PROMPT = """根据严格标准评估论文Tier。

标题: {title}
摘要: {abstract}
当前Tier: {current_tier}

Tier标准（严格执行）:
- A类(<20%): 范式突破+显著提升(>10%)+顶级机构标志工作+解决难题，需满足2+
- B类(30-40%): 方法创新+良好效果+实证研究+热门改进，需满足2+
- C类(50%+): 增量改进/应用导向/工具构建/只满足1条B类条件

大多数论文应该是C类。

输出JSON: {{"tier":"A/B/C","reason":"理由"}}"""


async def retier_batch(start_id: int, end_id: int):
    """处理指定ID范围"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .where(Paper.tier != None)
            .where(Paper.id >= start_id)
            .where(Paper.id <= end_id)
            .order_by(Paper.id)
        )
        papers = result.scalars().all()
        total = len(papers)
        logger.info(f"处理ID {start_id}-{end_id}: {total}篇")

        stats = {"A": 0, "B": 0, "C": 0}
        changes = 0

        for i, paper in enumerate(papers):
            try:
                prompt = TIER_PROMPT.format(
                    title=paper.title[:200] if paper.title else "",
                    abstract=paper.abstract[:1200] if paper.abstract else "",
                    current_tier=paper.tier or "B"
                )
                response = await asyncio.to_thread(ai_service._call_api, prompt, 150)
                result = ai_service._parse_json(response)
                new_tier = result.get("tier", paper.tier)

                if new_tier not in ["A", "B", "C"]:
                    new_tier = paper.tier

                stats[new_tier] = stats.get(new_tier, 0) + 1

                if new_tier != paper.tier:
                    paper.tier = new_tier
                    changes += 1

                if (i + 1) % 50 == 0:
                    await db.commit()
                    logger.info(f"进度: {i+1}/{total} | A:{stats['A']} B:{stats['B']} C:{stats['C']} | 变更:{changes}")

            except Exception as e:
                logger.warning(f"处理失败 ID={paper.id}: {e}")

        await db.commit()
        logger.info(f"完成! 最终: A:{stats['A']} B:{stats['B']} C:{stats['C']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1770)
    parser.add_argument("--end", type=int, default=20000)
    args = parser.parse_args()

    asyncio.run(retier_batch(args.start, args.end))