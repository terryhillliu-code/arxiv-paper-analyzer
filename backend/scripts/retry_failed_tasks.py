#!/usr/bin/env python3
"""失败任务恢复脚本。

定期检查失败的任务并重新加入队列。
"""

import asyncio
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from app.tasks.task_queue import TASK_DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def retry_failed_tasks(max_age_hours: int = 24, max_retries: int = 3):
    """重试失败的任务。

    Args:
        max_age_hours: 最大重试时间（小时），超过此时间的失败任务不再重试
        max_retries: 最大重试次数
    """
    conn = sqlite3.connect(TASK_DB_PATH)
    cursor = conn.cursor()

    # 查找可以重试的失败任务
    cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

    cursor.execute('''
        SELECT id, task_type, payload, error, completed_at
        FROM tasks
        WHERE status = 'failed'
        AND completed_at > ?
        ORDER BY completed_at DESC
    ''', (cutoff_time,))

    failed_tasks = cursor.fetchall()

    if not failed_tasks:
        logger.info("没有可重试的失败任务")
        conn.close()
        return 0

    logger.info(f"发现 {len(failed_tasks)} 个失败任务")

    # 重置为 pending
    reset_count = 0
    for task_id, task_type, payload, error, completed_at in failed_tasks:
        # 检查是否为网络错误（可重试）
        error_lower = (error or "").lower()
        is_retryable = any(keyword in error_lower for keyword in [
            'connection', 'network', 'timeout', 'refused', 'reset',
            'broken pipe', 'api', 'http', 'rate limit'
        ])

        if is_retryable:
            cursor.execute('''
                UPDATE tasks SET
                    status = 'pending',
                    progress = 0,
                    started_at = NULL,
                    completed_at = NULL,
                    message = '自动重试',
                    error = NULL
                WHERE id = ?
            ''', (task_id,))
            reset_count += 1
            logger.info(f"重试任务: {task_id} ({task_type})")

    conn.commit()
    conn.close()

    logger.info(f"已重置 {reset_count} 个任务")
    return reset_count


def cleanup_old_tasks(days: int = 7):
    """清理旧的已完成/失败任务。

    Args:
        days: 保留天数
    """
    conn = sqlite3.connect(TASK_DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # 删除旧任务
    cursor.execute('''
        DELETE FROM tasks
        WHERE status IN ('completed', 'failed')
        AND completed_at < ?
    ''', (cutoff,))

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        logger.info(f"已清理 {deleted} 个旧任务")

    return deleted


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="失败任务恢复")
    parser.add_argument(
        "--retry",
        action="store_true",
        help="重试失败的任务",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="清理旧任务",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="保留天数（用于清理）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("任务维护脚本")
    logger.info(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    if args.retry:
        retry_failed_tasks()

    if args.cleanup:
        cleanup_old_tasks(args.days)

    if not args.retry and not args.cleanup:
        # 默认：重试失败任务
        retry_failed_tasks()


if __name__ == "__main__":
    main()