#!/usr/bin/env python3
"""
数据完整性验证脚本
用途：验证 papers.db 和 knowledge_sync 表的数据完整性
"""

import sqlite3
from pathlib import Path

def verify_data_integrity():
    """验证数据完整性"""

    papers_db = Path.home() / "arxiv-paper-analyzer/backend/data/papers.db"
    karpathy_vault = Path.home() / "KarpathyVault"

    print("="*50)
    print("数据完整性验证")
    print("="*50)

    conn = sqlite3.connect(papers_db)
    conn.execute("PRAGMA foreign_keys = ON")

    # 1. 检查 papers.db 完整性
    print("\n=== 1. 数据库完整性 ===")
    result = conn.execute("PRAGMA integrity_check").fetchone()
    print(f"papers.db 完整性: {result[0]}")

    # 2. 检查 knowledge_sync 表是否存在
    print("\n=== 2. knowledge_sync 表 ===")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_sync'"
    ).fetchall()
    if tables:
        print("✅ knowledge_sync 表存在")
    else:
        print("❌ knowledge_sync 表不存在")
        conn.close()
        return False

    # 3. 检查外键约束
    print("\n=== 3. 外键约束检查 ===")
    orphans = conn.execute("""
        SELECT COUNT(*) FROM knowledge_sync k
        LEFT JOIN papers p ON k.paper_id = p.id
        WHERE p.id IS NULL
    """).fetchone()[0]
    print(f"孤立记录数: {orphans}")

    if orphans > 0:
        print("❌ 发现孤立记录!")
    else:
        print("✅ 无孤立记录")

    # 4. 检查唯一约束
    print("\n=== 4. 唯一约束检查 ===")
    duplicates = conn.execute("""
        SELECT paper_id, COUNT(*) as cnt
        FROM knowledge_sync
        GROUP BY paper_id
        HAVING cnt > 1
    """).fetchall()
    if duplicates:
        print(f"❌ 发现重复记录: {len(duplicates)} 条")
        for paper_id, cnt in duplicates[:5]:
            print(f"  paper_id={paper_id}: {cnt} 次")
    else:
        print("✅ 无重复记录")

    # 5. 检查文件系统一致性
    print("\n=== 5. 文件系统一致性 ===")
    synced = conn.execute("""
        SELECT raw_path, wiki_path FROM knowledge_sync
        WHERE sync_status = 'synced' AND raw_path IS NOT NULL
    """).fetchall()

    missing_files = 0
    for raw_path, wiki_path in synced[:100]:  # 只检查前100条
        if raw_path and not Path(raw_path).exists():
            missing_files += 1
            print(f"  缺失文件: {raw_path}")

    print(f"缺失文件数: {missing_files}/{len(synced)}")

    # 6. 统计摘要
    print("\n=== 6. 数据统计 ===")
    stats = {
        "papers_total": conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
        "papers_analyzed": conn.execute("SELECT COUNT(*) FROM papers WHERE has_analysis=1").fetchone()[0],
        "sync_total": conn.execute("SELECT COUNT(*) FROM knowledge_sync").fetchone()[0],
        "sync_pending": conn.execute("SELECT COUNT(*) FROM knowledge_sync WHERE sync_status='pending'").fetchone()[0],
        "sync_synced": conn.execute("SELECT COUNT(*) FROM knowledge_sync WHERE sync_status='synced'").fetchone()[0],
        "sync_failed": conn.execute("SELECT COUNT(*) FROM knowledge_sync WHERE sync_status='failed'").fetchone()[0],
    }

    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 7. 检查触发器
    print("\n=== 7. 触发器检查 ===")
    triggers = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='knowledge_sync'"
    ).fetchall()
    if triggers:
        for (name,) in triggers:
            print(f"✅ 触发器: {name}")
    else:
        print("⚠️ 无触发器")

    # 8. 检查索引
    print("\n=== 8. 索引检查 ===")
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='knowledge_sync'"
    ).fetchall()
    for (name,) in indexes:
        print(f"✅ 索引: {name}")

    conn.close()

    # 总结
    print("\n" + "="*50)
    if orphans == 0 and missing_files == 0 and len(duplicates) == 0:
        print("✅ 数据完整性验证通过!")
        return True
    else:
        print("❌ 数据完整性验证失败!")
        return False

if __name__ == "__main__":
    verify_data_integrity()