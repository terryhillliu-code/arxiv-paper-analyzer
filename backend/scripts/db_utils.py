#!/usr/bin/env python3
"""
数据库工具函数
用途：为 KarpathyVault 数据库脚本提供共享工具
"""

from pathlib import Path
import hashlib
import time
import sqlite3
from typing import Callable, Optional

# 常量
DB_PATH = Path.home() / "arxiv-paper-analyzer/backend/data/papers.db"
KARPATHY_VAULT = Path.home() / "KarpathyVault"
ZHIWEI_VAULT = Path.home() / "Documents" / "ZhiweiVault"


def get_db_checksum(db_path: Path = DB_PATH) -> str:
    """分块计算 SHA256 checksum，避免大文件内存问题

    Args:
        db_path: 数据库文件路径

    Returns:
        SHA256 hexdigest 字符串
    """
    sha256 = hashlib.sha256()
    with open(db_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def with_retry(func: Callable, max_retries: int = 3, delay: float = 0.5) -> any:
    """SQLite 锁冲突重试（指数退避）

    Args:
        func: 要执行的函数
        max_retries: 最大重试次数
        delay: 初始延迟秒数

    Returns:
        函数执行结果

    Raises:
        sqlite3.OperationalError: 重试耗尽后仍锁定
    """
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            raise


def validate_path(path: str, allowed_prefixes: Optional[list[str]] = None) -> bool:
    """路径安全验证，防止路径遍历攻击

    Args:
        path: 待验证路径
        allowed_prefixes: 允许的路径前缀列表

    Returns:
        是否在允许范围内
    """
    if allowed_prefixes is None:
        allowed_prefixes = [
            str(KARPATHY_VAULT),
            str(ZHIWEI_VAULT),
        ]
    abs_path = str(Path(path).resolve())
    return any(abs_path.startswith(prefix) for prefix in allowed_prefixes)