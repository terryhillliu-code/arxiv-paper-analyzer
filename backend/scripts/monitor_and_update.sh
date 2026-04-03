#!/bin/bash
# 监控 LanceDB 同步进度，完成后自动更新 rag_indexed

LOG_FILE=~/logs/lance_sync.log
PID_FILE=/tmp/lance_sync.pid

echo "开始监控 LanceDB 同步..."

while true; do
    # 检查进程是否还在运行
    if ! ps -p $(cat $PID_FILE 2>/dev/null) > /dev/null 2>&1; then
        echo "同步进程已结束"
        break
    fi

    # 获取当前进度
    PROGRESS=$(tail -20 $LOG_FILE 2>/dev/null | grep -oE '\[[0-9]+/11281\]' | tail -1)
    echo "$(date '+%H:%M:%S') - 进度: $PROGRESS"

    sleep 300  # 每 5 分钟检查一次
done

echo ""
echo "=== 同步完成，开始更新 rag_indexed ==="
cd ~/arxiv-paper-analyzer/backend && source venv/bin/activate
python scripts/update_rag_indexed.py

echo ""
echo "=== 完成 ==="