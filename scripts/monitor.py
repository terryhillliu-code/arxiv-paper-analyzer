#!/usr/bin/env python3
"""ArXiv 系统监控仪表板。

显示系统各组件的状态和关键指标。
"""

import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path


class SystemMonitor:
    """系统监控器"""

    def __init__(self):
        self.data_dir = Path.home() / "arxiv-paper-analyzer" / "backend" / "data"
        self.db_path = self.data_dir / "papers.db"
        self.tasks_db_path = self.data_dir / "tasks.db"

    def get_service_status(self) -> dict:
        """获取服务状态"""
        services = {}

        # Backend
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True
        )
        services["backend"] = "com.arxiv.backend" in result.stdout
        services["frontend"] = "com.arxiv.frontend" in result.stdout

        # 检查端口
        result = subprocess.run(
            ["lsof", "-i", ":8000"],
            capture_output=True, text=True
        )
        services["backend_port"] = "LISTEN" in result.stdout

        result = subprocess.run(
            ["lsof", "-i", ":5173"],
            capture_output=True, text=True
        )
        services["frontend_port"] = "LISTEN" in result.stdout

        return services

    def get_database_stats(self) -> dict:
        """获取数据库统计"""
        stats = {}

        if self.db_path.exists():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 论文数量
            cursor.execute("SELECT COUNT(*) FROM papers")
            stats["papers"] = cursor.fetchone()[0]

            # 已分析论文
            cursor.execute("SELECT COUNT(*) FROM papers WHERE analysis_report IS NOT NULL")
            stats["analyzed"] = cursor.fetchone()[0]

            # 最近 7 天新增
            cursor.execute("""
                SELECT COUNT(*) FROM papers
                WHERE created_at >= date('now', '-7 days')
            """)
            stats["recent_7days"] = cursor.fetchone()[0]

            # 数据库大小
            stats["db_size_mb"] = round(self.db_path.stat().st_size / 1024 / 1024, 2)

            conn.close()

        if self.tasks_db_path.exists():
            conn = sqlite3.connect(self.tasks_db_path)
            cursor = conn.cursor()

            # 待处理任务
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
            stats["pending_tasks"] = cursor.fetchone()[0]

            # 处理中任务
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'processing'")
            stats["processing_tasks"] = cursor.fetchone()[0]

            conn.close()

        return stats

    def get_storage_stats(self) -> dict:
        """获取存储统计"""
        stats = {}

        # PDF 存储
        pdf_dir = self.data_dir / "pdfs"
        if pdf_dir.exists():
            pdf_files = list(pdf_dir.glob("*.pdf"))
            stats["pdf_count"] = len(pdf_files)
            stats["pdf_size_gb"] = round(
                sum(f.stat().st_size for f in pdf_files) / 1024 / 1024 / 1024, 2
            )

        # 缓存
        cache_dir = self.data_dir / "mineru_cache"
        if cache_dir.exists():
            cache_files = list(cache_dir.rglob("*"))
            stats["cache_files"] = len([f for f in cache_files if f.is_file()])
            stats["cache_size_mb"] = round(
                sum(f.stat().st_size for f in cache_files if f.is_file()) / 1024 / 1024, 2
            )

        # 备份
        backup_dir = Path.home() / "arxiv-paper-analyzer" / "backups"
        if backup_dir.exists():
            backups = list(backup_dir.glob("*.db"))
            stats["backup_count"] = len(backups)
            stats["backup_size_mb"] = round(
                sum(f.stat().st_size for f in backups) / 1024 / 1024, 2
            )

        return stats

    def get_system_resources(self) -> dict:
        """获取系统资源"""
        resources = {}

        # 磁盘空间
        result = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            resources["disk_total"] = parts[1]
            resources["disk_used"] = parts[2]
            resources["disk_avail"] = parts[3]
            resources["disk_percent"] = parts[4]

        # 内存
        result = subprocess.run(
            ["vm_stat"],
            capture_output=True, text=True
        )
        pages_free = 0
        pages_total = 0
        for line in result.stdout.split("\n"):
            if "Pages free" in line:
                pages_free = int(line.split(":")[1].strip().rstrip("."))
            elif "Pages active" in line or "Pages inactive" in line or "Pages wired" in line:
                pages_total += int(line.split(":")[1].strip().rstrip("."))

        page_size = 16384  # macOS default
        resources["memory_free_gb"] = round(pages_free * page_size / 1024 / 1024 / 1024, 2)
        resources["memory_used_gb"] = round(pages_total * page_size / 1024 / 1024 / 1024, 2)

        return resources

    def get_health_check(self) -> dict:
        """健康检查"""
        health = {"status": "ok", "checks": []}

        # 数据库检查
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            conn.close()

            if result == "ok":
                health["checks"].append({"name": "database", "status": "ok"})
            else:
                health["checks"].append({"name": "database", "status": "error", "detail": result})
                health["status"] = "degraded"
        except Exception as e:
            health["checks"].append({"name": "database", "status": "error", "detail": str(e)})
            health["status"] = "error"

        # 磁盘空间检查
        resources = self.get_system_resources()
        avail_gb = float(resources.get("disk_avail", "0").rstrip("Gi"))
        if avail_gb < 10:
            health["checks"].append({
                "name": "disk_space",
                "status": "warning",
                "detail": f"仅剩 {avail_gb}GB"
            })
            if health["status"] == "ok":
                health["status"] = "degraded"
        else:
            health["checks"].append({"name": "disk_space", "status": "ok"})

        return health

    def generate_report(self, format: str = "text") -> str:
        """生成监控报告"""
        services = self.get_service_status()
        db_stats = self.get_database_stats()
        storage = self.get_storage_stats()
        resources = self.get_system_resources()
        health = self.get_health_check()

        if format == "json":
            return json.dumps({
                "timestamp": datetime.now().isoformat(),
                "services": services,
                "database": db_stats,
                "storage": storage,
                "resources": resources,
                "health": health,
            }, indent=2, ensure_ascii=False)

        # 文本格式
        lines = [
            "=" * 60,
            " ArXiv 平台监控报告",
            f" 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            "【服务状态】",
            f"  Backend:  {'✅ 运行中' if services.get('backend') else '❌ 已停止'}",
            f"  Frontend: {'✅ 运行中' if services.get('frontend') else '❌ 已停止'}",
            "",
            "【数据库统计】",
            f"  论文总数: {db_stats.get('papers', 0):,}",
            f"  已分析:   {db_stats.get('analyzed', 0):,}",
            f"  近7天新增: {db_stats.get('recent_7days', 0):,}",
            f"  待处理任务: {db_stats.get('pending_tasks', 0)}",
            f"  数据库大小: {db_stats.get('db_size_mb', 0)} MB",
            "",
            "【存储统计】",
            f"  PDF 文件: {storage.get('pdf_count', 0)} ({storage.get('pdf_size_gb', 0)} GB)",
            f"  缓存文件: {storage.get('cache_files', 0)} ({storage.get('cache_size_mb', 0)} MB)",
            f"  备份数量: {storage.get('backup_count', 0)} ({storage.get('backup_size_mb', 0)} MB)",
            "",
            "【系统资源】",
            f"  磁盘: {resources.get('disk_used', '?')}/{resources.get('disk_total', '?')} "
            f"(可用 {resources.get('disk_avail', '?')})",
            f"  内存: {resources.get('memory_used_gb', 0)} GB 已用, "
            f"{resources.get('memory_free_gb', 0)} GB 可用",
            "",
            "【健康状态】",
        ]

        for check in health.get("checks", []):
            status_icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(check["status"], "❓")
            lines.append(f"  {status_icon} {check['name']}: {check.get('detail', 'ok')}")

        lines.extend([
            "",
            f"  总体状态: {health['status'].upper()}",
            "=" * 60,
        ])

        return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv 系统监控")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--health", action="store_true", help="仅显示健康状态")
    args = parser.parse_args()

    monitor = SystemMonitor()

    if args.health:
        health = monitor.get_health_check()
        print(json.dumps(health, indent=2))
        return 0 if health["status"] in ("ok", "degraded") else 1

    format_type = "json" if args.json else "text"
    print(monitor.generate_report(format_type))


if __name__ == "__main__":
    sys.exit(main())