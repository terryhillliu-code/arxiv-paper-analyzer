#!/usr/bin/env python3
"""监控指标存储模块。

采集和存储系统运行指标，用于历史趋势分析。
数据存储在 heal_history.db 中。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Optional

import psutil

from monitor_config import (
    TASKS_DB_PATH,
    PAPERS_DB_PATH,
    QUALITY_DB_PATH,
    HEAL_HISTORY_DB_PATH,
    METRICS_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)


@dataclass
class MetricRecord:
    """指标记录"""
    timestamp: str
    metric_type: str
    metric_value: float
    metadata: Optional[dict[str, Any]] = None


class MetricsStore:
    """指标存储管理器"""

    RETENTION_DAYS = METRICS_RETENTION_DAYS

    def __init__(self, db_path: Path = HEAL_HISTORY_DB_PATH):
        self.db_path = db_path
        self._ensure_tables()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        """确保数据库表存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 指标历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    metadata TEXT
                )
            """)

            # 任务统计历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_stats_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    pending INTEGER DEFAULT 0,
                    running INTEGER DEFAULT 0,
                    completed INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    cancelled INTEGER DEFAULT 0,
                    avg_duration REAL DEFAULT 0
                )
            """)

            # 创建索引加速查询
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
                ON metrics_history(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_type
                ON metrics_history(metric_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_stats_timestamp
                ON task_stats_history(timestamp)
            """)

            conn.commit()

    def record_metric(self, metric_type: str, value: float, metadata: Optional[dict[str, Any]] = None) -> None:
        """记录单个指标"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO metrics_history (timestamp, metric_type, metric_value, metadata)
                    VALUES (?, ?, ?, ?)
                    """,
                    (datetime.now().isoformat(), metric_type, value, json.dumps(metadata) if metadata else None)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"记录指标失败: {e}")

    def record_task_stats(self, stats: dict[str, Any]) -> None:
        """记录任务统计"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO task_stats_history
                    (timestamp, pending, running, completed, failed, cancelled, avg_duration)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now().isoformat(),
                        stats.get("pending", 0),
                        stats.get("running", 0),
                        stats.get("completed", 0),
                        stats.get("failed", 0),
                        stats.get("cancelled", 0),
                        stats.get("avg_duration", 0)
                    )
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"记录任务统计失败: {e}")

    def get_metrics_history(
        self,
        metric_type: str,
        hours: int = 24,
        limit: int = 1000
    ) -> list[dict[str, Any]]:
        """获取指标历史数据"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
                cursor.execute(
                    """
                    SELECT timestamp, metric_value, metadata
                    FROM metrics_history
                    WHERE metric_type = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (metric_type, start_time, limit)
                )
                rows = cursor.fetchall()

                return [
                    {
                        "timestamp": row[0],
                        "value": row[1],
                        "metadata": json.loads(row[2]) if row[2] else None
                    }
                    for row in rows
                ]
        except sqlite3.Error as e:
            logger.error(f"获取指标历史失败: {e}")
            return []

    def get_task_stats_history(self, hours: int = 24, limit: int = 1000) -> list[dict[str, Any]]:
        """获取任务统计历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
                cursor.execute(
                    """
                    SELECT timestamp, pending, running, completed, failed, cancelled, avg_duration
                    FROM task_stats_history
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (start_time, limit)
                )
                rows = cursor.fetchall()

                return [
                    {
                        "timestamp": row[0],
                        "pending": row[1],
                        "running": row[2],
                        "completed": row[3],
                        "failed": row[4],
                        "cancelled": row[5],
                        "avg_duration": row[6]
                    }
                    for row in rows
                ]
        except sqlite3.Error as e:
            logger.error(f"获取任务统计历史失败: {e}")
            return []

    def cleanup_old_data(self) -> dict[str, int]:
        """清理过期数据"""
        threshold = (datetime.now() - timedelta(days=self.RETENTION_DAYS)).isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("DELETE FROM metrics_history WHERE timestamp < ?", (threshold,))
                metrics_deleted = cursor.rowcount

                cursor.execute("DELETE FROM task_stats_history WHERE timestamp < ?", (threshold,))
                stats_deleted = cursor.rowcount

                conn.commit()

                return {"metrics_deleted": metrics_deleted, "stats_deleted": stats_deleted}
        except sqlite3.Error as e:
            logger.error(f"清理过期数据失败: {e}")
            return {"metrics_deleted": 0, "stats_deleted": 0}


class MetricsCollector:
    """指标采集器"""

    def __init__(self, store: Optional[MetricsStore] = None):
        self.store = store or MetricsStore()

    def collect_all(self) -> dict[str, Any]:
        """采集所有指标"""
        results: dict[str, Any] = {}

        # 采集系统资源
        results["resources"] = self.collect_resources()

        # 采集任务统计（已合并速度计算）
        task_stats = self.collect_task_stats()
        results["tasks"] = task_stats
        results["speed"] = {
            "speed_hour": task_stats.get("speed_hour", 0),
            "speed_5min": task_stats.get("speed_5min", 0),
            "completed_hour": task_stats.get("completed_hour", 0),
            "completed_5min": task_stats.get("completed_5min", 0),
        }

        # 采集质量统计
        results["quality"] = self.collect_quality_stats()

        # 写入数据库
        self._store_metrics(results)

        return results

    def collect_resources(self) -> dict[str, Any]:
        """采集系统资源指标"""
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(str(Path.home()))

            return {
                "cpu_percent": cpu,
                "memory_percent": memory.percent,
                "memory_used_gb": memory.used / (1024**3),
                "memory_total_gb": memory.total / (1024**3),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024**3),
                "disk_total_gb": disk.total / (1024**3),
            }
        except Exception as e:
            logger.error(f"采集系统资源失败: {e}")
            return {"error": str(e)}

    def collect_task_stats(self) -> dict[str, Any]:
        """采集任务队列统计"""
        conn = None
        try:
            conn = sqlite3.connect(TASKS_DB_PATH)
            cursor = conn.cursor()

            # 状态分布
            cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            status_counts = dict(cursor.fetchall())

            # 任务类型分布
            cursor.execute("SELECT task_type, COUNT(*) FROM tasks WHERE status='pending' GROUP BY task_type")
            type_counts = dict(cursor.fetchall())

            # 最近完成的任务平均时长
            cursor.execute("""
                SELECT AVG(
                    (julianday(completed_at) - julianday(started_at)) * 86400
                )
                FROM tasks
                WHERE status='completed'
                AND completed_at > datetime('now', '-1 hour')
            """)
            avg_duration = cursor.fetchone()[0] or 0

            # 最近1小时和5分钟完成数 - 合并查询
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN completed_at > datetime('now', '-1 hour') THEN 1 ELSE 0 END) as hour_count,
                    SUM(CASE WHEN completed_at > datetime('now', '-5 minutes') THEN 1 ELSE 0 END) as min5_count
                FROM tasks
                WHERE status='completed'
            """)
            row = cursor.fetchone()
            completed_hour = row[0] or 0
            completed_5min = row[1] or 0

            # 计算速度
            speed_hour = round(completed_hour / 60, 2) if completed_hour > 0 else 0
            speed_5min = round(completed_5min / 5, 2) if completed_5min > 0 else 0

            return {
                "pending": status_counts.get("pending", 0),
                "running": status_counts.get("running", 0),
                "completed": status_counts.get("completed", 0),
                "failed": status_counts.get("failed", 0),
                "cancelled": status_counts.get("cancelled", 0),
                "avg_duration": avg_duration,
                "completed_hour": completed_hour,
                "completed_5min": completed_5min,
                "speed_hour": speed_hour,
                "speed_5min": speed_5min,
                "type_distribution": type_counts,
            }
        except Exception as e:
            logger.error(f"采集任务统计失败: {e}")
            return {"error": str(e)}
        finally:
            if conn:
                conn.close()

    def collect_quality_stats(self) -> dict[str, Any]:
        """采集质量统计"""
        conn = None
        try:
            # Tier 分布
            conn = sqlite3.connect(PAPERS_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tier, COUNT(*) FROM papers
                WHERE has_analysis=1
                GROUP BY tier
                ORDER BY tier
            """)
            tier_distribution = dict(cursor.fetchall())
            conn.close()
            conn = None

            # 质量问题分布
            quality_stats: dict[str, Any] = {"resolved": 0, "unresolved": 0, "types": {}}
            if QUALITY_DB_PATH.exists():
                conn = sqlite3.connect(QUALITY_DB_PATH)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT resolved, COUNT(*) FROM quality_issues
                    GROUP BY resolved
                """)
                resolved_counts = dict(cursor.fetchall())
                quality_stats["resolved"] = resolved_counts.get(1, 0)
                quality_stats["unresolved"] = resolved_counts.get(0, 0)

                cursor.execute("""
                    SELECT issue_type, COUNT(*) FROM quality_issues
                    WHERE resolved=0
                    GROUP BY issue_type
                    ORDER BY COUNT(*) DESC
                    LIMIT 10
                """)
                quality_stats["types"] = dict(cursor.fetchall())
                conn.close()
                conn = None

            return {
                "tier_distribution": tier_distribution,
                "quality_stats": quality_stats,
            }
        except Exception as e:
            logger.error(f"采集质量统计失败: {e}")
            return {"error": str(e)}
        finally:
            if conn:
                conn.close()

    def _store_metrics(self, results: dict[str, Any]) -> None:
        """将采集结果写入数据库"""
        # 存储资源指标
        resources = results.get("resources", {})
        if "cpu_percent" in resources:
            self.store.record_metric("cpu_percent", resources["cpu_percent"])
        if "memory_percent" in resources:
            self.store.record_metric("memory_percent", resources["memory_percent"])
        if "disk_percent" in resources:
            self.store.record_metric("disk_percent", resources["disk_percent"])

        # 存储速度指标
        speed = results.get("speed", {})
        if "speed_hour" in speed:
            self.store.record_metric("speed_hour", speed["speed_hour"])

        # 存储任务统计
        tasks = results.get("tasks", {})
        if "pending" in tasks:
            self.store.record_task_stats(tasks)

    def get_worker_status(self) -> list[dict[str, Any]]:
        """获取 Worker 进程状态"""
        workers: list[dict[str, Any]] = []
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split("\n"):
                if "task_worker.py" in line:
                    parts = line.split()
                    if len(parts) > 3:
                        workers.append({
                            "name": "task_worker",
                            "pid": parts[1],
                            "status": "running",
                            "concurrent": self._extract_concurrent(line),
                            "cpu": parts[2],
                            "memory": parts[3],
                        })
                elif "pdf_worker.py" in line:
                    parts = line.split()
                    if len(parts) > 3:
                        workers.append({
                            "name": "pdf_worker",
                            "pid": parts[1],
                            "status": "running",
                            "concurrent": self._extract_concurrent(line),
                            "cpu": parts[2],
                            "memory": parts[3],
                        })
        except Exception as e:
            logger.error(f"获取 Worker 状态失败: {e}")
        return workers

    def _extract_concurrent(self, line: str) -> str:
        """从命令行提取并发数"""
        if "--concurrent" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "--concurrent" and i + 1 < len(parts):
                    return parts[i + 1]
        return "?"


# 全局实例
metrics_store = MetricsStore()
metrics_collector = MetricsCollector(metrics_store)


def collect_and_store() -> dict[str, Any]:
    """采集并存储指标（供外部调用）"""
    return metrics_collector.collect_all()


if __name__ == "__main__":
    # 测试采集
    print("开始采集指标...")
    results = collect_and_store()
    print(json.dumps(results, indent=2, ensure_ascii=False))