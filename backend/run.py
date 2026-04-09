"""应用启动脚本。

使用 uvicorn 启动 FastAPI 服务。
"""

import os
import socket
import sys
import signal
import uvicorn

# 从环境变量读取配置，默认绑定 localhost（安全）
PORT = int(os.getenv("API_PORT", "8000"))
HOST = os.getenv("API_HOST", "127.0.0.1")
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: int = 10) -> bool:
    """等待端口释放"""
    import time
    start = time.time()
    while time.time() - start < timeout:
        if not is_port_in_use(port, host):
            return True
        print(f"端口 {port} 被占用，等待中...")
        time.sleep(1)
    return False


def graceful_shutdown(signum, frame):
    """优雅关闭"""
    print("\n正在关闭服务...")
    sys.exit(0)


if __name__ == "__main__":
    # 注册信号处理
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    # 检查端口
    if is_port_in_use(PORT, HOST):
        print(f"⚠️ 端口 {PORT} 已被占用")
        if not wait_for_port(PORT, HOST, timeout=5):
            print(f"❌ 端口 {PORT} 释放超时，退出")
            sys.exit(1)
        print(f"✅ 端口 {PORT} 已释放")

    print(f"🚀 启动服务: http://{HOST}:{PORT} (DEV_MODE={DEV_MODE})")
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=DEV_MODE,
    )