#!/bin/bash
# 论文分析系统启动脚本
# 启动Worker和监护进程

cd /Users/liufang/arxiv-paper-analyzer/backend
source venv/bin/activate

echo "=========================================="
echo "论文分析系统启动"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 1. 停止旧进程
echo "停止旧进程..."
pkill -f "task_worker.py" 2>/dev/null
pkill -f "pdf_worker.py" 2>/dev/null
pkill -f "watchdog.py" 2>/dev/null
sleep 2

# 2. 启动Worker
echo "启动分析Worker..."
nohup python scripts/task_worker.py --concurrent 6 > logs/worker.log 2>&1 &
echo "  PID: $!"

echo "启动PDF下载Worker..."
nohup python scripts/pdf_worker.py --concurrent 3 > logs/pdf_worker.log 2>&1 &
echo "  PID: $!"

sleep 2

# 3. 启动监护进程
echo "启动监护进程..."
nohup python scripts/watchdog.py > logs/watchdog.log 2>&1 &
echo "  PID: $!"

sleep 2

# 4. 显示状态
echo ""
echo "=========================================="
echo "进程状态:"
ps aux | grep -E "task_worker|pdf_worker|watchdog" | grep -v grep | awk '{print "  " $11 " - PID: " $2}'
echo "=========================================="

# 5. 显示进度
echo ""
echo "当前进度:"
python -c "
import sqlite3
conn = sqlite3.connect('data/papers.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM papers WHERE has_analysis = 1')
analyzed = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM papers WHERE pdf_local_path IS NOT NULL')
has_pdf = c.fetchone()[0]
print(f'  已分析: {analyzed}')
print(f'  有PDF: {has_pdf}')
conn.close()
"

echo ""
echo "日志文件:"
echo "  分析Worker: logs/worker.log"
echo "  PDF Worker: logs/pdf_worker.log"
echo "  监护进程: logs/watchdog.log"
echo ""
echo "查看监护状态: tail -f logs/watchdog.log"
echo "手动检查: python scripts/watchdog.py --once"