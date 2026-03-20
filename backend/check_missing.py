#!/usr/bin/env python
"""检查论文分析完整性。

检查哪些论文缺少：
- 思维导图 (outline)
- 标签 (tags)
- 一句话总结 (one_line_summary)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker
from app.models import Paper
from sqlalchemy import select


async def check_missing():
    """检查缺失的分析字段"""
    async with async_session_maker() as db:
        # 获取已分析的论文
        result = await db.execute(
            select(Paper)
            .where(Paper.publish_date >= "2026-03-19")
            .where(Paper.publish_date < "2026-03-20")
            .where(Paper.has_analysis == True)
        )
        papers = result.scalars().all()

        missing_outline = []
        missing_tags = []
        missing_summary = []
        missing_all = []

        for paper in papers:
            analysis_json = paper.analysis_json or {}

            # 检查 outline
            outline = analysis_json.get("outline", [])
            if not outline or (isinstance(outline, list) and len(outline) == 0):
                missing_outline.append(paper.id)

            # 检查 tags
            tags = analysis_json.get("tags", [])
            if not tags or (isinstance(tags, list) and len(tags) == 0):
                missing_tags.append(paper.id)

            # 检查 one_line_summary
            summary = analysis_json.get("one_line_summary", "")
            if not summary or summary.strip() == "":
                missing_summary.append(paper.id)

            # 检查是否全部缺失
            if (not outline or len(outline) == 0) and (not tags or len(tags) == 0) and (not summary or summary.strip() == ""):
                missing_all.append(paper.id)

        print(f"已分析论文总数: {len(papers)}")
        print(f"\n缺失统计:")
        print(f"  缺少 outline: {len(missing_outline)} 篇")
        print(f"  缺少 tags: {len(missing_tags)} 篇")
        print(f"  缺少 summary: {len(missing_summary)} 篇")
        print(f"  全部缺失: {len(missing_all)} 篇")

        if missing_all:
            print(f"\n需要重分析的论文 ID:")
            print(", ".join(map(str, missing_all[:50])))
            if len(missing_all) > 50:
                print(f"... 共 {len(missing_all)} 篇")

        return {
            "missing_outline": missing_outline,
            "missing_tags": missing_tags,
            "missing_summary": missing_summary,
            "missing_all": missing_all,
        }


if __name__ == "__main__":
    asyncio.run(check_missing())