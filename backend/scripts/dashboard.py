#!/usr/bin/env python3
"""ArXiv论文分析系统监控面板。

启动方式:
    python scripts/dashboard.py --port 8899

访问:
    http://localhost:8899
"""

import sqlite3
import json
import subprocess
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import argparse

# 导入配置
from monitor_config import (
    DATA_DIR,
    STATIC_DIR,
    TASKS_DB_PATH,
    PAPERS_DB_PATH,
    QUALITY_DB_PATH,
    HEAL_HISTORY_DB_PATH,
    AlertThresholds,
)

# 导入指标存储模块
try:
    from metrics_store import metrics_store, metrics_collector
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


class DashboardHandler(SimpleHTTPRequestHandler):
    """监控面板HTTP处理器"""

    def do_GET(self):
        parsed = urlparse(self.path)

        # API 端点
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
        # 静态资源
        elif parsed.path.startswith("/assets/"):
            self._serve_static(parsed.path)
        # 根路径和其他路径服务 React 应用
        else:
            self._serve_react_app()

    def _handle_api(self, parsed):
        """处理 API 请求"""
        if parsed.path == "/api/stats":
            self.send_json(self.get_stats())
        elif parsed.path == "/api/history":
            self.send_json(self.get_history())
        elif parsed.path == "/api/issues":
            self.send_json(self.get_issues())
        elif parsed.path == "/api/workers":
            self.send_json(self.get_workers())
        # 新增 API 端点
        elif parsed.path == "/api/history/metrics":
            params = parse_qs(parsed.query)
            hours = int(params.get("hours", ["24"])[0])
            metric_type = params.get("type", [None])[0]
            self.send_json(self.get_metrics_history(hours, metric_type))
        elif parsed.path == "/api/history/tasks":
            params = parse_qs(parsed.query)
            hours = int(params.get("hours", ["24"])[0])
            self.send_json(self.get_task_stats_history(hours))
        elif parsed.path == "/api/quality/trends":
            self.send_json(self.get_quality_trends())
        elif parsed.path == "/api/performance":
            self.send_json(self.get_performance())
        elif parsed.path == "/api/tasks/deep":
            self.send_json(self.get_deep_task_stats())
        elif parsed.path == "/api/alerts/history":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["20"])[0])
            self.send_json(self.get_alerts_history(limit))
        else:
            self.send_error(404)

    def _serve_static(self, path: str):
        """服务静态文件"""
        file_path = STATIC_DIR / path.lstrip("/")
        if file_path.exists():
            self.send_response(200)
            # 根据文件类型设置 Content-Type
            if path.endswith(".js"):
                self.send_header("Content-Type", "application/javascript")
            elif path.endswith(".css"):
                self.send_header("Content-Type", "text/css")
            elif path.endswith(".svg"):
                self.send_header("Content-Type", "image/svg+xml")
            else:
                self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(file_path.read_bytes())
        else:
            self.send_error(404)

    def _serve_react_app(self):
        """服务 React 应用 (index.html)"""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(index_path.read_bytes())
        else:
            # 如果静态文件不存在，回退到旧版 HTML
            self.send_html()

    def send_html(self):
        """发送HTML页面"""
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ArXiv论文分析监控</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1 { text-align: center; margin-bottom: 10px; color: #00d4ff; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }

        .card { background: #16213e; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card h2 { font-size: 14px; color: #888; margin-bottom: 10px; text-transform: uppercase; }
        .card .value { font-size: 36px; font-weight: bold; color: #00d4ff; }
        .card .sub { font-size: 12px; color: #666; margin-top: 5px; }

        .progress { background: #0f0f23; border-radius: 8px; height: 8px; margin-top: 10px; overflow: hidden; }
        .progress-bar { height: 100%; background: linear-gradient(90deg, #00d4ff, #00ff88); transition: width 0.3s; }

        .status-ok { color: #00ff88; }
        .status-warn { color: #ffaa00; }
        .status-error { color: #ff4444; }

        .table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .table th, .table td { padding: 8px; text-align: left; border-bottom: 1px solid #333; font-size: 12px; }
        .table th { color: #888; }

        .chart { height: 150px; background: #0f0f23; border-radius: 8px; margin-top: 10px; position: relative; overflow: hidden; }
        .chart-bar { position: absolute; bottom: 0; background: #00d4ff; opacity: 0.7; transition: height 0.3s; }

        .refresh { text-align: center; margin: 10px 0; color: #666; font-size: 12px; }

        .alert-box { border-radius: 12px; padding: 15px; margin-bottom: 20px; animation: pulse 2s infinite; }
        .alert-error { background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%); }
        .alert-warn { background: linear-gradient(135deg, #ffaa00 0%, #cc8800 100%); }
        .alert-ok { background: linear-gradient(135deg, #00ff88 0%, #00cc66 100%); }
        .alert-box h3 { margin-bottom: 10px; font-size: 16px; }
        .alert-box ul { margin-left: 20px; font-size: 14px; }
        .alert-box li { margin: 5px 0; }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
        }

        .big-number { font-size: 48px; font-weight: bold; }
        .good { color: #00ff88; }
        .bad { color: #ff4444; }
        .neutral { color: #00d4ff; }

        .indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
        .indicator-good { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
        .indicator-bad { background: #ff4444; box-shadow: 0 0 10px #ff4444; animation: blink 1s infinite; }
        .indicator-warn { background: #ffaa00; box-shadow: 0 0 10px #ffaa00; }

        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 ArXiv论文分析监控</h1>
        <div class="refresh" id="refresh-time">加载中... (每10秒自动刷新)</div>

        <div id="alert-box" class="alert-box alert-warn">
            <h3>⚠️ 系统状态检测中...</h3>
        </div>

        <div class="grid">
            <div class="card">
                <h2>论文分析进度</h2>
                <div class="value" id="analysis-progress">--</div>
                <div class="progress"><div class="progress-bar" id="analysis-bar" style="width: 0%"></div></div>
                <div class="sub">已分析 <span id="analyzed">--</span> / 总数 <span id="total">--</span></div>
            </div>

            <div class="card">
                <h2>PDF下载</h2>
                <div class="value" id="pdf-count">--</div>
                <div class="progress"><div class="progress-bar" id="pdf-bar" style="width: 0%"></div></div>
                <div class="sub">覆盖率 <span id="pdf-rate">--</span></div>
            </div>

            <div class="card">
                <h2>任务队列</h2>
                <div class="value"><span id="pending">--</span> <span style="font-size:16px;color:#888">待处理</span></div>
                <div class="sub">
                    运行中: <span id="running">--</span> |
                    已完成: <span id="completed">--</span> |
                    失败: <span id="failed" class="status-warn">--</span>
                </div>
            </div>

            <div class="card">
                <h2>质量问题</h2>
                <div class="value"><span id="issues">--</span> <span style="font-size:16px;color:#888">待修复</span></div>
                <div class="progress"><div class="progress-bar" id="issues-bar" style="width: 0%"></div></div>
                <div class="sub">已解决: <span id="resolved">--</span> (<span id="resolved-rate">--</span>)</div>
            </div>
        </div>

        <div class="grid" style="margin-top: 20px;">
            <div class="card">
                <h2>Worker进程</h2>
                <table class="table">
                    <thead><tr><th>进程</th><th>PID</th><th>状态</th><th>并发</th></tr></thead>
                    <tbody id="workers-table"></tbody>
                </table>
            </div>

            <div class="card">
                <h2>质量问题分布</h2>
                <table class="table">
                    <thead><tr><th>问题类型</th><th>数量</th></tr></thead>
                    <tbody id="issues-table"></tbody>
                </table>
            </div>

            <div class="card">
                <h2>处理速度 (最近1小时)</h2>
                <div class="value" id="speed">--</div>
                <div class="sub">篇/分钟</div>
                <div class="chart" id="speed-chart"></div>
            </div>

            <div class="card">
                <h2>系统状态</h2>
                <table class="table">
                    <tr><th>PDF同步</th><td id="sync-status">--</td></tr>
                    <tr><th>数据一致性</th><td id="consistency-status">--</td></tr>
                    <tr><th>最近更新</th><td id="last-update">--</td></tr>
                </table>
            </div>
        </div>

        <div class="card" style="margin-top: 20px;">
            <h2>最近失败任务</h2>
            <table class="table">
                <thead><tr><th>任务ID</th><th>类型</th><th>错误</th><th>时间</th></tr></thead>
                <tbody id="failed-tasks"></tbody>
            </table>
        </div>
    </div>

    <script>
        async function fetchAPI(endpoint) {
            try {
                const resp = await fetch(endpoint);
                return await resp.json();
            } catch (e) {
                console.error('API Error:', e);
                return null;
            }
        }

        async function refresh() {
            const stats = await fetchAPI('/api/stats');
            const issues = await fetchAPI('/api/issues');
            const workers = await fetchAPI('/api/workers');

            if (stats) {
                // 检测问题
                const problems = [];
                if (stats.failed > 10) problems.push('❌ 失败任务过多: ' + stats.failed + '个');
                if (stats.issues_unresolved > 1000) problems.push('⚠️ 质量问题待修复: ' + stats.issues_unresolved + '个');
                if (stats.pdf_sync > 0) problems.push('⚠️ PDF同步差异: ' + stats.pdf_sync);
                if (workers && workers.length === 0) problems.push('❌ 无Worker运行!');
                if (stats.running === 0 && stats.pending > 0) problems.push('⚠️ 有待处理任务但无运行中任务');
                if (stats.speed < 5 && stats.pending > 100) problems.push('⚠️ 处理速度过慢: ' + stats.speed + '篇/分钟');

                // 更新告警框
                const alertBox = document.getElementById('alert-box');
                if (problems.length === 0) {
                    alertBox.className = 'alert-box alert-ok';
                    alertBox.innerHTML = '<h3>✅ 系统运行正常</h3><ul><li>所有检查项通过</li></ul>';
                } else if (problems.some(p => p.includes('❌'))) {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerHTML = '<h3>❌ 发现严重问题</h3><ul>' + problems.map(p => '<li>' + p + '</li>').join('') + '</ul>';
                } else {
                    alertBox.className = 'alert-box alert-warn';
                    alertBox.innerHTML = '<h3>⚠️ 发现需要注意的问题</h3><ul>' + problems.map(p => '<li>' + p + '</li>').join('') + '</ul>';
                }

                // 主要指标 - 用颜色区分
                document.getElementById('analyzed').textContent = stats.analyzed;
                document.getElementById('total').textContent = stats.total;
                document.getElementById('analysis-progress').textContent = stats.progress + '%';
                document.getElementById('analysis-bar').style.width = stats.progress + '%';

                document.getElementById('pdf-count').textContent = stats.pdf_count;
                document.getElementById('pdf-rate').textContent = stats.pdf_rate + '%';
                document.getElementById('pdf-bar').style.width = stats.pdf_rate + '%';

                document.getElementById('pending').textContent = stats.pending;
                document.getElementById('running').textContent = stats.running;
                document.getElementById('completed').textContent = stats.completed;

                // 失败数用红色
                const failedEl = document.getElementById('failed');
                failedEl.textContent = stats.failed;
                failedEl.className = stats.failed > 10 ? 'status-error' : (stats.failed > 0 ? 'status-warn' : 'status-ok');

                // 质量问题用颜色
                const issuesEl = document.getElementById('issues');
                issuesEl.textContent = stats.issues_unresolved;
                issuesEl.className = stats.issues_unresolved > 1000 ? 'bad' : 'neutral';

                document.getElementById('resolved').textContent = stats.issues_resolved;
                document.getElementById('resolved-rate').textContent = stats.issues_rate + '%';
                document.getElementById('issues-bar').style.width = stats.issues_rate + '%';

                document.getElementById('speed').textContent = stats.speed || '--';
                document.getElementById('last-update').textContent = stats.last_update || '--';

                // 同步状态
                const syncStatus = document.getElementById('sync-status');
                if (stats.pdf_sync === 0) {
                    syncStatus.innerHTML = '<span class="indicator indicator-good"></span><span class="status-ok">正常</span>';
                } else {
                    syncStatus.innerHTML = '<span class="indicator indicator-warn"></span><span class="status-warn">差异 ' + stats.pdf_sync + '</span>';
                }

                const consistencyStatus = document.getElementById('consistency-status');
                consistencyStatus.innerHTML = '<span class="indicator indicator-good"></span><span class="status-ok">正常</span>';
            }

            if (issues) {
                const tbody = document.getElementById('issues-table');
                tbody.innerHTML = issues.map(i =>
                    '<tr><td>' + i.type + '</td><td class="' + (i.count > 500 ? 'status-warn' : '') + '">' + i.count + '</td></tr>'
                ).join('');
            }

            if (workers) {
                const tbody = document.getElementById('workers-table');
                if (workers.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="status-error">⚠️ 无Worker运行!</td></tr>';
                } else {
                    tbody.innerHTML = workers.map(w =>
                        '<tr><td><span class="indicator indicator-good"></span>' + w.name + '</td><td>' + w.pid + '</td><td class="status-ok">运行中</td><td>' + w.concurrent + '</td></tr>'
                    ).join('');
                }
            }

            document.getElementById('refresh-time').textContent =
                '最后更新: ' + new Date().toLocaleTimeString() + ' (每10秒自动刷新)';
        }

        refresh();
        setInterval(refresh, 10000);
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def send_json(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def get_stats(self):
        """获取统计数据"""
        stats = {}

        # 论文统计
        conn = sqlite3.connect(PAPERS_DB_PATH)
        stats["total"] = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        stats["analyzed"] = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE has_analysis=1"
        ).fetchone()[0]
        stats["pdf_count"] = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL"
        ).fetchone()[0]

        # PDF同步检查
        pdf_dir = DATA_DIR / "pdfs"
        pdf_files = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
        stats["pdf_sync"] = abs(pdf_files - stats["pdf_count"])
        stats["pdf_rate"] = round(stats["pdf_count"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0

        conn.close()

        stats["progress"] = round(stats["analyzed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0

        # 任务统计
        conn = sqlite3.connect(TASKS_DB_PATH)
        stats["pending"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='pending'"
        ).fetchone()[0]
        stats["running"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='running'"
        ).fetchone()[0]
        stats["completed"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='completed'"
        ).fetchone()[0]
        stats["failed"] = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='failed'"
        ).fetchone()[0]

        # 最近1小时处理速度
        hour_ago = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 使用SQLite的时间函数
        completed_hour = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status='completed' "
            "AND completed_at > datetime('now', '-1 hour')"
        ).fetchone()[0]
        stats["speed"] = round(completed_hour / 60, 1) if completed_hour > 0 else 0

        conn.close()

        # 质量问题统计
        if QUALITY_DB_PATH.exists():
            conn = sqlite3.connect(QUALITY_DB_PATH)
            stats["issues_resolved"] = conn.execute(
                "SELECT COUNT(*) FROM quality_issues WHERE resolved=1"
            ).fetchone()[0]
            stats["issues_unresolved"] = conn.execute(
                "SELECT COUNT(*) FROM quality_issues WHERE resolved=0"
            ).fetchone()[0]
            conn.close()
        else:
            stats["issues_resolved"] = 0
            stats["issues_unresolved"] = 0

        total_issues = stats["issues_resolved"] + stats["issues_unresolved"]
        stats["issues_rate"] = round(stats["issues_resolved"] / total_issues * 100, 1) if total_issues > 0 else 0

        stats["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return stats

    def get_issues(self):
        """获取问题类型分布"""
        issues = []
        if QUALITY_DB_PATH.exists():
            conn = sqlite3.connect(QUALITY_DB_PATH)
            rows = conn.execute(
                "SELECT issue_type, COUNT(*) as cnt FROM quality_issues "
                "WHERE resolved=0 GROUP BY issue_type ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            for row in rows:
                issues.append({"type": row[0], "count": row[1]})
            conn.close()
        return issues

    def get_workers(self):
        """获取Worker进程状态"""
        workers = []
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split("\n"):
                if "task_worker.py" in line:
                    parts = line.split()
                    workers.append({
                        "name": "task_worker",
                        "pid": parts[1],
                        "concurrent": self._extract_concurrent(line)
                    })
                elif "pdf_worker.py" in line:
                    parts = line.split()
                    workers.append({
                        "name": "pdf_worker",
                        "pid": parts[1],
                        "concurrent": self._extract_concurrent(line)
                    })
        except Exception:
            pass
        return workers

    def _extract_concurrent(self, line):
        """从命令行提取并发数"""
        if "--concurrent" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "--concurrent" and i + 1 < len(parts):
                    return parts[i + 1]
        return "?"

    def get_history(self):
        """获取历史数据（用于图表）"""
        if METRICS_AVAILABLE:
            return metrics_store.get_task_stats_history(hours=24)
        return []

    def get_metrics_history(self, hours: int = 24, metric_type: str = None):
        """获取指标历史数据"""
        if not METRICS_AVAILABLE:
            return {"error": "metrics_store module not available"}

        if metric_type:
            return metrics_store.get_metrics_history(metric_type, hours)
        else:
            # 返回所有类型的指标
            result = {}
            for mtype in ["cpu_percent", "memory_percent", "disk_percent", "speed_hour"]:
                result[mtype] = metrics_store.get_metrics_history(mtype, hours)
            return result

    def get_task_stats_history(self, hours: int = 24):
        """获取任务统计历史"""
        if not METRICS_AVAILABLE:
            return {"error": "metrics_store module not available"}
        return metrics_store.get_task_stats_history(hours)

    def get_quality_trends(self):
        """获取质量趋势数据"""
        trends = {}

        # Tier 分布
        conn = sqlite3.connect(PAPERS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tier, COUNT(*) FROM papers
            WHERE has_analysis=1
            GROUP BY tier
            ORDER BY tier
        """)
        trends["tier_distribution"] = dict(cursor.fetchall())

        # 总数
        cursor.execute("SELECT COUNT(*) FROM papers WHERE has_analysis=1")
        trends["analyzed_total"] = cursor.fetchone()[0]

        # 分析模式分布
        cursor.execute("""
            SELECT analysis_mode, COUNT(*) FROM papers
            WHERE has_analysis=1
            GROUP BY analysis_mode
        """)
        trends["analysis_mode"] = dict(cursor.fetchall())
        conn.close()

        # 质量问题趋势
        if QUALITY_DB_PATH.exists():
            conn = sqlite3.connect(QUALITY_DB_PATH)
            cursor = conn.cursor()

            # 问题类型分布
            cursor.execute("""
                SELECT issue_type, COUNT(*) FROM quality_issues
                WHERE resolved=0
                GROUP BY issue_type
                ORDER BY COUNT(*) DESC
            """)
            trends["issue_types"] = dict(cursor.fetchall())

            # 解决率
            cursor.execute("SELECT COUNT(*) FROM quality_issues WHERE resolved=1")
            resolved = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM quality_issues")
            total = cursor.fetchone()[0]
            trends["resolution_rate"] = round(resolved / total * 100, 1) if total > 0 else 0

            conn.close()

        trends["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return trends

    def get_performance(self):
        """获取实时性能数据"""
        perf = {}

        # 系统资源
        if METRICS_AVAILABLE:
            perf["resources"] = metrics_collector.collect_resources()

        # Worker 状态
        perf["workers"] = self.get_workers()

        # 任务队列状态
        conn = sqlite3.connect(TASKS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        perf["queue_status"] = dict(cursor.fetchall())
        conn.close()

        perf["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return perf

    def get_deep_task_stats(self):
        """获取任务队列深度分析"""
        stats = {}

        conn = sqlite3.connect(TASKS_DB_PATH)
        cursor = conn.cursor()

        # 状态分布
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        stats["status_distribution"] = dict(cursor.fetchall())

        # 失败任务详情
        cursor.execute("""
            SELECT id, task_type, error, completed_at
            FROM tasks
            WHERE status='failed'
            ORDER BY completed_at DESC
            LIMIT 20
        """)
        failed_rows = cursor.fetchall()
        stats["failed_tasks"] = [
            {"id": r[0], "type": r[1], "error": r[2], "time": r[3]}
            for r in failed_rows
        ]

        # 任务类型分布
        cursor.execute("""
            SELECT task_type, status, COUNT(*) FROM tasks
            GROUP BY task_type, status
        """)
        type_status = {}
        for row in cursor.fetchall():
            ttype, status, count = row
            if ttype not in type_status:
                type_status[ttype] = {}
            type_status[ttype][status] = count
        stats["type_status_distribution"] = type_status

        # 超时任务检测（running > 10分钟）
        cursor.execute("""
            SELECT id, task_type, started_at
            FROM tasks
            WHERE status='running'
            AND started_at < datetime('now', '-10 minutes')
        """)
        timeout_rows = cursor.fetchall()
        stats["timeout_tasks"] = [
            {"id": r[0], "type": r[1], "started_at": r[2]}
            for r in timeout_rows
        ]
        stats["timeout_count"] = len(timeout_rows)

        # 平均执行时长（最近完成的）
        cursor.execute("""
            SELECT AVG(
                (julianday(completed_at) - julianday(started_at)) * 86400
            )
            FROM tasks
            WHERE status='completed'
            AND completed_at > datetime('now', '-1 hour')
        """)
        stats["avg_duration_hour"] = cursor.fetchone()[0] or 0

        conn.close()

        stats["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return stats

    def get_alerts_history(self, limit: int = 20):
        """获取告警历史"""
        alerts = []
        if HEAL_HISTORY_DB_PATH.exists():
            conn = sqlite3.connect(HEAL_HISTORY_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, alert_type, message, notified
                FROM alerts
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            alerts = [
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "type": r[2],
                    "message": r[3],
                    "notified": r[4]
                }
                for r in rows
            ]
            conn.close()
        return alerts


def main():
    parser = argparse.ArgumentParser(description="ArXiv论文分析监控面板")
    parser.add_argument("--port", type=int, default=8899, help="服务端口")
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"监控面板启动: http://localhost:{args.port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")


if __name__ == "__main__":
    main()