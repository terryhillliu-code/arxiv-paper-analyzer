"""基于 SQLite 的简单任务队列。

支持任务的创建、查询、更新，适合单机部署场景。
优化：使用线程局部连接池减少连接开销，启用 WAL 模式提高并发。
"""

import asyncio
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from app.utils.resource_monitor import resource_monitor, is_safe_to_process

logger = logging.getLogger(__name__)

# 任务数据库路径
TASK_DB_PATH = Path(__file__).parent.parent.parent / "data" / "tasks.db"

# 线程局部连接池，减少频繁创建连接的开销
_thread_local = threading.local()

# 重试延迟配置（秒）
RETRY_DELAYS = {
    "rate_limit": 60.0,   # Rate Limit (429) 用长延迟
    "network": 10.0,      # 网络错误用短延迟
    "timeout": 10.0,      # 超时错误用短延迟
}


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """获取线程局部的数据库连接。

    每个线程使用独立的持久连接，减少连接创建开销。
    启用 WAL 模式提高并发性能。
    """
    if not hasattr(_thread_local, 'connections'):
        _thread_local.connections = {}

    key = str(db_path)
    if key not in _thread_local.connections:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        # 启用 WAL 模式，提高并发读写性能
        conn.execute("PRAGMA journal_mode=WAL")
        # 设置锁等待超时（5秒），避免锁竞争立即失败
        conn.execute("PRAGMA busy_timeout=5000")
        # 启用同步写入，保证数据安全
        conn.execute("PRAGMA synchronous=NORMAL")
        # 增大缓存，减少磁盘 IO
        conn.execute("PRAGMA cache_size=10000")
        # 自动 checkpoint 阈值（1000页）
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        _thread_local.connections[key] = conn
        logger.debug(f"创建新数据库连接: {key}")

    return _thread_local.connections[key]


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

    # 任务超时配置
    DEFAULT_TASK_TIMEOUT = 600  # 默认 10 分钟超时
    TASK_TIMEOUTS = {
        "analysis": 600,       # 论文分析任务 10 分钟
        "batch_analysis": 300, # 批量分析任务 5 分钟（5 篇论文并行，实际 <60s）
        "video_analysis": 180, # 视频分析任务 3 分钟（转录稿较短）
        "summary": 300,        # 摘要任务 5 分钟
        "fetch": 300,          # 抓取任务 5 分钟
        "pdf_download": 180,   # PDF 下载任务 3 分钟
    }

    def __init__(self, db_path: Path = TASK_DB_PATH, max_concurrent: int = 6):
        self.db_path = db_path
        self._ensure_db()
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)  # 全局并发限制
        self._active_tasks: set = set()  # 活跃任务追踪
        logger.info(f"任务队列初始化，最大并发: {max_concurrent}")

        # 自动注册已知处理器
        self._auto_register_handlers()

    def _auto_register_handlers(self):
        """自动注册已知任务处理器"""
        try:
            from app.tasks.analysis_task import AnalysisTaskHandler
            self._handlers["analysis"] = AnalysisTaskHandler.handle
            self._handlers["force_refresh"] = AnalysisTaskHandler.handle  # force_refresh 使用 analysis 的 handler
            logger.info("自动注册任务处理器: analysis, force_refresh")
        except ImportError:
            pass

        try:
            from app.tasks.pdf_download_task import PDFDownloadTaskHandler
            self._handlers["pdf_download"] = PDFDownloadTaskHandler.handle
            logger.info("自动注册任务处理器: pdf_download")
        except ImportError:
            pass

        try:
            from app.tasks.video_analysis_task import VideoAnalysisTaskHandler
            self._handlers["video_analysis"] = VideoAnalysisTaskHandler.handle
            logger.info("自动注册任务处理器: video_analysis")
        except ImportError:
            pass

    def _ensure_db(self):
        """确保数据库表存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = _get_connection(self.db_path)
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

        conn = _get_connection(self.db_path)
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

        logger.info(f"创建任务: {task_id} ({task_type})")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务详情"""
        conn = _get_connection(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = cursor.fetchone()

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

        conn = _get_connection(self.db_path)
        conn.execute(sql, params)
        conn.commit()

        logger.debug(f"更新任务 {task_id}: {updates}")

    def get_pending_tasks(self, limit: int = 10, task_type: str = None) -> list[Task]:
        """获取待处理的任务，优先处理 force_refresh 任务

        Args:
            limit: 最大返回数量
            task_type: 可选，只返回指定类型的任务
        """
        conn = _get_connection(self.db_path)

        if task_type:
            # 只获取指定类型的任务
            cursor = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'pending' AND task_type = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (task_type, limit),
            )
        else:
            # 获取所有类型，优先处理 batch_analysis 任务（效率最高）
            cursor = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'pending'
                ORDER BY
                    CASE
                        WHEN task_type = 'batch_analysis' THEN 0
                        WHEN task_type = 'force_refresh' THEN 1
                        ELSE 2
                    END,
                    created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()

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

        # 获取任务超时时间
        timeout = self.TASK_TIMEOUTS.get(task.task_type, self.DEFAULT_TASK_TIMEOUT)

        # 任务重试配置
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                # 更新处理进度
                if attempt > 0:
                    self.update_task(task.id, message=f"重试处理 (尝试 {attempt + 1}/{max_retries + 1})...")

                # 执行处理器（带超时）
                try:
                    result = await asyncio.wait_for(
                        handler(task, self),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(f"任务执行超时（超过 {timeout} 秒）")

                # 标记完成
                self.update_task(
                    task.id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    result=result,
                    message="处理完成",
                )

                # 任务完成后短暂休息
                status = resource_monitor.check_resources()
                if status.memory_percent > 90 or status.cpu_percent > 90:
                    await asyncio.sleep(1.0)

                return  # 成功，退出重试循环

            except TimeoutError as e:
                logger.error(f"任务 {task.id} 超时: {e}")
                if attempt < max_retries:
                    # 超时错误使用较短延迟
                    retry_delay = RETRY_DELAYS["timeout"]
                    logger.info(f"任务 {task.id} 将在 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.update_task(
                        task.id,
                        status=TaskStatus.FAILED,
                        error=f"任务超时，已重试 {max_retries} 次: {e}",
                    )

            except Exception as e:
                error_msg = str(e)
                logger.error(f"任务 {task.id} 失败: {e}", exc_info=True)

                # 根据错误类型选择重试延迟
                is_rate_limit = "429" in error_msg or "rate limit" in error_msg.lower()
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    'connection', 'network', 'timeout', 'refused', 'reset',
                    'broken pipe', 'api', 'http'
                ])

                if (is_rate_limit or is_network_error) and attempt < max_retries:
                    # Rate Limit 用长延迟，网络错误用短延迟
                    retry_delay = RETRY_DELAYS["rate_limit"] if is_rate_limit else RETRY_DELAYS["network"]
                    logger.info(f"{is_rate_limit and 'Rate Limit' or '网络错误'}，任务 {task.id} 将在 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.update_task(
                        task.id,
                        status=TaskStatus.FAILED,
                        error=f"任务失败: {error_msg}",
                    )
                    return

    async def run_worker(self, poll_interval: float = 2.0, task_type: str = None):
        """运行工作循环

        Args:
            poll_interval: 轮询间隔（秒）
            task_type: 可选，只处理指定类型的任务
        """
        self._running = True
        self._task_type_filter = task_type

        # 启动时恢复 stuck 任务
        self._recover_stuck_tasks()

        logger.info("任务队列工作器启动")
        if task_type:
            logger.info(f"只处理任务类型: {task_type}")

        # 活跃任务集合
        active_tasks = set()

        # 动态轮询间隔
        current_poll_interval = poll_interval
        idle_count = 0

        while self._running:
            try:
                # 清理已完成的任务
                done_tasks = [t for t in active_tasks if t.done()]
                for t in done_tasks:
                    active_tasks.discard(t)
                    try:
                        await t
                    except Exception as e:
                        logger.debug(f"任务异常: {e}")

                # 如果有可用槽位，启动新任务（批量获取）
                available_slots = self._semaphore._value if hasattr(self._semaphore, '_value') else 3
                needed = available_slots - len(active_tasks)
                if needed > 0:
                    # 批量获取任务，而不是逐个获取
                    tasks = self.get_pending_tasks(limit=min(needed, 5), task_type=self._task_type_filter)
                    for task in tasks:
                        # 立即更新状态为 running，防止重复处理
                        self.update_task(task.id, status=TaskStatus.RUNNING, message="开始处理...")

                        # 创建任务并添加到活跃集合
                        task_coro = self._process_task_internal(task)
                        active_tasks.add(asyncio.create_task(task_coro))

                    # 有任务处理时，缩短轮询间隔
                    if tasks:
                        current_poll_interval = 0.5
                        idle_count = 0

                # 如果没有活跃任务且没有待处理任务，等待
                if not active_tasks:
                    idle_count += 1
                    # 空闲时逐渐延长轮询间隔（最大 5 秒）
                    current_poll_interval = min(poll_interval + idle_count * 0.5, 5.0)
                    await asyncio.sleep(current_poll_interval)
                else:
                    # 短暂等待，避免忙等待
                    await asyncio.sleep(0.5)

                # 定期检查资源状态
                status = resource_monitor.check_resources()
                if status.warning and not status.is_safe:
                    logger.info(f"资源紧张: {status.warning}")
                    await asyncio.sleep(5.0)

            except Exception as e:
                logger.error(f"工作循环错误: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)

    async def _process_task_internal(self, task: Task):
        """内部任务处理方法"""
        async with self._semaphore:
            self._active_tasks.add(task.id)
            try:
                handler = self._handlers.get(task.task_type)
                if not handler:
                    self.update_task(
                        task.id,
                        status=TaskStatus.FAILED,
                        error=f"未知的任务类型: {task.task_type}",
                    )
                    return

                await self._execute_task(task, handler)
            finally:
                self._active_tasks.discard(task.id)

    def _recover_stuck_tasks(self):
        """恢复卡住的任务。

        将超时的 running 任务重置为 pending，使其可以重新处理。
        """
        # 超过 30 分钟的任务视为卡住
        stuck_threshold = (datetime.now() - timedelta(minutes=30)).isoformat()

        conn = _get_connection(self.db_path)
        cursor = conn.cursor()

        # 查找卡住的任务
        cursor.execute('''
            SELECT id, task_type, started_at FROM tasks
            WHERE status = 'running' AND started_at < ?
        ''', (stuck_threshold,))

        stuck_tasks = cursor.fetchall()

        if stuck_tasks:
            logger.warning(f"发现 {len(stuck_tasks)} 个卡住的任务，正在恢复...")

            # 重置为 pending
            cursor.execute('''
                UPDATE tasks SET
                    status = 'pending',
                    progress = 0,
                    started_at = NULL,
                    message = '系统恢复：重新处理'
                WHERE status = 'running' AND started_at < ?
            ''', (stuck_threshold,))

            conn.commit()

            for task_id, task_type, started_at in stuck_tasks:
                logger.info(f"已恢复任务: {task_id} ({task_type})")

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