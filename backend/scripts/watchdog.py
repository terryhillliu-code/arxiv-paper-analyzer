#!/usr/bin/env python3
"""Watchdog - 监控自愈服务健康状态。

每5分钟检查：
1. auto_heal 心跳文件是否更新（应在60秒内）
2. auto_heal 进程是否运行
3. launchd 服务状态

如果检测失败，自动重启服务。
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 配置
HEARTBEAT_FILE = Path(__file__).parent.parent / "data" / "auto_heal.heartbeat"
AUTO_HEAL_LOG = Path.home() / "logs" / "arxiv-auto-heal.log"
SERVICE_NAME = "com.arxiv.auto-heal"
MAX_HEARTBEAT_AGE = 120  # 秒，超过此时间认为心跳丢失

logger = None


def setup_logging():
    """设置日志"""
    import logging
    global logger
    logger = logging.getLogger("watchdog")
    logger.setLevel(logging.INFO)

    # 写入日志文件
    log_file = Path.home() / "logs" / "arxiv-watchdog.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(log_file)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(fh)

    # 也输出到控制台
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(ch)


def check_heartbeat() -> dict:
    """检查心跳文件"""
    result = {
        "status": "unknown",
        "last_heartbeat": None,
        "age_seconds": None,
        "message": ""
    }

    if not HEARTBEAT_FILE.exists():
        result["status"] = "missing"
        result["message"] = "心跳文件不存在"
        return result

    try:
        # 心跳文件是纯文本时间戳
        heartbeat_content = HEARTBEAT_FILE.read_text().strip()
        last_heartbeat = datetime.fromisoformat(heartbeat_content)
        age = (datetime.now() - last_heartbeat).total_seconds()

        result["last_heartbeat"] = heartbeat_content
        result["age_seconds"] = age

        if age > MAX_HEARTBEAT_AGE:
            result["status"] = "stale"
            result["message"] = f"心跳过期 ({age:.0f}秒)"
        else:
            result["status"] = "ok"
            result["message"] = f"心跳正常 ({age:.0f}秒前)"

    except Exception as e:
        result["status"] = "error"
        result["message"] = f"心跳检查失败: {e}"

    return result


def check_process_running() -> dict:
    """检查 auto_heal 进程是否运行"""
    result = {
        "status": "unknown",
        "pid": None,
        "message": ""
    }

    try:
        # 查找 auto_heal 进程
        cmd = ["pgrep", "-f", "auto_heal.py"]
        output = subprocess.run(cmd, capture_output=True, text=True)

        if output.returncode == 0 and output.stdout.strip():
            pids = output.stdout.strip().split('\n')
            result["status"] = "ok"
            result["pid"] = pids[0]  # 主进程PID
            result["message"] = f"进程运行中 (PID: {result['pid']})"
        else:
            result["status"] = "not_running"
            result["message"] = "进程未运行"

    except Exception as e:
        result["status"] = "error"
        result["message"] = f"进程检查失败: {e}"

    return result


def check_launchd_service() -> dict:
    """检查 launchd 服务状态"""
    result = {
        "status": "unknown",
        "message": ""
    }

    try:
        cmd = ["launchctl", "list", SERVICE_NAME]
        output = subprocess.run(cmd, capture_output=True, text=True)

        if output.returncode == 0:
            # 解析输出格式: {"PID" = "49763"; ...}
            content = output.stdout
            # 检查是否有 PID 字段且不为空
            pid_match = re.search(r'"PID"\s*=\s*(\d+)', content)
            if pid_match:
                pid = pid_match.group(1)
                result["status"] = "ok"
                result["message"] = f"服务运行中 (PID: {pid})"
            else:
                # PID 不存在，服务已加载但未运行
                result["status"] = "loaded_but_stopped"
                result["message"] = "服务已加载但未运行"
        else:
            result["status"] = "not_loaded"
            result["message"] = "服务未加载"

    except Exception as e:
        result["status"] = "error"
        result["message"] = f"launchd检查失败: {e}"

    return result


def restart_service() -> bool:
    """重启 auto_heal 服务"""
    try:
        # 先停止
        subprocess.run(["launchctl", "stop", SERVICE_NAME], check=False)
        logger.info("已停止 auto_heal 服务")

        # 等待进程完全退出
        import time
        time.sleep(2)

        # 清理可能的残留进程
        subprocess.run(["pkill", "-f", "auto_heal.py"], check=False)

        # 清理心跳文件，强制重新创建
        if HEARTBEAT_FILE.exists():
            HEARTBEAT_FILE.unlink()

        # 启动服务
        subprocess.run(["launchctl", "start", SERVICE_NAME], check=False)
        logger.info("已启动 auto_heal 服务")

        return True

    except Exception as e:
        logger.error(f"重启服务失败: {e}")
        return False


def run_check():
    """执行健康检查"""
    setup_logging()

    logger.info("=" * 50)
    logger.info("Watchdog 健康检查开始")
    logger.info("=" * 50)

    issues = []

    # 1. 检查心跳
    heartbeat_result = check_heartbeat()
    logger.info(f"心跳检查: {heartbeat_result['message']}")
    if heartbeat_result["status"] not in ["ok"]:
        issues.append(("heartbeat", heartbeat_result))

    # 2. 检查进程
    process_result = check_process_running()
    logger.info(f"进程检查: {process_result['message']}")
    if process_result["status"] not in ["ok"]:
        issues.append(("process", process_result))

    # 3. 检查 launchd 服务
    service_result = check_launchd_service()
    logger.info(f"服务检查: {service_result['message']}")
    if service_result["status"] not in ["ok"]:
        issues.append(("service", service_result))

    # 如果有问题，尝试重启
    if issues:
        logger.warning(f"发现 {len(issues)} 个问题")
        for issue_type, result in issues:
            logger.warning(f"  - {issue_type}: {result['message']}")

        logger.info("尝试重启 auto_heal 服务...")
        if restart_service():
            logger.info("重启成功")
        else:
            logger.error("重启失败，需要人工干预")
    else:
        logger.info("所有检查通过，auto_heal 服务正常")

    logger.info("=" * 50)
    logger.info("Watchdog 健康检查完成")
    logger.info("=" * 50)

    return len(issues) == 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watchdog - 监控自愈服务")
    parser.add_argument("--once", action="store_true", help="只检查一次")
    args = parser.parse_args()

    if args.once:
        success = run_check()
        sys.exit(0 if success else 1)
    else:
        # 持续监控模式（不推荐，应使用 launchd 定时运行）
        print("持续监控模式不推荐，请使用 launchd 定时运行: --once")
        sys.exit(1)
