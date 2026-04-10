#!/usr/bin/env python3
"""系统自动巡检脚本。

检查项目：
1. PDF文件与数据库同步
2. 任务队列状态
3. 数据一致性
4. 质量问题统计
5. Worker进程状态
"""

import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = BASE_DIR / "logs" / "health_check.log"


def log(msg: str):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_pdf_sync():
    """检查PDF同步状态"""
    pdf_dir = DATA_DIR / "pdfs"
    pdf_files = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0

    conn = sqlite3.connect(DATA_DIR / "papers.db")
    db_records = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL"
    ).fetchone()[0]

    # 检查数据库记录但文件不存在的情况
    missing_files = conn.execute(
        "SELECT arxiv_id, pdf_local_path FROM papers WHERE pdf_local_path IS NOT NULL"
    ).fetchall()
    conn.close()

    broken_links = 0
    for arxiv_id, path in missing_files:
        full_path = DATA_DIR.parent / path if path.startswith("data/") else Path(path)
        if not full_path.exists():
            broken_links += 1

    diff = pdf_files - db_records
    if diff != 0 or broken_links > 0:
        log(f"⚠️ PDF同步: 文件{pdf_files}个, 数据库{db_records}条, 差异{diff}, 断链{broken_links}")
        return False
    else:
        log(f"✅ PDF同步: 文件{pdf_files}个, 数据库{db_records}条")
        return True


def check_tasks():
    """检查任务队列"""
    conn = sqlite3.connect(DATA_DIR / "tasks.db")

    pending = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='pending'"
    ).fetchone()[0]

    running = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='running'"
    ).fetchone()[0]

    failed = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='failed'"
    ).fetchone()[0]

    stuck = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='running' "
        "AND started_at < datetime('now', '-1 hour')"
    ).fetchone()[0]

    conn.close()

    issues = []
    if failed > 20:
        issues.append(f"failed任务过多({failed})")
    if stuck > 0:
        issues.append(f"stuck任务({stuck})")

    if issues:
        log(f"⚠️ 任务队列: pending={pending}, running={running}, failed={failed}, stuck={stuck}")
        return False
    else:
        log(f"✅ 任务队列: pending={pending}, running={running}, failed={failed}")
        return True


def check_quality_issues():
    """检查质量问题"""
    db_path = DATA_DIR / "quality_issues.db"
    if not db_path.exists():
        log("✅ 质量问题: 数据库不存在")
        return True

    conn = sqlite3.connect(db_path)

    unresolved = conn.execute(
        "SELECT COUNT(*) FROM quality_issues WHERE resolved=0"
    ).fetchone()[0]

    # 按类型统计
    types = conn.execute(
        "SELECT issue_type, COUNT(*) FROM quality_issues "
        "WHERE resolved=0 GROUP BY issue_type ORDER BY COUNT(*) DESC LIMIT 3"
    ).fetchall()

    conn.close()

    if unresolved > 5000:
        log(f"⚠️ 质量问题: {unresolved}个未解决")
        return False
    else:
        log(f"✅ 质量问题: {unresolved}个未解决")
        return True


def check_workers():
    """检查Worker进程状态"""
    workers = []

    # 使用pgrep检查进程
    try:
        # 检查task_worker
        result = subprocess.run(
            ["pgrep", "-f", "task_worker.py"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            workers.append(("task_worker", True))
        else:
            workers.append(("task_worker", False))

        # 检查pdf_worker
        result = subprocess.run(
            ["pgrep", "-f", "pdf_worker.py"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            workers.append(("pdf_worker", True))
        else:
            workers.append(("pdf_worker", False))
    except Exception:
        pass

    running = [w[0] for w in workers if w[1]]
    stopped = [w[0] for w in workers if not w[1]]

    if len(stopped) == 0:
        log(f"✅ Worker: {', '.join(running)} 运行中")
        return True
    else:
        log(f"⚠️ Worker: {', '.join(stopped)} 未运行")
        return False


def check_data_consistency():
    """检查数据一致性"""
    conn = sqlite3.connect(DATA_DIR / "papers.db")

    # 检查has_analysis与实际内容是否一致
    bad1 = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE has_analysis=1 "
        "AND (analysis_json IS NULL OR LENGTH(analysis_json) < 500)"
    ).fetchone()[0]

    bad2 = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE has_analysis=0 "
        "AND analysis_json IS NOT NULL AND LENGTH(analysis_json) > 500"
    ).fetchone()[0]

    conn.close()

    if bad1 > 0 or bad2 > 0:
        log(f"⚠️ 数据一致性: has_analysis不匹配({bad1}+{bad2})")
        return False
    else:
        log("✅ 数据一致性: 正常")
        return True


def main():
    log("=" * 50)
    log("系统巡检开始")
    log("=" * 50)

    results = []
    results.append(("PDF同步", check_pdf_sync()))
    results.append(("任务队列", check_tasks()))
    results.append(("数据一致性", check_data_consistency()))
    results.append(("质量问题", check_quality_issues()))
    results.append(("Worker进程", check_workers()))

    log("-" * 50)
    issues = [name for name, ok in results if not ok]
    if issues:
        log(f"巡检完成，发现{len(issues)}个问题: {', '.join(issues)}")
    else:
        log("巡检完成，所有检查项正常")
    log("=" * 50)


if __name__ == "__main__":
    main()