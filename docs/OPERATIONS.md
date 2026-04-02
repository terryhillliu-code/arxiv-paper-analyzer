# ArXiv 平台运维手册

> 最后更新: 2026-04-01

---

## 一、服务总览

### 核心服务

| 服务 | 功能 | 端口 | 绑定地址 | 状态检查 |
|------|------|------|----------|----------|
| backend | API 服务 | 8000 | 127.0.0.1 | `curl localhost:8000/health` |
| frontend | 前端界面 | 5173 | localhost | `curl localhost:5173` |
| daily-workflow | 每日论文抓取 | - | - | 7:00 定时 |
| task-worker | 任务处理 | - | - | 按需启动 |

### 安全配置

| 项目 | 配置 | 说明 |
|------|------|------|
| 端口绑定 | `127.0.0.1` | 仅本地访问，不暴露外网 |
| API 文档 | 禁用 | `/docs`、`/redoc` 返回 404 |
| CORS | 仅 localhost | 不允许外部跨域请求 |

> 如需启用 API 文档，设置环境变量 `ENABLE_DOCS=true`

### 运维服务

| 服务 | 功能 | 定时 |
|------|------|------|
| db-backup | 数据库备份 | 每天 3:00 |
| log-rotate | 日志轮转 | 每天 4:00 |
| cache-cleanup | 缓存清理 | 每天 5:00 |
| health-check | 健康检查 | 每 5 分钟 |
| db-check | 数据库完整性 | 每周日 5:00 |

---

## 二、常用命令

### 服务管理

```bash
# 查看所有服务状态
launchctl list | grep arxiv

# 重启 Backend
launchctl stop com.arxiv.backend
launchctl start com.arxiv.backend

# 重启 Frontend
launchctl stop com.arxiv.frontend
launchctl start com.arxiv.frontend

# 手动运行每日任务
cd ~/arxiv-paper-analyzer/backend
source venv/bin/activate
python scripts/daily_workflow.py
```

### 健康检查

```bash
# 手动健康检查
~/arxiv-paper-analyzer/scripts/health_check.sh

# 带告警的健康检查
~/arxiv-paper-analyzer/scripts/health_check.sh --notify

# 查看健康日志
tail -50 ~/logs/arxiv-health.log
```

### 数据库操作

```bash
# 数据库备份
~/arxiv-paper-analyzer/scripts/backup_db.sh

# 数据库完整性检查
~/arxiv-paper-analyzer/scripts/check_db_integrity.sh

# 数据库修复（谨慎使用）
~/arxiv-paper-analyzer/scripts/check_db_integrity.sh --repair

# 查看数据库统计
sqlite3 ~/arxiv-paper-analyzer/backend/data/papers.db "
  SELECT 'papers', COUNT(*) FROM papers
  UNION ALL SELECT 'fetch_logs', COUNT(*) FROM fetch_logs;
"
```

### 缓存清理

```bash
# 查看缓存状态（dry-run）
~/arxiv-paper-analyzer/scripts/clean_cache.sh --dry-run

# 执行清理
~/arxiv-paper-analyzer/scripts/clean_cache.sh

# 清理旧 PDF（谨慎）
~/arxiv-paper-analyzer/scripts/clean_cache.sh --force-pdf
```

### 日志管理

```bash
# 查看各服务日志
tail -f ~/logs/arxiv-backend-debug.log    # API 详细日志
tail -f ~/logs/arxiv-frontend.log          # 前端日志
tail -f ~/logs/arxiv-worker.log            # 任务处理日志
tail -f ~/logs/arxiv-health.log            # 健康检查日志

# 手动日志轮转
~/arxiv-paper-analyzer/scripts/rotate_logs.sh
```

---

## 三、故障排查

### Backend 无法启动

**症状**: `ECONNREFUSED` 或端口 8000 无响应

**排查步骤**:
```bash
# 1. 检查端口占用
lsof -i :8000

# 2. 如果被占用，杀掉残留进程
kill -9 $(lsof -t -i :8000)

# 3. 重启服务
launchctl stop com.arxiv.backend
launchctl start com.arxiv.backend

# 4. 检查日志
tail -50 ~/logs/arxiv-backend-debug.log
```

### Frontend 无法访问

**症状**: 浏览器无法打开 localhost:5173

**排查步骤**:
```bash
# 1. 检查进程
ps aux | grep vite

# 2. 检查端口
lsof -i :5173

# 3. 重启服务
launchctl stop com.arxiv.frontend
launchctl start com.arxiv.frontend

# 4. 检查日志
tail -30 ~/logs/arxiv-frontend.log
```

### 数据库损坏

**症状**: 查询报错或数据异常

**排查步骤**:
```bash
# 1. 完整性检查
~/arxiv-paper-analyzer/scripts/check_db_integrity.sh

# 2. 如果有问题，从备份恢复
ls ~/arxiv-paper-analyzer/backups/

# 3. 恢复最新备份
cp ~/arxiv-paper-analyzer/backups/papers_YYYYMMDD_HHMMSS.db \
   ~/arxiv-paper-analyzer/backend/data/papers.db

# 4. 验证恢复结果
~/arxiv-paper-analyzer/scripts/check_db_integrity.sh
```

### 告警通知

**收到告警时的处理流程**:

1. 查看健康日志确认问题
2. 登录服务器检查服务状态
3. 根据故障类型执行对应修复
4. 确认服务恢复正常

---

## 四、配置文件

| 文件 | 位置 | 说明 |
|------|------|------|
| Backend 配置 | `backend/.env` | API 密钥、数据库路径 |
| Frontend 配置 | `frontend/.env` | API 地址 |
| launchd 配置 | `~/Library/LaunchAgents/com.arxiv.*.plist` | 服务定义 |

### 环境变量 (backend/.env)

```env
# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/papers.db

# AI 配置
AI_MODEL=kimi-k2.5

# PDF 解析
PDF_PARSER=auto
MINERU_PATH=/Users/liufang/zhiwei-rag/mineru-venv/bin/mineru

# 外部服务
RAG_PYTHON_PATH=/Users/liufang/zhiwei-rag/venv/bin/python3
```

---

## 五、备份与恢复

### 自动备份

- **时间**: 每天凌晨 3:00
- **保留**: 7 天
- **位置**: `~/arxiv-paper-analyzer/backups/`

### 手动备份

```bash
# 立即备份
~/arxiv-paper-analyzer/scripts/backup_db.sh

# 备份并清理旧文件
~/arxiv-paper-analyzer/scripts/backup_db.sh --rotate
```

### 恢复流程

```bash
# 1. 停止 Backend
launchctl stop com.arxiv.backend

# 2. 恢复数据库
cp ~/arxiv-paper-analyzer/backups/papers_YYYYMMDD_HHMMSS.db \
   ~/arxiv-paper-analyzer/backend/data/papers.db

# 3. 验证完整性
~/arxiv-paper-analyzer/scripts/check_db_integrity.sh

# 4. 重启 Backend
launchctl start com.arxiv.backend
```

---

## 六、监控指标

### 关键指标

| 指标 | 命令 | 正常值 |
|------|------|--------|
| 论文总数 | `curl -s localhost:8000/api/stats \| jq .total_papers` | 持续增长 |
| 健康状态 | `curl -s localhost:8000/health` | `{"status":"ok"}` |
| 数据库大小 | `du -h backend/data/papers.db` | < 200MB |
| PDF 存储 | `du -sh backend/data/pdfs/` | 监控增长 |

### 告警阈值

| 指标 | 阈值 | 处理 |
|------|------|------|
| Backend 无响应 | 5 分钟 | 自动重启 + 通知 |
| 数据库损坏 | 检测到 | 备份恢复 |
| 磁盘空间 < 10GB | - | 清理 PDF |

---

## 七、联系信息

- **项目文档**: `~/arxiv-paper-analyzer/README.md`
- **架构文档**: `~/arxiv-paper-analyzer/SYSTEM_ARCHITECTURE.md`
- **问题归档**: `~/zhiwei-docs/reports/`