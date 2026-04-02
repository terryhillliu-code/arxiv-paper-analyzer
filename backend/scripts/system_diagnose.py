#!/usr/bin/env python3
"""系统诊断脚本。

检查系统健康状态并输出报告。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from sqlalchemy import select, func
from app.database import async_session_maker
from app.models import Paper
from app.tasks.task_queue import task_queue
from app.utils.resource_monitor import resource_monitor


async def diagnose():
    """执行系统诊断。"""
    print("=" * 60)
    print("ArXiv 论文分析平台 - 系统诊断")
    print(f"诊断时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    async with async_session_maker() as db:
        # 论文统计
        result = await db.execute(select(func.count(Paper.id)))
        total = result.scalar()

        result = await db.execute(
            select(Paper.tier, func.count(Paper.id))
            .group_by(Paper.tier)
        )
        tiers = dict(result.fetchall())

        result = await db.execute(
            select(Paper.has_analysis, func.count(Paper.id))
            .group_by(Paper.has_analysis)
        )
        analysis = dict(result.fetchall())

        # 最近7天论文
        result = await db.execute(
            select(func.count(Paper.id))
            .where(Paper.created_at >= datetime.now() - timedelta(days=7))
        )
        recent = result.scalar()

        # 缺失数据
        result = await db.execute(
            select(func.count(Paper.id))
            .where(Paper.abstract == None)
        )
        no_abstract = result.scalar()

        result = await db.execute(
            select(func.count(Paper.id))
            .where(Paper.institutions == None)
        )
        no_institution = result.scalar()

        # 任务队列
        pending = task_queue.get_pending_tasks(limit=1000)

        # 系统资源
        status = resource_monitor.check_resources()

    # 输出报告
    print("\n【论文数据】")
    print(f"  总论文数: {total}")
    print(f"  Tier 分布: A={tiers.get('A', 0)} | B={tiers.get('B', 0)} | C={tiers.get('C', 0)}")
    print(f"  分析状态: 已分析={analysis.get(True, 0)} | 未分析={analysis.get(False, 0)}")
    print(f"  近7天新增: {recent}")

    print("\n【数据完整性】")
    print(f"  缺少摘要: {no_abstract}")
    print(f"  缺少机构: {no_institution}")

    print("\n【任务队列】")
    print(f"  待处理任务: {len(pending)}")

    print("\n【系统资源】")
    print(f"  CPU: {status.cpu_percent:.1f}%")
    print(f"  内存: {status.memory_percent:.1f}%")
    print(f"  状态: {'✅ 正常' if status.is_safe else '⚠️ 紧张'}")

    # 健康检查
    print("\n【健康检查】")
    issues = []

    if analysis.get(False, 0) > 50:
        issues.append(f"⚠️ 有 {analysis.get(False, 0)} 篇论文未分析")

    if len(pending) > 100:
        issues.append(f"⚠️ 任务队列积压 {len(pending)} 个任务")

    if not status.is_safe:
        issues.append(f"⚠️ 系统资源紧张")

    if issues:
        for issue in issues:
            print(f"  {issue}")
    else:
        print("  ✅ 系统运行正常")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(diagnose())