#!/usr/bin/env python3
"""
数据库回滚脚本
用途：删除 knowledge_sync 表，回滚数据库改造

使用方法：
  python scripts/rollback_knowledge_sync.py                    # 只删除新表
  python scripts/rollback_knowledge_sync.py <backup_dir>       # 从备份恢复
"""

import sqlite3
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
import sys

def get_db_checksum(db_path: str) -> str:
    """计算数据库 checksum"""
    with open(db_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def rollback_knowledge_sync(backup_dir: str = None):
    """回滚 knowledge_sync 表

    Args:
        backup_dir: 备份目录路径，如果提供则从备份恢复
    """

    papers_db = Path.home() / "arxiv-paper-analyzer/backend/data/papers.db"

    print("="*50)
    print("数据库回滚")
    print("="*50)

    # 1. 如果提供了备份目录，从备份恢复
    if backup_dir:
        print(f"\n=== 从备份恢复 ===")
        backup_path = Path(backup_dir)
        backup_db = backup_path / "papers.db"

        if not backup_db.exists():
            print(f"❌ 备份文件不存在: {backup_db}")
            return False

        # 验证备份完整性
        backup_checksum = get_db_checksum(str(backup_db))
        print(f"备份文件: {backup_db}")
        print(f"备份大小: {backup_db.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"备份 checksum: {backup_checksum[:16]}...")

        # 创建当前数据库的备份
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_backup = papers_db.with_suffix(f".db.before_rollback_{timestamp}")
        shutil.copy2(papers_db, current_backup)
        print(f"当前数据库已备份到: {current_backup}")

        # 恢复备份
        shutil.copy2(backup_db, papers_db)
        print(f"✅ 已从备份恢复: {backup_db}")

        # 验证恢复
        restored_checksum = get_db_checksum(str(papers_db))
        if restored_checksum == backup_checksum:
            print("✅ 恢复验证通过")
        else:
            print("❌ 恢复验证失败！checksum 不匹配")
            return False

        return True

    # 2. 否则只删除新表
    print(f"\n=== 删除新表 ===")
    print(f"数据库: {papers_db}")

    conn = sqlite3.connect(papers_db)
    conn.execute("PRAGMA foreign_keys = ON")

    # 检查表是否存在
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_sync'"
    ).fetchall()

    if not tables:
        print("⚠️ knowledge_sync 表不存在，无需回滚")
        conn.close()
        return True

    # 统计要删除的数据
    count = conn.execute("SELECT COUNT(*) FROM knowledge_sync").fetchone()[0]
    print(f"将删除 knowledge_sync 表中的 {count} 条记录")

    # 删除新表和视图
    conn.execute("DROP TABLE IF EXISTS knowledge_sync")
    conn.execute("DROP VIEW IF EXISTS v_karpathy_synced")
    conn.execute("DROP TRIGGER IF EXISTS trg_knowledge_sync_updated")

    conn.commit()
    print("✅ 已删除 knowledge_sync 表及相关对象")

    # 验证完整性
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"数据库完整性: {integrity}")

    # 验证表已删除
    tables_after = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_sync'"
    ).fetchall()
    if not tables_after:
        print("✅ 确认表已删除")
    else:
        print("❌ 表删除失败")
        conn.close()
        return False

    conn.close()
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 从指定备份恢复
        backup_dir = sys.argv[1]
        success = rollback_knowledge_sync(backup_dir)
    else:
        # 只删除新表
        success = rollback_knowledge_sync()

    sys.exit(0 if success else 1)