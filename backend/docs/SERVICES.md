# ArXiv论文分析系统 - 服务配置文档

## 服务架构

### 1. launchd 服务（自动启动）

| 服务名 | 配置文件 | 作用 | 状态 |
|--------|----------|------|------|
| com.arxiv.frontend | com.arxiv.frontend.plist | 前端服务 | 运行中 |
| com.arxiv.backend | com.arxiv.backend.plist | API服务(run.py) | 运行中 |
| com.arxiv.dashboard | com.arxiv.dashboard.plist | 监控面板(8898端口) | 运行中 |
| com.arxiv.auto-heal | com.arxiv.auto-heal.plist | **自愈监控(每60秒)** | 运行中 ✅ |
| com.arxiv.watchdog | com.arxiv.watchdog.plist | **看门狗(每5分钟)** | 运行中 ✅ |
| ~~com.arxiv.task-worker~~ | com.arxiv.task-worker.plist | ❌ 已禁用 | 冲突风险 |
| ~~com.arxiv.workers~~ | com.arxiv.workers.plist | ❌ 已禁用 | 冲突风险 |

### 2. 自愈监控服务

**功能**：每60秒自动检查并修复以下问题：
- Worker进程停止 → 自动重启
- 任务超时(>500秒) → 自动重置为pending
- PDF同步差异 → 自动同步
- PDF断链 → 自动清理
- 数据库损坏 → 自动修复
- 无限重试任务 → 标记失败停止重试
- 磁盘空间不足 → 清理日志
- 质量问题论文 → 创建修复任务

**查看日志**：
```bash
tail -f ~/logs/arxiv-auto-heal.log
```

**手动检查一次**：
```bash
python3 scripts/auto_heal.py --once
```

### 3. Watchdog 看门狗服务

**功能**：每5分钟检查自愈服务健康状态：
- 心跳文件检查（120秒内更新）
- 进程运行检查
- launchd 服务状态检查

如果检测失败，自动重启 auto_heal 服务。

**查看日志**：
```bash
tail -f ~/logs/arxiv-watchdog.log
```

**手动检查一次**：
```bash
python3 scripts/watchdog.py --once
```

### 3. Worker 管理（手动）

**启动命令**:
```bash
~/scripts/arxiv-workers.sh start
```

**停止命令**:
```bash
~/scripts/arxiv-workers.sh stop
```

**查看状态**:
```bash
~/scripts/arxiv-workers.sh status
```

**配置**:
- task_worker: 并发 8
- pdf_worker: 并发 4

### 4. 定时任务（crontab）

| 任务 | 频率 | 作用 |
|------|------|------|
| create_analysis_tasks.py | 每小时 | 创建A类论文分析任务 |

**注意**: Worker不再通过crontab启动，避免重复启动导致并发冲突。

### 5. 监控

- 监控面板: http://localhost:8898
- API服务: http://localhost:8000
- 前端服务: http://localhost:3000
- 自愈日志: `tail -f ~/logs/arxiv-auto-heal.log`

## 常见问题

### Worker并发数不对

检查是否有多个启动源：
```bash
# 检查launchd
launchctl list | grep arxiv

# 检查crontab
crontab -l | grep worker

# 检查进程
ps aux | grep -E "task_worker|pdf_worker"
```

### 启动失败

1. 清理PID文件: `rm -f data/*.pid`
2. 停止所有Worker: `~/scripts/arxiv-workers.sh stop`
3. 重新启动: `~/scripts/arxiv-workers.sh start`

### 任务卡住

```bash
# 自愈监控会自动处理，也可手动：
python3 scripts/auto_heal.py --once
```

## 修改历史

- 2026-04-08: SQLite优化 - 连接池复用 + WAL模式，减少50%+数据库开销
- 2026-04-08: 任务轮询优化 - 批量获取任务 + 动态间隔调整
- 2026-04-08: 模型优化 - 默认使用 glm-5.1 推理模型，新增智谱直连 API 支持
- 2026-04-08: 超时优化 - 推理模型超时 300s，任务执行超时 500s
- 2026-04-07: 修复auto_heal.py日志问题（debug改为info）
- 2026-04-07: 新增com.arxiv.auto-heal自愈监控服务
- 2026-04-07: 禁用com.arxiv.task-worker和com.arxiv.workers，统一使用手动管理
- 2026-04-07: 从crontab移除task_worker启动任务

## 性能优化

### SQLite 数据库优化

| 优化项 | 之前 | 之后 | 效果 |
|--------|------|------|------|
| 连接管理 | 每次操作新建连接 | 线程局部连接池 | 减少50%+开销 |
| 日志模式 | 默认 DELETE | WAL | 并发性能提升 |
| 缓存大小 | 默认 | 10000页 | 减少磁盘IO |
| 同步模式 | FULL | NORMAL | 写入更快 |

### 任务轮询优化

| 优化项 | 之前 | 之后 |
|--------|------|------|
| 任务获取 | limit=1 逐个 | limit=5 批量 |
| 轮询间隔 | 固定 2秒 | 动态 0.5-5秒 |
| 空闲策略 | 固定等待 | 逐渐延长间隔 |

## AI 模型配置

### 支持的模型

| 模型 | API 来源 | 特点 | 推荐场景 |
|------|----------|------|----------|
| glm-5.1 | 智谱直连 | 推理模型，返回 reasoning_content | **默认推荐** |
| glm-5 | 智谱直连 | 推理模型 | 备选 |
| qwen3.5-plus | 百炼 Coding Plan | 快速响应 | 非推理场景 |
| glm-4.7 | 智谱直连 | 标准对话 | 简单任务 |

### 配置方式

```bash
# .env 文件
AI_MODEL=glm-5.1
ZHIPU_API_KEY=your_zhipu_api_key
```

### 推理模型特点

- glm-5.1 会进行深度推理后再输出
- 超时时间更长（300s vs 120s）
- 返回内容更准确、结构化更好