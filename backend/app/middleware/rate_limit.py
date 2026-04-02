"""速率限制中间件。

简单的内存速率限制实现，适用于单实例部署。
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件。

    基于客户端 IP 的速率限制。
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_limit: int = 10,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_limit = burst_limit

        # 存储请求记录: {ip: {"minute": [(timestamp,)], "hour": [(timestamp,)]}}
        self.request_records = defaultdict(lambda: {"minute": [], "hour": []})

        # 排除的路径（健康检查等）
        self.exempt_paths = {"/health", "/", "/favicon.ico"}

    def get_client_ip(self, request: Request) -> str:
        """获取客户端 IP"""
        # 优先使用 X-Forwarded-For（代理场景）
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # 使用直接连接 IP
        if request.client:
            return request.client.host

        return "unknown"

    def cleanup_old_records(self, ip: str):
        """清理过期记录"""
        now = time.time()

        # 清理超过 1 分钟的记录
        self.request_records[ip]["minute"] = [
            t for t in self.request_records[ip]["minute"]
            if now - t < 60
        ]

        # 清理超过 1 小时的记录
        self.request_records[ip]["hour"] = [
            t for t in self.request_records[ip]["hour"]
            if now - t < 3600
        ]

    def check_rate_limit(self, ip: str) -> tuple[bool, str]:
        """检查是否超过速率限制

        Returns:
            (is_allowed, reason)
        """
        now = time.time()
        self.cleanup_old_records(ip)

        # 检查突发限制（10 秒内）
        recent_burst = [t for t in self.request_records[ip]["minute"] if now - t < 10]
        if len(recent_burst) >= self.burst_limit:
            return False, f"突发请求过多，请稍后再试（限制: {self.burst_limit}/10秒）"

        # 检查每分钟限制
        if len(self.request_records[ip]["minute"]) >= self.requests_per_minute:
            return False, f"请求过于频繁，请稍后再试（限制: {self.requests_per_minute}/分钟）"

        # 检查每小时限制
        if len(self.request_records[ip]["hour"]) >= self.requests_per_hour:
            return False, f"已达到小时请求限制（限制: {self.requests_per_hour}/小时）"

        return True, ""

    async def dispatch(self, request: Request, call_next: Callable):
        """处理请求"""

        # 排除健康检查等路径
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        # 排除静态文件
        if request.url.path.startswith("/static"):
            return await call_next(request)

        # 获取客户端 IP
        client_ip = self.get_client_ip(request)

        # 检查速率限制
        is_allowed, reason = self.check_rate_limit(client_ip)

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁",
                    "reason": reason,
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        # 记录请求
        now = time.time()
        self.request_records[client_ip]["minute"].append(now)
        self.request_records[client_ip]["hour"].append(now)

        # 继续处理请求
        return await call_next(request)


# 速率限制装饰器（可选，用于特定路由）
def rate_limit(requests: int = 10, window: int = 60):
    """速率限制装饰器

    Args:
        requests: 允许的请求数
        window: 时间窗口（秒）
    """
    from functools import wraps
    from fastapi import Request

    records = defaultdict(list)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # 获取 request 对象
            req = request or next((a for a in args if isinstance(a, Request)), None)
            if not req:
                return await func(*args, **kwargs)

            client_ip = req.client.host if req.client else "unknown"
            now = time.time()

            # 清理过期记录
            records[client_ip] = [t for t in records[client_ip] if now - t < window]

            # 检查限制
            if len(records[client_ip]) >= requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁，{window}秒内最多 {requests} 次请求",
                )

            # 记录请求
            records[client_ip].append(now)

            return await func(*args, **kwargs)

        return wrapper

    return decorator