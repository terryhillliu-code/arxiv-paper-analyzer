#!/usr/bin/env python3
"""系统统一配置。

所有超时阈值、并发配置统一管理，避免配置分散不一致。
"""

# ===== 任务超时配置 =====
# 执行超时：asyncio.wait_for() 的超时时间
# 自愈检查超时：auto_heal.py 检查 running 任务的超时阈值
# 恢复超时：Worker 重启后恢复卡住任务的阈值

TASK_TIMEOUTS = {
    "analysis": {
        "execute": 500,      # 推理模型需要更长超时（秒）
        "heal_check": 600,   # 自愈检查超时（秒）
        "recover": 720,      # Worker重启恢复超时（秒）
    },
    "force_refresh": {
        "execute": 500,
        "heal_check": 600,
        "recover": 720,
    },
    "pdf_download": {
        "execute": 150,      # 必须大于 pdf_service.DOWNLOAD_TIMEOUT (120秒)
        "heal_check": 180,
        "recover": 300,
    },
    "summary": {
        "execute": 300,
        "heal_check": 400,
        "recover": 600,
    },
    "fetch": {
        "execute": 300,
        "heal_check": 400,
        "recover": 600,
    },
}

# 默认超时（未配置的任务类型使用）
DEFAULT_TIMEOUT = {
    "execute": 400,
    "heal_check": 500,
    "recover": 600,
}


# ===== 并发配置 =====
CONCURRENT_CONFIG = {
    "task_worker": 8,    # task_worker 默认并发数
    "pdf_worker": 4,     # pdf_worker 默认并发数
}


# ===== 资源阈值 =====
RESOURCE_THRESHOLDS = {
    "cpu_warning": 90,        # CPU 告警阈值 (%)
    "cpu_critical": 95,       # CPU 严重告警阈值 (%)
    "memory_warning": 90,     # 内存告警阈值 (%)
    "memory_critical": 95,    # 内存严重告警阈值 (%)
    "disk_warning": 80,       # 磁盘告警阈值 (%)
}


# ===== 自愈配置 =====
AUTO_HEAL_CONFIG = {
    "check_interval": 60,           # 自愈检查间隔（秒）
    "max_consecutive_errors": 5,    # 最大连续错误次数
    "max_retries_per_task": 3,      # 单任务最大重试次数
    "alert_cooldown_minutes": 30,   # 告警冷却时间（分钟）
}


# ===== PDF配置 =====
PDF_CONFIG = {
    "download_timeout": 120,   # PDF 下载超时（秒）
    "max_retries": 3,          # 下载重试次数
}


def get_timeout(task_type: str, timeout_type: str = "execute") -> int:
    """获取指定任务类型的超时配置。

    Args:
        task_type: 任务类型
        timeout_type: 超时类型 (execute/heal_check/recover)

    Returns:
        超时秒数
    """
    config = TASK_TIMEOUTS.get(task_type, DEFAULT_TIMEOUT)
    return config.get(timeout_type, DEFAULT_TIMEOUT[timeout_type])