#!/usr/bin/env python
"""并行修复缺少 tags 和 summary 的论文分析。"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)
logger = logging.getLogger(__name__)

from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from sqlalchemy import select, update

MAX_CONCURRENT = 6  # 并发数


async def get_papers_need_fix():
    """获取需要修复的论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.publish_date >= "2026-03-19")
            .where(Paper.publish_date < "2026-03-20")
            .where(Paper.has_analysis == True)
        )
        papers = result.scalars().all()

        need_fix = []
        for paper in papers:
            analysis_json = paper.analysis_json or {}
            tags = analysis_json.get("tags", [])
            summary = analysis_json.get("one_line_summary", "")

            if not tags or not summary or summary.strip() == "":
                need_fix.append(paper)

        return need_fix


async def fix_paper(paper, semaphore):
    """修复单篇论文"""
    async with semaphore:
        try:
            report = paper.analysis_report or ""
            if not report:
                logger.warning(f"论文 {paper.id} 没有报告")
                return False

            # 使用 glm-5 快速提取 JSON
            from app.prompts.templates import ANALYSIS_JSON_PROMPT
            from app.config import get_settings
            from openai import OpenAI

            settings = get_settings()
            client = OpenAI(
                api_key=settings.coding_plan_api_key,
                base_url="https://coding.dashscope.aliyuncs.com/v1",
            )

            prompt = ANALYSIS_JSON_PROMPT.format(report=report[:8000])

            def _sync_call():
                return client.chat.completions.create(
                    model="glm-5",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )

            response = await asyncio.to_thread(_sync_call)
            response_text = response.choices[0].message.content or ""
            new_json = ai_service._parse_json(response_text)

            # 合并到现有 JSON
            current_json = paper.analysis_json or {}
            for key in ["tags", "one_line_summary", "outline", "key_contributions", "tier"]:
                if key in new_json and new_json[key]:
                    current_json[key] = new_json[key]

            # 更新数据库
            async with async_session_maker() as db:
                await db.execute(
                    update(Paper)
                    .where(Paper.id == paper.id)
                    .values(
                        analysis_json=current_json,
                        tags=current_json.get("tags"),
                        tier=current_json.get("tier"),
                    )
                )
                await db.commit()

            logger.info(f"✅ 修复: {paper.id} tier={current_json.get('tier')} tags={current_json.get('tags')}")
            return True

        except Exception as e:
            logger.error(f"❌ 修复失败 {paper.id}: {e}")
            return False


async def main():
    logger.info("=" * 50)
    logger.info("并行修复缺少 tags/summary 的论文")
    logger.info(f"并发数: {MAX_CONCURRENT}")
    logger.info("=" * 50)

    papers = await get_papers_need_fix()
    logger.info(f"需要修复: {len(papers)} 篇")

    if not papers:
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    start = asyncio.get_event_loop().time()
    done = 0

    async def process(paper):
        nonlocal done
        ok = await fix_paper(paper, semaphore)
        done += 1
        elapsed = asyncio.get_event_loop().time() - start
        rate = done / (elapsed / 60) if elapsed > 0 else 0
        remaining = (len(papers) - done) / rate if rate > 0 else 0
        logger.info(f"[{done}/{len(papers)}] {rate:.1f}/min | 剩余{remaining:.1f}分钟")
        return ok

    results = await asyncio.gather(*[process(p) for p in papers])
    logger.info(f"修复完成: OK={sum(1 for r in results if r)}/{len(papers)}")


if __name__ == "__main__":
    asyncio.run(main())