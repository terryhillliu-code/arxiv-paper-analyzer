#!/usr/bin/env python3
"""测试 metrics_store 模块"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# 添加父目录到 path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from metrics_store import MetricsStore, MetricsCollector


class TestMetricsStore:
    """测试 MetricsStore 类"""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test_metrics.db"
        yield db_path
        # 清理
        if db_path.exists():
            db_path.unlink()

    def test_ensure_tables(self, temp_db):
        """测试表创建"""
        store = MetricsStore(temp_db)

        # 检查表是否存在
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('metrics_history', 'task_stats_history')
            """)
            tables = [row[0] for row in cursor.fetchall()]

        assert "metrics_history" in tables
        assert "task_stats_history" in tables

    def test_record_metric(self, temp_db):
        """测试记录指标"""
        store = MetricsStore(temp_db)

        store.record_metric("cpu_percent", 45.5)

        # 验证记录
        history = store.get_metrics_history("cpu_percent", hours=1)
        assert len(history) == 1
        assert history[0]["value"] == 45.5

    def test_record_metric_with_metadata(self, temp_db):
        """测试带元数据的指标记录"""
        store = MetricsStore(temp_db)

        store.record_metric("speed_hour", 10.5, {"worker": "task_worker"})

        history = store.get_metrics_history("speed_hour", hours=1)
        assert len(history) == 1
        assert history[0]["metadata"]["worker"] == "task_worker"

    def test_record_task_stats(self, temp_db):
        """测试记录任务统计"""
        store = MetricsStore(temp_db)

        stats = {
            "pending": 100,
            "running": 5,
            "completed": 1000,
            "failed": 2,
            "cancelled": 10,
            "avg_duration": 120.5
        }
        store.record_task_stats(stats)

        history = store.get_task_stats_history(hours=1)
        assert len(history) == 1
        assert history[0]["pending"] == 100
        assert history[0]["completed"] == 1000

    def test_get_metrics_history_limit(self, temp_db):
        """测试历史数据限制"""
        store = MetricsStore(temp_db)

        # 插入多条记录
        for i in range(20):
            store.record_metric("cpu_percent", float(i))

        # 限制返回数量
        history = store.get_metrics_history("cpu_percent", hours=1, limit=10)
        assert len(history) == 10

    def test_cleanup_old_data(self, temp_db):
        """测试清理过期数据"""
        store = MetricsStore(temp_db)

        # 插入记录
        store.record_metric("cpu_percent", 50.0)

        # 手动插入一条过期数据
        old_time = (datetime.now() - timedelta(days=10)).isoformat()
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO metrics_history (timestamp, metric_type, metric_value) VALUES (?, ?, ?)",
                (old_time, "old_metric", 100.0)
            )
            conn.commit()

        # 清理
        result = store.cleanup_old_data()
        assert result["metrics_deleted"] == 1


class TestMetricsCollector:
    """测试 MetricsCollector 类"""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """创建临时存储"""
        db_path = tmp_path / "test_metrics.db"
        store = MetricsStore(db_path)
        yield store
        if db_path.exists():
            db_path.unlink()

    def test_collect_resources(self, temp_store):
        """测试采集系统资源"""
        collector = MetricsCollector(temp_store)

        result = collector.collect_resources()

        # 检查必要字段
        assert "cpu_percent" in result
        assert "memory_percent" in result
        assert "disk_percent" in result

        # 检查值范围
        assert 0 <= result["cpu_percent"] <= 100
        assert 0 <= result["memory_percent"] <= 100
        assert 0 <= result["disk_percent"] <= 100

    def test_get_worker_status(self, temp_store):
        """测试获取 Worker 状态"""
        collector = MetricsCollector(temp_store)

        workers = collector.get_worker_status()

        # 应该返回列表
        assert isinstance(workers, list)

    def test_extract_concurrent(self, temp_store):
        """测试提取并发数"""
        collector = MetricsCollector(temp_store)

        line = "python task_worker.py --concurrent 6"
        result = collector._extract_concurrent(line)

        assert result == "6"

    def test_extract_concurrent_no_flag(self, temp_store):
        """测试无并发标志"""
        collector = MetricsCollector(temp_store)

        line = "python task_worker.py"
        result = collector._extract_concurrent(line)

        assert result == "?"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])