#!/usr/bin/env python3
"""创建 videos 表迁移脚本

创建独立的 Video 表，用于存储抖音/Bilibili视频内容。

用法：
    python scripts/create_videos_table.py
"""

import sqlite3
from pathlib import Path


def migrate(db_path: str):
    """执行迁移"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查表是否已存在
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='videos'
    """)

    if cursor.fetchone():
        print("videos 表已存在")
        conn.close()
        return

    # 创建 videos 表
    cursor.execute("""
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- 视频基本信息
            title TEXT NOT NULL,
            video_id VARCHAR(100),
            platform VARCHAR(50),
            video_url VARCHAR(500),
            cover_url VARCHAR(500),

            -- 创作者信息
            speaker VARCHAR(200),
            speaker_id VARCHAR(100),

            -- 视频元数据
            duration INTEGER,
            publish_date DATETIME,
            view_count INTEGER,
            like_count INTEGER,
            comment_count INTEGER,

            -- 内容
            transcript TEXT,
            description TEXT,

            -- 分析结果
            has_analysis BOOLEAN DEFAULT 0 NOT NULL,
            analysis_report TEXT,
            analysis_json JSON,

            -- 质量等级
            tier VARCHAR(1),

            -- 标签与分类
            tags JSON,
            category VARCHAR(100),

            -- 知识关联
            knowledge_links JSON,
            action_items JSON,

            -- Markdown 输出
            md_output_path VARCHAR(500),

            -- 元数据
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_videos_video_id ON videos(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_videos_platform ON videos(platform)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_videos_tier ON videos(tier)")

    conn.commit()
    conn.close()
    print("✓ videos 表创建成功")


def cleanup_papers_video_fields(db_path: str):
    """清理 papers 表中的视频字段（如果存在）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取现有列
    cursor.execute("PRAGMA table_info(papers)")
    columns = {row[1] for row in cursor.fetchall()}

    # SQLite 不支持 DROP COLUMN，只能重建表
    # 这里只是检查，不实际删除
    video_columns = ["duration", "speaker", "platform", "video_url"]
    existing_video_cols = [c for c in video_columns if c in columns]

    if existing_video_cols:
        print(f"注意: papers 表中存在视频字段 {existing_video_cols}")
        print("这些字段将在下次数据库重建时清理（SQLite 限制）")

    conn.close()


if __name__ == "__main__":
    import sys

    # 默认数据库路径
    db_path = Path(__file__).parent.parent / "data" / "papers.db"

    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"数据库不存在: {db_path}")
        sys.exit(0)

    print(f"迁移数据库: {db_path}")
    migrate(str(db_path))
    cleanup_papers_video_fields(str(db_path))