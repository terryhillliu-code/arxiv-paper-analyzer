#!/bin/bash
# ArXiv 缓存清理脚本
# 用法: ./clean_cache.sh [--dry-run]

DATA_DIR="$HOME/arxiv-paper-analyzer/backend/data"
LOG_FILE="$HOME/logs/arxiv-cache-cleanup.log"
CACHE_RETENTION_DAYS=7
PDF_RETENTION_DAYS=30

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

# 清理 mineru 缓存
clean_mineru_cache() {
    local cache_dir="$DATA_DIR/mineru_cache"
    local dry_run="$1"

    if [ -d "$cache_dir" ]; then
        local before_size=$(du -sh "$cache_dir" 2>/dev/null | cut -f1)
        local count=$(find "$cache_dir" -type f 2>/dev/null | wc -l)

        log "MinerU 缓存: $count 个文件, 大小: $before_size"

        if [ "$dry_run" = "true" ]; then
            local to_delete=$(find "$cache_dir" -type f -mtime +$CACHE_RETENTION_DAYS 2>/dev/null | wc -l)
            log "  [DRY-RUN] 将删除 $to_delete 个超过 $CACHE_RETENTION_DAYS 天的文件"
        else
            find "$cache_dir" -type f -mtime +$CACHE_RETENTION_DAYS -delete 2>/dev/null
            local after_size=$(du -sh "$cache_dir" 2>/dev/null | cut -f1)
            log "  ✅ 清理完成: $before_size -> $after_size"
        fi
    else
        log "MinerU 缓存目录不存在"
    fi
}

# 清理旧 PDF（可选）
clean_old_pdfs() {
    local pdf_dir="$DATA_DIR/pdfs"
    local dry_run="$1"

    if [ -d "$pdf_dir" ]; then
        local before_size=$(du -sh "$pdf_dir" 2>/dev/null | cut -f1)
        local count=$(find "$pdf_dir" -type f -name "*.pdf" 2>/dev/null | wc -l)

        log "PDF 存储: $count 个文件, 大小: $before_size"

        if [ "$dry_run" = "true" ]; then
            local to_delete=$(find "$pdf_dir" -type f -name "*.pdf" -atime +$PDF_RETENTION_DAYS 2>/dev/null | wc -l)
            log "  [DRY-RUN] 将删除 $to_delete 个超过 $PDF_RETENTION_DAYS 天未访问的 PDF"
        else
            # 默认不删除 PDF，只报告
            log "  ℹ️ PDF 清理需要手动确认，使用 --force-pdf 参数"
        fi
    fi
}

# 清理临时文件
clean_temp_files() {
    local dry_run="$1"

    log "清理临时文件..."

    # WAL 和 SHM 文件（SQLite 临时文件）
    for ext in "wal" "shm"; do
        for f in "$DATA_DIR"/*.$ext; do
            if [ -f "$f" ]; then
                if [ "$dry_run" = "true" ]; then
                    log "  [DRY-RUN] 将删除: $f"
                else
                    rm "$f"
                    log "  ✅ 已删除: $f"
                fi
            fi
        done
    done

    # 旧备份文件（data 目录下的 .bak, .backup_* 等）
    for pattern in "*.bak" "*.backup_*" "*.new_schema" "*.old"; do
        for f in $(find "$DATA_DIR" -maxdepth 1 -name "$pattern" 2>/dev/null); do
            if [ -f "$f" ]; then
                local age=$(( ($(date +%s) - $(stat -f %m "$f")) / 86400 ))
                if [ "$age" -gt 1 ]; then
                    if [ "$dry_run" = "true" ]; then
                        log "  [DRY-RUN] 将删除旧备份: $f (${age} 天)"
                    else
                        rm "$f"
                        log "  ✅ 已删除旧备份: $f (${age} 天)"
                    fi
                fi
            fi
        done
    done
}

# 主流程
main() {
    local dry_run="false"
    local clean_pdfs="false"

    for arg in "$@"; do
        case "$arg" in
            --dry-run) dry_run="true" ;;
            --force-pdf) clean_pdfs="true" ;;
        esac
    done

    log "=== 缓存清理开始 ==="
    log "模式: $([ "$dry_run" = "true" ] && echo "DRY-RUN" || echo "执行")"

    clean_mineru_cache "$dry_run"
    clean_temp_files "$dry_run"

    if [ "$clean_pdfs" = "true" ]; then
        clean_old_pdfs "$dry_run"
    fi

    # 报告磁盘使用
    log ""
    log "磁盘使用:"
    du -sh "$DATA_DIR"/* 2>/dev/null | sort -hr | head -10 | while read line; do
        log "  $line"
    done

    log "=== 清理完成 ==="
}

main "$@"