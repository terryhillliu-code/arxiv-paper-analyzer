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