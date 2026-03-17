"""FastAPI 应用入口模块。

配置应用生命周期、中间件和路由。
"""

import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.routers import papers

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    启动时初始化资源和数据库，关闭时清理资源。
    """
    # 启动时
    logger.info("应用启动中...")

    settings = get_settings()

    # 创建数据目录
    pdf_storage_path = Path(settings.pdf_storage_path)
    pdf_storage_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"PDF 存储目录: {pdf_storage_path}")

    # 初始化数据库
    await init_db()
    logger.info("数据库初始化完成")

    yield

    # 关闭时
    logger.info("应用关闭中...")


# 创建 FastAPI 实例
app = FastAPI(
    title="ArXiv论文智能分析平台",
    description="基于 Claude AI 的 ArXiv 论文智能分析与管理系统",
    version="1.0.0",
    lifespan=lifespan,
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "*",  # 允许所有来源（生产环境应限制）
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(papers.router)


# 全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器。

    捕获所有未处理的异常，返回友好的 JSON 错误信息。
    """
    logger.error(f"未处理的异常: {exc}\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "error": str(exc),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理器。

    处理 HTTP 异常，返回标准化的 JSON 错误响应。
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path),
        },
    )


@app.get("/", tags=["root"])
async def root() -> dict:
    """根路由。

    返回欢迎信息和 API 文档链接。
    """
    return {
        "message": "欢迎使用 ArXiv 论文智能分析平台",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """健康检查端点。

    用于检测服务是否正常运行。
    """
    return {"status": "ok"}