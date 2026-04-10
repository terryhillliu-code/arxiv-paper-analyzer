#!/usr/bin/env python3
"""论文分析系统进程管理器。

使用PID文件锁，确保单实例运行。
提供统一启动、停止、状态检查入口。
"""

import fcntl
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psutil

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 配置
CONFIG = {
    "backend_path": Path(__file__).parent.parent,
    "pid_dir": Path(__file__).parent.parent / "logs",
    "task_worker_concurrent": 8,
    "pdf_worker_concurrent": 4,
    "check_interval": 30,  # 监护检查间隔
    "stuck_threshold": 300,  # 任务卡住阈值（秒）
}

# PID文件路径
PID_FILES = {
    "manager": CONFIG["pid_dir"] / "paper_manager.pid",
    "task_worker": CONFIG["pid_dir"] / "task_worker.pid",
    "pdf_worker": CONFIG["pid_dir"] / "pdf_worker.pid",
}


class ProcessManager:
    """进程管理器"""

    def __init__(self):
        self.pid_dir = CONFIG["pid_dir"]
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        self.manager_pid_file = PID_FILES["manager"]
        self.running = True
        self._lock_file = None

    def acquire_lock(self) -> bool:
        """获取进程锁，确保单实例"""
        try:
            self._lock_file = open(self.manager_pid_file, 'w')
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.write(str(os.getpid()))
            self._lock_file.flush()
            return True
        except (IOError, BlockingIOError):
            if self._lock_file:
                self._lock_file.close()
            return False

    def release_lock(self):
        """释放进程锁"""
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self.manager_pid_file.unlink(missing_ok=True)
            except:
                pass

    def is_process_running(self, pid: int) -> bool:
        """检查进程是否运行"""
        try:
            return psutil.Process(pid).is_running()
        except psutil.NoSuchProcess:
            return False

    def read_pid(self, name: str) -> Optional[int]:
        """读取PID文件"""
        pid_file = PID_FILES.get(name)
        if not pid_file or not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text().strip())
        except:
            return None

    def write_pid(self, name: str, pid: int):
        """写入PID文件"""
        pid_file = PID_FILES.get(name)
        if pid_file:
            pid_file.write_text(str(pid))

    def clear_pid(self, name: str):
        """清除PID文件"""
        pid_file = PID_FILES.get(name)
        if pid_file:
            pid_file.unlink(missing_ok=True)

    def start_worker(self, name: str, script: str, concurrent: int) -> Optional[int]:
        """启动Worker进程"""
        # 检查是否已运行
        existing_pid = self.read_pid(name)
        if existing_pid and self.is_process_running(existing_pid):
            logger.info(f"{name} 已运行 (PID: {existing_pid})")
            return existing_pid

        # 启动新进程
        cmd = [
            sys.executable,
            str(CONFIG["backend_path"] / script),
            "--concurrent", str(concurrent),
        ]

        log_file = CONFIG["pid_dir"] / f"{name}.log"
        with open(log_file, 'w') as log:
            proc = psutil.Popen(
                cmd,
                stdout=log,
                stderr=log,
                cwd=str(CONFIG["backend_path"]),
                start_new_session=True,
            )

        self.write_pid(name, proc.pid)
        logger.info(f"启动 {name} (PID: {proc.pid})")
        return proc.pid

    def stop_worker(self, name: str) -> bool:
        """停止Worker进程"""
        pid = self.read_pid(name)
        if not pid:
            logger.info(f"{name} 未运行")
            return True

        try:
            proc = psutil.Process(pid)
            proc.terminate()

            # 等待进程结束
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

            logger.info(f"停止 {name} (PID: {pid})")
        except psutil.NoSuchProcess:
            logger.info(f"{name} 进程不存在")
        finally:
            self.clear_pid(name)

        return True

    def stop_all(self):
        """停止所有Worker"""
        self.stop_worker("task_worker")
        self.stop_worker("pdf_worker")
        self.release_lock()

    def check_stuck_tasks(self) -> int:
        """检查并重置卡住的任务"""
        try:
            conn = sqlite3.connect(str(CONFIG["backend_path"] / "data" / "tasks.db"))
            c = conn.cursor()

            threshold = (datetime.now() - timedelta(seconds=CONFIG["stuck_threshold"])).isoformat()
            c.execute('''
                UPDATE tasks
                SET status = 'pending', started_at = NULL, progress = 0
                WHERE status = 'running' AND started_at < ?
            ''', (threshold,))
            count = c.rowcount
            conn.commit()
            conn.close()

            if count > 0:
                logger.info(f"重置 {count} 个卡住的任务")

            return count
        except Exception as e:
            logger.error(f"检查卡住任务失败: {e}")
            return 0

    def get_status(self) -> dict:
        """获取系统状态"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "workers": {},
            "tasks": {},
            "papers": {},
        }

        # Worker状态
        for name in ["task_worker", "pdf_worker"]:
            pid = self.read_pid(name)
            running = pid and self.is_process_running(pid)
            status["workers"][name] = {
                "pid": pid,
                "running": running,
            }

        # 任务状态
        try:
            conn = sqlite3.connect(str(CONFIG["backend_path"] / "data" / "tasks.db"))
            c = conn.cursor()
            c.execute('SELECT status, COUNT(*) FROM tasks WHERE task_type = "analysis" GROUP BY status')
            status["tasks"] = dict(c.fetchall())
            conn.close()
        except:
            pass

        # 论文状态
        try:
            conn = sqlite3.connect(str(CONFIG["backend_path"] / "data" / "papers.db"))
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM papers WHERE has_analysis = 1')
            status["papers"]["analyzed"] = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL')
            status["papers"]["has_pdf"] = c.fetchone()[0]
            conn.close()
        except:
            pass

        return status

    def health_check(self) -> dict:
        """健康检查并自动修复"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "issues": [],
            "fixed": [],
        }

        # 检查Worker是否运行
        for name in ["task_worker", "pdf_worker"]:
            pid = self.read_pid(name)
            if not pid or not self.is_process_running(pid):
                report["issues"].append(f"{name} not running")
                # 自动重启
                script = f"scripts/{name}.py"
                concurrent = CONFIG[f"{name}_concurrent"]
                self.start_worker(name, script, concurrent)
                report["fixed"].append(f"restarted {name}")

        # 检查卡住任务
        stuck = self.check_stuck_tasks()
        if stuck > 0:
            report["issues"].append(f"{stuck} stuck tasks")
            report["fixed"].append("reset stuck tasks")

        return report

    def run(self):
        """运行管理器（监护模式）"""
        if not self.acquire_lock():
            logger.error("另一个实例正在运行")
            sys.exit(1)

        logger.info("=" * 60)
        logger.info("进程管理器启动")
        logger.info("=" * 60)

        # 启动Workers
        self.start_worker("task_worker", "scripts/task_worker.py", CONFIG["task_worker_concurrent"])
        self.start_worker("pdf_worker", "scripts/pdf_worker.py", CONFIG["pdf_worker_concurrent"])

        # 注册退出处理
        def signal_handler(signum, frame):
            logger.info("收到停止信号")
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # 监护循环
        try:
            while self.running:
                time.sleep(CONFIG["check_interval"])

                # 健康检查
                report = self.health_check()

                # 打印状态
                status = self.get_status()
                papers = status.get("papers", {})
                logger.info(
                    f"进度: 已分析 {papers.get('analyzed', 0)}, "
                    f"PDF {papers.get('has_pdf', 0)} | "
                    f"任务: {status.get('tasks', {})}"
                )

                if report["issues"]:
                    logger.warning(f"问题: {report['issues']}, 已修复: {report['fixed']}")

        finally:
            self.stop_all()
            logger.info("进程管理器已停止")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="论文分析系统进程管理器")
    parser.add_argument("action", choices=["start", "stop", "status", "check", "run"])
    args = parser.parse_args()

    manager = ProcessManager()

    if args.action == "start":
        if not manager.acquire_lock():
            print("错误: 另一个实例正在运行")
            sys.exit(1)
        manager.start_worker("task_worker", "scripts/task_worker.py", CONFIG["task_worker_concurrent"])
        manager.start_worker("pdf_worker", "scripts/pdf_worker.py", CONFIG["pdf_worker_concurrent"])
        print("Workers已启动")
        manager.release_lock()

    elif args.action == "stop":
        manager.stop_all()
        print("所有进程已停止")

    elif args.action == "status":
        status = manager.get_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.action == "check":
        report = manager.health_check()
        print(json.dumps(report, indent=2, default=str))

    elif args.action == "run":
        manager.run()


if __name__ == "__main__":
    main()