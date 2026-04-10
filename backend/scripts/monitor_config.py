"""监控面板配置。

集中管理数据库路径、告警阈值等配置项。
"""

from pathlib import Path

# ============================================================
# 路径配置
# ============================================================

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# 数据库路径
TASKS_DB_PATH = DATA_DIR / "tasks.db"
PAPERS_DB_PATH = DATA_DIR / "papers.db"
QUALITY_DB_PATH = DATA_DIR / "quality_issues.db"
HEAL_HISTORY_DB_PATH = DATA_DIR / "heal_history.db"

# 静态文件目录
STATIC_DIR = BASE_DIR / "static" / "monitor"

# 日志目录
LOG_DIR = BASE_DIR / "logs"

# ============================================================
# 告警阈值配置
# ============================================================

class AlertThresholds:
    """告警阈值配置"""

    # 任务相关
    FAILED_TASKS_WARNING = 10  # 失败任务数警告阈值
    TIMEOUT_TASKS_WARNING = 1  # 超时任务数警告阈值
    PENDING_TASKS_WARNING = 100  # 待处理任务数警告阈值

    # 质量相关
    QUALITY_ISSUES_WARNING = 100  # 质量问题数警告阈值

    # 资源相关
    CPU_PERCENT_WARNING = 70
    CPU_PERCENT_ERROR = 90
    MEMORY_PERCENT_WARNING = 85
    MEMORY_PERCENT_ERROR = 95
    DISK_PERCENT_WARNING = 80
    DISK_PERCENT_ERROR = 90

    # Worker 相关
    MIN_WORKERS = 1  # 最少 Worker 数量

# ============================================================
# 数据保留配置
# ============================================================

METRICS_RETENTION_DAYS = 7  # 指标数据保留天数

# ============================================================
# 采集配置
# ============================================================

METRICS_COLLECT_INTERVAL = 60  # 指标采集间隔（秒）
DASHBOARD_REFRESH_INTERVAL = 10  # 前端刷新间隔（秒）