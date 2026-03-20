"""任务相关 API 路由。

提供异步任务的创建、查询、管理接口。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.tasks import task_queue, TaskStatus
from app.tasks.analysis_task import register_analysis_handler
from app.utils.resource_monitor import resource_monitor

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# 注册任务处理器
register_analysis_handler(task_queue)


class CreateAnalysisTaskRequest(BaseModel):
    """创建分析任务请求"""

    paper_id: int
    use_mineru: bool = True
    force_refresh: bool = False


class TaskResponse(BaseModel):
    """任务响应"""

    id: str
    task_type: str
    status: str
    progress: int
    message: str
    error: str | None = None
    result: dict | None = None

    class Config:
        from_attributes = True


@router.post("/analysis", response_model=TaskResponse)
async def create_analysis_task(request: CreateAnalysisTaskRequest):
    """创建论文分析任务

    立即返回任务 ID，分析在后台进行。
    前端可以轮询 /api/tasks/{task_id} 获取进度。
    """
    task = task_queue.create_task(
        task_type="analysis",
        payload={
            "paper_id": request.paper_id,
            "use_mineru": request.use_mineru,
            "force_refresh": request.force_refresh,
        },
    )

    # 立即开始处理（在后台）
    import asyncio

    asyncio.create_task(task_queue.process_task(task))

    return TaskResponse(
        id=task.id,
        task_type=task.task_type,
        status=task.status.value,
        progress=task.progress,
        message=task.message,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """获取任务状态

    前端可以定期调用此接口获取任务进度。
    """
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskResponse(
        id=task.id,
        task_type=task.task_type,
        status=task.status.value,
        progress=task.progress,
        message=task.message,
        error=task.error,
        result=task.result,
    )


@router.get("/")
async def list_tasks(
    status: str | None = Query(None, description="筛选状态"),
    limit: int = Query(20, ge=1, le=100),
):
    """列出任务"""
    # 简化实现：只返回最近的任务
    import sqlite3
    from app.tasks.task_queue import TASK_DB_PATH

    conn = sqlite3.connect(TASK_DB_PATH)

    if status:
        cursor = conn.execute(
            """
            SELECT id, task_type, status, progress, message, created_at
            FROM tasks
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, limit),
        )
    else:
        cursor = conn.execute(
            """
            SELECT id, task_type, status, progress, message, created_at
            FROM tasks
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    rows = cursor.fetchall()
    conn.close()

    return {
        "tasks": [
            {
                "id": row[0],
                "task_type": row[1],
                "status": row[2],
                "progress": row[3],
                "message": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]
    }


@router.get("/resources/status")
async def get_system_resources():
    """获取系统资源状态

    用于监控系统资源使用情况，防止过热和资源不足。
    """
    status = resource_monitor.check_resources()

    return {
        "cpu_percent": round(status.cpu_percent, 1),
        "memory_percent": round(status.memory_percent, 1),
        "memory_used_gb": round(status.memory_used_gb, 2),
        "memory_total_gb": round(status.memory_total_gb, 2),
        "temperature": round(status.temperature, 1) if status.temperature else None,
        "is_safe": status.is_safe,
        "warning": status.warning,
        "status_string": resource_monitor.get_status_string(),
        "queue": task_queue.get_queue_status(),
    }