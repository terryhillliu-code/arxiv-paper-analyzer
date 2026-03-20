"""压力测试：写入队列架构。

测试场景：
1. 50 个并发任务
2. 8 个 Worker 并行
3. 模拟真实 API 延迟（2-3秒）
4. 验证数据一致性
"""

import asyncio
import logging
import sys
import time
import random
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker
from app.models import Paper
from sqlalchemy import select, func

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 写入队列服务 ====================

@dataclass
class WriteTask:
    """写入任务"""
    task_id: str
    paper_id: int
    analysis_report: str
    analysis_json: Dict[str, Any]
    has_analysis: bool = True
    future: asyncio.Future = None


class DatabaseWriteService:
    """数据库写入服务 - 单一消费者模式"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._queue = asyncio.Queue()
            cls._instance._running = False
            cls._instance._write_count = 0
            cls._instance._error_count = 0
            cls._instance._max_queue_size = 0
        return cls._instance

    async def start(self):
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._write_worker())
        logger.info("✅ 写入服务已启动")

    async def submit(self, task: WriteTask) -> bool:
        task.future = asyncio.get_event_loop().create_future()
        await self._queue.put(task)

        # 跟踪最大队列大小
        if self._queue.qsize() > self._max_queue_size:
            self._max_queue_size = self._queue.qsize()

        try:
            return await asyncio.wait_for(task.future, timeout=60.0)
        except asyncio.TimeoutError:
            logger.error(f"写入超时: {task.task_id}")
            return False

    async def _write_worker(self):
        from sqlalchemy import select

        logger.info("📝 写入协程启动")

        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                success = await self._execute_write(task)
                if task.future and not task.future.done():
                    task.future.set_result(success)
                self._write_count += 1
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"写入错误: {e}", exc_info=True)
                self._error_count += 1

    async def _execute_write(self, task: WriteTask) -> bool:
        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Paper).where(Paper.id == task.paper_id)
                )
                paper = result.scalar_one_or_none()

                if not paper:
                    logger.warning(f"论文不存在: {task.paper_id}")
                    return False

                paper.analysis_report = task.analysis_report
                paper.analysis_json = task.analysis_json
                paper.has_analysis = task.has_analysis
                await db.commit()
                return True

        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
        return {
            "write_count": self._write_count,
            "error_count": self._error_count,
            "queue_size": self._queue.qsize(),
            "max_queue_size": self._max_queue_size,
        }

    def stop(self):
        self._running = False


db_write_service = DatabaseWriteService()


# ==================== 压力测试 ====================

async def stress_worker(worker_id: int, tasks: list[tuple], results: list):
    """压力测试工作协程"""
    for task_id, paper_id, delay in tasks:
        try:
            # 模拟 API 调用
            await asyncio.sleep(delay)

            # 创建写入任务
            write_task = WriteTask(
                task_id=task_id,
                paper_id=paper_id,
                analysis_report=f"# 压力测试报告\n\nTask: {task_id}\nWorker: {worker_id}\nTime: {datetime.now()}",
                analysis_json={
                    "stress_test": True,
                    "worker_id": worker_id,
                    "task_id": task_id,
                },
            )

            # 提交到队列
            start = time.time()
            success = await db_write_service.submit(write_task)
            write_time = time.time() - start

            results.append({
                "worker_id": worker_id,
                "task_id": task_id,
                "paper_id": paper_id,
                "success": success,
                "write_time": write_time,
            })

            if not success:
                logger.error(f"[Worker {worker_id}] ❌ {task_id}")

        except Exception as e:
            logger.error(f"[Worker {worker_id}] 异常: {e}")
            results.append({
                "worker_id": worker_id,
                "task_id": task_id,
                "paper_id": paper_id,
                "success": False,
                "error": str(e),
            })


async def verify_data_integrity(paper_ids: list[int]) -> bool:
    """验证数据完整性"""
    logger.info("🔍 验证数据完整性...")

    async with async_session_maker() as db:
        for paper_id in paper_ids:
            result = await db.execute(
                select(Paper).where(Paper.id == paper_id)
            )
            paper = result.scalar_one_or_none()

            if not paper:
                logger.error(f"论文不存在: {paper_id}")
                return False

            if not paper.has_analysis:
                logger.error(f"论文 {paper_id} has_analysis=False")
                return False

            if not paper.analysis_json:
                logger.error(f"论文 {paper_id} analysis_json 为空")
                return False

    logger.info("✅ 数据完整性验证通过")
    return True


async def stress_test():
    """压力测试主函数"""
    logger.info("=" * 60)
    logger.info("压力测试：写入队列架构")
    logger.info("=" * 60)

    # 配置
    NUM_WORKERS = 8
    NUM_TASKS = 50
    MIN_API_DELAY = 1.5
    MAX_API_DELAY = 3.0

    logger.info(f"📋 配置: {NUM_WORKERS} Workers, {NUM_TASKS} 任务")
    logger.info(f"⏱️ API 延迟: {MIN_API_DELAY}-{MAX_API_DELAY}s")

    # 1. 启动写入服务
    await db_write_service.start()

    # 2. 获取测试论文
    async with async_session_maker() as db:
        # 重置测试论文状态
        result = await db.execute(
            select(Paper.id).limit(NUM_TASKS + 10)
        )
        all_paper_ids = [row[0] for row in result.fetchall()]

    paper_ids = all_paper_ids[:NUM_TASKS]
    logger.info(f"📄 测试论文: {len(paper_ids)} 篇")

    # 3. 重置论文状态
    logger.info("🔄 重置论文状态...")
    async with async_session_maker() as db:
        for paper_id in paper_ids:
            result = await db.execute(
                select(Paper).where(Paper.id == paper_id)
            )
            paper = result.scalar_one_or_none()
            if paper:
                paper.has_analysis = False
                paper.analysis_json = None
        await db.commit()

    # 4. 生成任务
    tasks = []
    for i, paper_id in enumerate(paper_ids):
        delay = random.uniform(MIN_API_DELAY, MAX_API_DELAY)
        tasks.append((f"stress_{i:03d}", paper_id, delay))

    # 5. 分配给 Workers
    chunk_size = len(tasks) // NUM_WORKERS + 1
    chunks = [tasks[i:i+chunk_size] for i in range(0, len(tasks), chunk_size)]

    logger.info(f"🔧 任务分配: {[len(c) for c in chunks]}")

    # 6. 并行执行
    results = []
    start_time = time.time()

    workers = [
        stress_worker(i, chunks[i], results)
        for i in range(len(chunks))
    ]
    await asyncio.gather(*workers)

    total_time = time.time() - start_time

    # 7. 等待队列清空
    logger.info("⏳ 等待队列清空...")
    for _ in range(30):
        if db_write_service._queue.qsize() == 0:
            break
        await asyncio.sleep(0.5)

    # 8. 验证数据完整性
    integrity_ok = await verify_data_integrity(paper_ids)

    # 9. 统计结果
    logger.info("=" * 60)
    logger.info("压力测试结果")
    logger.info("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    avg_write_time = sum(r["write_time"] for r in results) / len(results) if results else 0

    stats = db_write_service.get_stats()

    logger.info(f"总任务数: {len(results)}")
    logger.info(f"成功: {success_count}, 失败: {fail_count}")
    logger.info(f"总耗时: {total_time:.2f}s")
    logger.info(f"平均写入时间: {avg_write_time:.4f}s")
    logger.info(f"最大队列深度: {stats['max_queue_size']}")
    logger.info(f"数据完整性: {'✅ 通过' if integrity_ok else '❌ 失败'}")

    # 计算性能
    throughput = len(results) / total_time
    theoretical_serial = len(results) * ((MIN_API_DELAY + MAX_API_DELAY) / 2 + avg_write_time)
    speedup = theoretical_serial / total_time

    logger.info(f"吞吐量: {throughput:.2f} 任务/秒")
    logger.info(f"加速比: {speedup:.2f}x")

    # 10. 停止服务
    db_write_service.stop()

    # 最终判断
    all_ok = (success_count == len(results)) and integrity_ok and (stats['error_count'] == 0)

    logger.info("=" * 60)
    if all_ok:
        logger.info("🎉 压力测试通过！")
    else:
        logger.error("❌ 压力测试失败！")
    logger.info("=" * 60)

    return all_ok


if __name__ == "__main__":
    success = asyncio.run(stress_test())
    sys.exit(0 if success else 1)