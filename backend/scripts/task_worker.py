#!/usr/bin/env python3
"""后台任务处理器。

持续处理任务队列中的分析任务。
支持断网重连、任务恢复、健康检查、PID锁定防重复启动。
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from app.tasks.task_queue import TaskQueue, TASK_DB_PATH
from app.tasks.analysis_task import register_analysis_handler
from app.utils.resource_monitor import resource_monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# PID 文件路径
PID_FILE = Path(__file__).parent.parent / "data" / "worker.pid"

# 全局标志
_shutdown = False


def acquire_pid_lock() -> bool:
    """获取 PID 锁，防止重复启动。

    Returns:
        True 如果成功获取锁，False 如果已有其他进程持有
    """
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 检查是否存在 PID 文件
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            # 检查进程是否还在运行
            if Path(f"/proc/{old_pid}").exists() or os.path.exists(f"/proc/{old_pid}"):
                logger.error(f"❌ 已有 Worker 进程运行 (PID: {old_pid})，退出")
                return False
            # macOS 检查方式
            try:
                os.kill(old_pid, 0)  # 检查进程是否存在
                logger.error(f"❌ 已有 Worker 进程运行 (PID: {old_pid})，退出")
                return False
            except OSError:
                # 进程不存在，清理旧 PID 文件
                logger.info(f"清理旧 PID 文件 (进程 {old_pid} 已不存在)")
                PID_FILE.unlink()
        except (ValueError, OSError):
            # PID 文件损坏，清理
            PID_FILE.unlink()

    # 写入当前 PID
    PID_FILE.write_text(str(os.getpid()))
    logger.info(f"✅ PID 锁已获取 (PID: {os.getpid()})")
    return True


def release_pid_lock():
    """释放 PID 锁"""
    if PID_FILE.exists():
        try:
            current_pid = int(PID_FILE.read_text().strip())
            if current_pid == os.getpid():
                PID_FILE.unlink()
                logger.info("✅ PID 锁已释放")
        except (ValueError, OSError):
            pass


def signal_handler(signum, frame):
    """信号处理器"""
    global _shutdown
    logger.info(f"收到信号 {signum}，准备优雅退出...")
    _shutdown = True


async def health_check(task_queue: TaskQueue, interval: int = 300):
    """定期健康检查。

    Args:
        task_queue: 任务队列
        interval: 检查间隔（秒）
    """
    while not _shutdown:
        try:
            await asyncio.sleep(interval)

            # 检查网络连接
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.openai.com", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status < 500:
                            logger.debug("网络连接正常")
                        else:
                            logger.warning(f"API 服务异常: {resp.status}")
            except Exception as e:
                logger.warning(f"网络检查失败: {e}")

            # 检查任务队列状态
            conn = sqlite3.connect(TASK_DB_PATH)
            cursor = conn.cursor()
            cursor.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status')
            stats = dict(cursor.fetchall())
            conn.close()

            logger.info(f"健康检查 | 待处理: {stats.get('pending', 0)} | 运行中: {stats.get('running', 0)} | 已完成: {stats.get('completed', 0)}")

            # 恢复卡住的任务
            stuck_threshold = (datetime.now() - timedelta(minutes=30)).isoformat()
            conn = sqlite3.connect(TASK_DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tasks SET status='pending', progress=0, started_at=NULL
                WHERE status='running' AND started_at < ?
            ''', (stuck_threshold,))
            if cursor.rowcount > 0:
                logger.warning(f"恢复了 {cursor.rowcount} 个卡住的任务")
            conn.commit()
            conn.close()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"健康检查错误: {e}")


async def process_tasks(max_concurrent: int = 6):
    """持续处理任务队列。

    Args:
        max_concurrent: 最大并发数
    """
    global _shutdown

    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 创建新的任务队列实例，使用指定的并发数
    task_queue = TaskQueue(db_path=TASK_DB_PATH, max_concurrent=max_concurrent)

    # 注册处理器
    register_analysis_handler(task_queue)

    # 注册批量分析处理器
    try:
        from app.tasks.batch_analysis_task import register_batch_analysis_handler
        register_batch_analysis_handler(task_queue)
        logger.info("已注册 batch_analysis 处理器")
    except ImportError as e:
        logger.warning(f"无法注册 batch_analysis 处理器: {e}")

    logger.info("=" * 60)
    logger.info("任务处理器启动")
    logger.info(f"最大并发: {max_concurrent}")
    logger.info("=" * 60)

    # 启动健康检查（后台任务）
    health_task = asyncio.create_task(health_check(task_queue, interval=300))

    try:
        # 启动任务队列工作器
        await task_queue.run_worker(poll_interval=2.0)
    except asyncio.CancelledError:
        logger.info("任务处理器被取消")
    finally:
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        logger.info("任务处理器已停止")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="后台任务处理器")
    parser.add_argument(
        "--concurrent",
        type=int,
        default=6,
        help="并发处理数",
    )

    args = parser.parse_args()

    # 获取 PID 锁，防止重复启动
    if not acquire_pid_lock():
        sys.exit(1)

    try:
        asyncio.run(process_tasks(max_concurrent=args.concurrent))
    except KeyboardInterrupt:
        logger.info("任务处理器已停止")
    finally:
        release_pid_lock()