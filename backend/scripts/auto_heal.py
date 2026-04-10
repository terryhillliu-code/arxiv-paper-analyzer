#!/usr/bin/env python3
"""ArXiv系统自愈监控服务。

常驻运行，自动检测问题并修复。
每60秒检查一次，发现问题自动处理。

功能:
1. 自动检测并修复常见问题
2. 记录自愈历史，便于分析趋势
3. 系统健康评分
4. 严重问题告警通知
"""

import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 配置
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志 - 简化配置，依赖launchd stdout重定向
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger(__name__)

# 全局标志
_shutdown = False

# 导入统一配置
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.task_timeouts import TASK_TIMEOUTS, RESOURCE_THRESHOLDS, AUTO_HEAL_CONFIG

# 阈值配置（使用统一配置）
THRESHOLDS = {
    "task_timeout_seconds": {
        "analysis": TASK_TIMEOUTS["analysis"]["heal_check"],
        "force_refresh": TASK_TIMEOUTS["force_refresh"]["heal_check"],
        "pdf_download": TASK_TIMEOUTS["pdf_download"]["heal_check"],
    },
    "max_failed_tasks": 50,  # 失败任务超过50个告警
    "max_pdf_sync_diff": 10,  # PDF同步差异超过10个自动修复
    "min_running_tasks": 2,  # 最少运行任务数
    "max_quality_issues": 3000,  # 质量问题上限
    "max_pending_tasks": 5000,  # 任务积压预警阈值
    "max_retries_per_task": AUTO_HEAL_CONFIG["max_retries_per_task"],
    "cpu_threshold": RESOURCE_THRESHOLDS["cpu_warning"],
    "memory_threshold": RESOURCE_THRESHOLDS["memory_warning"],
    "disk_threshold": RESOURCE_THRESHOLDS["disk_warning"],
    "expected_concurrent": 12,  # 预期并发任务数(task_worker=8 + pdf_worker=4)
    "api_rate_limit_pause": AUTO_HEAL_CONFIG["alert_cooldown_minutes"] * 60,
    "max_log_size_mb": 50,
    "max_log_age_days": 30,
    "min_process_rate": 50,
    "health_report_interval_hours": 6,
}

# 告警配置
ALERT_CONFIG = {
    "feishu_webhook": os.environ.get("FEISHU_WEBHOOK", ""),
    "dingtalk_webhook": os.environ.get("DINGTALK_WEBHOOK", ""),
    "alert_cooldown_minutes": 30,  # 同类告警冷却时间
}


def init_heal_history_db():
    """初始化自愈历史数据库"""
    db_path = DATA_DIR / "heal_history.db"
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS heal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            description TEXT,
            details TEXT,
            health_score INTEGER
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT,
            notified INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def record_heal_event(event_type: str, description: str, details: dict = None, health_score: int = 0):
    """记录自愈事件"""
    db_path = DATA_DIR / "heal_history.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO heal_events (timestamp, event_type, description, details, health_score) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), event_type, description, json.dumps(details) if details else None, health_score)
    )
    conn.commit()
    conn.close()


def get_recent_heal_stats(hours: int = 24) -> dict:
    """获取最近N小时的自愈统计"""
    db_path = DATA_DIR / "heal_history.db"
    if not db_path.exists():
        return {"total": 0, "by_type": {}}

    conn = sqlite3.connect(db_path)
    threshold = (datetime.now() - timedelta(hours=hours)).isoformat()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM heal_events WHERE timestamp > ?", (threshold,))
    total = c.fetchone()[0]

    c.execute("SELECT event_type, COUNT(*) FROM heal_events WHERE timestamp > ? GROUP BY event_type", (threshold,))
    by_type = {row[0]: row[1] for row in c.fetchall()}

    conn.close()
    return {"total": total, "by_type": by_type}


def calculate_health_score(report: dict) -> int:
    """计算系统健康评分 (0-100)

    评分规则:
    - 基础分100
    - Worker停止: -20/个
    - 任务超时: -5/个
    - 失败任务过多: -10
    - 资源过载(CPU>90%或内存>90%): -15
    - 任务积压(>5000): -10
    - PDF断链: -3/个
    - API限流: -10
    """
    score = 100

    # Worker状态
    if report.get("workers"):
        score -= len(report["workers"].get("stopped", [])) * 20

    # 任务状态
    if report.get("tasks"):
        score -= len(report["tasks"].get("stuck", [])) * 5
        if report["tasks"].get("failed", 0) > THRESHOLDS["max_failed_tasks"]:
            score -= 10

    # 资源状态
    if report.get("resources"):
        if report["resources"].get("cpu", 0) > THRESHOLDS["cpu_threshold"]:
            score -= 15
        if report["resources"].get("memory", 0) > THRESHOLDS["memory_threshold"]:
            score -= 15

    # 任务积压
    if report.get("backlog"):
        if report["backlog"].get("pending", 0) > THRESHOLDS["max_pending_tasks"]:
            score -= 10

    # PDF断链
    if report.get("pdf"):
        score -= report["pdf"].get("broken_links", 0) * 3

    # API限流
    if report.get("api_status"):
        if report["api_status"].get("rate_limited", False):
            score -= 10

    return max(0, min(100, score))


def send_alert(message: str, alert_type: str = "warning"):
    """发送告警通知"""
    import urllib.request

    # 检查冷却时间
    db_path = DATA_DIR / "heal_history.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        threshold = (datetime.now() - timedelta(minutes=ALERT_CONFIG["alert_cooldown_minutes"])).isoformat()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM alerts WHERE alert_type=? AND timestamp > ? AND notified=1",
                  (alert_type, threshold))
        if c.fetchone()[0] > 0:
            logger.debug(f"告警冷却中: {alert_type}")
            conn.close()
            return
        conn.close()

    sent = False

    # 飞书通知
    if ALERT_CONFIG["feishu_webhook"]:
        try:
            data = json.dumps({
                "msg_type": "text",
                "content": {"text": f"⚠️ ArXiv系统告警\n{message}"}
            }).encode('utf-8')
            req = urllib.request.Request(
                ALERT_CONFIG["feishu_webhook"],
                data=data,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"已发送飞书告警: {alert_type}")
            sent = True
        except Exception as e:
            logger.warning(f"飞书告警发送失败: {e}")

    # 钉钉通知
    if ALERT_CONFIG["dingtalk_webhook"]:
        try:
            data = json.dumps({
                "msgtype": "text",
                "text": {"content": f"⚠️ ArXiv系统告警\n{message}"}
            }).encode('utf-8')
            req = urllib.request.Request(
                ALERT_CONFIG["dingtalk_webhook"],
                data=data,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"已发送钉钉告警: {alert_type}")
            sent = True
        except Exception as e:
            logger.warning(f"钉钉告警发送失败: {e}")

    # 记录告警
    if sent:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO alerts (timestamp, alert_type, message, notified) VALUES (?, ?, ?, 1)",
            (datetime.now().isoformat(), alert_type, message)
        )
        conn.commit()
        conn.close()


class SystemMonitor:
    """系统监控器"""

    def __init__(self):
        self.last_check = None
        self.consecutive_errors = 0
        self.heal_count = 0

    def check_workers(self) -> dict:
        """检查Worker进程状态"""
        result = {"running": [], "stopped": [], "issues": []}

        # 检查task_worker
        task_worker_running = False
        pdf_worker_running = False

        try:
            r = subprocess.run(
                ["pgrep", "-f", "task_worker.py"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                pids = r.stdout.strip().split("\n")
                if len(pids) == 1:
                    task_worker_running = True
                    result["running"].append(f"task_worker(PID:{pids[0]})")
                else:
                    result["issues"].append(f"多个task_worker进程: {pids}")
        except Exception as e:
            result["issues"].append(f"task_worker检查失败: {e}")

        try:
            r = subprocess.run(
                ["pgrep", "-f", "pdf_worker.py"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                pids = r.stdout.strip().split("\n")
                if len(pids) == 1:
                    pdf_worker_running = True
                    result["running"].append(f"pdf_worker(PID:{pids[0]})")
                else:
                    result["issues"].append(f"多个pdf_worker进程: {pids}")
        except Exception as e:
            result["issues"].append(f"pdf_worker检查失败: {e}")

        if not task_worker_running:
            result["stopped"].append("task_worker")
        if not pdf_worker_running:
            result["stopped"].append("pdf_worker")

        return result

    def check_tasks(self) -> dict:
        """检查任务状态"""
        result = {"running": 0, "pending": 0, "failed": 0, "stuck": [], "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        now = datetime.now()

        # 统计
        result["running"] = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE status="running"'
        ).fetchone()[0]
        result["pending"] = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE status="pending"'
        ).fetchone()[0]
        result["failed"] = conn.execute(
            'SELECT COUNT(*) FROM tasks WHERE status="failed"'
        ).fetchone()[0]

        # 检查超时任务
        for row in conn.execute(
            'SELECT id, task_type, started_at FROM tasks WHERE status="running"'
        ):
            task_id, task_type, started_at = row
            elapsed = (now - datetime.fromisoformat(started_at)).total_seconds()
            timeout = THRESHOLDS["task_timeout_seconds"].get(task_type, 400)

            if elapsed > timeout:
                result["stuck"].append(
                    {"id": task_id, "type": task_type, "elapsed": int(elapsed)}
                )

        conn.close()

        # 检查问题
        if result["failed"] > THRESHOLDS["max_failed_tasks"]:
            result["issues"].append(f"失败任务过多: {result['failed']}个")

        if result["running"] < THRESHOLDS["min_running_tasks"] and result["pending"] > 100:
            result["issues"].append(
                f"运行任务过少({result['running']}), 但有大量待处理({result['pending']})"
            )

        return result

    def check_pdf_sync(self) -> dict:
        """检查PDF同步状态"""
        result = {"diff": 0, "broken_links": 0, "issues": []}

        pdf_dir = DATA_DIR / "pdfs"
        if not pdf_dir.exists():
            result["issues"].append("PDF目录不存在")
            return result

        conn = sqlite3.connect(DATA_DIR / "papers.db")

        # 统计实际文件
        actual_files = len(list(pdf_dir.glob("*.pdf")))

        # 统计数据库记录
        db_records = conn.execute(
            'SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL'
        ).fetchone()[0]

        result["diff"] = abs(actual_files - db_records)

        # 检查断链
        for row in conn.execute(
            'SELECT id, arxiv_id, pdf_local_path FROM papers WHERE pdf_local_path IS NOT NULL'
        ):
            paper_id, arxiv_id, path = row
            if path.startswith("data/"):
                full_path = BASE_DIR / path
            else:
                full_path = Path(path)
            if not full_path.exists():
                result["broken_links"] += 1

        conn.close()

        if result["diff"] > THRESHOLDS["max_pdf_sync_diff"]:
            result["issues"].append(f"PDF同步差异过大: {result['diff']}个")

        if result["broken_links"] > 0:
            result["issues"].append(f"断链: {result['broken_links']}个")

        return result

    def check_quality(self) -> dict:
        """检查质量问题"""
        result = {"unresolved": 0, "issues": []}

        db_path = DATA_DIR / "quality_issues.db"
        if not db_path.exists():
            return result

        conn = sqlite3.connect(db_path)
        result["unresolved"] = conn.execute(
            'SELECT COUNT(*) FROM quality_issues WHERE resolved=0'
        ).fetchone()[0]
        conn.close()

        if result["unresolved"] > THRESHOLDS["max_quality_issues"]:
            result["issues"].append(f"质量问题过多: {result['unresolved']}个")

        return result

    def check_database_health(self) -> dict:
        """检查数据库健康状态"""
        result = {"null_ids": 0, "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        null_ids = conn.execute("SELECT COUNT(*) FROM tasks WHERE id IS NULL").fetchone()[0]
        if null_ids > 0:
            result["null_ids"] = null_ids
            result["issues"].append(f"发现{null_ids}个id为NULL的任务")
            # 自动修复：删除无效任务
            conn.execute("DELETE FROM tasks WHERE id IS NULL")
            conn.commit()
            logger.info(f"已删除{null_ids}个id为NULL的任务")
        conn.close()

        return result

    def check_failed_tasks(self) -> dict:
        """检查失败任务，识别伪失败和需要重试的任务"""
        import json
        result = {"false_failed": 0, "needs_retry": 0, "issues": []}

        conn_t = sqlite3.connect(DATA_DIR / "tasks.db")
        conn_p = sqlite3.connect(DATA_DIR / "papers.db")

        # 检查pdf_download失败任务
        c_t = conn_t.cursor()
        c_t.execute('SELECT id, payload, error FROM tasks WHERE task_type="pdf_download" AND status="failed"')
        for row in c_t.fetchall():
            task_id, payload_str, error = row
            payload = json.loads(payload_str)
            paper_id = payload.get('paper_id')

            # 检查论文状态
            c_p = conn_p.cursor()
            c_p.execute('SELECT pdf_local_path FROM papers WHERE id=?', (paper_id,))
            paper_result = c_p.fetchone()

            if paper_result and paper_result[0]:
                # PDF已存在，伪失败
                result["false_failed"] += 1
            else:
                # PDF确实缺失，需要重试
                result["needs_retry"] += 1

        # 检查analysis失败任务
        c_t.execute('SELECT id, payload FROM tasks WHERE task_type IN ("analysis", "force_refresh") AND status="failed"')
        for row in c_t.fetchall():
            task_id, payload_str = row
            payload = json.loads(payload_str)
            paper_id = payload.get('paper_id')

            c_p = conn_p.cursor()
            c_p.execute('SELECT has_analysis FROM papers WHERE id=?', (paper_id,))
            paper_result = c_p.fetchone()

            if paper_result and paper_result[0]:
                # 已有分析，伪失败
                result["false_failed"] += 1
            else:
                # 无分析，需要重试
                result["needs_retry"] += 1

        conn_t.close()
        conn_p.close()

        if result["false_failed"] + result["needs_retry"] > 0:
            result["issues"].append(f"失败任务: {result['false_failed']}伪失败, {result['needs_retry']}需重试")

        return result

    def check_duplicate_tasks(self) -> dict:
        """检查重复任务"""
        result = {"duplicates": 0, "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")

        # 检查同一paper_id的重复pending任务
        c = conn.cursor()
        c.execute('''
            SELECT task_type, json_extract(payload, '$.paper_id'), COUNT(*) as cnt
            FROM tasks WHERE status IN ('pending', 'running')
            GROUP BY task_type, json_extract(payload, '$.paper_id')
            HAVING cnt > 1
        ''')
        duplicates = c.fetchall()
        result["duplicates"] = len(duplicates)

        if result["duplicates"] > 0:
            result["issues"].append(f"发现{result['duplicates']}组重复任务")

        conn.close()
        return result

    def heal_failed_tasks(self, false_failed: int, needs_retry: int) -> tuple:
        """修复失败任务"""
        import json
        deleted = 0
        reset = 0

        conn_t = sqlite3.connect(DATA_DIR / "tasks.db")
        conn_p = sqlite3.connect(DATA_DIR / "papers.db")

        # 处理pdf_download伪失败
        c_t = conn_t.cursor()
        c_t.execute('SELECT id, payload FROM tasks WHERE task_type="pdf_download" AND status="failed"')
        for row in c_t.fetchall():
            task_id, payload_str = row
            payload = json.loads(payload_str)
            paper_id = payload.get('paper_id')

            c_p = conn_p.cursor()
            c_p.execute('SELECT pdf_local_path FROM papers WHERE id=?', (paper_id,))
            paper_result = c_p.fetchone()

            if paper_result and paper_result[0]:
                # 删除伪失败任务
                conn_t.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                deleted += 1
                logger.info(f"删除伪失败PDF任务: {task_id[:8]}")
            else:
                # 重置为pending重试
                conn_t.execute('UPDATE tasks SET status="pending", error=NULL, message="自愈：重试" WHERE id=?', (task_id,))
                reset += 1
                logger.info(f"重置PDF下载任务: {task_id[:8]}")

        # 处理analysis伪失败
        c_t.execute('SELECT id, payload FROM tasks WHERE task_type IN ("analysis", "force_refresh") AND status="failed"')
        for row in c_t.fetchall():
            task_id, payload_str = row
            payload = json.loads(payload_str)
            paper_id = payload.get('paper_id')

            c_p = conn_p.cursor()
            c_p.execute('SELECT has_analysis FROM papers WHERE id=?', (paper_id,))
            paper_result = c_p.fetchone()

            if paper_result and paper_result[0]:
                conn_t.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                deleted += 1
                logger.info(f"删除伪失败分析任务: {task_id[:8]}")
            else:
                conn_t.execute('UPDATE tasks SET status="pending", error=NULL, message="自愈：重试" WHERE id=?', (task_id,))
                reset += 1
                logger.info(f"重置分析任务: {task_id[:8]}")

        conn_t.commit()
        conn_t.close()
        conn_p.close()

        if deleted + reset > 0:
            self.heal_count += deleted + reset

        return deleted, reset

    def heal_duplicate_tasks(self) -> int:
        """清理重复任务，保留最早的一个"""
        import json
        cleaned = 0

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        c = conn.cursor()

        # 找出重复任务组
        c.execute('''
            SELECT task_type, json_extract(payload, '$.paper_id'), MIN(id) as keep_id
            FROM tasks WHERE status IN ('pending', 'running')
            GROUP BY task_type, json_extract(payload, '$.paper_id')
            HAVING COUNT(*) > 1
        ''')
        duplicates = c.fetchall()

        for task_type, paper_id, keep_id in duplicates:
            # 删除除保留任务外的其他任务
            c.execute('''
                DELETE FROM tasks
                WHERE task_type=? AND status IN ('pending', 'running')
                AND json_extract(payload, '$.paper_id')=?
                AND id != ?
            ''', (task_type, paper_id, keep_id))
            removed = c.rowcount
            if removed > 0:
                cleaned += removed
                logger.info(f"清理重复任务: {task_type} paper_id={paper_id}, 删除{removed}个")

        conn.commit()
        conn.close()

        if cleaned > 0:
            self.heal_count += cleaned

        return cleaned

    def check_resources(self) -> dict:
        """检查系统资源状态"""
        result = {"cpu": 0, "memory": 0, "disk": 0, "issues": [], "overloaded": False}

        try:
            import psutil
            result["cpu"] = psutil.cpu_percent(interval=1)
            result["memory"] = psutil.virtual_memory().percent
            result["disk"] = psutil.disk_usage(BASE_DIR.parent).percent

            if result["cpu"] > THRESHOLDS["cpu_threshold"]:
                result["issues"].append(f"CPU过载: {result['cpu']}%")
                result["overloaded"] = True

            if result["memory"] > THRESHOLDS["memory_threshold"]:
                result["issues"].append(f"内存过载: {result['memory']}%")
                result["overloaded"] = True

            if result["disk"] > THRESHOLDS["disk_threshold"]:
                result["issues"].append(f"磁盘空间不足: {result['disk']}%")

        except ImportError:
            result["issues"].append("psutil未安装，无法监控资源")

        return result

    def check_concurrent_tasks(self) -> dict:
        """检查并发任务数是否合理"""
        result = {"running": 0, "expected": THRESHOLDS["expected_concurrent"], "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        result["running"] = conn.execute('SELECT COUNT(*) FROM tasks WHERE status="running"').fetchone()[0]
        conn.close()

        # 如果running任务远少于预期，可能Worker有问题
        if result["running"] < result["expected"] // 2 and result["running"] < THRESHOLDS["min_running_tasks"]:
            result["issues"].append(f"并发任务过少: {result['running']}/{result['expected']}")

        return result

    def check_task_backlog(self) -> dict:
        """检查任务积压情况"""
        result = {"pending": 0, "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        result["pending"] = conn.execute('SELECT COUNT(*) FROM tasks WHERE status="pending"').fetchone()[0]
        conn.close()

        if result["pending"] > THRESHOLDS["max_pending_tasks"]:
            result["issues"].append(f"任务积压严重: {result['pending']}个待处理")

        return result

    def check_repeated_timeout(self) -> dict:
        """检查反复超时任务（同一任务多次重置）"""
        result = {"repeated": 0, "tasks": [], "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        # 查找message中有多次"自愈"或"重置"的任务
        c = conn.cursor()
        c.execute('''
            SELECT id, task_type, message FROM tasks
            WHERE status IN ('pending', 'running')
            AND (message LIKE '%自愈%' OR message LIKE '%重试%' OR message LIKE '%超时%')
        ''')

        # 统计每个任务的重置次数（通过message中的关键词计数）
        for row in c.fetchall():
            task_id, task_type, message = row
            # 简单判断：如果message包含"自愈"，可能是第一次；如果包含"重试"多次，则是反复
            reset_count = message.count("重试") + message.count("重置")
            if reset_count >= THRESHOLDS["max_retries_per_task"]:
                result["tasks"].append({"id": task_id, "type": task_type, "count": reset_count})
                result["repeated"] += 1

        conn.close()

        if result["repeated"] > 0:
            result["issues"].append(f"发现{result['repeated']}个反复超时任务")

        return result

    def heal_repeated_timeout_tasks(self, tasks: list) -> int:
        """处理反复超时任务：标记为有问题，不再自动重试"""
        handled = 0

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        for task in tasks:
            # 将反复超时任务标记为failed，并记录原因
            conn.execute('''
                UPDATE tasks SET
                    status='failed',
                    error='反复超时，已超过最大重试次数，需人工检查',
                    message='自愈：标记为问题任务'
                WHERE id=?
            ''', (task["id"],))
            handled += 1
            logger.warning(f"标记反复超时任务: {task['id'][:8]} (重试{task['count']}次)")

        conn.commit()
        conn.close()

        if handled > 0:
            self.heal_count += handled

        return handled

    def check_api_rate_limit(self) -> dict:
        """检查API限流迹象"""
        result = {"rate_limited": False, "recent_429": 0, "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        c = conn.cursor()

        # 检查最近是否有429错误
        from datetime import datetime, timedelta
        threshold = (datetime.now() - timedelta(minutes=5)).isoformat()
        c.execute('''
            SELECT COUNT(*) FROM tasks
            WHERE status='failed'
            AND error LIKE '%429%'
            AND completed_at > ?
        ''', (threshold,))
        result["recent_429"] = c.fetchone()[0]

        conn.close()

        if result["recent_429"] >= 3:  # 5分钟内3次429认为被限流
            result["rate_limited"] = True
            result["issues"].append(f"API疑似限流: 近5分钟{result['recent_429']}次429错误")

        return result

    def heal_api_rate_limit(self) -> int:
        """API限流自愈：暂停pending任务处理"""
        paused = 0

        # 实际暂停由task_queue.py的resource_monitor处理
        # 这里只记录告警，不做实际操作
        logger.warning(f"API限流告警，建议等待{THRESHOLDS['api_rate_limit_pause']}秒后继续")
        return paused  # 返回0，实际暂停由其他机制处理

    def check_quality_repair_pipeline(self) -> dict:
        """检查质量问题修复链路是否完整"""
        result = {"unresolved_papers": 0, "missing_tasks": 0, "issues": []}

        quality_db = DATA_DIR / "quality_issues.db"
        if not quality_db.exists():
            return result

        conn_q = sqlite3.connect(quality_db)
        conn_p = sqlite3.connect(DATA_DIR / "papers.db")
        conn_t = sqlite3.connect(DATA_DIR / "tasks.db")

        c_q = conn_q.cursor()
        c_p = conn_p.cursor()
        c_t = conn_t.cursor()

        # 获取未解决的论文
        c_q.execute('SELECT DISTINCT arxiv_id FROM quality_issues WHERE resolved=0')
        unresolved_arxiv_ids = [row[0] for row in c_q.fetchall()]
        result["unresolved_papers"] = len(unresolved_arxiv_ids)

        # 检查是否有对应的force_refresh任务
        missing = 0
        for arxiv_id in unresolved_arxiv_ids[:100]:  # 只检查前100个，避免太慢
            c_p.execute('SELECT id FROM papers WHERE arxiv_id=?', (arxiv_id,))
            paper = c_p.fetchone()
            if not paper:
                continue
            paper_id = paper[0]

            # 检查是否有pending/running的force_refresh任务
            c_t.execute('''
                SELECT id FROM tasks
                WHERE task_type='force_refresh'
                AND status IN ('pending', 'running')
                AND json_extract(payload, '$.paper_id')=?
            ''', (paper_id,))
            if not c_t.fetchone():
                missing += 1

        result["missing_tasks"] = missing
        if missing > 5:
            result["issues"].append(f"{missing}篇问题论文缺少修复任务")

        conn_q.close()
        conn_p.close()
        conn_t.close()

        return result

    def heal_quality_repair_pipeline(self) -> int:
        """为缺少任务的问题论文创建force_refresh任务"""
        import uuid

        quality_db = DATA_DIR / "quality_issues.db"
        if not quality_db.exists():
            return 0

        conn_q = sqlite3.connect(quality_db)
        conn_p = sqlite3.connect(DATA_DIR / "papers.db")
        conn_t = sqlite3.connect(DATA_DIR / "tasks.db")

        c_q = conn_q.cursor()
        c_p = conn_p.cursor()
        c_t = conn_t.cursor()

        # 获取未解决的论文
        c_q.execute('SELECT DISTINCT arxiv_id FROM quality_issues WHERE resolved=0')
        unresolved_arxiv_ids = [row[0] for row in c_q.fetchall()]

        created = 0
        for arxiv_id in unresolved_arxiv_ids:
            # 获取paper_id
            c_p.execute('SELECT id FROM papers WHERE arxiv_id=?', (arxiv_id,))
            paper = c_p.fetchone()
            if not paper:
                continue
            paper_id = paper[0]

            # 检查是否已有任务
            c_t.execute('''
                SELECT id FROM tasks
                WHERE task_type='force_refresh'
                AND status IN ('pending', 'running')
                AND json_extract(payload, '$.paper_id')=?
            ''', (paper_id,))
            if c_t.fetchone():
                continue

            # 创建任务
            task_id = str(uuid.uuid4())[:8]
            payload = f'{{"paper_id": {paper_id}}}'
            c_t.execute('''
                INSERT INTO tasks (id, task_type, payload, status, created_at)
                VALUES (?, 'force_refresh', ?, 'pending', datetime('now'))
            ''', (task_id, payload))
            created += 1

        conn_t.commit()
        conn_q.close()
        conn_p.close()
        conn_t.close()

        if created > 0:
            self.heal_count += created
            logger.info(f"为{created}篇问题论文创建了修复任务")

        return created

    def check_database_integrity(self) -> dict:
        """检查数据库完整性"""
        result = {"corrupted": [], "issues": []}

        for db_name in ["tasks.db", "papers.db", "quality_issues.db"]:
            db_path = DATA_DIR / db_name
            if not db_path.exists():
                continue

            try:
                conn = sqlite3.connect(db_path)
                # 运行完整性检查
                c = conn.cursor()
                c.execute("PRAGMA integrity_check")
                check_result = c.fetchone()[0]
                if check_result != "ok":
                    result["corrupted"].append(db_name)
                    result["issues"].append(f"{db_name} 损坏: {check_result}")
                conn.close()
            except Exception as e:
                result["corrupted"].append(db_name)
                result["issues"].append(f"{db_name} 无法打开: {e}")

        return result

    def heal_database_integrity(self, corrupted: list) -> int:
        """修复损坏的数据库"""
        import shutil
        healed = 0

        for db_name in corrupted:
            db_path = DATA_DIR / db_name
            backup_path = DATA_DIR / f"{db_name}.bak"

            try:
                # 尝试导出并重建
                conn = sqlite3.connect(db_path)
                c = conn.cursor()

                # 获取所有表
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in c.fetchall()]

                # 创建备份
                shutil.copy(db_path, backup_path)
                logger.info(f"已备份损坏数据库: {db_name}")

                # 尝试修复：导出数据到新库
                new_db_path = DATA_DIR / f"{db_name}.new"
                new_conn = sqlite3.connect(new_db_path)

                for table in tables:
                    if table.startswith("sqlite_"):
                        continue
                    try:
                        # 获取表结构
                        c.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'")
                        create_sql = c.fetchone()[0]
                        if create_sql:
                            new_conn.execute(create_sql)

                            # 复制数据
                            rows = c.execute(f"SELECT * FROM {table}").fetchall()
                            if rows:
                                placeholders = ",".join(["?" for _ in rows[0]])
                                new_conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
                    except Exception as e:
                        logger.warning(f"修复表 {table} 失败: {e}")

                new_conn.commit()
                new_conn.close()
                conn.close()

                # 替换原文件
                db_path.unlink()
                new_db_path.rename(db_path)
                healed += 1
                logger.info(f"已修复数据库: {db_name}")

            except Exception as e:
                logger.error(f"修复数据库 {db_name} 失败: {e}")

        return healed

    def check_infinite_retry(self) -> dict:
        """检查无限重试的任务"""
        result = {"infinite_retry": [], "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        c = conn.cursor()

        # 查找重试次数过多的任务（通过message中的"自愈"计数）
        c.execute('''
            SELECT id, task_type, message, started_at
            FROM tasks
            WHERE status IN ('pending', 'running')
            AND (message LIKE '%自愈%' OR message LIKE '%重试%' OR message LIKE '%重置%')
        ''')

        for row in c.fetchall():
            task_id, task_type, message, started_at = row
            # 统计重试次数
            retry_count = message.count("自愈") + message.count("重试") + message.count("重置")
            if retry_count >= THRESHOLDS["max_retries_per_task"]:
                result["infinite_retry"].append({
                    "id": task_id,
                    "type": task_type,
                    "retry_count": retry_count
                })

        conn.close()

        if result["infinite_retry"]:
            result["issues"].append(f"发现{len(result['infinite_retry'])}个无限重试任务")

        return result

    def heal_infinite_retry(self, tasks: list) -> int:
        """处理无限重试任务"""
        healed = 0
        conn = sqlite3.connect(DATA_DIR / "tasks.db")

        for task in tasks:
            # 标记为失败，停止重试
            conn.execute('''
                UPDATE tasks SET
                    status='failed',
                    error='超过最大重试次数，需人工检查',
                    message='自愈：停止无限重试'
                WHERE id=?
            ''', (task["id"],))
            healed += 1
            logger.warning(f"停止无限重试任务: {task['id']} ({task['retry_count']}次)")

        conn.commit()
        conn.close()

        return healed

    def check_disk_space(self) -> dict:
        """检查磁盘空间"""
        result = {"percent": 0, "issues": []}

        try:
            import shutil
            total, used, free = shutil.disk_usage(BASE_DIR.parent)
            result["percent"] = round(used / total * 100, 1)

            if result["percent"] > THRESHOLDS["disk_threshold"]:
                result["issues"].append(f"磁盘空间不足: {result['percent']}%已使用")

                # 计算可清理空间
                pdf_dir = DATA_DIR / "pdfs"
                if pdf_dir.exists():
                    pdf_size = sum(f.stat().st_size for f in pdf_dir.glob("*.pdf")) / (1024**3)
                    result["pdf_size_gb"] = round(pdf_size, 2)

        except Exception as e:
            result["issues"].append(f"磁盘检查失败: {e}")

        return result

    def heal_disk_space(self) -> int:
        """清理磁盘空间"""
        cleaned = 0

        # 1. 清理过期日志
        log_dir = LOG_DIR
        if log_dir.exists():
            for log_file in log_dir.glob("*.log"):
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if (datetime.now() - mtime).days > THRESHOLDS["max_log_age_days"]:
                    log_file.unlink()
                    cleaned += 1
                    logger.info(f"删除过期日志: {log_file.name}")

        # 2. 清理临时文件
        for temp_pattern in ["*.tmp", "*.temp", "*.bak"]:
            for temp_file in DATA_DIR.glob(temp_pattern):
                temp_file.unlink()
                cleaned += 1

        # 3. 清理旧的备份数据库
        for bak_file in DATA_DIR.glob("*.db.bak"):
            bak_file.unlink()
            cleaned += 1

        return cleaned

    def ensure_workers_running(self) -> dict:
        """确保Worker进程运行，检测数量是否正确"""
        result = {
            "task_worker": {"running": False, "count": 0},
            "pdf_worker": {"running": False, "count": 0},
            "issues": []
        }

        # 检测 task_worker 数量
        try:
            r = subprocess.run(["pgrep", "-f", "task_worker.py"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                pids = r.stdout.strip().split('\n')
                count = len([p for p in pids if p])
                result["task_worker"]["running"] = count > 0
                result["task_worker"]["count"] = count
                if count > 1:
                    result["issues"].append(f"task_worker 重复 ({count}个)")
                elif count == 0:
                    result["issues"].append("task_worker 未运行")
        except Exception as e:
            result["issues"].append(f"task_worker 检测失败: {e}")

        # 检测 pdf_worker 数量
        try:
            r = subprocess.run(["pgrep", "-f", "pdf_worker.py"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                pids = r.stdout.strip().split('\n')
                count = len([p for p in pids if p])
                result["pdf_worker"]["running"] = count > 0
                result["pdf_worker"]["count"] = count
                if count > 1:
                    result["issues"].append(f"pdf_worker 重复 ({count}个)")
                elif count == 0:
                    result["issues"].append("pdf_worker 未运行")
        except Exception as e:
            result["issues"].append(f"pdf_worker 检测失败: {e}")

        return result

    def start_workers(self) -> int:
        """启动停止的Worker，使用正确的 venv 环境"""
        started = 0
        venv_python = BASE_DIR / "venv" / "bin" / "python"

        # 检查并启动 task_worker
        try:
            r = subprocess.run(["pgrep", "-f", "task_worker.py"], capture_output=True, text=True, timeout=5)
            pids = r.stdout.strip().split('\n') if r.returncode == 0 else []
            count = len([p for p in pids if p])

            if count == 0:
                # 启动新进程
                proc = subprocess.Popen(
                    [str(venv_python), "scripts/task_worker.py", "--concurrent", "8"],
                    cwd=BASE_DIR,
                    start_new_session=True,
                    stdout=open(LOG_DIR / "task_worker.log", "a"),
                    stderr=subprocess.STDOUT,
                )
                logger.info(f"已启动 task_worker (PID: {proc.pid})")
                # 写入 PID 文件
                (DATA_DIR / "task_worker.pid").write_text(str(proc.pid))
                started += 1
                # 等待验证
                time.sleep(3)
                if proc.poll() is not None:
                    logger.error(f"task_worker 启动后立即退出 (code: {proc.returncode})")
            elif count > 1:
                logger.warning(f"task_worker 有 {count} 个进程，尝试清理...")
                self._clean_duplicate_workers("task_worker")
        except Exception as e:
            logger.error(f"启动 task_worker 失败: {e}")

        # 检查并启动 pdf_worker
        try:
            r = subprocess.run(["pgrep", "-f", "pdf_worker.py"], capture_output=True, text=True, timeout=5)
            pids = r.stdout.strip().split('\n') if r.returncode == 0 else []
            count = len([p for p in pids if p])

            if count == 0:
                # 启动新进程
                proc = subprocess.Popen(
                    [str(venv_python), "scripts/pdf_worker.py", "--concurrent", "4"],
                    cwd=BASE_DIR,
                    start_new_session=True,
                    stdout=open(LOG_DIR / "pdf_worker.log", "a"),
                    stderr=subprocess.STDOUT,
                )
                logger.info(f"已启动 pdf_worker (PID: {proc.pid})")
                # 写入 PID 文件
                (DATA_DIR / "pdf_worker.pid").write_text(str(proc.pid))
                started += 1
                # 等待验证
                time.sleep(3)
                if proc.poll() is not None:
                    logger.error(f"pdf_worker 启动后立即退出 (code: {proc.returncode})")
            elif count > 1:
                logger.warning(f"pdf_worker 有 {count} 个进程，尝试清理...")
                self._clean_duplicate_workers("pdf_worker")
        except Exception as e:
            logger.error(f"启动 pdf_worker 失败: {e}")

        return started

    def _clean_duplicate_workers(self, worker_type: str) -> int:
        """清理重复的 Worker 进程，保留最新的一个"""
        try:
            r = subprocess.run(
                ["pgrep", "-f", f"{worker_type}.py"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode != 0:
                return 0

            pids = [int(p) for p in r.stdout.strip().split('\n') if p]
            if len(pids) <= 1:
                return 0

            # 按启动时间排序，保留最新的
            pids_with_time = []
            for pid in pids:
                try:
                    stat = os.stat(f"/proc/{pid}") if os.path.exists(f"/proc/{pid}") else None
                    # macOS 使用 ps 获取启动时间
                    ps_r = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True)
                    pids_with_time.append((pid, ps_r.stdout.strip()))
                except:
                    pids_with_time.append((pid, ""))

            # 保留最后一个（最新的）
            pids_to_kill = pids[:-1]
            killed = 0
            for pid in pids_to_kill:
                try:
                    os.kill(pid, signal.SIGTERM)
                    logger.info(f"已终止重复的 {worker_type} (PID: {pid})")
                    killed += 1
                except Exception as e:
                    logger.warning(f"终止 {worker_type} PID {pid} 失败: {e}")

            return killed
        except Exception as e:
            logger.error(f"清理重复 {worker_type} 失败: {e}")
            return 0

    def write_heartbeat(self):
        """写入心跳文件"""
        heartbeat_file = DATA_DIR / "auto_heal.heartbeat"
        heartbeat_file.write_text(datetime.now().isoformat())

    def check_self_health(self) -> dict:
        """自检：检查自身运行状态"""
        result = {"healthy": True, "issues": []}

        # 检查心跳文件
        heartbeat_file = DATA_DIR / "auto_heal.heartbeat"
        if heartbeat_file.exists():
            last_heartbeat = datetime.fromisoformat(heartbeat_file.read_text().strip())
            elapsed = (datetime.now() - last_heartbeat).total_seconds()
            if elapsed > 120:  # 超过2分钟未更新心跳
                result["healthy"] = False
                result["issues"].append(f"心跳过期: {int(elapsed)}秒")
        else:
            result["issues"].append("心跳文件不存在")

        return result

    def check_log_files(self) -> dict:
        """检查日志文件状态"""
        result = {"total_size_mb": 0, "large_files": [], "old_files": [], "issues": []}

        log_dir = LOG_DIR
        if not log_dir.exists():
            return result

        now = datetime.now()
        total_size = 0

        for log_file in log_dir.glob("*.log"):
            size_mb = log_file.stat().st_size / (1024 * 1024)
            total_size += size_mb
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            age_days = (now - mtime).days

            if size_mb > THRESHOLDS["max_log_size_mb"]:
                result["large_files"].append({"path": str(log_file.name), "size_mb": round(size_mb, 2)})

            if age_days > THRESHOLDS["max_log_age_days"]:
                result["old_files"].append({"path": str(log_file.name), "age_days": age_days})

        result["total_size_mb"] = round(total_size, 2)

        if result["large_files"]:
            result["issues"].append(f"{len(result['large_files'])}个日志文件过大")
        if result["old_files"]:
            result["issues"].append(f"{len(result['old_files'])}个日志文件过期")

        return result

    def heal_log_files(self, large_files: list, old_files: list) -> tuple:
        """清理日志文件：压缩大文件，删除过期文件"""
        compressed = 0
        deleted = 0
        import gzip
        import shutil

        for file_info in large_files:
            log_path = LOG_DIR / file_info["path"]
            if log_path.exists():
                # 压缩日志
                gz_path = log_path.with_suffix(".log.gz")
                with open(log_path, 'rb') as f_in:
                    with gzip.open(gz_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                log_path.unlink()
                compressed += 1
                logger.info(f"压缩日志: {file_info['path']}")

        for file_info in old_files:
            log_path = LOG_DIR / file_info["path"]
            if log_path.exists() and log_path.suffix == ".log":
                # 删除过期日志
                log_path.unlink()
                deleted += 1
                logger.info(f"删除过期日志: {file_info['path']}")

        if compressed + deleted > 0:
            self.heal_count += compressed + deleted

        return compressed, deleted

    def check_process_rate(self) -> dict:
        """检查任务处理速度"""
        result = {"rate_1h": 0, "rate_6h": 0, "trend": "stable", "issues": []}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        c = conn.cursor()
        now = datetime.now()

        # 1小时处理速度
        threshold_1h = (now - timedelta(hours=1)).isoformat()
        c.execute('SELECT COUNT(*) FROM tasks WHERE status="completed" AND completed_at > ?', (threshold_1h,))
        result["rate_1h"] = c.fetchone()[0]

        # 6小时处理速度
        threshold_6h = (now - timedelta(hours=6)).isoformat()
        c.execute('SELECT COUNT(*) FROM tasks WHERE status="completed" AND completed_at > ?', (threshold_6h,))
        count_6h = c.fetchone()[0]
        result["rate_6h"] = round(count_6h / 6, 1)

        conn.close()

        # 计算趋势
        if result["rate_1h"] < result["rate_6h"] * 0.5:
            result["trend"] = "declining"
            result["issues"].append(f"处理速度下降严重: {result['rate_1h']}/h < {result['rate_6h']}/h")
        elif result["rate_1h"] < THRESHOLDS["min_process_rate"]:
            result["trend"] = "slow"
            result["issues"].append(f"处理速度过慢: {result['rate_1h']}/h")

        return result

    def check_database_size(self) -> dict:
        """检查数据库大小"""
        result = {"tasks_db_mb": 0, "papers_db_mb": 0, "issues": []}

        for db_name in ["tasks.db", "papers.db"]:
            db_path = DATA_DIR / db_name
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                result[f"{db_name.replace('.db', '_db_mb')}"] = round(size_mb, 2)

        # papers.db超过200MB告警
        if result["papers_db_mb"] > 200:
            result["issues"].append(f"papers.db过大: {result['papers_db_mb']}MB")

        return result

    def predict_completion_time(self) -> dict:
        """预测任务完成时间"""
        result = {"pending": 0, "rate_per_hour": 0, "eta_hours": 0, "eta_date": ""}

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        c = conn.cursor()

        c.execute('SELECT COUNT(*) FROM tasks WHERE status="pending"')
        result["pending"] = c.fetchone()[0]

        # 使用最近6小时的平均速度
        threshold = (datetime.now() - timedelta(hours=6)).isoformat()
        c.execute('SELECT COUNT(*) FROM tasks WHERE status="completed" AND completed_at > ?', (threshold,))
        completed_6h = c.fetchone()[0]
        result["rate_per_hour"] = round(completed_6h / 6, 1) if completed_6h > 0 else 0

        conn.close()

        if result["rate_per_hour"] > 0:
            result["eta_hours"] = round(result["pending"] / result["rate_per_hour"], 1)
            eta_date = datetime.now() + timedelta(hours=result["eta_hours"])
            result["eta_date"] = eta_date.strftime("%Y-%m-%d %H:%M")

        return result

    def generate_health_report(self, report: dict) -> str:
        """生成健康报告"""
        prediction = self.predict_completion_time()

        lines = [
            "=" * 50,
            "ArXiv系统健康报告",
            f"时间: {report['time']}",
            "=" * 50,
            "",
            f"健康评分: {report.get('health_score', 0)}/100",
            "",
            "任务状态:",
            f"  运行中: {report['tasks']['running']}",
            f"  待处理: {report['tasks']['pending']}",
            f"  失败: {report['tasks']['failed']}",
            "",
            "处理速度:",
            f"  当前: {report['process_rate']['rate_1h']}个/小时",
            f"  6小时平均: {report['process_rate']['rate_6h']}个/小时",
            f"  趋势: {report['process_rate']['trend']}",
            "",
            "预测:",
            f"  剩余任务: {prediction['pending']}个",
            f"  预计完成: {prediction['eta_date'] or '无法预测'}",
            "",
            "资源:",
            f"  CPU: {report['resources']['cpu']}%",
            f"  内存: {report['resources']['memory']}%",
            f"  磁盘: {report['resources']['disk']}%",
            "",
            "24小时自愈:",
            f"  总计: {report['heal_stats']['total']}次",
        ]

        for event_type, count in report['heal_stats']['by_type'].items():
            lines.append(f"    {event_type}: {count}次")

        if report['issues']:
            lines.append("")
            lines.append(f"问题({len(report['issues'])}个):")
            for issue in report['issues'][:5]:
                lines.append(f"  - {issue}")

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)

    def heal_stuck_tasks(self, stuck_tasks: list) -> int:
        """修复卡住的任务"""
        if not stuck_tasks:
            return 0

        conn = sqlite3.connect(DATA_DIR / "tasks.db")
        count = 0
        for task in stuck_tasks:
            conn.execute(
                'UPDATE tasks SET status="pending", started_at=NULL, message="自愈：超时重置" WHERE id=?',
                (task["id"],),
            )
            count += 1
            logger.info(f"重置超时任务: {task['id'][:8]} ({task['type']}, {task['elapsed']}秒)")
        conn.commit()
        conn.close()

        self.heal_count += count
        return count

    def heal_pdf_sync(self, diff: int, broken_links: int) -> tuple:
        """修复PDF同步问题"""
        synced = 0
        cleaned = 0

        if diff > 0:
            # 同步多出的文件
            pdf_dir = DATA_DIR / "pdfs"
            conn = sqlite3.connect(DATA_DIR / "papers.db")

            db_paths = set()
            for row in conn.execute(
                'SELECT pdf_local_path FROM papers WHERE pdf_local_path IS NOT NULL'
            ):
                path = row[0].replace("data/", "")
                db_paths.add(Path(path).name)

            actual_files = set(f.name for f in pdf_dir.glob("*.pdf"))
            extra_files = actual_files - db_paths

            for pdf_file in extra_files:
                arxiv_id = pdf_file.replace(".pdf", "")
                result = conn.execute(
                    'SELECT id FROM papers WHERE arxiv_id=?', (arxiv_id,)
                ).fetchone()
                if result:
                    conn.execute(
                        'UPDATE papers SET pdf_local_path=? WHERE id=?',
                        (f"data/pdfs/{pdf_file}", result[0]),
                    )
                    synced += 1
                    logger.info(f"同步PDF: {arxiv_id}")

            conn.commit()
            conn.close()

        if broken_links > 0:
            # 清理断链
            conn = sqlite3.connect(DATA_DIR / "papers.db")
            for row in conn.execute(
                'SELECT id, pdf_local_path FROM papers WHERE pdf_local_path IS NOT NULL'
            ):
                paper_id, path = row
                if path.startswith("data/"):
                    full_path = BASE_DIR / path
                else:
                    full_path = Path(path)
                if not full_path.exists():
                    conn.execute(
                        'UPDATE papers SET pdf_local_path=NULL WHERE id=?', (paper_id,)
                    )
                    cleaned += 1
                    logger.info(f"清理断链: paper_id={paper_id}")

            conn.commit()
            conn.close()

        if synced > 0 or cleaned > 0:
            self.heal_count += synced + cleaned

        return synced, cleaned

    def heal_stopped_workers(self, stopped: list) -> int:
        """启动停止的Worker"""
        if not stopped:
            return 0

        started = 0
        for worker in stopped:
            if worker == "task_worker":
                subprocess.Popen(
                    ["python3", "scripts/task_worker.py", "--concurrent", "8"],
                    cwd=BASE_DIR,
                    start_new_session=True,
                )
                logger.info("已启动 task_worker")
                started += 1
            elif worker == "pdf_worker":
                subprocess.Popen(
                    ["python3", "scripts/pdf_worker.py", "--concurrent", "4"],
                    cwd=BASE_DIR,
                    start_new_session=True,
                )
                logger.info("已启动 pdf_worker")
                started += 1

        self.heal_count += started
        return started

    def run_check(self) -> dict:
        """执行完整检查"""
        report = {
            "time": datetime.now().isoformat(),
            "workers": None,
            "tasks": None,
            "pdf": None,
            "quality": None,
            "healed": [],
            "issues": [],
        }

        # 检查Worker
        workers = self.check_workers()
        report["workers"] = workers
        report["issues"].extend(workers.get("issues", []))

        # 自愈：启动停止的Worker
        if workers["stopped"]:
            started = self.heal_stopped_workers(workers["stopped"])
            if started > 0:
                report["healed"].append(f"启动了{started}个Worker")

        # 检查任务
        tasks = self.check_tasks()
        report["tasks"] = tasks
        report["issues"].extend(tasks.get("issues", []))

        # 自愈：重置超时任务
        if tasks["stuck"]:
            reset = self.heal_stuck_tasks(tasks["stuck"])
            if reset > 0:
                report["healed"].append(f"重置了{reset}个超时任务")

        # 检查PDF
        pdf = self.check_pdf_sync()
        report["pdf"] = pdf
        report["issues"].extend(pdf.get("issues", []))

        # 自愈：修复PDF同步
        if pdf["diff"] > 0 or pdf["broken_links"] > 0:
            synced, cleaned = self.heal_pdf_sync(pdf["diff"], pdf["broken_links"])
            if synced > 0:
                report["healed"].append(f"同步了{synced}个PDF")
            if cleaned > 0:
                report["healed"].append(f"清理了{cleaned}个断链")

        # 检查质量
        quality = self.check_quality()
        report["quality"] = quality
        report["issues"].extend(quality.get("issues", []))

        # 检查数据库健康
        db_health = self.check_database_health()
        report["db_health"] = db_health
        report["issues"].extend(db_health.get("issues", []))

        # 检查失败任务
        failed_tasks = self.check_failed_tasks()
        report["failed_tasks"] = failed_tasks
        report["issues"].extend(failed_tasks.get("issues", []))

        # 自愈：清理伪失败，重置需要重试的任务
        if failed_tasks["false_failed"] > 0 or failed_tasks["needs_retry"] > 0:
            deleted, reset = self.heal_failed_tasks(failed_tasks["false_failed"], failed_tasks["needs_retry"])
            if deleted > 0:
                report["healed"].append(f"删除{deleted}个伪失败任务")
            if reset > 0:
                report["healed"].append(f"重置{reset}个失败任务重试")

        # 检查重复任务
        duplicates = self.check_duplicate_tasks()
        report["duplicates"] = duplicates
        report["issues"].extend(duplicates.get("issues", []))

        # 自愈：清理重复任务
        if duplicates["duplicates"] > 0:
            cleaned = self.heal_duplicate_tasks()
            if cleaned > 0:
                report["healed"].append(f"清理{cleaned}个重复任务")

        # 检查系统资源
        resources = self.check_resources()
        report["resources"] = resources
        report["issues"].extend(resources.get("issues", []))

        # 检查并发任务数
        concurrent = self.check_concurrent_tasks()
        report["concurrent"] = concurrent
        report["issues"].extend(concurrent.get("issues", []))

        # 检查任务积压
        backlog = self.check_task_backlog()
        report["backlog"] = backlog
        report["issues"].extend(backlog.get("issues", []))

        # 检查反复超时任务
        repeated_timeout = self.check_repeated_timeout()
        report["repeated_timeout"] = repeated_timeout
        report["issues"].extend(repeated_timeout.get("issues", []))

        # 自愈：标记反复超时任务为问题任务
        if repeated_timeout["repeated"] > 0:
            handled = self.heal_repeated_timeout_tasks(repeated_timeout["tasks"])
            if handled > 0:
                report["healed"].append(f"标记{handled}个反复超时任务")

        # 检查API限流
        api_status = self.check_api_rate_limit()
        report["api_status"] = api_status
        report["issues"].extend(api_status.get("issues", []))

        # 检查质量问题修复链路
        quality_pipeline = self.check_quality_repair_pipeline()
        report["quality_pipeline"] = quality_pipeline
        report["issues"].extend(quality_pipeline.get("issues", []))

        # 自愈：为缺少任务的问题论文创建force_refresh任务
        if quality_pipeline["missing_tasks"] > 0:
            created = self.heal_quality_repair_pipeline()
            if created > 0:
                report["healed"].append(f"创建{created}个质量修复任务")

        # 检查日志文件
        log_status = self.check_log_files()
        report["log_status"] = log_status
        report["issues"].extend(log_status.get("issues", []))

        # 自愈：清理日志文件
        if log_status["large_files"] or log_status["old_files"]:
            compressed, deleted = self.heal_log_files(log_status["large_files"], log_status["old_files"])
            if compressed > 0:
                report["healed"].append(f"压缩{compressed}个日志文件")
            if deleted > 0:
                report["healed"].append(f"删除{deleted}个过期日志")

        # 检查处理速度
        process_rate = self.check_process_rate()
        report["process_rate"] = process_rate
        report["issues"].extend(process_rate.get("issues", []))

        # 检查数据库完整性
        db_integrity = self.check_database_integrity()
        report["db_integrity"] = db_integrity
        report["issues"].extend(db_integrity.get("issues", []))

        # 自愈：修复损坏的数据库
        if db_integrity["corrupted"]:
            healed = self.heal_database_integrity(db_integrity["corrupted"])
            if healed > 0:
                report["healed"].append(f"修复{healed}个数据库")

        # 检查无限重试任务
        infinite_retry = self.check_infinite_retry()
        report["infinite_retry"] = infinite_retry
        report["issues"].extend(infinite_retry.get("issues", []))

        # 自愈：停止无限重试
        if infinite_retry["infinite_retry"]:
            healed = self.heal_infinite_retry(infinite_retry["infinite_retry"])
            if healed > 0:
                report["healed"].append(f"停止{healed}个无限重试任务")

        # 检查磁盘空间
        disk_space = self.check_disk_space()
        report["disk_space"] = disk_space
        report["issues"].extend(disk_space.get("issues", []))

        # 自愈：清理磁盘空间
        if disk_space.get("percent", 0) > THRESHOLDS["disk_threshold"]:
            cleaned = self.heal_disk_space()
            if cleaned > 0:
                report["healed"].append(f"清理{cleaned}个文件释放空间")

        # 确保Worker运行
        worker_status = self.ensure_workers_running()
        report["worker_status"] = worker_status
        if not worker_status["task_worker"] or not worker_status["pdf_worker"]:
            started = self.start_workers()
            if started > 0:
                report["healed"].append(f"启动{started}个Worker")

        # 写入心跳
        self.write_heartbeat()

        # 检查数据库大小
        db_size = self.check_database_size()
        report["db_size"] = db_size
        report["issues"].extend(db_size.get("issues", []))

        # 获取自愈统计
        report["heal_stats"] = get_recent_heal_stats(24)

        # 计算健康评分
        report["health_score"] = calculate_health_score(report)

        # 记录自愈事件
        if report["healed"]:
            for heal_action in report["healed"]:
                record_heal_event("auto_heal", heal_action, {"issues": report["issues"]}, report["health_score"])

        # 发送告警（健康评分<60或有关键问题）
        if report["health_score"] < 60:
            critical_issues = [i for i in report["issues"] if any(kw in i for kw in ["停止", "过载", "限流", "严重"])]
            if critical_issues:
                send_alert(
                    f"健康评分: {report['health_score']}\n问题: {', '.join(critical_issues[:3])}",
                    alert_type="critical"
                )
        elif report["health_score"] < 80:
            send_alert(
                f"健康评分: {report['health_score']}\n问题: {len(report['issues'])}个",
                alert_type="warning"
            )

        self.last_check = datetime.now()
        return report


async def monitor_loop(interval: int = 60):
    """监控循环"""
    monitor = SystemMonitor()
    logger.info(f"自愈监控启动，检查间隔: {interval}秒")

    # 导入指标采集模块
    try:
        from metrics_store import collect_and_store
        METRICS_AVAILABLE = True
        logger.info("指标采集模块已加载")
    except ImportError:
        METRICS_AVAILABLE = False
        logger.warning("指标采集模块未找到，历史数据采集已禁用")

    while not _shutdown:
        try:
            report = monitor.run_check()

            # 采集并存储指标
            if METRICS_AVAILABLE:
                try:
                    collect_and_store()
                except Exception as e:
                    logger.warning(f"指标采集失败: {e}")

            # 输出摘要
            summary = []
            summary.append(f"running={report['tasks']['running']}")
            summary.append(f"pending={report['tasks']['pending']}")
            summary.append(f"failed={report['tasks']['failed']}")
            summary.append(f"stuck={len(report['tasks']['stuck'])}")
            summary.append(f"cpu={report['resources']['cpu']:.0f}%")
            summary.append(f"mem={report['resources']['memory']:.0f}%")

            if report["healed"]:
                logger.info(f"检查完成 | {' | '.join(summary)} | 已修复: {', '.join(report['healed'])}")
            elif report["issues"]:
                logger.warning(f"检查完成 | {' | '.join(summary)} | 问题: {len(report['issues'])}个")
            else:
                logger.info(f"检查完成 | {' | '.join(summary)}")

        except Exception as e:
            logger.error(f"检查错误: {e}")
            monitor.consecutive_errors += 1

            if monitor.consecutive_errors >= 5:
                logger.error("连续错误超过5次，停止监控")
                break

        await asyncio.sleep(interval)


def signal_handler(signum, frame):
    """信号处理器"""
    global _shutdown
    logger.info(f"收到信号 {signum}，准备退出...")
    _shutdown = True


def main():
    import argparse

    # 初始化自愈历史数据库
    init_heal_history_db()

    parser = argparse.ArgumentParser(description="ArXiv系统自愈监控")
    parser.add_argument("--interval", type=int, default=60, help="检查间隔(秒)")
    parser.add_argument("--once", action="store_true", help="只检查一次")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    if args.once:
        monitor = SystemMonitor()
        report = monitor.run_check()

        print("\n" + "=" * 60)
        print("系统检查报告")
        print("=" * 60)

        print(f"\n时间: {report['time']}")
        print(f"\nWorkers:")
        for w in report['workers']['running']:
            print(f"  ✓ {w}")
        for w in report['workers']['stopped']:
            print(f"  ✗ {w} (已停止)")

        print(f"\n任务状态:")
        print(f"  Running: {report['tasks']['running']}")
        print(f"  Pending: {report['tasks']['pending']}")
        print(f"  Failed: {report['tasks']['failed']}")
        print(f"  Stuck: {len(report['tasks']['stuck'])}")

        print(f"\nPDF同步:")
        print(f"  差异: {report['pdf']['diff']}")
        print(f"  断链: {report['pdf']['broken_links']}")

        print(f"\n质量问题:")
        print(f"  未解决: {report['quality']['unresolved']}")

        print(f"\n失败任务:")
        print(f"  伪失败: {report['failed_tasks']['false_failed']}")
        print(f"  需重试: {report['failed_tasks']['needs_retry']}")

        print(f"\n重复任务:")
        print(f"  重复组: {report['duplicates']['duplicates']}")

        print(f"\n系统资源:")
        print(f"  CPU: {report['resources']['cpu']}%")
        print(f"  内存: {report['resources']['memory']}%")
        print(f"  磁盘: {report['resources']['disk']}%")

        print(f"\n并发状态:")
        print(f"  运行: {report['concurrent']['running']}/{report['concurrent']['expected']}")

        print(f"\n任务积压:")
        print(f"  待处理: {report['backlog']['pending']}")

        print(f"\n反复超时:")
        print(f"  问题任务: {report['repeated_timeout']['repeated']}")

        print(f"\nAPI状态:")
        print(f"  限流: {'是' if report['api_status']['rate_limited'] else '否'}")

        # 质量修复链路
        if 'quality_pipeline' in report:
            print(f"\n质量修复链路:")
            print(f"  待修复论文: {report['quality_pipeline']['unresolved_papers']}")
            print(f"  缺少任务: {report['quality_pipeline']['missing_tasks']}")

        # 健康评分
        score = report.get('health_score', 0)
        if score >= 80:
            score_icon = "🟢"
        elif score >= 60:
            score_icon = "🟡"
        else:
            score_icon = "🔴"
        print(f"\n健康评分:")
        print(f"  {score_icon} {score}/100")

        # 处理速度
        if 'process_rate' in report:
            print(f"\n处理速度:")
            print(f"  当前: {report['process_rate']['rate_1h']}个/小时")
            print(f"  6小时平均: {report['process_rate']['rate_6h']}个/小时")
            print(f"  趋势: {report['process_rate']['trend']}")

        # 预测
        prediction = monitor.predict_completion_time()
        if prediction:
            print(f"\n预测:")
            print(f"  剩余: {prediction.get('pending', 0)}个")
            print(f"  预计完成: {prediction.get('eta_date', '无法预测')}")

        # 日志状态
        if 'log_status' in report:
            print(f"\n日志状态:")
            print(f"  总大小: {report['log_status']['total_size_mb']}MB")
            if report['log_status']['large_files']:
                print(f"  大文件: {len(report['log_status']['large_files'])}个")
            if report['log_status']['old_files']:
                print(f"  过期: {len(report['log_status']['old_files'])}个")

        # 最近自愈统计
        stats = report.get('heal_stats', get_recent_heal_stats(24))
        print(f"\n24小时自愈统计:")
        print(f"  总计: {stats['total']}次")
        for event_type, count in stats['by_type'].items():
            print(f"  {event_type}: {count}次")

        if report['healed']:
            print(f"\n✅ 已修复: {', '.join(report['healed'])}")

        if report['issues']:
            print(f"\n⚠️ 问题: {len(report['issues'])}个")
            for issue in report['issues']:
                print(f"  - {issue}")

        print("\n" + "=" * 60)

    else:
        asyncio.run(monitor_loop(args.interval))


if __name__ == "__main__":
    main()
