#!/usr/bin/env python3
"""数据库迁移脚本：添加 Semantic Scholar 评分字段。

新增字段：
- citation_count: 引用数
- influential_citation_count: 有影响力的引用数
- s2_paper_id: Semantic Scholar 论文 ID

使用方法：
    python scripts/migrate_add_s2_fields.py
"""

import sqlite3
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings


def migrate():
    """执行迁移。"""
    settings = get_settings()
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")

    print(f"数据库路径: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查字段是否已存在
    cursor.execute("PRAGMA table_info(papers)")
    columns = [col[1] for col in cursor.fetchall()]

    new_columns = [
        ("citation_count", "INTEGER"),
        ("influential_citation_count", "INTEGER"),
        ("s2_paper_id", "VARCHAR(50)"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            print(f"添加字段: {col_name} ({col_type})")
            cursor.execute(f"ALTER TABLE papers ADD COLUMN {col_name} {col_type}")
        else:
            print(f"字段已存在: {col_name}")

    conn.commit()
    conn.close()

    print("迁移完成！")


if __name__ == "__main__":
    migrate()