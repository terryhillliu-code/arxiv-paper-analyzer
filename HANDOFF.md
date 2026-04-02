# 归档记录

## 2026-03-18 思维导图功能修复

### 任务概述
修复 PaperDetail 页面的思维导图显示问题，支持重新分析后的嵌套大纲格式。

### 完成内容
1. **修复 MindMap 数据格式**
   - 问题：simple-mind-map 库期望 `{ data: {...}, children: [...] }` 格式，之前错误使用了 `root` 包装
   - 修复：移除 `root` 包装，直接传入节点数据

2. **修复 React StrictMode 双重初始化**
   - 问题：React StrictMode 在开发模式下会运行 useEffect 两次
   - 修复：添加 `isInitializingRef` 守卫防止重复初始化

3. **支持新旧大纲格式**
   - 旧格式：扁平字符串数组 `["章节1", "章节2"]`
   - 新格式：嵌套对象数组 `[{ title: "章节1", children: [...] }]`
   - 代码自动检测并处理两种格式

4. **添加备用树形视图**
   - 当 MindMap 渲染失败时显示层级树形结构
   - 主章节和子章节有视觉区分

5. **添加相关论文/参考文献显示**
   - 提取 `key_references`（关键参考文献）
   - 提取 `similar_papers`（相似研究方向）

### 修改文件
- `frontend/src/pages/PaperDetail.jsx` - MindMap 组件修复
- `frontend/src/index.css` - 思维导图样式
- `backend/app/prompts/templates.py` - 提示词模板更新
- `backend/app/services/ai_service.py` - AI 服务解析逻辑
- `frontend/package.json` - simple-mind-map 依赖

### Git 提交
- `84559f8` feat: 修复思维导图显示并支持嵌套大纲格式

### 验证结果
- 重新分析论文后思维导图正常显示
- 新旧大纲格式均能正确渲染
- 相关论文/参考文献正常展示

---

## 2026-04-01 Backend 服务 launchd 配置

### 问题
Backend API 服务没有 launchd 配置，依赖手动启动。当终端关闭时进程终止，无自动恢复机制。

### 影响
- 服务中断约 4 小时（11:11 - 15:34）
- Frontend 无法连接 Backend API

### 修复
创建 `~/Library/LaunchAgents/com.arxiv.backend.plist`：
- `KeepAlive=true` - 自动重启
- `RunAtLoad=true` - 登录时启动
- `ProcessType=Background` - 后台进程

### 服务状态（修复后）
| 服务 | launchd | 状态 |
|------|---------|------|
| frontend | ✅ | KeepAlive=true |
| backend | ✅ | KeepAlive=true |
| daily-workflow | ✅ | 定时 7:00 |
| task-worker | ✅ | RunAtLoad=false |

### 相关文档
- 详细报告：`~/zhiwei-docs/reports/20260401_arxiv_backend_incident.md`

---

## 2026-04-01 服务运维加固

### 背景
Backend 服务中断问题修复后，进行全面运维加固。

### 完成内容

#### 1. 数据库自动备份
- 脚本: `scripts/backup_db.sh`
- 定时: 每天 3:00
- 保留: 7 天
- 配置: `com.arxiv.db-backup.plist`

#### 2. 日志轮转
- 脚本: `scripts/rotate_logs.sh`
- 定时: 每天 4:00
- 阈值: 10MB 触发轮转
- 配置: `com.arxiv.log-rotate.plist`

#### 3. 健康检查与告警
- 脚本: `scripts/health_check.sh`
- 定时: 每 5 分钟
- 功能: 检查服务 + 自动重启 + 钉钉告警
- 配置: `com.arxiv.health-check.plist`

#### 4. 数据库完整性检查
- 脚本: `scripts/check_db_integrity.sh`
- 定时: 每周日 5:00
- 配置: `com.arxiv.db-check.plist`

#### 5. 启动脚本优化
- 文件: `backend/run.py`
- 功能: 启动前端口检查，避免冲突

#### 6. 运维文档
- 文件: `docs/OPERATIONS.md`
- 内容: 服务管理、故障排查、备份恢复

### 服务总览

| 服务 | launchd | 定时 | 状态 |
|------|---------|------|------|
| frontend | KeepAlive | - | 运行中 |
| backend | KeepAlive | - | 运行中 |
| daily-workflow | - | 7:00 | 已加载 |
| task-worker | - | 按需 | 已加载 |
| db-backup | - | 3:00 | 已加载 |
| log-rotate | - | 4:00 | 已加载 |
| health-check | - | 5分钟 | 已加载 |
| db-check | - | 周日 5:00 | 已加载 |

### 相关文档
- 运维手册: `docs/OPERATIONS.md`
- 事故报告: `~/zhiwei-docs/reports/20260401_arxiv_backend_incident.md`

---

## 2026-04-01 安全加固

### 背景
完成运维加固后，进行安全加固。

### 完成内容

#### 1. 端口绑定限制
- 文件: `backend/run.py`
- 修改: `0.0.0.0` → `127.0.0.1`
- 效果: 仅本地访问，不暴露外网

#### 2. API 文档访问控制
- 文件: `backend/app/main.py`
- 修改: 默认禁用 `/docs`、`/redoc`
- 环境变量: `ENABLE_DOCS=true` 可启用

#### 3. CORS 安全
- 文件: `backend/app/main.py`
- 修改: 移除 `allow_origins=["*"]`
- 效果: 仅允许 localhost 跨域

#### 4. 缓存清理机制
- 脚本: `scripts/clean_cache.sh`
- 定时: 每天 5:00
- 功能: 清理 mineru_cache、临时文件

#### 5. 文件权限
- 修复: `backend/.env` 权限改为 `600`
- 效果: 仅所有者可读写

### 安全验证

```
端口绑定: localhost:8000 ✅
API 文档: 404 (已禁用) ✅
.env 权限: 600 ✅
```

### 服务总览（9 个服务）

| 服务 | 定时 | 功能 |
|------|------|------|
| frontend | KeepAlive | 前端 |
| backend | KeepAlive | API |
| daily-workflow | 7:00 | 每日抓取 |
| task-worker | 按需 | 任务处理 |
| db-backup | 3:00 | 数据库备份 |
| log-rotate | 4:00 | 日志轮转 |
| cache-cleanup | 5:00 | 缓存清理 |
| health-check | 5 分钟 | 健康检查 |
| db-check | 周日 5:00 | 完整性检查 |