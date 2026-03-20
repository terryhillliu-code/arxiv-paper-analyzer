#!/usr/bin/env python
"""重新评估所有论文的 tier。

使用新的严格标准重新评估 tier，修复之前过于宽松的问题。
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)
logger = logging.getLogger(__name__)

from app.database import async_session_maker
from app.models import Paper
from sqlalchemy import select, func, update
from app.services.ai_service import ai_service


TIER_PROMPT = """你是一位严格的学术论文评审专家。请评估以下论文的等级。

## 论文信息
标题: {title}
摘要: {abstract}

## 评估标准（严格执行）

**Tier A（顶尖创新）** - 预期占比 10-15%
- 提出全新的方法/理论范式，颠覆现有认知
- 在主流基准上取得显著 SOTA（提升 >5%）
- 引发广泛社区关注，具有里程碑意义
- **判断要点**：如果是增量改进、应用导向、初步探索，则不是 A

**Tier B（有价值贡献）** - 预期占比 50-60%
- 有明确的创新点或实证价值
- 方法合理但非颠覆性
- 对领域有一定推动作用
- **判断要点**：大部分论文应该在这个等级

**Tier C（一般参考）** - 预期占比 25-35%
- 增量式改进（性能提升 <2%）
- 应用导向，缺乏方法创新
- 初步探索，实验不充分
- **判断要点**：如果只是"又一个 X 方法"或"X 应用于 Y"，则是 C

## 重要提醒
- **不要轻易给 A**！A 是留给真正的突破性工作的
- 大部分论文应该是 B 或 C
- 如果不确定，默认给 B

请直接输出 JSON 格式：
{{"tier": "A/B/C", "reason": "简短理由（20字以内）"}}
"""


async def get_all_analyzed_papers():
    """获取所有已分析论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == True)
            .order_by(Paper.id)
        )
        return result.scalars().all()


async def reevaluate_tier(paper, semaphore, client):
    """重新评估单篇论文的 tier"""
    async with semaphore:
        try:
            prompt = TIER_PROMPT.format(
                title=paper.title,
                abstract=paper.abstract or "无摘要"
            )

            def _call():
                return client.chat.completions.create(
                    model="glm-5",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=256,
                )

            import asyncio as aio
            response = await aio.to_thread(_call)
            text = response.choices[0].message.content or ""

            # 解析 JSON
            import json
            import re

            # 尝试提取 JSON
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
                new_tier = data.get("tier", "B").upper()
                reason = data.get("reason", "")[:30]
            else:
                new_tier = "B"
                reason = "解析失败"

            if new_tier not in ["A", "B", "C"]:
                new_tier = "B"

            # 更新数据库
            old_tier = paper.tier
            async with async_session_maker() as db:
                await db.execute(
                    update(Paper)
                    .where(Paper.id == paper.id)
                    .values(tier=new_tier)
                )
                await db.commit()

            if old_tier != new_tier:
                logger.info(f"{paper.id}: {old_tier} → {new_tier} | {reason}")
            return new_tier

        except Exception as e:
            logger.error(f"❌ {paper.id}: {e}")
            return None


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="重新评估 tier")
    parser.add_argument("--parallel", type=int, default=8, help="并发数")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不更新")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("重新评估论文 Tier")
    logger.info("=" * 50)

    papers = await get_all_analyzed_papers()
    logger.info(f"待评估: {len(papers)} 篇")

    if args.dry_run:
        # 统计当前分布
        tiers = {"A": 0, "B": 0, "C": 0}
        for p in papers:
            if p.tier in tiers:
                tiers[p.tier] += 1
        print(f"\n当前分布: A={tiers['A']} B={tiers['B']} C={tiers['C']}")
        return

    from app.config import get_settings
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(
        api_key=settings.coding_plan_api_key,
        base_url="https://coding.dashscope.aliyuncs.com/v1",
    )

    semaphore = asyncio.Semaphore(args.parallel)
    start = asyncio.get_event_loop().time()
    done = 0
    new_tiers = {"A": 0, "B": 0, "C": 0}

    async def process(paper):
        nonlocal done
        tier = await reevaluate_tier(paper, semaphore, client)
        done += 1
        if tier:
            new_tiers[tier] += 1
        if done % 50 == 0:
            elapsed = asyncio.get_event_loop().time() - start
            rate = done / (elapsed / 60)
            logger.info(f"[{done}/{len(papers)}] {rate:.0f}/min | A={new_tiers['A']} B={new_tiers['B']} C={new_tiers['C']}")
        return tier

    await asyncio.gather(*[process(p) for p in papers])

    logger.info(f"\n完成! 新分布: A={new_tiers['A']} B={new_tiers['B']} C={new_tiers['C']}")


if __name__ == "__main__":
    asyncio.run(main())