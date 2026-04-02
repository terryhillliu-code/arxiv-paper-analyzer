# ArXiv 平台灾难恢复计划

> 最后更新: 2026-04-01
> 版本: 1.0

---

## 一、概述

本文档定义了 ArXiv 论文智能分析平台的灾难恢复策略和操作步骤。

### 1.1 系统组件

| 组件 | 数据类型 | 恢复优先级 |
|------|----------|------------|
| 数据库 | 论文元数据、分析结果 | P0（最高） |
| PDF 文件 | 原始论文文件 | P1 |
| 配置文件 | 环境变量、密钥 | P0 |
| 应用代码 | Python/React 代码 | P2（可重新部署） |

### 1.2 备份策略

| 数据 | 备份频率 | 保留时间 | 位置 |
|------|----------|----------|------|
| 数据库 | 每天 3:00 | 7 天 | `~/arxiv-paper-analyzer/backups/` |
| 配置文件 | 手动 | 永久 | `~/.secrets/` |
| 代码 | Git 实时 | - | GitHub |

---

## 二、灾难场景与恢复步骤

### 2.1 数据库损坏

**症状**: API 返回数据库错误，完整性检查失败

**恢复步骤**:

```bash
# 1. 停止服务
launchctl stop com.arxiv.backend

# 2. 检查损坏程度
sqlite3 ~/arxiv-paper-analyzer/backend/data/papers.db "PRAGMA integrity_check;"

# 3. 恢复最新备份
ls -lt ~/arxiv-paper-analyzer/backups/papers_*.db | head -1

# 4. 恢复数据库
BACKUP_FILE=$(ls -t ~/arxiv-paper-analyzer/backups/papers_*.db | head -1)
cp "$BACKUP_FILE" ~/arxiv-paper-analyzer/backend/data/papers.db

# 5. 验证恢复
sqlite3 ~/arxiv-paper-analyzer/backend/data/papers.db "PRAGMA integrity_check;"

# 6. 重启服务
launchctl start com.arxiv.backend

# 7. 验证功能
curl http://localhost:8000/health
curl http://localhost:8000/api/stats
```

**数据丢失评估**:
- 恢复到最近备份点（最多丢失 24 小时数据）
- 需要重新抓取丢失期间的论文

### 2.2 服务无法启动

**症状**: `launchctl start` 失败，进程立即退出

**排查步骤**:

```bash
# 1. 检查日志
tail -100 ~/logs/arxiv-backend-debug.log

# 2. 检查端口占用
lsof -i :8000

# 3. 检查进程
ps aux | grep python | grep arxiv

# 4. 手动启动测试
cd ~/arxiv-paper-analyzer/backend
source venv/bin/activate
python run.py

# 5. 检查配置
cat .env | grep -v KEY

# 6. 检查数据库
sqlite3 data/papers.db "SELECT COUNT(*) FROM papers;"
```

**常见问题修复**:

| 问题 | 解决方案 |
|------|----------|
| 端口占用 | `kill -9 $(lsof -t -i :8000)` |
| 数据库锁定 | 删除 `.db-wal` 和 `.db-shm` 文件 |
| 配置缺失 | 检查 `.env` 文件 |
| 依赖问题 | `pip install -r requirements.txt` |

### 2.3 磁盘空间耗尽

**症状**: 写入失败，系统变慢

**处理步骤**:

```bash
# 1. 检查磁盘使用
df -h /
du -sh ~/arxiv-paper-analyzer/*/

# 2. 清理缓存
~/arxiv-paper-analyzer/scripts/clean_cache.sh

# 3. 清理旧日志
rm ~/logs/arxiv-*.log.* 2>/dev/null

# 4. 清理旧备份（保留 3 天）
find ~/arxiv-paper-analyzer/backups -mtime +3 -delete

# 5. 可选：清理旧 PDF（谨慎）
# 仅清理 30 天未访问的 PDF
find ~/arxiv-paper-analyzer/backend/data/pdfs -atime +30 -name "*.pdf" -delete
```

### 2.4 配置丢失（API Key 等）

**症状**: AI 分析失败，认证错误

**恢复步骤**:

```bash
# 1. 检查配置文件
cat ~/arxiv-paper-analyzer/backend/.env

# 2. 从备份恢复
# 假设配置已备份到 ~/.secrets/
cp ~/.secrets/arxiv.env ~/arxiv-paper-analyzer/backend/.env

# 3. 设置正确权限
chmod 600 ~/arxiv-paper-analyzer/backend/.env

# 4. 重启服务
launchctl stop com.arxiv.backend
launchctl start com.arxiv.backend
```

### 2.5 完全重建

**场景**: 系统完全崩溃，需要从零开始

**步骤**:

```bash
# 1. 克隆代码
git clone https://github.com/your-repo/arxiv-paper-analyzer.git
cd arxiv-paper-analyzer

# 2. 安装依赖
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install

# 3. 恢复配置
cp ~/.secrets/arxiv.env backend/.env
chmod 600 backend/.env

# 4. 恢复数据库
cp ~/arxiv-paper-analyzer/backups/papers_*.db backend/data/papers.db

# 5. 加载服务
for plist in ~/Library/LaunchAgents/com.arxiv.*.plist; do
    launchctl load "$plist"
done

# 6. 验证
curl http://localhost:8000/health
```

---

## 三、预防措施

### 3.1 监控告警

| 监控项 | 阈值 | 告警方式 |
|--------|------|----------|
| 服务状态 | 停止 | 钉钉通知 |
| 磁盘空间 | < 10GB | 钉钉通知 |
| 数据库完整性 | 检查失败 | 钉钉通知 |
| 内存使用 | > 90% | 日志记录 |

### 3.2 定期检查

```bash
# 每日自动检查（已配置）
# - 健康检查：每 5 分钟
# - 数据库完整性：每周日 5:00

# 手动检查命令
~/arxiv-paper-analyzer/scripts/monitor.py --health
```

### 3.3 备份验证

```bash
# 验证备份完整性
for db in ~/arxiv-paper-analyzer/backups/*.db; do
    echo "检查: $db"
    sqlite3 "$db" "PRAGMA integrity_check;"
done
```

---

## 四、应急联系人

| 角色 | 负责内容 |
|------|----------|
| 系统管理员 | 服务重启、配置恢复 |
| 数据管理员 | 数据库恢复、备份管理 |

---

## 五、恢复时间目标

| 灾难类型 | RTO（恢复时间目标） | RPO（恢复点目标） |
|----------|---------------------|-------------------|
| 服务崩溃 | 5 分钟 | 0 |
| 数据库损坏 | 30 分钟 | 24 小时 |
| 磁盘故障 | 2 小时 | 24 小时 |
| 完全重建 | 4 小时 | 24 小时 |

---

## 六、演练计划

### 6.1 定期演练

- **频率**: 每季度一次
- **内容**:
  1. 模拟数据库损坏，执行恢复流程
  2. 验证备份可用性
  3. 测试告警通知

### 6.2 演练记录

| 日期 | 场景 | 结果 | 问题 |
|------|------|------|------|
| 2026-04-01 | 数据库恢复 | 通过 | - |

---

## 七、附录

### 7.1 快速命令参考

```bash
# 服务管理
launchctl list | grep arxiv          # 查看服务状态
launchctl stop com.arxiv.backend     # 停止服务
launchctl start com.arxiv.backend    # 启动服务

# 数据库
sqlite3 papers.db ".tables"          # 查看表
sqlite3 papers.db "PRAGMA integrity_check;"  # 完整性检查

# 日志
tail -f ~/logs/arxiv-backend-debug.log
grep -i error ~/logs/arxiv-*.log

# 监控
~/arxiv-paper-analyzer/scripts/monitor.py
~/arxiv-paper-analyzer/scripts/health_check.sh
```

### 7.2 关键文件路径

| 文件 | 路径 |
|------|------|
| 数据库 | `~/arxiv-paper-analyzer/backend/data/papers.db` |
| 备份 | `~/arxiv-paper-analyzer/backups/` |
| 配置 | `~/arxiv-paper-analyzer/backend/.env` |
| 日志 | `~/logs/arxiv-*.log` |
| 服务配置 | `~/Library/LaunchAgents/com.arxiv.*.plist` |