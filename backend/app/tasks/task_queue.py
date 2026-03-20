"""基于 SQLite 的简单任务队列。

支持任务的创建、查询、更新，适合单机部署场景。
"""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from app.utils.resource_monitor import resource_monitor, is_safe_to_process

logger = logging.getLogger(__name__)

# 任务数据库路径
TASK_DB_PATH = Path(__file__).parent.parent.parent / "data" / "tasks.db"


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"  # 等待处理
    RUNNING = "running"  # 正在处理
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


@dataclass
class Task:
    """任务对象"""

    id: str
    task_type: str
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "task_type": self.task_type,
            "payload": self.payload,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskQueue:
    """任务队列管理器"""

    def __init__(self, db_path: Path = TASK_DB_PATH, max_concurrent: int = 6):
        self.db_path = db_path
        self._ensure_db()
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)  # 全局并发限制
        self._active_tasks: set = set()  # 活跃任务追踪
        logger.info(f"任务队列初始化，最大并发: {max_concurrent}")

    def _ensure_db(self):
        """确保数据库表存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                result TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def register_handler(self, task_type: str, handler: Callable):
        """注册任务处理器"""
        self._handlers[task_type] = handler
        logger.info(f"注册任务处理器: {task_type}")

    def create_task(self, task_type: str, payload: Dict[str, Any]) -> Task:
        """创建新任务"""
        import uuid

        task_id = str(uuid.uuid4())[:8]
        task = Task(
            id=task_id,
            task_type=task_type,
            payload=payload,
            created_at=datetime.now(),
        )

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO tasks (id, task_type, payload, status, progress, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.task_type,
                json.dumps(task.payload),
                task.status.value,
                task.progress,
                task.message,
                task.created_at.isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        logger.info(f"创建任务: {task_id} ({task_type})")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Task(
            id=row[0],
            task_type=row[1],
            payload=json.loads(row[2]),
            status=TaskStatus(row[3]),
            progress=row[4],
            message=row[5],
            result=json.loads(row[6]) if row[6] else None,
            error=row[7],
            created_at=datetime.fromisoformat(row[8]) if row[8] else None,
            started_at=datetime.fromisoformat(row[9]) if row[9] else None,
            completed_at=datetime.fromisoformat(row[10]) if row[10] else None,
        )

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """更新任务状态"""
        task = self.get_task(task_id)
        if not task:
            return

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status.value)

            if status == TaskStatus.RUNNING:
                updates.append("started_at = ?")
                params.append(datetime.now().isoformat())
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)

        if message is not None:
            updates.append("message = ?")
            params.append(message)

        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))

        if error is not None:
            updates.append("error = ?")
            params.append(error)

        if not updates:
            return

        params.append(task_id)
        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"

        conn = sqlite3.connect(self.db_path)
        conn.execute(sql, params)
        conn.commit()
        conn.close()

        logger.debug(f"更新任务 {task_id}: {updates}")

    def get_pending_tasks(self, limit: int = 10) -> list[Task]:
        """获取待处理的任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for row in rows:
            tasks.append(
                Task(
                    id=row[0],
                    task_type=row[1],
                    payload=json.loads(row[2]),
                    status=TaskStatus(row[3]),
                    progress=row[4],
                    message=row[5],
                    result=json.loads(row[6]) if row[6] else None,
                    error=row[7],
                    created_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    started_at=datetime.fromisoformat(row[9]) if row[9] else None,
                    completed_at=datetime.fromisoformat(row[10]) if row[10] else None,
                )
            )
        return tasks

    async def process_task(self, task: Task):
        """处理单个任务（带并发控制）"""
        handler = self._handlers.get(task.task_type)
        if not handler:
            self.update_task(
                task.id,
                status=TaskStatus.FAILED,
                error=f"未知的任务类型: {task.task_type}",
            )
            return

        # 使用 Semaphore 限制并发
        async with self._semaphore:
            self._active_tasks.add(task.id)
            try:
                await self._execute_task(task, handler)
            finally:
                self._active_tasks.discard(task.id)

    async def _execute_task(self, task: Task, handler: Callable):
        """执行任务的内部逻辑"""
        # 检查系统资源
        status = resource_monitor.check_resources()
        logger.info(f"系统资源状态: {resource_monitor.get_status_string()}")

        if not status.is_safe:
            # 等待资源可用
            self.update_task(
                task.id,
                message=f"等待系统资源: {status.warning}",
            )
            safe = await resource_monitor.wait_for_resources(max_wait=60.0)
            if not safe:
                self.update_task(
                    task.id,
                    status=TaskStatus.FAILED,
                    error=f"系统资源不足: {status.warning}",
                )
                return

        try:
            # 标记为运行中
            self.update_task(task.id, status=TaskStatus.RUNNING, message="开始处理...")

            # 执行处理器
            result = await handler(task, self)

            # 标记完成
            self.update_task(
                task.id,
                status=TaskStatus.COMPLETED,
                progress=100,
                result=result,
                message="处理完成",
            )

            # 任务完成后短暂休息（激进策略）
            status = resource_monitor.check_resources()
            if status.memory_percent > 90 or status.cpu_percent > 90:
                await asyncio.sleep(1.0)  # 资源极紧张
            # else: 不休息

        except Exception as e:
            logger.error(f"任务 {task.id} 失败: {e}", exc_info=True)
            self.update_task(
                task.id,
                status=TaskStatus.FAILED,
                error=str(e),
            )

    async def run_worker(self, poll_interval: float = 2.0):
        """运行工作循环"""
        self._running = True
        logger.info("任务队列工作器启动")

        while self._running:
            try:
                # 获取待处理任务
                tasks = self.get_pending_tasks(limit=1)

                if tasks:
                    # 处理一个任务
                    await self.process_task(tasks[0])
                else:
                    # 无任务时等待
                    await asyncio.sleep(poll_interval)

                # 定期检查资源状态
                status = resource_monitor.check_resources()
                if status.warning:
                    logger.warning(f"资源警告: {status.warning}")
                    # 如果资源紧张，增加休息时间
                    if not status.is_safe:
                        logger.info("资源紧张，等待恢复...")
                        await asyncio.sleep(10.0)

            except Exception as e:
                logger.error(f"工作循环错误: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)

    def stop(self):
        """停止工作循环"""
        self._running = False
        logger.info("任务队列工作器停止")

    def get_active_count(self) -> int:
        """获取当前活跃任务数"""
        return len(self._active_tasks)

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        pending = len(self.get_pending_tasks(limit=1000))
        return {
            "pending": pending,
            "active": len(self._active_tasks),
            "max_concurrent": self._semaphore._value if hasattr(self._semaphore, '_value') else 3,
        }


# 全局实例
task_queue = TaskQueue()