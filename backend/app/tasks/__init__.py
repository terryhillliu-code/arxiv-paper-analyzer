"""后台任务模块。

提供异步任务处理能力，避免阻塞 API 响应。
"""

from .task_queue import task_queue, TaskStatus
from .analysis_task import AnalysisTaskHandler

__all__ = ["task_queue", "TaskStatus", "AnalysisTaskHandler"]