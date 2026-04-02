"""API 认证中间件。

简单的 Token 认证实现，保护关键端点。
"""

import os
import secrets
from typing import Optional
from functools import wraps

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# 从环境变量读取 API Token
API_TOKEN = os.getenv("API_TOKEN", "")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"

# 需要认证的端点前缀
PROTECTED_PATHS = [
    "/api/fetch",
    "/api/papers/generate",
    "/api/papers/*/analyze",
    "/api/tasks",
]

# 只读端点（不需要认证）
READ_ONLY_PATHS = [
    "/health",
    "/",
    "/api/papers",  # GET 请求
    "/api/tags",
    "/api/categories",
    "/api/stats",
]


security = HTTPBearer(auto_error=False)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
    """验证 API Token

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        True if valid

    Raises:
        HTTPException: 401 if invalid or missing
    """
    if not AUTH_ENABLED:
        return True

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="缺少认证 Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 使用 secrets.compare_digest 防止时序攻击
    if not API_TOKEN or not secrets.compare_digest(token, API_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="无效的 API Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True


def generate_token() -> str:
    """生成安全的 API Token

    Returns:
        32 字节的十六进制 token
    """
    return secrets.token_hex(32)


class AuthMiddleware:
    """认证中间件。

    基于路径的认证检查。
    """

    def __init__(self):
        self.auth_enabled = AUTH_ENABLED
        self.api_token = API_TOKEN

    def is_protected_path(self, path: str, method: str) -> bool:
        """检查路径是否需要认证

        Args:
            path: 请求路径
            method: HTTP 方法

        Returns:
            True if authentication required
        """
        if not self.auth_enabled:
            return False

        # GET 请求到只读端点不需要认证
        if method == "GET":
            for read_path in READ_ONLY_PATHS:
                if path.startswith(read_path.replace("*", "")):
                    return False
            # 其他 GET 请求需要认证
            return True

        # POST, PUT, DELETE 等写操作需要认证
        for protected in PROTECTED_PATHS:
            # 处理通配符
            pattern = protected.replace("*", "")
            if path.startswith(pattern):
                return True

        return False

    async def __call__(self, request: Request, call_next):
        """处理请求"""

        # 检查是否需要认证
        if self.is_protected_path(request.url.path, request.method):
            # 获取 Authorization header
            auth_header = request.headers.get("Authorization", "")

            if not auth_header.startswith("Bearer "):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "需要 API Token 认证",
                        "hint": "请在 Authorization header 中提供 Bearer token",
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )

            token = auth_header[7:]  # 移除 "Bearer " 前缀

            # 验证 token
            if not self.api_token or not secrets.compare_digest(token, self.api_token):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "无效的 API Token",
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # 继续处理请求
        return await call_next(request)


# 依赖注入版本（用于路由装饰器）
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """获取当前用户（基于 Token）

    用于路由级别的认证。
    """
    if not AUTH_ENABLED:
        return "anonymous"

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="未认证",
        )

    token = credentials.credentials

    if not API_TOKEN or not secrets.compare_digest(token, API_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="无效的 Token",
        )

    return "authenticated_user"


def require_auth(func):
    """认证装饰器

    用于保护特定路由。
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if AUTH_ENABLED:
            # 检查是否有认证信息
            request = kwargs.get("request")
            if request:
                auth_header = request.headers.get("Authorization", "")
                if not auth_header.startswith("Bearer "):
                    raise HTTPException(401, "需要认证")

                token = auth_header[7:]
                if not API_TOKEN or not secrets.compare_digest(token, API_TOKEN):
                    raise HTTPException(401, "无效的 Token")

        return await func(*args, **kwargs)

    return wrapper


if __name__ == "__main__":
    # 生成新 token 的命令行工具
    print("生成新的 API Token:")
    print(generate_token())
    print("\n请将此 token 设置到环境变量 API_TOKEN 中")