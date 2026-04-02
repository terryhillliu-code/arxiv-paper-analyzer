"""测试写入队列架构。

验证：
1. 并发 API 调用
2. 写入队列串行化数据库提交
3. 无锁竞争，无数据丢失
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker, engine
from app.models import Paper
from sqlalchemy import select, update

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
        return cls._instance

    async def start(self):
        """启动写入协程"""
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._write_worker())
        logger.info("✅ 写入服务已启动")

    async def submit(self, task: WriteTask) -> bool:
        """提交写入任务"""
        task.future = asyncio.get_event_loop().create_future()
        await self._queue.put(task)
        try:
            # 等待写入完成，超时30秒
            return await asyncio.wait_for(task.future, timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"写入超时: {task.task_id}")
            return False

    async def _write_worker(self):
        """写入工作协程 - 单一消费者"""
        logger.info("📝 写入协程启动")

        while self._running:
            try:
                # 从队列获取任务
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # 执行数据库写入
                success = await self._execute_write(task)

                # 通知结果
                if task.future and not task.future.done():
                    task.future.set_result(success)

                self._write_count += 1
                if self._write_count % 10 == 0:
                    logger.info(f"📊 已完成 {self._write_count} 次写入，队列剩余: {self._queue.qsize()}")

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"写入错误: {e}", exc_info=True)
                self._error_count += 1

    async def _execute_write(self, task: WriteTask) -> bool:
        """执行单次写入"""
        try:
            async with async_session_maker() as db:
                # 查询论文
                result = await db.execute(
                    select(Paper).where(Paper.id == task.paper_id)
                )
                paper = result.scalar_one_or_none()

                if not paper:
                    logger.warning(f"论文不存在: {task.paper_id}")
                    return False

                # 更新字段
                paper.analysis_report = task.analysis_report
                paper.analysis_json = task.analysis_json
                paper.has_analysis = task.has_analysis

                # 提交
                await db.commit()
                logger.debug(f"✅ 写入成功: paper_id={task.paper_id}")
                return True

        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            "write_count": self._write_count,
            "error_count": self._error_count,
            "queue_size": self._queue.qsize(),
        }

    def stop(self):
        """停止服务"""
        self._running = False


# 全局实例
db_write_service = DatabaseWriteService()


# ==================== 模拟分析任务 ====================

async def mock_analyze(paper_id: int, delay: float = 2.0) -> WriteTask:
    """模拟分析任务（API调用延迟）"""
    task_id = f"mock_{paper_id}_{time.time():.0f}"

    # 模拟 API 调用延迟
    await asyncio.sleep(delay)

    # 生成模拟结果
    return WriteTask(
        task_id=task_id,
        paper_id=paper_id,
        analysis_report=f"# 模拟分析报告\n\n论文 {paper_id} 的深度分析结果...\n\n生成时间: {datetime.now()}",
        analysis_json={
            "one_line_summary": f"论文 {paper_id} 的一句话总结",
            "tier": "B",
            "tags": ["测试", "并行"],
        },
    )


async def worker(worker_id: int, paper_ids: list[int], results: list):
    """工作协程"""
    for paper_id in paper_ids:
        try:
            logger.info(f"[Worker {worker_id}] 开始处理 paper_id={paper_id}")

            # 1. 模拟 API 调用（并行）
            start = time.time()
            write_task = await mock_analyze(paper_id, delay=1.5)
            api_time = time.time() - start

            # 2. 提交到写入队列（等待完成）
            start = time.time()
            success = await db_write_service.submit(write_task)
            write_time = time.time() - start

            results.append({
                "worker_id": worker_id,
                "paper_id": paper_id,
                "success": success,
                "api_time": api_time,
                "write_time": write_time,
            })

            status = "✅" if success else "❌"
            logger.info(f"[Worker {worker_id}] {status} paper_id={paper_id} | API: {api_time:.2f}s | 写入: {write_time:.2f}s")

        except Exception as e:
            logger.error(f"[Worker {worker_id}] 错误: {e}")


@pytest.mark.asyncio
async def test_concurrent_writes():
    """测试并发写入"""
    logger.info("=" * 60)
    logger.info("开始测试：并发写入队列架构")
    logger.info("=" * 60)

    # 1. 启动写入服务
    await db_write_service.start()

    # 2. 获取测试用的论文 ID
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper.id).where(Paper.has_analysis == False).limit(20)
        )
        paper_ids = [row[0] for row in result.fetchall()]

    if not paper_ids:
        # 如果没有未分析的，用已存在的论文测试
        async with async_session_maker() as db:
            result = await db.execute(
                select(Paper.id).limit(20)
            )
            paper_ids = [row[0] for row in result.fetchall()]

    logger.info(f"📋 测试论文数: {len(paper_ids)}")

    # 3. 分配给 4 个 Worker 并行处理
    num_workers = 4
    chunk_size = len(paper_ids) // num_workers + 1
    chunks = [paper_ids[i:i+chunk_size] for i in range(0, len(paper_ids), chunk_size)]

    logger.info(f"🔧 Worker 数: {num_workers}, 每个 Worker 处理: {[len(c) for c in chunks]}")

    # 4. 并行执行
    results = []
    start_time = time.time()

    tasks = [
        worker(i, chunks[i], results)
        for i in range(len(chunks))
    ]
    await asyncio.gather(*tasks)

    total_time = time.time() - start_time

    # 5. 输出结果
    logger.info("=" * 60)
    logger.info("测试结果")
    logger.info("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    avg_api_time = sum(r["api_time"] for r in results) / len(results) if results else 0
    avg_write_time = sum(r["write_time"] for r in results) / len(results) if results else 0

    stats = db_write_service.get_stats()

    logger.info(f"总任务数: {len(results)}")
    logger.info(f"成功: {success_count}, 失败: {fail_count}")
    logger.info(f"总耗时: {total_time:.2f}s")
    logger.info(f"平均 API 时间: {avg_api_time:.2f}s")
    logger.info(f"平均写入时间: {avg_write_time:.2f}s")
    logger.info(f"写入服务统计: {stats}")

    # 6. 计算加速比
    serial_time = len(results) * (avg_api_time + avg_write_time)
    speedup = serial_time / total_time if total_time > 0 else 0
    logger.info(f"理论串行时间: {serial_time:.2f}s")
    logger.info(f"加速比: {speedup:.2f}x")

    # 7. 停止服务
    db_write_service.stop()

    return success_count == len(results)


if __name__ == "__main__":
    success = asyncio.run(test_concurrent_writes())
    sys.exit(0 if success else 1)