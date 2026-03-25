#!/usr/bin/env python3
"""论文分析系统管理工具。

提供统一的命令行界面，涵盖分析、验证、评分同步和级别重估。
"""

import argparse
import asyncio
import logging
import sys
import time
import os
import json
import subprocess
from pathlib import Path
from typing import List, Optional, Set

# 模糊匹配库
from fuzzywuzzy import fuzz

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_maker
from app.models import Paper
from sqlalchemy import select, func, update
from app.services.ai_service import ai_service
from app.services.paper_analyzer import paper_analyzer
from app.services.s2_service import get_s2_service
from app.services.knowledge_bridge import KnowledgeBridgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("manage")


# ==================== 子命令处理逻辑 ====================

async def cmd_analyze(args):
    """处理 analyze 子命令（原 two_stage_analyze.py）"""
    logger.info("=" * 40)
    logger.info("🚀 开始两阶段论文分析")
    logger.info("=" * 40)

    semaphore = asyncio.Semaphore(args.parallel)

    # 日期过滤
    from datetime import datetime, timedelta
    date_filter = None
    if args.days > 0:
        date_filter = datetime.now() - timedelta(days=args.days)
        logger.info(f"📅 仅分析 {args.days} 天内的论文 (>= {date_filter.strftime('%Y-%m-%d')})")

    # 阶段 1：快速模式评估
    if not args.skip_quick:
        async with async_session_maker() as db:
            query = select(Paper).where(Paper.has_analysis == False)
            if date_filter:
                query = query.where(Paper.publish_date >= date_filter)
            if not args.no_sort:
                query = query.order_by(Paper.citation_count.desc().nulls_last())
            else:
                query = query.order_by(Paper.publish_date.desc())

            result = await db.execute(query)
            papers = result.scalars().all()

        if args.min_citations > 0:
            papers = [p for p in papers if (p.citation_count or 0) >= args.min_citations]

        if args.top_n > 0:
            papers = papers[:args.top_n]

        logger.info(f"【阶段1】快速模式评估: {len(papers)} 篇")
        if papers:
            start = time.time()
            done = 0
            tasks = [paper_analyzer.analyze_paper(p, semaphore, quick_mode=True) for p in papers]
            for coro in asyncio.as_completed(tasks):
                await coro
                done += 1
                if done % 5 == 0 or done == len(papers):
                    elapsed = time.time() - start
                    rate = done / (elapsed / 60) if elapsed > 0 else 0
                    logger.info(f"进度: {done}/{len(papers)} | 速率: {rate:.1f} 篇/分")

    # 阶段 2：完整模式分析 (Tier A)
    if not args.quick_only:
        async with async_session_maker() as db:
            query = select(Paper).where(Paper.tier == 'A', Paper.full_analysis == False)
            if date_filter:
                query = query.where(Paper.publish_date >= date_filter)
            result = await db.execute(query)
            tier_a_papers = result.scalars().all()

        logger.info(f"【阶段2】Tier A 完整模式分析: {len(tier_a_papers)} 篇")
        for p in tier_a_papers:
            await paper_analyzer.analyze_paper(p, semaphore, quick_mode=False)


async def cmd_verify(args):
    """处理 verify 子命令（原 verify.py）"""
    from app.services.paper_analyzer import PaperAnalyzer
    
    # 质量检测函数 (从 verify.py 迁移)
    def check_quality(paper):
        issues = []
        report_len = len(paper.analysis_report) if paper.analysis_report else 0
        if report_len < 100: issues.append("report 太短")
        
        j = paper.analysis_json or {}
        if not j.get("tags"): issues.append("tags 为空")
        if not j.get("one_line_summary"): issues.append("summary 为空")
        if not j.get("tier"): issues.append("tier 为空")
        
        return issues

    async with async_session_maker() as db:
        result = await db.execute(select(Paper).where(Paper.has_analysis == True))
        papers = result.scalars().all()

    logger.info(f"检测 {len(papers)} 篇论文质量...")
    to_fix = []
    for p in papers:
        issues = check_quality(p)
        if issues:
            logger.warning(f"ID {p.id} 问题: {', '.join(issues)}")
            to_fix.append(p)

    if args.fix and to_fix:
        logger.info(f"开始修复 {len(to_fix)} 篇论文...")
        semaphore = asyncio.Semaphore(args.parallel)
        await asyncio.gather(*[paper_analyzer.analyze_paper(p, semaphore, quick_mode=True) for p in to_fix])


async def cmd_reevaluate(args):
    """处理 reevaluate 子命令（原 reevaluate_tier.py）"""
    async with async_session_maker() as db:
        query = select(Paper).where(Paper.has_analysis == True)
        if args.min_citations > 0:
            query = query.where(Paper.citation_count >= args.min_citations)
        result = await db.execute(query)
        papers = result.scalars().all()

    logger.info(f"重新评估 {len(papers)} 篇论文的 Tier...")
    semaphore = asyncio.Semaphore(args.parallel)

    async def worker(paper):
        async with semaphore:
            res = await ai_service.reevaluate_tier(
                title=paper.title,
                abstract=paper.abstract,
                citation_count=paper.citation_count,
                publish_date=str(paper.publish_date)
            )
            new_tier = res.get("tier")
            if new_tier and new_tier != paper.tier:
                logger.info(f"变更 {paper.id}: {paper.tier} -> {new_tier} ({res.get('reason')})")
                async with async_session_maker() as db_inner:
                    await db_inner.execute(update(Paper).where(Paper.id == paper.id).values(tier=new_tier))
                    await db_inner.commit()

    await asyncio.gather(*[worker(p) for p in papers])


async def cmd_sync_scores(args):
    """处理 sync-scores 子命令（原 fetch_s2_scores.py）"""
    s2 = get_s2_service()
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper).where(Paper.arxiv_id != None, Paper.citation_count == None)
        )
        papers = result.scalars().all()

    if not papers:
        logger.info("所有论文已有评分")
        return

    logger.info(f"同步 {len(papers)} 篇论文的 Semantic Scholar 评分...")
    batch_size = 100
    for i in range(0, len(papers), batch_size):
        batch = papers[i:i+batch_size]
        ids = [p.arxiv_id for p in batch]
        metrics = await s2.batch_get_metrics(ids)
        
        async with async_session_maker() as db_inner:
            for p in batch:
                if p.arxiv_id in metrics:
                    m = metrics[p.arxiv_id]
                    await db_inner.execute(
                        update(Paper).where(Paper.id == p.id).values(
                            citation_count=m['citation_count'],
                            influential_citation_count=m['influential_citation_count'],
                            s2_paper_id=m['s2_paper_id']
                        )
                    )
            await db_inner.commit()
        logger.info(f"进度: {min(i+batch_size, len(papers))}/{len(papers)}")


async def cmd_export_notebook(args):
    """处理 export-notebook 子命令 (v2.2: 增加模糊匹配加固)"""
    from app.services.knowledge_bridge import KnowledgeBridgeService
    from app.services.arxiv_service import ArxivService

    bridge = KnowledgeBridgeService()
    FUZZY_THRESHOLD = args.fuzzy_threshold  # 模糊匹配阈值 (参数化)

    # 获取 RAG 语义匹配的标题/ID (如果提供了 query)
    rag_titles: Set[str] = set()
    if args.query:
        logger.info(f"🔍 正在通过 zhiwei-rag 进行语义检索: {args.query}")
        try:
            rag_venv = "/Users/liufang/zhiwei-rag/venv/bin/python3"
            bridge_script = "/Users/liufang/zhiwei-rag/bridge.py"

            result = subprocess.run(
                [rag_venv, bridge_script, "retrieve", args.query, "--top-k", "20"],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                rag_data = json.loads(result.stdout)
                for item in rag_data:
                    source = item.get("source", "")
                    title_part = os.path.basename(source).replace(".md", "")
                    if title_part.startswith("[") and "]" in title_part:
                        title_part = title_part.split("]", 1)[1].strip()
                    rag_titles.add(title_part)
                logger.info(f"✅ RAG 召回了 {len(rag_titles)} 个潜在匹配项")
            else:
                logger.error(f"❌ RAG 检索失败: {result.stderr}")
        except Exception as e:
            logger.error(f"⚠️ RAG 联动异常: {e}")

    async with async_session_maker() as db:
        tiers = args.tiers.split(',')

        # 基础查询：已分析过的高质量论文
        query = select(Paper).where(Paper.tier.in_(tiers), Paper.has_analysis == True)

        # 混合检索过滤
        if args.query:
            from sqlalchemy import or_
            fuzzy_query = f"%{args.query.strip().replace(' ', '%')}%"
            conditions = [Paper.title.ilike(fuzzy_query)]

            if rag_titles:
                for rt in list(rag_titles)[:10]:
                    if len(rt) > 20:
                        rt_part = rt[:20].strip()
                        conditions.append(Paper.title.contains(rt_part))
                    else:
                        conditions.append(Paper.title.ilike(f"%{rt}%"))

            query = query.where(or_(*conditions))

        # 扩大搜索范围，后续用模糊匹配过滤
        query = query.limit(args.limit * 3 if args.limit > 0 else 30)

        result = await db.execute(query)
        candidate_papers = list(result.scalars().all())

    # ===== v2.2 新增: 模糊匹配过滤 =====
    papers = []
    if args.query and rag_titles:
        logger.info(f"🔧 对 {len(candidate_papers)} 个候选进行模糊匹配 (阈值: {FUZZY_THRESHOLD})...")

        for paper in candidate_papers:
            paper_title = paper.title.lower()
            matched = False

            # 对每个 RAG 召回的标题进行模糊匹配
            for rag_title in rag_titles:
                rag_title_lower = rag_title.lower()

                # 使用 token_sort_ratio 处理空格/连字符差异
                # 例如 "Mixture of Depths" vs "Mixture-of-Depths"
                ratio = fuzz.token_sort_ratio(paper_title, rag_title_lower)

                if ratio >= FUZZY_THRESHOLD:
                    logger.info(f"  ✅ 模糊匹配: '{paper.title[:40]}' ↔ '{rag_title[:40]}' ({ratio}%)")
                    matched = True
                    break

            if matched:
                papers.append(paper)

        # 如果模糊匹配结果不足，补充直接匹配的结果
        if len(papers) < (args.limit if args.limit > 0 else 10):
            for paper in candidate_papers:
                if paper not in papers:
                    papers.append(paper)
                    if args.limit > 0 and len(papers) >= args.limit:
                        break

        logger.info(f"📊 模糊匹配后: {len(papers)} 篇")
    else:
        papers = candidate_papers[:args.limit] if args.limit > 0 else candidate_papers

    # ===== v2.1 新增: ArXiv 全时域搜索补漏 =====
    min_papers = args.min_papers  # 最少期望论文数 (参数化)
    if args.query and len(papers) < min_papers and args.auto_search:
        logger.info(f"⚠️ 本地库仅找到 {len(papers)} 篇，触发 ArXiv 全时域搜索...")

        async with async_session_maker() as db:
            search_result = await ArxivService.fetch_by_relevance(
                db, args.query, max_results=10
            )

        new_papers = search_result.get("papers", [])
        if new_papers:
            logger.info(f"📥 ArXiv 搜索新增 {len(new_papers)} 篇论文，开始快速分析...")

            # 对新论文进行快速分析
            semaphore = asyncio.Semaphore(2)
            for paper in new_papers:
                logger.info(f"🔬 快速分析: {paper.title[:50]}...")
                try:
                    await paper_analyzer.analyze_paper(paper, semaphore, quick_mode=True)
                except Exception as e:
                    logger.warning(f"分析失败 {paper.arxiv_id}: {e}")

            # 重新查询符合条件的论文
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Paper).where(
                        Paper.tier.in_(tiers),
                        Paper.has_analysis == True,
                        Paper.title.ilike(f"%{args.query.replace(' ', '%')}%")
                    ).limit(args.limit if args.limit > 0 else 10)
                )
                papers = list(result.scalars().all())

    if not papers and not args.include_videos:
        logger.info(f"未找到符合条件 ({args.tiers}) 的已分析论文")
        logger.info(f"💡 提示: 使用 --auto-search 参数可自动从 ArXiv 搜索补充")
        logger.info(f"💡 提示: 使用 --include-videos 参数可同时导出视频笔记")
        return

    success_count = 0
    if papers:
        logger.info(f"开始导出 {len(papers)} 篇论文到 NotebookLM 格式 (模板: {args.template})...")
        for p in papers:
            logger.info(f"正在桥接: {p.title[:50]}...")
            if await bridge.bridge_paper(p, template_key=args.template):
                success_count += 1
        logger.info("=" * 40)
        logger.info(f"论文导出完成！成功: {success_count} / {len(papers)}")
        logger.info(f"文件已存入本地暂存区: /tmp/notebooklm_export")

    # ===== v2.2 新增: 多源知识混合导出 (视频笔记) =====
    video_success = 0
    if args.include_videos:
        logger.info("\n" + "=" * 40)
        logger.info("📹 开始导出视频笔记...")
        video_files = bridge.scan_video_notes(query=args.query, limit=args.video_limit)
        for vf in video_files:
            logger.info(f"正在桥接视频笔记: {vf.stem[:50]}...")
            if await bridge.bridge_generic_markdown(vf, doc_type="VIDEO", template_key=args.template):
                video_success += 1
        logger.info(f"视频笔记导出完成！成功: {video_success} / {len(video_files)}")

    # 汇总
    total_success = success_count + video_success
    logger.info("=" * 40)
    logger.info(f"🎯 多源知识导出完成！总计: {total_success} 个素材")
    logger.info(f"   - 论文: {success_count}")
    if args.include_videos:
        logger.info(f"   - 视频笔记: {video_success}")
    logger.info(f"📂 导出路径: /tmp/notebooklm_export")
    logger.info("=" * 40)


# ==================== 命令行入口 ====================

def main():
    parser = argparse.ArgumentParser(description="ArXiv 论文分析管理工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="执行两阶段分析")
    p_analyze.add_argument("--parallel", type=int, default=4, help="并发数")
    p_analyze.add_argument("--top-n", type=int, default=0, help="仅分析前 N 篇")
    p_analyze.add_argument("--min-citations", type=int, default=0, help="最小引用数")
    p_analyze.add_argument("--skip-quick", action="store_true", help="跳过快速分析阶段")
    p_analyze.add_argument("--quick-only", action="store_true", help="仅执行快速分析")
    p_analyze.add_argument("--no-sort", action="store_true", help="不按引用数排序")
    p_analyze.add_argument("--days", type=int, default=0, help="仅分析最近 N 天的论文 (0=全部)")
    p_analyze.add_argument("--tier-a-only", action="store_true", help="仅对 Tier A 执行完整分析")

    # verify
    p_verify = subparsers.add_parser("verify", help="检测分析质量")
    p_verify.add_argument("--fix", action="store_true", help="自动修复有问题的分析")
    p_verify.add_argument("--parallel", type=int, default=4, help="修复并发数")

    # reevaluate
    p_reevaluate = subparsers.add_parser("reevaluate", help="重新评估 Tier 等级")
    p_reevaluate.add_argument("--min-citations", type=int, default=0, help="最小引用数限制")
    p_reevaluate.add_argument("--parallel", type=int, default=4, help="并发数")

    # sync-scores
    subparsers.add_parser("sync-scores", help="从 Semantic Scholar 同步评分")

    # export-notebook
    p_export = subparsers.add_parser("export-notebook", help="导出精选论文到 NotebookLM (v2.1)")
    p_export.add_argument("--tiers", type=str, default="A,B", help="要导出的等级，逗度分隔 (默认 A,B)")
    p_export.add_argument("--limit", type=int, default=0, help="限制导出数量")
    p_export.add_argument("--query", type=str, default=None, help="按标题关键词或语义过滤")
    p_export.add_argument("--template", type=str, default="default", help="提示词模板 (default, tech_comparison, podcast_script)")
    p_export.add_argument("--auto-search", action="store_true", help="本地库不足时自动从 ArXiv 搜索补充")
    p_export.add_argument("--include-videos", action="store_true", help="同时导出 Obsidian 视频笔记 (多源混合导出)")
    p_export.add_argument("--video-limit", type=int, default=5, help="视频笔记最大导出数量 (配合 --include-videos)")
    p_export.add_argument("--fuzzy-threshold", type=int, default=75, help="模糊匹配阈值 (0-100, 默认 75)")
    p_export.add_argument("--min-papers", type=int, default=5, help="触发 ArXiv 搜索的最少论文数 (默认 5)")

    args = parser.parse_args()

    if args.command == "analyze":
        asyncio.run(cmd_analyze(args))
    elif args.command == "verify":
        asyncio.run(cmd_verify(args))
    elif args.command == "reevaluate":
        asyncio.run(cmd_reevaluate(args))
    elif args.command == "sync-scores":
        asyncio.run(cmd_sync_scores(args))
    elif args.command == "export-notebook":
        asyncio.run(cmd_export_notebook(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
