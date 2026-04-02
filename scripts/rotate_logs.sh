#!/bin/bash
# ArXiv 日志轮转脚本
# 用法: ./rotate_logs.sh

LOG_DIR="$HOME/logs"
MAX_SIZE_KB=10240  # 10MB
MAX_COUNT=5

rotate_log() {
    local log_file="$1"
    local base_name="${log_file%.*}"
    local extension="${log_file##*.}"

    # 检查文件大小
    if [ -f "$log_file" ]; then
        size_kb=$(du -k "$log_file" | cut -f1)
        if [ "$size_kb" -gt "$MAX_SIZE_KB" ]; then
            echo "轮转: $log_file (${size_kb}KB > ${MAX_SIZE_KB}KB)"

            # 删除最旧的备份
            if [ -f "${base_name}.${MAX_COUNT}.${extension}" ]; then
                rm "${base_name}.${MAX_COUNT}.${extension}"
            fi

            # 轮转现有备份
            for i in $(seq $((MAX_COUNT-1)) -1 1); do
                if [ -f "${base_name}.${i}.${extension}" ]; then
                    mv "${base_name}.${i}.${extension}" "${base_name}.$((i+1)).${extension}"
                fi
            done

            # 压缩并移动当前日志
            if [ -f "${base_name}.1.${extension}" ]; then
                gzip "${base_name}.1.${extension}" 2>/dev/null
            fi
            mv "$log_file" "${base_name}.1.${extension}"

            echo "✅ 已轮转: ${base_name}.1.${extension}"
        fi
    fi
}

# 轮转 ArXiv 相关日志
for log in arxiv-backend-debug arxiv-backend arxiv-frontend arxiv-worker arxiv-batch-analyze; do
    rotate_log "$LOG_DIR/${log}.log"
done

echo "日志轮转完成: $(date)"