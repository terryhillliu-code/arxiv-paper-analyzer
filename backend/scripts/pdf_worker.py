#!/usr/bin/env python3
"""PDF下载后台Worker。

独立进程，后台下载PDF用于：
1. 存档备用
2. 深度分析（可选）
3. RAG索引

启动方式：
    python scripts/pdf_worker.py --concurrent 3
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks.task_queue import TaskQueue, TASK_DB_PATH
from app.tasks.pdf_download_task import register_pdf_download_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 全局标志
_shutdown = False


def signal_handler(signum, frame):
    """信号处理器"""
    global _shutdown
    logger.info(f"收到信号 {signum}，准备优雅退出...")
    _shutdown = True


async def process_pdfs(max_concurrent: int = 3):
    """处理PDF下载任务

    Args:
        max_concurrent: 最大并发数（建议2-3，避免占满带宽）
    """
    global _shutdown

    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 创建任务队列
    task_queue = TaskQueue(db_path=TASK_DB_PATH, max_concurrent=max_concurrent)

    logger.info("=" * 60)
    logger.info("PDF下载Worker启动")
    logger.info(f"最大并发: {max_concurrent}")
    logger.info("=" * 60)

    try:
        # 只处理 pdf_download 类型的任务
        await task_queue.run_worker(poll_interval=5.0, task_type="pdf_download")
    except asyncio.CancelledError:
        logger.info("任务处理器被取消")
    finally:
        logger.info("PDF下载Worker已停止")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PDF下载后台Worker")
    parser.add_argument(
        "--concurrent",
        type=int,
        default=3,
        help="并发下载数（建议2-3）",
    )

    args = parser.parse_args()

    try:
        asyncio.run(process_pdfs(max_concurrent=args.concurrent))
    except KeyboardInterrupt:
        logger.info("PDF下载Worker已停止")