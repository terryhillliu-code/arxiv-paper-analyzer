#!/usr/bin/env python3
"""任务进度监控脚本。

实时显示任务队列状态和处理进度。
"""

import sqlite3
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_maker
from sqlalchemy import select, func
from app.models import Paper


class ProgressMonitor:
    """进度监控器"""

    def __init__(self, db_path: str = "data/tasks.db"):
        self.db_path = db_path

    def get_task_stats(self) -> Dict[str, Any]:
        """获取任务统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 状态分布
        cursor.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status')
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 最近完成
        one_min_ago = (datetime.now() - timedelta(minutes=1)).isoformat()
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE status="completed" AND completed_at > ?', (one_min_ago,))
        one_min = cursor.fetchone()[0]

        five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        cursor.execute('SELECT COUNT(*) FROM tasks WHERE status="completed" AND completed_at > ?', (five_min_ago,))
        five_min = cursor.fetchone()[0]

        conn.close()

        return {
            "completed": status_counts.get("completed", 0),
            "pending": status_counts.get("pending", 0),
            "running": status_counts.get("running", 0),
            "failed": status_counts.get("failed", 0),
            "recent_1min": one_min,
            "recent_5min": five_min,
        }

    async def get_paper_stats(self) -> Dict[str, Any]:
        """获取论文统计"""
        async with async_session_maker() as db:
            total = await db.execute(select(func.count(Paper.id)))
            total_count = total.scalar()

            analyzed = await db.execute(select(func.count(Paper.id)).where(Paper.has_analysis == True))
            analyzed_count = analyzed.scalar()

            tier_a = await db.execute(select(func.count(Paper.id)).where(Paper.tier == 'A'))
            tier_a_count = tier_a.scalar()

            tier_a_done = await db.execute(
                select(func.count(Paper.id)).where(Paper.tier == 'A', Paper.has_analysis == True)
            )
            tier_a_done_count = tier_a_done.scalar()

            tier_b = await db.execute(select(func.count(Paper.id)).where(Paper.tier == 'B'))
            tier_b_count = tier_b.scalar()

            tier_b_done = await db.execute(
                select(func.count(Paper.id)).where(Paper.tier == 'B', Paper.has_analysis == True)
            )
            tier_b_done_count = tier_b_done.scalar()

            return {
                "total": total_count,
                "analyzed": analyzed_count,
                "analyzed_percent": analyzed_count / total_count * 100 if total_count > 0 else 0,
                "tier_a": tier_a_count,
                "tier_a_done": tier_a_done_count,
                "tier_b": tier_b_count,
                "tier_b_done": tier_b_done_count,
            }

    def print_status(self, task_stats: Dict, paper_stats: Dict):
        """打印状态"""
        now = datetime.now().strftime("%H:%M:%S")

        print(f"\n[{now}] === 任务队列状态 ===")
        print(f"完成: {task_stats['completed']}")
        print(f"待处理: {task_stats['pending']}")
        print(f"运行中: {task_stats['running']}")
        print(f"失败: {task_stats['failed']}")

        # 吞吐量
        if task_stats['recent_5min'] > 0:
            throughput = task_stats['recent_5min'] * 12
            print(f"\n吞吐量: ~{throughput}/小时 (基于最近5分钟)")

        print(f"\n=== 论文分析进度 ===")
        print(f"总数: {paper_stats['total']}")
        print(f"已分析: {paper_stats['analyzed']} ({paper_stats['analyzed_percent']:.1f}%)")
        print(f"Tier A: {paper_stats['tier_a_done']}/{paper_stats['tier_a']} ({paper_stats['tier_a_done']/paper_stats['tier_a']*100:.1f}%)")
        print(f"Tier B: {paper_stats['tier_b_done']}/{paper_stats['tier_b']} ({paper_stats['tier_b_done']/paper_stats['tier_b']*100:.1f}%)")

        # 预估
        if task_stats['recent_5min'] > 0:
            remaining = task_stats['pending'] + task_stats['running']
            hours = remaining / throughput
            print(f"\n预估完成: {hours:.1f} 小时处理 {remaining} 个任务")

    async def run(self, interval: int = 30, count: int = 10):
        """运行监控循环"""
        for i in range(count):
            task_stats = self.get_task_stats()
            paper_stats = await self.get_paper_stats()
            self.print_status(task_stats, paper_stats)

            if i < count - 1:
                await asyncio.sleep(interval)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="任务进度监控")
    parser.add_argument("--interval", type=int, default=30, help="刷新间隔（秒）")
    parser.add_argument("--count", type=int, default=10, help="刷新次数")

    args = parser.parse_args()

    monitor = ProgressMonitor()
    await monitor.run(interval=args.interval, count=args.count)


if __name__ == "__main__":
    asyncio.run(main())