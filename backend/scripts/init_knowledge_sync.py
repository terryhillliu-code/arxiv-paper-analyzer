#!/usr/bin/env python3
"""
数据库改造初始化脚本
用途：创建 knowledge_sync 表，追踪论文 → KarpathyVault 的同步状态
"""

import sqlite3
import hashlib
import time
from pathlib import Path
from datetime import datetime

# ==================== 工具函数 ====================

def get_db_checksum(db_path: str) -> str:
    """计算数据库 checksum，用于验证备份完整性"""
    with open(db_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def validate_path(path: str) -> bool:
    """验证路径在允许范围内，防止路径遍历攻击"""
    allowed_prefixes = [
        str(Path.home() / "KarpathyVault"),
        str(Path.home() / "Documents" / "ZhiweiVault"),
    ]
    abs_path = str(Path(path).resolve())
    return any(abs_path.startswith(prefix) for prefix in allowed_prefixes)

def with_retry(func, max_retries=3, delay=0.5):
    """带重试的数据库操作，处理 SQLite 锁冲突"""
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))  # 指数退避
                continue
            raise

# ==================== 主函数 ====================

def init_knowledge_sync():
    """初始化 knowledge_sync 表，从现有数据推断状态"""

    papers_db = Path.home() / "arxiv-paper-analyzer/backend/data/papers.db"

    if not papers_db.exists():
        print(f"❌ 数据库不存在: {papers_db}")
        return False

    print(f"数据库路径: {papers_db}")
    print(f"数据库大小: {papers_db.stat().st_size / 1024 / 1024:.1f} MB")

    # 1. 计算原始数据库 checksum
    print("\n=== Step 1: 计算原始 checksum ===")
    original_checksum = get_db_checksum(str(papers_db))
    print(f"原始 checksum: {original_checksum[:16]}...")

    conn = sqlite3.connect(papers_db)

    # 2. 启用外键约束（SQLite 默认关闭）
    print("\n=== Step 2: 启用外键约束 ===")
    conn.execute("PRAGMA foreign_keys = ON")
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    print(f"外键约束状态: {'启用' if result[0] else '禁用'}")

    # 3. 检查表是否已存在
    print("\n=== Step 3: 检查现有表 ===")
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_sync'"
    ).fetchall()
    if existing:
        print("⚠️ knowledge_sync 表已存在，跳过创建")
    else:
        print("knowledge_sync 表不存在，准备创建...")

    # 4. 创建新表（带重试）
    print("\n=== Step 4: 创建新表 ===")
    def create_tables():
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id INTEGER NOT NULL UNIQUE,
                raw_path TEXT,
                wiki_path TEXT,
                wiki_category TEXT,
                sync_status TEXT DEFAULT 'pending',
                sync_version INTEGER DEFAULT 1,
                raw_created_at DATETIME,
                wiki_created_at DATETIME,
                last_sync_at DATETIME,
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES papers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_sync_paper ON knowledge_sync(paper_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_sync_status ON knowledge_sync(sync_status);

            CREATE TRIGGER IF NOT EXISTS trg_knowledge_sync_updated
            AFTER UPDATE ON knowledge_sync
            BEGIN
                UPDATE knowledge_sync SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;
        """)
    with_retry(create_tables)
    print("✅ 新表创建完成")

    # 5. 从现有数据推断状态
    print("\n=== Step 5: 从现有数据推断状态 ===")
    papers = conn.execute("""
        SELECT id, arxiv_id, md_output_path
        FROM papers
        WHERE md_output_path IS NOT NULL
    """).fetchall()

    print(f"找到 {len(papers)} 篇有 md_output_path 的论文")

    inserted = 0
    skipped = 0
    already_exists = 0

    for paper_id, arxiv_id, md_path in papers:
        if md_path and 'KarpathyVault' in str(md_path):
            # 路径验证
            if not validate_path(md_path):
                print(f"  ⚠️ 跳过非法路径: {md_path}")
                skipped += 1
                continue

            # 插入记录（带重试）
            def insert_record(pid=paper_id, mp=md_path):
                conn.execute("""
                    INSERT OR IGNORE INTO knowledge_sync
                    (paper_id, raw_path, wiki_path, sync_status)
                    VALUES (?, ?, ?, 'synced')
                """, (pid, mp, mp))

            before = conn.execute("SELECT COUNT(*) FROM knowledge_sync").fetchone()[0]
            with_retry(insert_record)
            after = conn.execute("SELECT COUNT(*) FROM knowledge_sync").fetchone()[0]

            if after > before:
                inserted += 1
            else:
                already_exists += 1

    conn.commit()
    print(f"✅ 插入: {inserted}, 已存在: {already_exists}, 跳过: {skipped}")

    # 6. 验证外键约束
    print("\n=== Step 6: 验证外键约束 ===")
    orphans = conn.execute("""
        SELECT COUNT(*) FROM knowledge_sync k
        LEFT JOIN papers p ON k.paper_id = p.id
        WHERE p.id IS NULL
    """).fetchone()[0]
    print(f"孤立记录数: {orphans}")

    # 7. 统计
    print("\n=== Step 7: 统计 ===")
    stats = conn.execute("""
        SELECT sync_status, COUNT(*)
        FROM knowledge_sync
        GROUP BY sync_status
    """).fetchall()

    for status, count in stats:
        print(f"  {status}: {count}")

    # 8. 验证数据库完整性
    print("\n=== Step 8: 验证数据库完整性 ===")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"数据库完整性: {integrity}")

    conn.close()

    # 9. 验证 checksum
    print("\n=== Step 9: 验证 checksum ===")
    final_checksum = get_db_checksum(str(papers_db))
    print(f"最终 checksum: {final_checksum[:16]}...")

    if inserted > 0 or already_exists > 0:
        print("✅ 数据库已修改")

    print("\n" + "="*50)
    print("✅ 初始化完成!")
    print("="*50)

    return True

if __name__ == "__main__":
    init_knowledge_sync()