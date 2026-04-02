#!/bin/bash
# ArXiv 数据库自动备份脚本
# 用法: ./backup_db.sh [--rotate]

BACKUP_DIR="$HOME/arxiv-paper-analyzer/backups"
DB_DIR="$HOME/arxiv-paper-analyzer/backend/data"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# 创建备份
backup() {
    echo "=== 开始备份 ===" $(date)

    # 备份 papers.db
    if [ -f "$DB_DIR/papers.db" ]; then
        cp "$DB_DIR/papers.db" "$BACKUP_DIR/papers_$DATE.db"
        size=$(ls -lh "$BACKUP_DIR/papers_$DATE.db" | awk '{print $5}')
        echo "✅ papers.db -> papers_$DATE.db ($size)"
    fi

    # 备份 tasks.db
    if [ -f "$DB_DIR/tasks.db" ]; then
        cp "$DB_DIR/tasks.db" "$BACKUP_DIR/tasks_$DATE.db"
        size=$(ls -lh "$BACKUP_DIR/tasks_$DATE.db" | awk '{print $5}')
        echo "✅ tasks.db -> tasks_$DATE.db ($size)"
    fi

    # 记录备份日志
    echo "$(date '+%Y-%m-%d %H:%M:%S') 备份完成" >> "$BACKUP_DIR/backup.log"
}

# 轮转旧备份
rotate() {
    echo "=== 清理旧备份 ==="
    find "$BACKUP_DIR" -name "*.db" -mtime +$RETENTION_DAYS -exec rm -v {} \;
    echo "保留最近 $RETENTION_DAYS 天的备份"
}

# 显示状态
status() {
    echo "=== 备份状态 ==="
    echo "备份目录: $BACKUP_DIR"
    echo "数据库目录: $DB_DIR"
    echo ""
    echo "数据库文件:"
    ls -lh "$DB_DIR"/*.db 2>/dev/null
    echo ""
    echo "最近备份:"
    ls -lht "$BACKUP_DIR"/*.db 2>/dev/null | head -5
    echo ""
    echo "备份占用空间:"
    du -sh "$BACKUP_DIR"
}

case "$1" in
    --rotate)
        backup
        rotate
        ;;
    --status)
        status
        ;;
    *)
        backup
        ;;
esac