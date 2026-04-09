"""数据库写入服务。

提供写入队列，避免 SQLite 并发写入锁竞争。
API 调用可以并行，写入串行化。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class WriteTask:
    """写入任务"""
    paper_id: int
    analysis_report: str
    analysis_json: Dict[str, Any]
    tier: Optional[str] = None
    summary: Optional[str] = None  # 一段话总结
    action_items: Optional[list] = None
    knowledge_links: Optional[list] = None
    tags: Optional[list] = None
    md_output_path: Optional[str] = None
    has_analysis: bool = True
    full_analysis: Optional[bool] = None
    analysis_mode: Optional[str] = None  # "quick" 或 "full"
    future: asyncio.Future = field(default=None, repr=False)


class DatabaseWriteService:
    """数据库写入服务 - 单一消费者模式

    解决 SQLite 并发写入锁竞争问题：
    - API 调用可以完全并行
    - 写入通过队列串行化
    - 单一协程处理所有数据库提交
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._queue: asyncio.Queue = None
            cls._instance._running = False
            cls._instance._write_count = 0
            cls._instance._error_count = 0
            cls._instance._started = False
        return cls._instance

    async def start(self):
        """启动写入服务"""
        if self._started:
            return

        self._queue = asyncio.Queue()
        self._running = True
        self._started = True

        # 启动写入协程
        asyncio.create_task(self._write_worker())
        logger.info("✅ 数据库写入服务已启动")

    async def submit(self, task: WriteTask) -> bool:
        """提交写入任务

        Args:
            task: 写入任务

        Returns:
            是否成功
        """
        if not self._started:
            await self.start()

        task.future = asyncio.get_running_loop().create_future()
        logger.info(f"📥 提交写入任务: paper_id={task.paper_id}")
        await self._queue.put(task)
        logger.info(f"📤 任务已入队，队列大小: {self._queue.qsize()}")

        try:
            # 等待写入完成，超时180秒（增加以适应高并发）
            return await asyncio.wait_for(task.future, timeout=180.0)
        except asyncio.TimeoutError:
            logger.error(f"写入超时: paper_id={task.paper_id}")
            return False

    async def _write_worker(self):
        """写入工作协程 - 单一消费者"""
        from app.database import async_session_maker
        from app.models import Paper
        from sqlalchemy import select

        logger.info("📝 写入协程启动")

        while self._running:
            try:
                # 从队列获取任务
                logger.debug("等待队列任务...")
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                logger.info(f"🔄 从队列取出任务: paper_id={task.paper_id}")

                # 执行数据库写入
                success = await self._execute_write(task, async_session_maker, Paper, select)

                # 通知结果
                if task.future and not task.future.done():
                    task.future.set_result(success)

                self._write_count += 1

                if self._write_count % 10 == 0:
                    logger.info(f"📊 写入服务: 已完成 {self._write_count} 次，队列剩余: {self._queue.qsize()}")

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"写入错误: {e}", exc_info=True)
                self._error_count += 1

    async def _execute_write(self, task: WriteTask, async_session_maker, Paper, select) -> bool:
        """执行单次写入"""
        try:
            logger.info(f"🔧 开始数据库写入: paper_id={task.paper_id}")
            async with async_session_maker() as db:
                # 查询论文
                logger.debug(f"查询论文: paper_id={task.paper_id}")
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

                # 更新扩展字段
                if task.tier:
                    paper.tier = task.tier
                if task.summary:
                    paper.summary = task.summary
                if task.action_items:
                    paper.action_items = task.action_items
                if task.knowledge_links:
                    paper.knowledge_links = task.knowledge_links
                if task.tags:
                    paper.tags = task.tags
                if task.md_output_path:
                    paper.md_output_path = task.md_output_path
                if task.full_analysis is not None:
                    paper.full_analysis = task.full_analysis
                if task.analysis_mode:
                    paper.analysis_mode = task.analysis_mode

                # 提交
                logger.debug(f"准备提交: paper_id={task.paper_id}")
                await db.commit()
                logger.info(f"✅ 数据库写入成功: paper_id={task.paper_id}")
                return True

        except Exception as e:
            logger.error(f"数据库写入失败: {e}", exc_info=True)
            return False

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            "write_count": self._write_count,
            "error_count": self._error_count,
            "queue_size": self._queue.qsize() if self._queue else 0,
        }

    def stop(self):
        """停止服务"""
        self._running = False
        logger.info("写入服务已停止")


# 全局实例
db_write_service = DatabaseWriteService()