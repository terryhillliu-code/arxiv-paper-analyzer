#!/usr/bin/env python3
"""修复质量问题论文。

重新分析存在质量问题的论文：
1. 从quality_issues.db获取问题论文列表
2. 创建重新分析任务（使用新Prompt）
3. 分析完成后标记问题已解决

支持按问题类型筛选：
    --issue-type fabricated,fabricated_numbers
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tasks.task_queue import TaskQueue, TASK_DB_PATH
from app.tasks.analysis_task import register_analysis_handler

# 数据库路径
PAPERS_DB = Path(__file__).parent.parent / "data" / "papers.db"
QUALITY_DB = Path(__file__).parent.parent / "data" / "quality_issues.db"


def get_problem_papers(issue_types: list = None):
    """获取需要重新分析的论文

    Args:
        issue_types: 问题类型列表，如 ["fabricated", "fabricated_numbers"]
                    如果为 None，则获取所有未解决的问题论文
    """
    conn = sqlite3.connect(str(QUALITY_DB))
    c = conn.cursor()

    if issue_types:
        # 按指定问题类型筛选
        placeholders = ','.join(['?' for _ in issue_types])
        c.execute(f'''
            SELECT DISTINCT arxiv_id
            FROM quality_issues
            WHERE resolved = 0
            AND issue_type IN ({placeholders})
        ''', issue_types)
    else:
        # 获取所有未解决的问题
        c.execute('''
            SELECT DISTINCT arxiv_id
            FROM quality_issues
            WHERE resolved = 0
        ''')

    arxiv_ids = [row[0] for row in c.fetchall()]
    conn.close()

    if not arxiv_ids:
        return []

    # 获取对应的paper_id
    conn2 = sqlite3.connect(str(PAPERS_DB))
    c2 = conn2.cursor()
    c2.execute(f'''
        SELECT id, arxiv_id, title
        FROM papers
        WHERE arxiv_id IN ({','.join(['?' for _ in arxiv_ids])})
        AND has_analysis = 1
    ''', arxiv_ids)
    papers = c2.fetchall()
    conn2.close()

    return papers


def mark_issues_resolved(arxiv_id: str):
    """标记问题已解决"""
    conn = sqlite3.connect(str(QUALITY_DB))
    c = conn.cursor()
    c.execute('''
        UPDATE quality_issues
        SET resolved = 1, resolved_at = datetime('now')
        WHERE arxiv_id = ? AND resolved = 0
    ''', (arxiv_id,))
    conn.commit()
    conn.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="修复质量问题论文")
    parser.add_argument("--limit", type=int, default=50, help="最大处理数量")
    parser.add_argument("--dry-run", action="store_true", help="仅显示计划，不执行")
    parser.add_argument("--issue-type", type=str, default=None,
                        help="指定问题类型，多个用逗号分隔，如: fabricated,fabricated_numbers")
    args = parser.parse_args()

    print("=" * 60)
    print("质量问题修复工具")
    print("=" * 60)

    # 解析问题类型
    issue_types = None
    if args.issue_type:
        issue_types = [t.strip() for t in args.issue_type.split(",")]
        print(f"筛选问题类型: {issue_types}")

    # 获取问题论文
    papers = get_problem_papers(issue_types)
    print(f"发现 {len(papers)} 篇问题论文")

    if not papers:
        print("无需修复")
        return

    # 限制数量
    papers = papers[:args.limit]

    if args.dry_run:
        print("\n计划重新分析:")
        for paper_id, arxiv_id, title in papers:
            print(f"  [{arxiv_id}] {title[:40]}...")
        return

    # 创建任务队列
    task_queue = TaskQueue(db_path=TASK_DB_PATH, max_concurrent=5)
    register_analysis_handler(task_queue)

    print(f"\n创建 {len(papers)} 个重新分析任务...")

    created = 0
    for paper_id, arxiv_id, title in papers:
        task = task_queue.create_task(
            task_type="analysis",
            payload={
                "paper_id": paper_id,
                "quick_mode": True,
                "force_refresh": True,  # 强制刷新
            }
        )
        created += 1
        print(f"  ✓ [{arxiv_id}] task_id={task.id}")

    print(f"\n✅ 已创建 {created} 个任务")
    print("\n任务将由后台Worker自动处理，新Prompt将生成更高质量的分析")


if __name__ == "__main__":
    asyncio.run(main())