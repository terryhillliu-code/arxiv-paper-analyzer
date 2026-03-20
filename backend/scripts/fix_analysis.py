#!/usr/bin/env python
"""统一的论文分析修复工具。

功能:
- 检查缺失字段
- 并行修复缺失数据
- 输出修复报告

用法:
    python scripts/fix_analysis.py [--check] [--fix] [--parallel N]
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
from app.services.ai_service import ai_service
from sqlalchemy import select, update, func


async def get_papers_with_missing_fields(date_from: str = "2026-03-19", date_to: str = "2026-03-20"):
    """获取缺失字段的论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.publish_date >= date_from)
            .where(Paper.publish_date < date_to)
            .where(Paper.has_analysis == True)
        )
        papers = result.scalars().all()

        missing_papers = []
        stats = {"total": len(papers), "missing_tags": 0, "missing_summary": 0, "missing_outline": 0}

        for paper in papers:
            j = paper.analysis_json or {}
            tags = j.get("tags", [])
            summary = j.get("one_line_summary", "")
            outline = j.get("outline", [])

            is_missing = False
            if not tags or (isinstance(tags, list) and len(tags) == 0):
                stats["missing_tags"] += 1
                is_missing = True
            if not summary or summary.strip() == "":
                stats["missing_summary"] += 1
                is_missing = True
            if not outline or (isinstance(outline, list) and len(outline) == 0):
                stats["missing_outline"] += 1
                is_missing = True

            if is_missing:
                missing_papers.append(paper)

        return missing_papers, stats


async def fix_paper(paper, semaphore, quick_client):
    """修复单篇论文"""
    async with semaphore:
        try:
            if not paper.analysis_report:
                logger.warning(f"论文 {paper.id} 无报告，跳过")
                return False, "no_report"

            from app.prompts.templates import ANALYSIS_JSON_PROMPT

            prompt = ANALYSIS_JSON_PROMPT.format(report=paper.analysis_report[:8000])

            # 重试机制
            MAX_RETRIES = 3
            new_json = {}
            for attempt in range(MAX_RETRIES):
                def _sync_call():
                    return quick_client.chat.completions.create(
                        model="glm-5",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=4096,
                    )

                response = await asyncio.to_thread(_sync_call)
                text = response.choices[0].message.content or ""
                new_json = ai_service._parse_json(text)

                # 验证
                is_valid, missing = ai_service.validate_analysis_json(new_json)
                if is_valid:
                    break

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
            return True, None

        except Exception as e:
            logger.error(f"❌ 修复失败 {paper.id}: {e}")
            return False, str(e)


async def main():
    parser = argparse.ArgumentParser(description="论文分析修复工具")
    parser.add_argument("--check", action="store_true", help="只检查不修复")
    parser.add_argument("--fix", action="store_true", help="执行修复")
    parser.add_argument("--parallel", type=int, default=6, help="并行数")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("论文分析修复工具")
    logger.info("=" * 50)

    # 检查缺失
    papers, stats = await get_papers_with_missing_fields()

    print(f"\n=== 统计 ===")
    print(f"总论文数: {stats['total']}")
    print(f"缺少 tags: {stats['missing_tags']}")
    print(f"缺少 summary: {stats['missing_summary']}")
    print(f"缺少 outline: {stats['missing_outline']}")
    print(f"需要修复: {len(papers)} 篇\n")

    if args.check or not args.fix:
        if papers:
            print("需要修复的论文 ID:")
            print(", ".join([str(p.id) for p in papers[:20]]))
            if len(papers) > 20:
                print(f"... 共 {len(papers)} 篇")
        return

    if not papers:
        logger.info("无需修复")
        return

    # 执行修复
    from app.config import get_settings
    from openai import OpenAI

    settings = get_settings()
    quick_client = OpenAI(
        api_key=settings.coding_plan_api_key,
        base_url="https://coding.dashscope.aliyuncs.com/v1",
    )

    semaphore = asyncio.Semaphore(args.parallel)
    start = asyncio.get_event_loop().time()

    async def process(paper, idx):
        ok, err = await fix_paper(paper, semaphore, quick_client)
        elapsed = asyncio.get_event_loop().time() - start
        rate = (idx + 1) / (elapsed / 60) if elapsed > 0 else 0
        remaining = (len(papers) - idx - 1) / rate if rate > 0 else 0
        logger.info(f"[{idx+1}/{len(papers)}] {rate:.1f}/min | 剩余{remaining:.1f}分钟")
        return ok

    results = await asyncio.gather(*[process(p, i) for i, p in enumerate(papers)])
    success = sum(1 for r in results if r)
    logger.info(f"\n修复完成: 成功 {success}/{len(papers)}")


if __name__ == "__main__":
    asyncio.run(main())