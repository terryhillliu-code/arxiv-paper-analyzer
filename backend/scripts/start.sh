#!/bin/bash
# 论文分析系统 - 统一启动脚本
# 使用PID文件锁，确保稳定运行

cd /Users/liufang/arxiv-paper-analyzer/backend
source venv/bin/activate

echo "=========================================="
echo "论文分析系统"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 检查是否已运行
if [ -f logs/paper_manager.pid ]; then
    PID=$(cat logs/paper_manager.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "系统已在运行 (PID: $PID)"
        echo "查看状态: python scripts/process_manager.py status"
        exit 0
    fi
    # 清理残留PID文件
    rm -f logs/paper_manager.pid
fi

# 清理残留进程
echo "清理残留进程..."
pkill -f "task_worker.py" 2>/dev/null
pkill -f "pdf_worker.py" 2>/dev/null
sleep 1

# 启动管理器（后台运行）
echo "启动进程管理器..."
nohup python scripts/process_manager.py run > logs/manager.log 2>&1 &
MANAGER_PID=$!

echo "管理器 PID: $MANAGER_PID"
sleep 3

# 显示状态
echo ""
echo "=========================================="
python scripts/process_manager.py status | python -c "
import sys, json
data = json.load(sys.stdin)
print('Workers:')
for name, info in data.get('workers', {}).items():
    status = '运行中' if info['running'] else '未运行'
    print(f'  {name}: {status} (PID: {info.get(\"pid\", \"无\")})')
print('进度:')
papers = data.get('papers', {})
print(f'  已分析: {papers.get(\"analyzed\", 0)}')
print(f'  有PDF: {papers.get(\"has_pdf\", 0)}')
"
echo "=========================================="
echo ""
echo "管理命令:"
echo "  查看状态: python scripts/process_manager.py status"
echo "  健康检查: python scripts/process_manager.py check"
echo "  停止系统: python scripts/process_manager.py stop"
echo "  查看日志: tail -f logs/manager.log"