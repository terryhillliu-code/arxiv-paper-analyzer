#!/usr/bin/env python3
"""任务队列清理脚本。

清理过期任务：
- pending 任务对应的论文已分析 → 标记为 completed
- failed 任务超过 7 天 → 删除
"""

import sqlite3
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TASK_DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"


async def cleanup_tasks():
    """清理过期任务。"""
    conn = sqlite3.connect(TASK_DB_PATH)
    cursor = conn.cursor()

    # 1. 处理 pending 任务
    cursor.execute('SELECT id, payload, created_at FROM tasks WHERE status="pending"')
    pending_tasks = cursor.fetchall()

    completed_count = 0
    stale_count = 0

    async with async_session_maker() as session:
        for task_id, payload_json, created_at in pending_tasks:
            payload = json.loads(payload_json)
            paper_id = payload.get('paper_id')

            if paper_id:
                result = await session.execute(select(Paper).where(Paper.id == paper_id))
                paper = result.scalar_one_or_none()

                if paper and paper.has_analysis:
                    # 论文已分析，标记任务完成
                    now_time = datetime.now().isoformat()
                    cursor.execute(
                        'UPDATE tasks SET status="completed", completed_at=? WHERE id=?',
                        (now_time, task_id)
                    )
                    completed_count += 1
                    logger.debug(f"任务 {task_id} → completed (paper #{paper_id} 已分析)")
                else:
                    # 检查任务是否过期（超过 24 小时）
                    task_time = datetime.fromisoformat(created_at)
                    if datetime.now() - task_time > timedelta(hours=24):
                        cursor.execute(
                            'UPDATE tasks SET status="failed", error="timeout" WHERE id=?',
                            (task_id,)
                        )
                        stale_count += 1
                        logger.debug(f"任务 {task_id} → failed (超时)")

    # 2. 清理老旧 failed 任务（超过 7 天）
    cutoff_failed = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute(
        'DELETE FROM tasks WHERE status="failed" AND created_at < ?',
        (cutoff_failed,)
    )
    deleted_failed = cursor.rowcount

    # 3. 清理老旧 completed 任务（超过 30 天）
    cutoff_completed = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute(
        'DELETE FROM tasks WHERE status="completed" AND completed_at < ?',
        (cutoff_completed,)
    )
    deleted_completed = cursor.rowcount

    conn.commit()

    # 统计结果
    cursor.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status')
    final_stats = dict(cursor.fetchall())

    conn.close()

    logger.info("=== 任务清理结果 ===")
    logger.info(f"pending → completed: {completed_count}")
    logger.info(f"pending → failed (超时): {stale_count}")
    logger.info(f"删除过期 failed 任务: {deleted_failed}")
    logger.info(f"删除过期 completed 任务: {deleted_completed}")
    logger.info("")
    logger.info("=== 当前任务队列 ===")
    for status, count in final_stats.items():
        logger.info(f"{status}: {count}")


async def main():
    """主函数。"""
    logger.info("=" * 60)
    logger.info("任务队列清理脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    await cleanup_tasks()

    logger.info("\n清理完成!")


if __name__ == "__main__":
    asyncio.run(main())