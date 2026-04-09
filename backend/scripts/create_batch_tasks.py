#!/usr/bin/env python3
"""批量论文分析任务创建脚本。

将待分析论文打包成批量任务，提高处理效率。

用法:
    python scripts/create_batch_tasks.py --batch-size 5 --limit 100
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks.task_queue import TaskQueue, TASK_DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_batch_tasks(batch_size: int = 5, limit: int = 100, dry_run: bool = False):
    """创建批量分析任务。

    Args:
        batch_size: 每批处理的论文数量
        limit: 最大处理论文数量
        dry_run: 只预览，不实际创建
    """
    import sqlite3

    # 连接 papers 数据库获取待分析论文
    papers_db = Path(__file__).parent.parent / "data" / "papers.db"
    if not papers_db.exists():
        logger.error(f"数据库不存在: {papers_db}")
        return

    conn = sqlite3.connect(str(papers_db))
    cursor = conn.cursor()

    # 获取待分析论文
    cursor.execute("""
        SELECT id, arxiv_id, title
        FROM papers
        WHERE has_analysis = 0
          AND abstract IS NOT NULL
          AND abstract != ''
        ORDER BY id ASC
        LIMIT ?
    """, (limit,))

    pending_papers = cursor.fetchall()
    conn.close()

    if not pending_papers:
        logger.info("没有待分析的论文")
        return

    logger.info(f"发现 {len(pending_papers)} 篇待分析论文")

    if dry_run:
        logger.info("[DRY RUN] 预览模式，不创建任务")
        for i in range(0, len(pending_papers), batch_size):
            batch = pending_papers[i:i + batch_size]
            logger.info(f"批次 {i // batch_size + 1}: {[p[0] for p in batch]}")
        return

    # 创建任务队列
    task_queue = TaskQueue(db_path=TASK_DB_PATH)

    # 注册处理器（仅为了自动注册逻辑）
    try:
        from app.tasks.batch_analysis_task import register_batch_analysis_handler
        register_batch_analysis_handler(task_queue)
    except ImportError:
        pass

    # 分批创建任务
    created_count = 0
    for i in range(0, len(pending_papers), batch_size):
        batch = pending_papers[i:i + batch_size]
        paper_ids = [p[0] for p in batch]

        # 创建批量任务
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i // batch_size}"

        try:
            task = task_queue.create_task(
                "batch_analysis",
                {
                    "paper_ids": paper_ids,
                    "batch_id": batch_id,
                }
            )
            logger.info(f"创建批量任务: {task.id} -> {len(paper_ids)} 篇论文")
            created_count += 1
        except Exception as e:
            logger.error(f"创建任务失败: {e}")

    logger.info(f"完成: 创建 {created_count} 个批量任务")


def main():
    parser = argparse.ArgumentParser(description="创建批量分析任务")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="每批处理的论文数量 (默认: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最大处理论文数量 (默认: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不创建任务",
    )

    args = parser.parse_args()

    create_batch_tasks(
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()