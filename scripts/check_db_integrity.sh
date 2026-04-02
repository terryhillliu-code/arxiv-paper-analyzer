#!/bin/bash
# ArXiv 数据库完整性检查脚本
# 用法: ./check_db_integrity.sh [--repair]

DB_DIR="$HOME/arxiv-paper-analyzer/backend/data"
LOG_FILE="$HOME/logs/arxiv-db-check.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

check_integrity() {
    local db_file="$1"
    local db_name=$(basename "$db_file")

    log "检查: $db_name"

    result=$(sqlite3 "$db_file" "PRAGMA integrity_check;" 2>&1)

    if [ "$result" = "ok" ]; then
        log "✅ $db_name 完整性 OK"

        # 额外统计
        tables=$(sqlite3 "$db_file" "SELECT name FROM sqlite_master WHERE type='table';" 2>&1)
        log "   表: $(echo $tables | tr '\n' ' ')"

        # 数据库大小
        size=$(ls -lh "$db_file" | awk '{print $5}')
        log "   大小: $size"

        return 0
    else
        log "❌ $db_name 完整性问题: $result"
        return 1
    fi
}

check_tables() {
    local db_file="$1"
    log "统计 $db_file 表记录数:"

    tables=$(sqlite3 "$db_file" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';" 2>&1)

    for table in $tables; do
        count=$(sqlite3 "$db_file" "SELECT COUNT(*) FROM $table;" 2>&1)
        log "   $table: $count 条记录"
    done
}

repair_database() {
    local db_file="$1"
    local backup_file="${db_file}.repair_backup"

    log "尝试修复: $db_file"

    # 备份
    cp "$db_file" "$backup_file"
    log "已备份到: $backup_file"

    # 导出并重建
    local dump_file="${db_file}.sql"
    sqlite3 "$db_file" ".dump" > "$dump_file" 2>&1

    rm "$db_file"
    sqlite3 "$db_file" < "$dump_file" 2>&1

    # 检查修复结果
    result=$(sqlite3 "$db_file" "PRAGMA integrity_check;" 2>&1)
    if [ "$result" = "ok" ]; then
        log "✅ 修复成功"
        rm "$dump_file"
        return 0
    else
        log "❌ 修复失败，恢复备份"
        mv "$backup_file" "$db_file"
        return 1
    fi
}

# 主流程
main() {
    log "=== 数据库完整性检查 ==="

    issues=0

    for db in "$DB_DIR"/*.db; do
        if [ -f "$db" ]; then
            if ! check_integrity "$db"; then
                issues=$((issues + 1))

                if [ "$1" = "--repair" ]; then
                    repair_database "$db"
                fi
            fi

            check_tables "$db"
            log ""
        fi
    done

    log "=== 检查完成 ==="

    if [ $issues -gt 0 ]; then
        log "⚠️ 发现 $issues 个问题"
        if [ "$1" != "--repair" ]; then
            log "提示: 使用 --repair 参数尝试修复"
        fi
        return 1
    else
        log "✅ 所有数据库正常"
        return 0
    fi
}

main "$@"