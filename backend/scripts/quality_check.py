#!/usr/bin/env python3
"""定期抽查文档质量。

检查最新生成的文档：
1. JSON字段完整性
2. 报告长度
3. 数字编造检测

记录问题到数据库和日志文件。
"""

import json
import random
import sqlite3
import re
from pathlib import Path
from datetime import datetime

# 问题记录数据库路径
QUALITY_DB_PATH = Path(__file__).parent.parent / "data" / "quality_issues.db"
QUALITY_LOG_PATH = Path(__file__).parent.parent / "logs" / "quality_issues.log"
# 其他数据库路径（用于创建修复任务）
PAPERS_DB_PATH = Path(__file__).parent.parent / "data" / "papers.db"
TASK_DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"


def _ensure_quality_db():
    """确保问题记录数据库存在"""
    QUALITY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(QUALITY_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arxiv_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            issue_detail TEXT,
            checked_at TEXT NOT NULL,
            resolved INTEGER DEFAULT 0,
            resolved_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _log_issue(arxiv_id: str, issue_type: str, issue_detail: str):
    """记录问题到数据库和日志"""
    checked_at = datetime.now().isoformat()

    # 写入数据库
    conn = sqlite3.connect(QUALITY_DB_PATH)
    conn.execute("""
        INSERT INTO quality_issues (arxiv_id, issue_type, issue_detail, checked_at)
        VALUES (?, ?, ?, ?)
    """, (arxiv_id, issue_type, issue_detail, checked_at))
    conn.commit()
    conn.close()

    # 写入日志文件
    QUALITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUALITY_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{checked_at} | {arxiv_id} | {issue_type} | {issue_detail}\n")


def check_json_fields(analysis_json: dict, quick_mode: bool = False) -> dict:
    """检查JSON字段完整性"""
    # quick_mode 只需要基本字段
    if quick_mode:
        required_fields = [
            "tier", "tags", "one_line_summary", "key_contributions", "outline"
        ]
    else:
        required_fields = [
            "tier", "tags", "one_line_summary", "key_contributions",
            "outline", "methodology", "strengths", "weaknesses"
        ]
    missing = []
    empty = []

    for field in required_fields:
        if field not in analysis_json:
            missing.append(field)
        elif analysis_json.get(field) in [None, [], ""]:
            empty.append(field)

    return {"missing": missing, "empty": empty}


def check_number_fabrication(abstract: str, one_line_summary: str) -> dict:
    """检查数字是否来自摘要"""
    if not abstract or not one_line_summary:
        return {"status": "skipped", "reason": "缺少摘要或总结"}

    # 提取总结中的数字
    numbers_in_summary = re.findall(r'\d+\.?\d*%', one_line_summary)
    numbers_in_summary += re.findall(r'\d+\.?\d*倍', one_line_summary)

    # 清理摘要中的LaTeX格式（如 16.59\% -> 16.59%）
    abstract_cleaned = abstract.replace('\\%', '%')

    fabricated = []
    for num in numbers_in_summary:
        if num not in abstract_cleaned:
            fabricated.append(num)

    return {
        "status": "pass" if not fabricated else "warning",
        "fabricated_numbers": fabricated
    }


def check_deep_quality(analysis_json: dict, abstract: str) -> dict:
    """检查深度分析质量"""
    issues = []

    # 1. 一句话总结质量（必须80-150字）
    summary = analysis_json.get("one_line_summary", "")
    if summary:
        if len(summary) < 80:
            issues.append(("short_summary", f"总结太短({len(summary)}字，需80-150字)"))
        elif len(summary) > 200:
            issues.append(("long_summary", f"总结太长({len(summary)}字，需80-150字)"))

    # 2. 关键贡献质量（每条至少25字）
    contributions = analysis_json.get("key_contributions", [])
    if not contributions or len(contributions) == 0:
        issues.append(("no_contributions", "无关键贡献"))
    elif len(contributions) < 2:
        issues.append(("few_contributions", f"关键贡献过少({len(contributions)}条)"))
    else:
        # 检查贡献是否空洞
        for i, contrib in enumerate(contributions[:2]):
            contrib_str = str(contrib)
            if len(contrib_str) < 25:
                issues.append(("thin_contribution", f"贡献{i+1}内容单薄({len(contrib_str)}字)"))

    # 3. 大纲质量
    outline = analysis_json.get("outline", [])
    if not outline or len(outline) == 0:
        issues.append(("no_outline", "无大纲"))
    elif len(outline) < 2:
        issues.append(("thin_outline", f"大纲过简({len(outline)}节)"))

    # 4. 标签质量
    tags = analysis_json.get("tags", [])
    if not tags or len(tags) == 0:
        issues.append(("no_tags", "无标签"))
    elif len(tags) < 2:
        issues.append(("few_tags", f"标签过少({len(tags)}个)"))

    return {"issues": issues, "issue_count": len(issues)}


def sample_check(sample_size: int = 5):
    """抽查最近生成的文档"""
    # 确保问题记录数据库存在
    _ensure_quality_db()

    conn = sqlite3.connect('data/papers.db')
    c = conn.cursor()

    # 随机抽查最近分析的论文（包含 analysis_mode）
    c.execute("""
        SELECT id, arxiv_id, title, abstract, analysis_json, analysis_report, analysis_mode
        FROM papers
        WHERE has_analysis = 1
        AND LENGTH(abstract) >= 100
        AND LENGTH(analysis_json) >= 500
        ORDER BY RANDOM()
        LIMIT ?
    """, (sample_size,))

    samples = c.fetchall()
    conn.close()

    print("=" * 60)
    print(f"质量抽查报告 - 样本数: {len(samples)}")
    print("=" * 60)

    issues = []

    for paper_id, arxiv_id, title, abstract, analysis_json, report, analysis_mode in samples:
        print(f"\n📄 [{arxiv_id}] {title[:40]}...")

        try:
            json_data = json.loads(analysis_json)
        except:
            print("  ❌ JSON解析失败")
            issues.append((arxiv_id, "JSON解析失败", ""))
            _log_issue(arxiv_id, "json_parse_failed", "JSON解析失败")
            continue

        # 检查字段完整性（根据 analysis_mode）
        is_quick_mode = analysis_mode in ['quick', 'historical']
        field_check = check_json_fields(json_data, quick_mode=is_quick_mode)
        if field_check["missing"]:
            print(f"  ⚠️ 缺失字段: {field_check['missing']}")
            detail = str(field_check['missing'])
            issues.append((arxiv_id, "缺失字段", detail))
            _log_issue(arxiv_id, "missing_fields", detail)
        elif field_check["empty"]:
            print(f"  ⚠️ 空字段: {field_check['empty']}")
            detail = str(field_check['empty'])
            issues.append((arxiv_id, "空字段", detail))
            _log_issue(arxiv_id, "empty_fields", detail)
        else:
            print("  ✅ 字段完整")

        # 检查数字编造
        one_line = json_data.get("one_line_summary", "")
        fabric_check = check_number_fabrication(abstract, one_line)
        if fabric_check["status"] == "warning":
            print(f"  ⚠️ 可能编造数字: {fabric_check['fabricated_numbers']}")
            detail = str(fabric_check['fabricated_numbers'])
            issues.append((arxiv_id, "编造数字", detail))
            _log_issue(arxiv_id, "fabricated_numbers", detail)
        else:
            print("  ✅ 数字来源正常")

        # 检查深度分析质量
        deep_check = check_deep_quality(json_data, abstract)
        if deep_check["issue_count"] > 0:
            for issue_type, issue_detail in deep_check["issues"]:
                print(f"  ⚠️ 深度质量: {issue_detail}")
                issues.append((arxiv_id, issue_type, issue_detail))
                _log_issue(arxiv_id, f"deep_{issue_type}", issue_detail)
        else:
            print("  ✅ 深度分析质量正常")

        # 检查报告长度
        if report and len(report) >= 500:
            print(f"  ✅ 报告长度: {len(report)} 字符")
        else:
            print(f"  ⚠️ 报告过短: {len(report) if report else 0} 字符")

    print("\n" + "=" * 60)
    if issues:
        print(f"发现问题: {len(issues)} 个")
        for arxiv_id, issue_type, detail in issues:
            print(f"  - {arxiv_id}: {issue_type} {detail}")
        print(f"问题已记录到: {QUALITY_DB_PATH} 和 {QUALITY_LOG_PATH}")

        # 自动创建force_refresh任务修复问题
        _create_force_refresh_tasks(issues)
    else:
        print("✅ 所有样本质量正常")
    print("=" * 60)

    return issues


def _create_force_refresh_tasks(issues):
    """为问题论文创建force_refresh任务"""
    import uuid

    # 获取唯一的arxiv_id列表
    arxiv_ids = list(set(issue[0] for issue in issues))
    if not arxiv_ids:
        return

    conn_p = sqlite3.connect(PAPERS_DB_PATH)
    conn_t = sqlite3.connect(TASK_DB_PATH)

    c_p = conn_p.cursor()
    c_t = conn_t.cursor()

    created = 0
    for arxiv_id in arxiv_ids:
        # 获取paper_id
        c_p.execute('SELECT id FROM papers WHERE arxiv_id=?', (arxiv_id,))
        paper = c_p.fetchone()
        if not paper:
            continue

        paper_id = paper[0]

        # 检查是否已有pending/running的force_refresh任务
        c_t.execute('''
            SELECT id FROM tasks
            WHERE task_type='force_refresh'
            AND status IN ('pending', 'running')
            AND json_extract(payload, '$.paper_id')=?
        ''', (paper_id,))
        if c_t.fetchone():
            continue  # 已有任务，跳过

        # 创建任务
        task_id = str(uuid.uuid4())[:8]
        payload = f'{{"paper_id": {paper_id}}}'
        c_t.execute('''
            INSERT INTO tasks (id, task_type, payload, status, created_at)
            VALUES (?, 'force_refresh', ?, 'pending', datetime('now'))
        ''', (task_id, payload))
        created += 1

    conn_t.commit()
    conn_p.close()
    conn_t.close()

    if created > 0:
        print(f"已创建 {created} 个force_refresh任务用于修复")


def show_stats():
    """显示问题统计"""
    if not QUALITY_DB_PATH.exists():
        print("暂无质量检查记录")
        return

    conn = sqlite3.connect(QUALITY_DB_PATH)
    c = conn.cursor()

    # 总体统计
    c.execute("SELECT COUNT(*) FROM quality_issues")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM quality_issues WHERE resolved = 1")
    resolved = c.fetchone()[0]

    print("=" * 60)
    print("质量问题统计")
    print("=" * 60)
    print(f"总问题数: {total}")
    print(f"已解决: {resolved}")
    print(f"未解决: {total - resolved}")

    # 按类型统计
    print("\n问题类型分布:")
    c.execute("""
        SELECT issue_type, COUNT(*) as cnt
        FROM quality_issues
        WHERE resolved = 0
        GROUP BY issue_type
        ORDER BY cnt DESC
    """)
    for issue_type, cnt in c.fetchall():
        print(f"  - {issue_type}: {cnt}")

    # 最近问题
    print("\n最近10条未解决问题:")
    c.execute("""
        SELECT arxiv_id, issue_type, issue_detail, checked_at
        FROM quality_issues
        WHERE resolved = 0
        ORDER BY checked_at DESC
        LIMIT 10
    """)
    for arxiv_id, issue_type, detail, checked_at in c.fetchall():
        checked_time = checked_at.split("T")[0] if "T" in checked_at else checked_at[:10]
        print(f"  [{checked_time}] {arxiv_id}: {issue_type} {detail[:50]}")

    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=5, help="抽查样本数")
    parser.add_argument("--stats", action="store_true", help="显示问题统计")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        sample_check(args.sample)