#!/usr/bin/env python
"""两阶段论文分析流程。

阶段1：快速模式评估所有论文的 tier
阶段2：对 Tier A 论文用完整模式重新分析

用法:
    python scripts/two_stage_analyze.py [--parallel N]
"""

import argparse
import asyncio
import logging
import sys
import time
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
from app.outputs.markdown_generator import MarkdownGenerator


async def get_unanalyzed_papers():
    """获取未分析的论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == False)
            .order_by(Paper.publish_date.desc())
        )
        return result.scalars().all()


async def get_tier_a_papers():
    """获取需要完整模式分析的 Tier A 论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.tier == 'A')
            .where(Paper.full_analysis == False)  # 标记是否已完整分析
        )
        return result.scalars().all()


async def direct_write(paper_id, report, analysis_json, md_path, full_analysis=False):
    """写入数据库"""
    async with async_session_maker() as db:
        values = {
            "analysis_report": report,
            "analysis_json": analysis_json,
            "has_analysis": True,
            "tier": analysis_json.get("tier"),
            "tags": analysis_json.get("tags"),
            "md_output_path": md_path,
        }
        if full_analysis:
            values["full_analysis"] = True
        await db.execute(update(Paper).where(Paper.id == paper_id).values(**values))
        await db.commit()


async def quick_analyze(paper, semaphore):
    """快速模式分析（仅摘要）"""
    async with semaphore:
        try:
            result = await ai_service.generate_deep_analysis(
                title=paper.title,
                authors=paper.authors or [],
                institutions=paper.institutions or [],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=paper.categories or [],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=paper.abstract or "",
                quick_mode=True,
            )

            report = result.get("report", "")
            analysis_json = result.get("analysis_json", {})

            generator = MarkdownGenerator()
            export_result = generator._local_generate_paper_md(
                paper_data={
                    "title": paper.title,
                    "authors": paper.authors or [],
                    "institutions": paper.institutions or [],
                    "publish_date": str(paper.publish_date) if paper.publish_date else "",
                    "arxiv_url": paper.arxiv_url or "",
                    "arxiv_id": paper.arxiv_id,
                    "tags": analysis_json.get("tags"),
                },
                analysis_json=analysis_json or {},
                report=report or "",
            )

            await direct_write(paper.id, report, analysis_json, export_result.get("md_path"))
            tier = analysis_json.get("tier", "B")
            logger.info(f"✅ {paper.id} tier={tier}")
            return tier
        except Exception as e:
            logger.error(f"❌ {paper.id}: {e}")
            return None


async def full_analyze(paper, semaphore):
    """完整模式分析（PDF全文 + kimi-k2.5）"""
    async with semaphore:
        try:
            # 下载 PDF 并提取文本
            from app.services.pdf_service import PDFService
            pdf_service = PDFService()

            if not paper.pdf_url:
                logger.warning(f"论文 {paper.id} 无 PDF URL，跳过完整分析")
                return False

            content = await pdf_service.extract_text(paper.pdf_url)
            if not content:
                logger.warning(f"论文 {paper.id} PDF 提取失败")
                return False

            result = await ai_service.generate_deep_analysis(
                title=paper.title,
                authors=paper.authors or [],
                institutions=paper.institutions or [],
                publish_date=str(paper.publish_date) if paper.publish_date else "",
                categories=paper.categories or [],
                arxiv_url=paper.arxiv_url or "",
                pdf_url=paper.pdf_url or "",
                content=content,
                quick_mode=False,  # 完整模式
            )

            report = result.get("report", "")
            analysis_json = result.get("analysis_json", {})

            generator = MarkdownGenerator()
            export_result = generator._local_generate_paper_md(
                paper_data={
                    "title": paper.title,
                    "authors": paper.authors or [],
                    "institutions": paper.institutions or [],
                    "publish_date": str(paper.publish_date) if paper.publish_date else "",
                    "arxiv_url": paper.arxiv_url or "",
                    "arxiv_id": paper.arxiv_id,
                    "tags": analysis_json.get("tags"),
                },
                analysis_json=analysis_json or {},
                report=report or "",
            )

            await direct_write(paper.id, report, analysis_json, export_result.get("md_path"), full_analysis=True)
            logger.info(f"✅ 完整分析: {paper.id}")
            return True
        except Exception as e:
            logger.error(f"❌ 完整分析失败 {paper.id}: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(description="两阶段论文分析")
    parser.add_argument("--parallel", type=int, default=4, help="并发数")
    parser.add_argument("--skip-quick", action="store_true", help="跳过阶段1（已快速分析）")
    parser.add_argument("--tier-a-only", action="store_true", help="仅处理 Tier A")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("两阶段论文分析")
    logger.info("=" * 60)

    semaphore = asyncio.Semaphore(args.parallel)

    # ========== 阶段1：快速模式评估所有论文 ==========
    if not args.skip_quick and not args.tier_a_only:
        papers = await get_unanalyzed_papers()
        logger.info(f"\n【阶段1】快速模式评估: {len(papers)} 篇")

        if papers:
            start = time.time()
            done = 0
            tier_a_count = 0

            async def process(paper):
                nonlocal done, tier_a_count
                tier = await quick_analyze(paper, semaphore)
                done += 1
                if tier == 'A':
                    tier_a_count += 1
                elapsed = time.time() - start
                rate = done / (elapsed / 60) if elapsed > 0 else 0
                remaining = (len(papers) - done) / rate if rate > 0 else 0
                logger.info(f"[{done}/{len(papers)}] {rate:.1f}/min | 剩余{remaining:.1f}min | Tier A: {tier_a_count}")
                return tier

            tiers = await asyncio.gather(*[process(p) for p in papers])
            logger.info(f"阶段1完成: Tier A={tier_a_count}, Tier B/C={len(papers)-tier_a_count}")

    # ========== 阶段2：Tier A 论文完整模式分析 ==========
    if not args.tier_a_only or args.skip_quick:
        # 获取所有 Tier A 论文（包括已有的和新的）
        async with async_session_maker() as db:
            result = await db.execute(
                select(Paper)
                .where(Paper.tier == 'A')
            )
            tier_a_papers = result.scalars().all()

        logger.info(f"\n【阶段2】Tier A 完整模式分析: {len(tier_a_papers)} 篇")

        if tier_a_papers:
            logger.info("注意：Tier A 完整模式需要下载 PDF，速度较慢...")

            start = time.time()
            done = 0

            for paper in tier_a_papers:
                ok = await full_analyze(paper, semaphore)
                done += 1
                elapsed = time.time() - start
                logger.info(f"[{done}/{len(tier_a_papers)}] {paper.title[:40]}...")

    logger.info("\n" + "=" * 60)
    logger.info("分析完成")


if __name__ == "__main__":
    asyncio.run(main())