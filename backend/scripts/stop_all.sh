#!/bin/bash
# 论文分析系统停止脚本

cd /Users/liufang/arxiv-paper-analyzer/backend

echo "=========================================="
echo "停止论文分析系统"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 停止所有进程
echo "停止Worker..."
pkill -f "task_worker.py" 2>/dev/null && echo "  已停止 task_worker"
pkill -f "pdf_worker.py" 2>/dev/null && echo "  已停止 pdf_worker"
pkill -f "watchdog.py" 2>/dev/null && echo "  已停止 watchdog"

sleep 2

# 显示状态
echo ""
echo "剩余进程:"
ps aux | grep -E "task_worker|pdf_worker|watchdog" | grep -v grep || echo "  无"