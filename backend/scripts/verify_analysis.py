#!/usr/bin/env python
"""分析质量检测脚本。

检测分析结果的质量，发现需要修复的论文。

用法:
    python scripts/verify_analysis.py [--fix] [--parallel N]
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
from sqlalchemy import select, update
from app.services.ai_service import ai_service
from app.outputs.markdown_generator import MarkdownGenerator


# ==================== 质量检测规则 ====================

def check_report_quality(paper: Paper) -> dict:
    """检查报告质量。

    Returns:
        dict: {
            "valid": bool,
            "issues": list[str],
            "severity": "critical" | "warning"
        }
    """
    issues = []
    severity = "warning"

    # 1. 检查 report 长度
    report_len = len(paper.analysis_report) if paper.analysis_report else 0
    if report_len < 100:
        issues.append(f"report 太短 ({report_len} 字符)")
        severity = "critical"
    elif report_len < 1000:
        issues.append(f"report 偏短 ({report_len} 字符)")
        severity = "warning"

    # 2. 检查 report 是否是错误信息
    if paper.analysis_report:
        error_patterns = [
            "未提供具体研究内容",
            "无法提取有效",
            "是一篇待分析的学术论文",
            "内容为空",
            "test_",
        ]
        for pattern in error_patterns:
            if pattern in paper.analysis_report:
                issues.append(f"report 包含错误信息: '{pattern}'")
                severity = "critical"
                break

    # 3. 检查 JSON 关键字段
    j = paper.analysis_json or {}

    if not j.get("tags") or len(j.get("tags", [])) == 0:
        issues.append("tags 为空")
        if severity != "critical":
            severity = "warning"

    if not j.get("one_line_summary"):
        issues.append("one_line_summary 为空")
        severity = "critical"

    if not j.get("tier"):
        issues.append("tier 为空")
        severity = "critical"

    if not j.get("outline") or len(j.get("outline", [])) == 0:
        issues.append("outline 为空")
        # outline 空不是关键问题

    if not j.get("key_contributions") or len(j.get("key_contributions", [])) == 0:
        issues.append("key_contributions 为空")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "severity": severity,
    }


def check_data_sync(paper: Paper) -> dict:
    """检查数据库字段与 analysis_json 是否同步。

    Returns:
        dict: {"sync_issues": list[str]}
    """
    issues = []
    j = paper.analysis_json or {}

    # 检查 summary 同步
    if j.get("one_line_summary") and paper.summary != j.get("one_line_summary"):
        issues.append("summary 未同步")

    # 检查 tags 同步
    if j.get("tags") and paper.tags != j.get("tags"):
        issues.append("tags 未同步")

    # 检查 tier 同步
    if j.get("tier") and paper.tier != j.get("tier"):
        issues.append("tier 未同步")

    return {"sync_issues": issues}


async def verify_all():
    """检测所有已分析论文的质量。"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper).where(Paper.has_analysis == True)
        )
        papers = result.scalars().all()

    logger.info(f"检测 {len(papers)} 篇已分析论文...")

    critical_issues = []
    warning_issues = []
    sync_issues = []

    for p in papers:
        quality = check_report_quality(p)
        if not quality["valid"]:
            issue_entry = {
                "id": p.id,
                "title": p.title[:50],
                "tier": p.tier,
                "issues": quality["issues"],
            }
            if quality["severity"] == "critical":
                critical_issues.append(issue_entry)
            else:
                warning_issues.append(issue_entry)

        sync = check_data_sync(p)
        if sync["sync_issues"]:
            sync_issues.append({
                "id": p.id,
                "issues": sync["sync_issues"],
            })

    # 输出报告
    print("\n" + "=" * 60)
    print("分析质量检测报告")
    print("=" * 60)

    print(f"\n总论文数: {len(papers)}")
    print(f"严重问题: {len(critical_issues)} 篇")
    print(f"一般问题: {len(warning_issues)} 篇")
    print(f"同步问题: {len(sync_issues)} 篇")

    if critical_issues:
        print("\n=== 严重问题（需要重新分析）===")
        for item in critical_issues[:10]:
            print(f"ID {item['id']} [{item['tier']}]: {item['title']}")
            print(f"  问题: {', '.join(item['issues'])}")
        if len(critical_issues) > 10:
            print(f"... 还有 {len(critical_issues) - 10} 篇")

    if warning_issues:
        print("\n=== 一般问题 ===")
        for item in warning_issues[:5]:
            print(f"ID {item['id']}: {', '.join(item['issues'])}")

    if sync_issues:
        print("\n=== 同步问题 ===")
        for item in sync_issues[:5]:
            print(f"ID {item['id']}: {', '.join(item['issues'])}")

    return critical_issues, warning_issues, sync_issues


async def fix_issues(critical_issues: list, parallel: int = 4):
    """修复有问题的论文。"""
    if not critical_issues:
        logger.info("没有需要修复的论文")
        return

    logger.info(f"开始修复 {len(critical_issues)} 篇论文...")

    semaphore = asyncio.Semaphore(parallel)
    fixed = 0
    failed = 0

    async def fix_one(item):
        nonlocal fixed, failed
        async with semaphore:
            try:
                async with async_session_maker() as db:
                    result = await db.execute(
                        select(Paper).where(Paper.id == item["id"])
                    )
                    paper = result.scalar_one()

                    logger.info(f"修复: {paper.id} - {paper.title[:40]}")

                    # 重新分析
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

                    if analysis_json.get("tags") and analysis_json.get("one_line_summary"):
                        # 生成 Markdown
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

                        await db.execute(
                            update(Paper).where(Paper.id == paper.id).values(
                                analysis_report=report,
                                analysis_json=analysis_json,
                                has_analysis=True,
                                tier=analysis_json.get("tier"),
                                tags=analysis_json.get("tags"),
                                summary=analysis_json.get("one_line_summary"),
                                md_output_path=export_result.get("md_path"),
                            )
                        )
                        await db.commit()
                        fixed += 1
                        logger.info(f"✅ {paper.id}: tier={analysis_json.get('tier')}")
                    else:
                        failed += 1
                        logger.error(f"❌ {paper.id}: JSON 解析失败")

            except Exception as e:
                failed += 1
                logger.error(f"❌ {item['id']}: {e}")

    await asyncio.gather(*[fix_one(item) for item in critical_issues])
    logger.info(f"修复完成: 成功 {fixed}, 失败 {failed}")


async def fix_sync_issues(sync_issues: list):
    """修复同步问题。"""
    if not sync_issues:
        return

    logger.info(f"修复 {len(sync_issues)} 个同步问题...")

    async with async_session_maker() as db:
        for item in sync_issues:
            result = await db.execute(select(Paper).where(Paper.id == item["id"]))
            paper = result.scalar_one()
            j = paper.analysis_json or {}

            values = {}
            if "summary 未同步" in item["issues"] and j.get("one_line_summary"):
                values["summary"] = j["one_line_summary"]
            if "tags 未同步" in item["issues"] and j.get("tags"):
                values["tags"] = j["tags"]
            if "tier 未同步" in item["issues"] and j.get("tier"):
                values["tier"] = j["tier"]

            if values:
                await db.execute(
                    update(Paper).where(Paper.id == item["id"]).values(**values)
                )
                logger.info(f"✅ 同步 {item['id']}: {list(values.keys())}")

        await db.commit()


async def main():
    parser = argparse.ArgumentParser(description="分析质量检测")
    parser.add_argument("--fix", action="store_true", help="自动修复问题")
    parser.add_argument("--parallel", type=int, default=4, help="修复并发数")
    args = parser.parse_args()

    critical, warnings, sync = await verify_all()

    if args.fix:
        if critical:
            await fix_issues(critical, args.parallel)
        if sync:
            await fix_sync_issues(sync)

        # 重新检测
        print("\n" + "=" * 60)
        print("修复后重新检测")
        print("=" * 60)
        await verify_all()


if __name__ == "__main__":
    asyncio.run(main())