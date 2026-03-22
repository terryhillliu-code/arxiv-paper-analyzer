# 知微系统：NotebookLM 联动工具使用指南

本指南介绍如何使用最新集成的 `export-notebook` 能力，将本地研究成果高效同步至云端“超级大脑” NotebookLM。

## 1. 快速开始 (快速导出)

打开终端，进入 `arxiv-paper-analyzer/backend` 目录，执行以下命令：

```bash
# 自动提取库中所有的 Tier A 和 B 级论文（经过 AI 深度分析的）
./venv/bin/python3 scripts/manage.py export-notebook
```

### 更多常用选项：
- **仅导出最精华 (Tier A)**：
  ```bash
  ./venv/bin/python3 scripts/manage.py export-notebook --tiers A
  ```
- **限制导出数量（如最近 5 篇）**：
  ```bash
  ./venv/bin/python3 scripts/manage.py export-notebook --limit 5
  ```

---

## 2. 操作效果与产出

执行完毕后，系统会在本地暂存区 `/tmp/notebooklm_export/` 生成按论文标题命名的文件夹。

### 获得的内容：
1. **`analysis.md` (清洗后的报告)**：
   - 移除了 Obsidian 的 `[[双链]]` 标记，避免 NotebookLM 解析混乱。
   - 移除了本地路径引用，重构了**元数据头**（包含等级、评分、来源）。
   - 保留了完整的深度分析内容，非常适合 NotebookLM 生成播客（Podcast）和思维导图。
2. **`*.pdf` (原始附件)**：
   - 自动从本地库中提取关联的原始 PDF 文件并改名为规范名称。

### 协作建议 (一键投喂)：
1. 打开浏览器登录 [NotebookLM](https://notebooklm.google.com/)。
2. 创建一个新笔记本（例如“AI 深度研究”）。
3. 直接将 `/tmp/notebooklm_export/` 下的对应文件夹中的 `analysis.md` 和 `PDF` **一键拖入**上传。
4. **效果**：NotebookLM 将能够基于您本地已筛选的高质量深度分析（而非原始论文的晦涩内容）为您提供极精准的总结、对比问答和音频生成。

---

## 3. 其他管理指令速查

归一化后的 `scripts/manage.py` 还支持以下核心操作：

- **分析新论文**：`python3 scripts/manage.py analyze`
- **自动检测与修复**：`python3 scripts/manage.py verify --fix`
- **同步引用评分**：`python3 scripts/manage.py sync-scores`
- **重估 Tier 等级**：`python3 scripts/manage.py reevaluate`

---

## 4. 未来扩展
本工具已预留 `ITransportStrategy` 接口。如果您后续获取了 **NotebookLM MCP Server**，我们可以通过简单配置实现“指令级直传”，连拖拽步骤都将省去。
