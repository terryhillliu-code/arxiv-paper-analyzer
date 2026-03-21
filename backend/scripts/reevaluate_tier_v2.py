#!/usr/bin/env python3
"""重新评估已分析论文的 tier 等级。

用法:
    # 检查需要重新评估的论文数量
    python scripts/reevaluate_tier_v2.py --check

    # 重新评估所有论文（按新规则）
    python scripts/reevaluate_tier_v2.py --run --parallel 4

    # 只重新评估高引用论文
    python scripts/reevaluate_tier_v2.py --run --min-citations 50
"""

import argparse
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


TIER_PROMPT = """你是一位学术论文评审专家。请根据以下标准重新评估论文的 tier 等级。

## 论文信息
标题: {title}
摘要: {abstract}
引用数: {citation_count}

## Tier 标准（严格按照此标准评级）

**"A"（顶尖创新）** - 预期占比 10-15%
- 提出全新方法/理论范式
- 在主流基准上取得显著 SOTA
- 引发广泛社区关注
- 引用数通常 > 500（但不是唯一标准）

**"B"（有价值贡献）** - 预期占比 50-60%
- 有明确创新点或实证价值
- 方法合理但非颠覆性
- 引用数通常 50-500

**"C"（一般参考）** - 预期占比 25-35%
- 增量式改进、应用导向、初步探索或工程实现
- 创新性有限但仍有参考价值
- **注意：C 不是差评！C 表示"值得参考但不突出"**
- 数据集构建、工程实现、应用案例 → 通常给 C
- 引用数通常 < 50

## 评估要点

1. 如果是增量改进、数据集构建、工程实现 → 给 C
2. 如果有明确创新但非颠覆 → 给 B
3. 只有真正的突破性工作才给 A

## 输出格式
直接输出 JSON：
{{"tier": "A/B/C", "reason": "简短理由（20字内）"}}
"""


async def check_stats():
    """检查需要重新评估的论文统计。"""
    async with async_session_maker() as db:
        # 总数
        total = await db.execute(select(func.count(Paper.id)).where(Paper.has_analysis == True))
        total_count = total.scalar()

        # Tier 分布
        tier_a = await db.execute(select(func.count(Paper.id)).where(Paper.has_analysis == True, Paper.tier == 'A'))
        tier_b = await db.execute(select(func.count(Paper.id)).where(Paper.has_analysis == True, Paper.tier == 'B'))
        tier_c = await db.execute(select(func.count(Paper.id)).where(Paper.has_analysis == True, Paper.tier == 'C'))

        print(f"已分析论文总数: {total_count}")
        print(f"\n当前 Tier 分布:")
        print(f"  A: {tier_a.scalar()} ({tier_a.scalar()/total_count*100:.1f}%) - 预期 10-15%")
        print(f"  B: {tier_b.scalar()} ({tier_b.scalar()/total_count*100:.1f}%) - 预期 50-60%")
        print(f"  C: {tier_c.scalar()} ({tier_c.scalar()/total_count*100:.1f}%) - 预期 25-35%")


async def reevaluate_tier(parallel: int = 4, min_citations: int = 0):
    """重新评估 tier。"""
    async with async_session_maker() as db:
        query = select(Paper).where(Paper.has_analysis == True)

        if min_citations > 0:
            query = query.where(Paper.citation_count >= min_citations)

        result = await db.execute(query.order_by(Paper.citation_count.desc()))
        papers = result.scalars().all()

    logger.info(f"需要重新评估: {len(papers)} 篇论文")

    semaphore = asyncio.Semaphore(parallel)
    updated = {'A': 0, 'B': 0, 'C': 0}

    async def evaluate_one(paper):
        async with semaphore:
            try:
                prompt = TIER_PROMPT.format(
                    title=paper.title,
                    abstract=paper.abstract[:1000] if paper.abstract else "无",
                    citation_count=paper.citation_count or "未知"
                )

                response = await ai_service.quick_client.chat.completions.create(
                    model="glm-5",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.3,
                )

                import json
                result_text = response.choices[0].message.content.strip()
                # 提取 JSON
                if '{' in result_text:
                    result_text = result_text[result_text.find('{'):result_text.rfind('}')+1]
                result = json.loads(result_text)

                new_tier = result.get('tier', paper.tier)
                reason = result.get('reason', '')

                if new_tier != paper.tier:
                    async with async_session_maker() as db:
                        await db.execute(
                            update(Paper)
                            .where(Paper.id == paper.id)
                            .values(tier=new_tier)
                        )
                        await db.commit()

                    old_tier = paper.tier
                    logger.info(f"变更: {paper.title[:40]}... {old_tier} → {new_tier} ({reason})")
                else:
                    logger.debug(f"保持: {paper.title[:40]}... tier={new_tier}")

                updated[new_tier] = updated.get(new_tier, 0) + 1
                return new_tier

            except Exception as e:
                logger.error(f"评估失败: {paper.id} - {e}")
                return paper.tier

    await asyncio.gather(*[evaluate_one(p) for p in papers])

    logger.info(f"\n重新评估完成!")
    logger.info(f"  A: {updated.get('A', 0)}")
    logger.info(f"  B: {updated.get('B', 0)}")
    logger.info(f"  C: {updated.get('C', 0)}")


def main():
    parser = argparse.ArgumentParser(description="重新评估 tier 等级")
    parser.add_argument("--check", action="store_true", help="检查统计")
    parser.add_argument("--run", action="store_true", help="执行重新评估")
    parser.add_argument("--parallel", type=int, default=4, help="并发数")
    parser.add_argument("--min-citations", type=int, default=0, help="最小引用数")
    args = parser.parse_args()

    if args.check:
        asyncio.run(check_stats())
    elif args.run:
        asyncio.run(reevaluate_tier(args.parallel, args.min_citations))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()