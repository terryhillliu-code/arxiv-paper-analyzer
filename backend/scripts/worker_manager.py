#!/usr/bin/env python3
"""Worker统一管理脚本。

功能:
1. 启动/停止/重启所有Worker
2. 防止重复启动（PID锁）
3. 自动清理卡住的任务
4. 状态监控

用法:
    python scripts/worker_manager.py start      # 启动所有Worker
    python scripts/worker_manager.py stop       # 停止所有Worker
    python scripts/worker_manager.py restart    # 重启所有Worker
    python scripts/worker_manager.py status     # 查看状态
    python scripts/worker_manager.py cleanup    # 清理卡住任务
"""

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Worker配置
WORKERS = {
    "task_worker": {
        "script": "scripts/task_worker.py",
        "concurrent": 8,
        "log": "task_worker.log",
    },
    "pdf_worker": {
        "script": "scripts/pdf_worker.py",
        "concurrent": 4,
        "log": "pdf_worker.log",
    },
}

# 超时配置（秒）
TIMEOUTS = {
    "analysis": 400,
    "force_refresh": 400,
    "pdf_download": 150,
}


def get_pid(worker_name: str) -> int | None:
    """获取Worker的PID"""
    pid_file = DATA_DIR / f"{worker_name}.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            # 检查进程是否存在
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)
    return None


def is_running(worker_name: str) -> bool:
    """检查Worker是否运行中"""
    # 检查PID文件
    pid = get_pid(worker_name)
    if pid:
        return True

    # 检查进程
    result = subprocess.run(
        ["pgrep", "-f", f"{worker_name}.py"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0 and result.stdout.strip()


def start_worker(worker_name: str) -> bool:
    """启动单个Worker"""
    if is_running(worker_name):
        print(f"  ⚠️ {worker_name} 已在运行中")
        return False

    config = WORKERS[worker_name]
    script = BASE_DIR / config["script"]
    concurrent = config["concurrent"]
    log_file = LOG_DIR / config["log"]

    # 启动进程
    cmd = [
        sys.executable,
        str(script),
        "--concurrent", str(concurrent),
    ]

    with open(log_file, "a") as log:
        process = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            cwd=BASE_DIR,
            start_new_session=True,
        )

    # 写入PID文件
    pid_file = DATA_DIR / f"{worker_name}.pid"
    pid_file.write_text(str(process.pid))

    print(f"  ✅ {worker_name} 已启动 (PID: {process.pid}, 并发: {concurrent})")
    return True


def stop_worker(worker_name: str) -> bool:
    """停止单个Worker"""
    pid = get_pid(worker_name)
    if not pid:
        # 尝试用pgrep查找
        result = subprocess.run(
            ["pgrep", "-f", f"{worker_name}.py"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split()[0])
        else:
            print(f"  ⚠️ {worker_name} 未运行")
            return False

    try:
        # 先发送SIGTERM
        os.kill(pid, signal.SIGTERM)

        # 等待进程结束
        for _ in range(10):
            try:
                os.kill(pid, 0)
                import time
                time.sleep(0.5)
            except OSError:
                break
        else:
            # 强制终止
            os.kill(pid, signal.SIGKILL)

        print(f"  ✅ {worker_name} 已停止 (PID: {pid})")
    except OSError:
        print(f"  ⚠️ {worker_name} 进程不存在")

    # 清理PID文件
    pid_file = DATA_DIR / f"{worker_name}.pid"
    pid_file.unlink(missing_ok=True)
    return True


def cleanup_stuck_tasks():
    """清理卡住的任务"""
    conn = sqlite3.connect(DATA_DIR / "tasks.db")
    cursor = conn.cursor()

    # 按任务类型检测卡住任务
    recovered = 0
    now = datetime.now()

    for task_type, timeout in TIMEOUTS.items():
        threshold = (now - timedelta(seconds=timeout + 30)).isoformat()
        cursor.execute('''
            SELECT COUNT(*) FROM tasks
            WHERE status = 'running' AND task_type = ? AND started_at < ?
        ''', (task_type, threshold))
        count = cursor.fetchone()[0]

        if count > 0:
            cursor.execute('''
                UPDATE tasks SET
                    status = 'pending',
                    started_at = NULL,
                    message = '系统恢复：任务超时自动重置'
                WHERE status = 'running' AND task_type = ? AND started_at < ?
            ''', (task_type, threshold))
            print(f"  ⚠️ 重置 {count} 个卡住的 {task_type} 任务")
            recovered += count

    conn.commit()
    conn.close()

    if recovered == 0:
        print("  ✅ 无卡住任务")
    else:
        print(f"  ✅ 共重置 {recovered} 个任务")

    return recovered


def show_status():
    """显示系统状态"""
    print("=" * 60)
    print("ArXiv论文分析系统 - Worker状态")
    print("=" * 60)

    # Worker状态
    print("\n📦 Worker进程:")
    for name in WORKERS:
        pid = get_pid(name)
        if pid:
            config = WORKERS[name]
            print(f"  ✅ {name}: 运行中 (PID: {pid}, 并发: {config['concurrent']})")
        else:
            print(f"  ❌ {name}: 未运行")

    # 任务队列状态
    print("\n📊 任务队列:")
    conn = sqlite3.connect(DATA_DIR / "tasks.db")

    for task_type in ["analysis", "pdf_download", "force_refresh"]:
        pending = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE task_type=? AND status="pending"',
            (task_type,)
        ).fetchone()[0]

        running = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE task_type=? AND status="running"',
            (task_type,)
        ).fetchone()[0]

        completed = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE task_type=? AND status="completed"',
            (task_type,)
        ).fetchone()[0]

        deferred = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE task_type=? AND status="deferred"',
            (task_type,)
        ).fetchone()[0] if task_type == "force_refresh" else 0

        status = f"待处理={pending}, 运行中={running}, 已完成={completed}"
        if deferred:
            status += f", 暂停={deferred}"
        print(f"  {task_type}: {status}")

    conn.close()

    # 最近速度
    print("\n⚡ 处理速度:")
    conn = sqlite3.connect(DATA_DIR / "tasks.db")
    five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
    completed_5min = conn.execute(
        'SELECT COUNT(*) FROM tasks WHERE status="completed" AND completed_at > ?',
        (five_min_ago,)
    ).fetchone()[0]
    conn.close()

    speed = completed_5min / 5 if completed_5min > 0 else 0
    print(f"  最近5分钟: {completed_5min}个 ({speed:.1f}个/分钟)")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Worker管理脚本")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "cleanup"])
    args = parser.parse_args()

    if args.action == "status":
        show_status()
    elif args.action == "cleanup":
        print("清理卡住任务...")
        cleanup_stuck_tasks()
    elif args.action == "start":
        print("启动所有Worker...")
        for name in WORKERS:
            start_worker(name)
        print("\n✅ 启动完成")
    elif args.action == "stop":
        print("停止所有Worker...")
        for name in WORKERS:
            stop_worker(name)
        print("\n✅ 停止完成")
    elif args.action == "restart":
        print("重启所有Worker...")
        for name in WORKERS:
            stop_worker(name)
        print()
        import time
        time.sleep(2)
        for name in WORKERS:
            start_worker(name)
        print("\n✅ 重启完成")


if __name__ == "__main__":
    main()