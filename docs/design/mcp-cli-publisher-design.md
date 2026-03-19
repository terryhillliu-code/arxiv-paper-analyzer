# ArXiv Paper Analyzer 扩展设计文档

> 版本: v1.0
> 日期: 2026-03-19
> 状态: 设计阶段

---

## 一、概述

### 1.1 目标

为 arxiv-paper-analyzer 系统扩展以下能力：
1. **MCP Server** - 让 AI 助手（Claude Desktop 等）能够查询和操作论文数据
2. **CLI 工具** - 提供命令行界面进行论文管理
3. **Publisher 模块** - 支持多平台内容发布（公众号、飞书、邮件、Webhook）

### 1.2 设计原则

- **向后兼容**: 不破坏现有功能，增量扩展
- **职责分离**: 读取走 DB 直连，写入走 HTTP API
- **独立部署**: zhiwei-obsidian 服务保持独立
- **可配置权限**: 通过配置文件控制只读/完全访问
- **完整测试**: 单元测试 + 集成测试覆盖

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户交互层                              │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│  CLI Tool   │  MCP Server │  Web UI     │  API Endpoints  │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬────────┘
       │             │             │               │
       ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                      服务层 (HTTP API)                       │
│  /api/papers  /api/trending  /api/fetch  /api/publish       │
└──────────────────────────┬──────────────────────────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ PostgreSQL  │     │   Redis     │     │  File Store │
│   (数据)    │     │  (缓存)     │     │  (文件)     │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 2.2 模块关系

```
backend/
├── app/
│   ├── mcp/                    # 新增: MCP Server
│   │   ├── __init__.py
│   │   ├── server.py           # MCP 服务主入口
│   │   ├── tools/              # MCP Tools 定义
│   │   │   ├── search.py
│   │   │   ├── paper.py
│   │   │   ├── trending.py
│   │   │   ├── analyze.py
│   │   │   └── export.py
│   │   └── transport/          # 传输层
│   │       ├── stdio.py
│   │       └── sse.py
│   │
│   ├── cli/                    # 新增: CLI 工具
│   │   ├── __init__.py
│   │   ├── main.py             # CLI 主入口
│   │   └── commands/           # 子命令
│   │       ├── fetch.py
│   │       ├── search.py
│   │       ├── analyze.py
│   │       ├── export.py
│   │       ├── trending.py
│   │       ├── publish.py
│   │       └── stats.py
│   │
│   ├── publishers/             # 新增: 发布器
│   │   ├── __init__.py
│   │   ├── base.py             # 基类
│   │   ├── wechat_mp.py        # 微信公众号
│   │   ├── feishu.py           # 飞书
│   │   ├── email.py            # 邮件
│   │   └── webhook.py          # Webhook
│   │
│   ├── exporters/              # 新增: 导出器
│   │   ├── __init__.py
│   │   ├── base.py             # 基类
│   │   ├── obsidian.py         # 重构自现有代码
│   │   └── bibtex.py           # 新增
│   │
│   └── services/               # 现有服务
│       ├── arxiv_service.py
│       ├── ai_service.py
│       └── obsidian_client.py  # 保留，调用 zhiwei-obsidian
```

---

## 三、MCP Server 设计

### 3.1 传输协议

支持两种传输方式：

| 协议 | 用途 | 配置 |
|------|------|------|
| stdio | Claude Desktop 本地集成 | `mcp_server.command = "python -m app.mcp.server"` |
| SSE | 远程服务集成 | `http://localhost:8000/mcp/sse` |

### 3.2 权限控制

通过配置文件 `mcp_config.yaml` 控制：

```yaml
# mcp_config.yaml
permission:
  mode: "read_only"  # read_only | full_access

  # read_only 模式允许的工具
  read_only_tools:
    - search_papers
    - get_paper
    - get_trending
    - export_to_bibtex

  # full_access 模式额外允许的工具
  full_access_tools:
    - analyze_paper
    - generate_summary
    - export_to_obsidian
```

### 3.3 Tools 定义

#### Tool 1: search_papers

```python
{
    "name": "search_papers",
    "description": "搜索论文，支持关键词、分类、日期范围筛选",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "categories": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
            "date_from": {"type": "string", "format": "date"},
            "date_to": {"type": "string", "format": "date"},
            "sort_by": {"type": "string", "enum": ["newest", "popularity"]},
            "limit": {"type": "integer", "default": 20}
        }
    }
}
```

**实现**: 直接查询 PostgreSQL 数据库

#### Tool 2: get_paper

```python
{
    "name": "get_paper",
    "description": "获取论文详情，包括摘要、分析结果、相关论文",
    "inputSchema": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "integer", "description": "论文 ID"},
            "include_analysis": {"type": "boolean", "default": true}
        },
        "required": ["paper_id"]
    }
}
```

**实现**: 直接查询数据库，组装完整论文信息

#### Tool 3: get_trending

```python
{
    "name": "get_trending",
    "description": "获取热门论文列表（按日期分组）",
    "inputSchema": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 7, "description": "最近几天"},
            "limit_per_day": {"type": "integer", "default": 20}
        }
    }
}
```

**实现**: 调用 `/api/papers/trending/daily` 端点

#### Tool 4: analyze_paper

```python
{
    "name": "analyze_paper",
    "description": "对论文进行深度分析（需要完全访问权限）",
    "inputSchema": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "integer"},
            "force_refresh": {"type": "boolean", "default": false}
        },
        "required": ["paper_id"]
    }
}
```

**实现**: 调用 HTTP API `POST /api/papers/{id}/analyze`

#### Tool 5: generate_summary

```python
{
    "name": "generate_summary",
    "description": "为论文生成 AI 摘要（需要完全访问权限）",
    "inputSchema": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "integer"},
            "regenerate": {"type": "boolean", "default": false}
        },
        "required": ["paper_id"]
    }
}
```

**实现**: 调用 HTTP API `POST /api/papers/{id}/summarize`

#### Tool 6: export_to_obsidian

```python
{
    "name": "export_to_obsidian",
    "description": "导出论文到 Obsidian（需要完全访问权限）",
    "inputSchema": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "integer"},
            "folder": {"type": "string", "default": "Inbox"}
        },
        "required": ["paper_id"]
    }
}
```

**实现**: 调用 zhiwei-obsidian 服务（127.0.0.1:8766）

#### Tool 7: export_to_bibtex

```python
{
    "name": "export_to_bibtex",
    "description": "导出论文引用为 BibTeX 格式",
    "inputSchema": {
        "type": "object",
        "properties": {
            "paper_ids": {"type": "array", "items": {"type": "integer"}},
            "output_file": {"type": "string"}
        },
        "required": ["paper_ids"]
    }
}
```

**实现**: 直接查询数据库，生成 BibTeX 格式

### 3.4 数据访问模式

```
┌─────────────────────────────────────────────────────┐
│                    MCP Server                        │
├─────────────────────┬───────────────────────────────┤
│      读取操作       │           写入操作            │
│  (search/get/trend) │  (analyze/generate/export)    │
├─────────────────────┼───────────────────────────────┤
│   直连 PostgreSQL   │      调用 HTTP API            │
│   SQLAlchemy ORM    │   requests.post(endpoint)     │
└─────────────────────┴───────────────────────────────┘
```

**原因**: 读取高频且需要灵活性，写入需要经过业务逻辑验证。

---

## 四、CLI 工具设计

### 4.1 命令概览

```bash
arxiv <command> [options]

Commands:
  fetch      抓取论文
  search     搜索论文
  analyze    分析论文
  export     导出论文
  trending   查看热门
  publish    发布内容
  stats      查看统计
```

### 4.2 命令详细设计

#### fetch - 抓取论文

```bash
arxiv fetch [OPTIONS]

Options:
  --categories TEXT   分类列表，逗号分隔 [default: cs.AI,cs.CL,cs.LG,cs.CV]
  --date TEXT         指定日期 (YYYY-MM-DD)
  --from-date TEXT    开始日期
  --to-date TEXT      结束日期
  --max-results INT   最大数量 [default: 300]
  --auto-summary      自动生成摘要 [default: True]
  --dry-run           试运行，不实际写入

Examples:
  arxiv fetch                           # 抓取今天和昨天
  arxiv fetch --date 2026-03-19         # 抓取指定日期
  arxiv fetch --from-date 2026-03-01 --to-date 2026-03-19
```

#### search - 搜索论文

```bash
arxiv search [OPTIONS] QUERY

Arguments:
  QUERY  搜索关键词

Options:
  --categories TEXT   分类过滤
  --tags TEXT         标签过滤
  --sort-by [newest|popularity]  排序方式
  --limit INT         返回数量 [default: 20]
  --format [table|json|md]       输出格式 [default: table]

Examples:
  arxiv search "attention mechanism"
  arxiv search "LLM" --categories cs.CL --sort-by popularity
  arxiv search "GPU" --format json
```

#### analyze - 分析论文

```bash
arxiv analyze [OPTIONS] PAPER_ID

Arguments:
  PAPER_ID  论文 ID

Options:
  --force-refresh    强制刷新分析结果
  --wait             等待分析完成

Examples:
  arxiv analyze 123
  arxiv analyze 123 --force-refresh --wait
```

#### export - 导出论文

```bash
arxiv export [OPTIONS] PAPER_IDS

Arguments:
  PAPER_IDS  论文 ID 列表，逗号分隔或范围

Options:
  --format [obsidian|bibtex|json]  导出格式 [default: obsidian]
  --output PATH                    输出文件路径
  --folder TEXT                    Obsidian 目标文件夹 [default: Inbox]

Examples:
  arxiv export 123                    # 导出到 Obsidian Inbox
  arxiv export 123,124,125            # 批量导出
  arxiv export 1-10                   # 范围导出
  arxiv export 123 --format bibtex -o refs.bib
```

#### trending - 热门论文

```bash
arxiv trending [OPTIONS]

Options:
  --days INT         最近几天 [default: 7]
  --per-day INT      每天数量 [default: 20]
  --analyze          对 Top 论文进行分析

Examples:
  arxiv trending              # 最近 7 天热门
  arxiv trending --days 3     # 最近 3 天
  arxiv trending --analyze    # 分析热门论文
```

#### publish - 发布内容

```bash
arxiv publish [OPTIONS]

Options:
  --platform [wechat|feishu|email|webhook]  发布平台
  --template TEXT                           模板名称
  --paper-ids TEXT                          论文 ID 列表
  --dry-run                                 预览不发送

Examples:
  arxiv publish --platform wechat --paper-ids 1,2,3
  arxiv publish --platform feishu --template daily_report
  arxiv publish --dry-run                     # 预览
```

#### stats - 统计信息

```bash
arxiv stats [OPTIONS]

Options:
  --detail    显示详细统计

Examples:
  arxiv stats
  arxiv stats --detail
```

### 4.3 输出格式

CLI 自动根据终端宽度调整输出格式：

| 格式 | 用途 | 触发条件 |
|------|------|----------|
| table | 终端阅读 | 默认，TTY 终端 |
| json | 脚本处理 | `--format json` 或管道输出 |
| md | 文档生成 | `--format md` |

---

## 五、Publisher 模块设计

### 5.1 发布器基类

```python
# app/publishers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class PublishResult:
    success: bool
    platform: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

class BasePublisher(ABC):
    """发布器基类"""

    name: str = "base"
    requires_auth: bool = True

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """验证配置"""
        pass

    @abstractmethod
    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict]] = None,
        **kwargs
    ) -> PublishResult:
        """发布内容"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """测试连接"""
        pass

    def render_template(self, template_name: str, context: Dict) -> str:
        """渲染模板"""
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader("templates/publishers"))
        template = env.get_template(f"{self.name}/{template_name}")
        return template.render(**context)
```

### 5.2 微信公众号发布器

```python
# app/publishers/wechat_mp.py
from .base import BasePublisher, PublishResult
import aiohttp

class WeChatMPPublisher(BasePublisher):
    """微信公众号发布器"""

    name = "wechat_mp"
    requires_auth = True

    def _validate_config(self) -> None:
        required = ["app_id", "app_secret"]
        for key in required:
            if key not in self.config:
                raise ValueError(f"缺少配置: {key}")

    async def _get_access_token(self) -> str:
        """获取 access_token"""
        async with aiohttp.ClientSession() as session:
            url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={self.config['app_id']}&secret={self.config['app_secret']}"
            async with session.get(url) as resp:
                data = await resp.json()
                if "access_token" in data:
                    return data["access_token"]
                raise Exception(f"获取 token 失败: {data}")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict]] = None,
        **kwargs
    ) -> PublishResult:
        """发布图文消息"""
        try:
            token = await self._get_access_token()

            # 构建图文消息
            articles = [{
                "title": title or "今日论文精选",
                "author": kwargs.get("author", "ArXiv Bot"),
                "digest": kwargs.get("digest", ""),
                "content": content,
                "content_source_url": kwargs.get("source_url", ""),
            }]

            async with aiohttp.ClientSession() as session:
                url = f"https://api.weixin.qq.com/cgi-bin/material/add_news?access_token={token}"
                async with session.post(url, json={"articles": articles}) as resp:
                    data = await resp.json()

                    if "media_id" in data:
                        return PublishResult(
                            success=True,
                            platform=self.name,
                            message_id=data["media_id"],
                            metadata={"media_id": data["media_id"]}
                        )
                    else:
                        return PublishResult(
                            success=False,
                            platform=self.name,
                            error=data.get("errmsg", "未知错误")
                        )
        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.name,
                error=str(e)
            )

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            await self._get_access_token()
            return True
        except:
            return False
```

### 5.3 飞书发布器

```python
# app/publishers/feishu.py
from .base import BasePublisher, PublishResult
import aiohttp

class FeishuPublisher(BasePublisher):
    """飞书发布器"""

    name = "feishu"

    def _validate_config(self) -> None:
        required = ["webhook_url"]
        for key in required:
            if key not in self.config:
                raise ValueError(f"缺少配置: {key}")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict]] = None,
        **kwargs
    ) -> PublishResult:
        """发送飞书消息"""
        message = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title or "论文推送"},
                    "template": "blue"
                },
                "elements": [
                    {"tag": "markdown", "content": content}
                ]
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config["webhook_url"],
                json=message
            ) as resp:
                data = await resp.json()
                if data.get("StatusCode") == 0:
                    return PublishResult(success=True, platform=self.name)
                else:
                    return PublishResult(
                        success=False,
                        platform=self.name,
                        error=data.get("msg", "发送失败")
                    )

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config["webhook_url"],
                    json={"msg_type": "text", "content": {"text": "测试连接"}}
                ) as resp:
                    data = await resp.json()
                    return data.get("StatusCode") == 0
        except:
            return False
```

### 5.4 邮件发布器

```python
# app/publishers/email.py
from .base import BasePublisher, PublishResult
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailPublisher(BasePublisher):
    """邮件发布器"""

    name = "email"

    def _validate_config(self) -> None:
        required = ["smtp_host", "smtp_port", "sender", "recipients"]
        for key in required:
            if key not in self.config:
                raise ValueError(f"缺少配置: {key}")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict]] = None,
        **kwargs
    ) -> PublishResult:
        """发送邮件"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title or "ArXiv 论文推送"
        msg["From"] = self.config["sender"]
        msg["To"] = ", ".join(self.config["recipients"])

        # 纯文本版本
        msg.attach(MIMEText(content, "plain", "utf-8"))

        # HTML 版本（如果有）
        if kwargs.get("html_content"):
            msg.attach(MIMEText(kwargs["html_content"], "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.config["smtp_host"],
                port=self.config["smtp_port"],
                username=self.config.get("smtp_user"),
                password=self.config.get("smtp_password"),
                use_tls=self.config.get("use_tls", True)
            )
            return PublishResult(success=True, platform=self.name)
        except Exception as e:
            return PublishResult(success=False, platform=self.name, error=str(e))

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            await aiosmtplib.send(
                None,
                hostname=self.config["smtp_host"],
                port=self.config["smtp_port"],
                use_tls=self.config.get("use_tls", True)
            )
            return True
        except:
            return False
```

### 5.5 Webhook 发布器

```python
# app/publishers/webhook.py
from .base import BasePublisher, PublishResult
import aiohttp

class WebhookPublisher(BasePublisher):
    """通用 Webhook 发布器"""

    name = "webhook"

    def _validate_config(self) -> None:
        if "url" not in self.config:
            raise ValueError("缺少配置: url")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict]] = None,
        **kwargs
    ) -> PublishResult:
        """发送 Webhook 请求"""
        payload = {
            "title": title,
            "content": content,
            "papers": papers,
            **kwargs
        }

        headers = self.config.get("headers", {})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config["url"],
                json=payload,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return PublishResult(
                        success=True,
                        platform=self.name,
                        metadata={"response": data}
                    )
                else:
                    text = await resp.text()
                    return PublishResult(
                        success=False,
                        platform=self.name,
                        error=f"HTTP {resp.status}: {text}"
                    )

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config["url"],
                    json={"test": True},
                    timeout=5
                ) as resp:
                    return resp.status < 400
        except:
            return False
```

### 5.6 配置示例

```yaml
# publishers_config.yaml
publishers:
  wechat_mp:
    enabled: true
    app_id: "${WECHAT_APP_ID}"
    app_secret: "${WECHAT_APP_SECRET}"

  feishu:
    enabled: true
    webhook_url: "${FEISHU_WEBHOOK_URL}"

  email:
    enabled: true
    smtp_host: "smtp.example.com"
    smtp_port: 587
    sender: "bot@example.com"
    recipients:
      - "user1@example.com"
      - "user2@example.com"
    smtp_user: "${SMTP_USER}"
    smtp_password: "${SMTP_PASSWORD}"
    use_tls: true

  webhook:
    enabled: true
    url: "${WEBHOOK_URL}"
    headers:
      Authorization: "Bearer ${WEBHOOK_TOKEN}"

templates:
  daily_report: "templates/publishers/common/daily_report.md"
  paper_digest: "templates/publishers/common/paper_digest.md"
```

---

## 六、Exporter 模块设计

### 6.1 导出器基类

```python
# app/exporters/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseExporter(ABC):
    """导出器基类"""

    name: str = "base"

    @abstractmethod
    def export_paper(self, paper: Dict[str, Any]) -> str:
        """导出单篇论文"""
        pass

    @abstractmethod
    def export_papers(self, papers: list[Dict[str, Any]]) -> str:
        """导出多篇论文"""
        pass
```

### 6.2 BibTeX 导出器

```python
# app/exporters/bibtex.py
from .base import BaseExporter
from typing import Dict, Any, List

class BibTeXExporter(BaseExporter):
    """BibTeX 格式导出器"""

    name = "bibtex"

    def _generate_key(self, paper: Dict[str, Any]) -> str:
        """生成引用键"""
        # 格式: FirstAuthorYear + 首词
        first_author = paper.get("authors", ["Unknown"])[0].split()[-1]
        year = paper.get("publish_date", "")[:4]
        title_word = paper.get("title", "").split()[0] if paper.get("title") else "Paper"
        return f"{first_author}{year}{title_word}".lower()

    def _escape_latex(self, text: str) -> str:
        """转义 LaTeX 特殊字符"""
        replacements = {
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def export_paper(self, paper: Dict[str, Any]) -> str:
        """导出单篇论文为 BibTeX"""
        key = self._generate_key(paper)
        title = self._escape_latex(paper.get("title", ""))
        authors = " and ".join(paper.get("authors", []))
        year = paper.get("publish_date", "")[:4]
        arxiv_id = paper.get("arxiv_id", "")
        url = paper.get("pdf_url", f"https://arxiv.org/abs/{arxiv_id}")
        abstract = self._escape_latex(paper.get("abstract", ""))

        entry_type = "@article" if arxiv_id else "@misc"

        bibtex = f"""{entry_type}{{{key},
  author = {{{authors}}},
  title = {{{title}}},
  year = {{{year}}},
  eprint = {{{arxiv_id}}},
  primaryClass = {{{paper.get("primary_category", "")}}},
  url = {{{url}}},
  abstract = {{{abstract}}}
}}
"""
        return bibtex

    def export_papers(self, papers: List[Dict[str, Any]]) -> str:
        """导出多篇论文"""
        entries = [self.export_paper(p) for p in papers]
        return "\n".join(entries)
```

### 6.3 Obsidian 导出器（重构）

```python
# app/exporters/obsidian.py
from .base import BaseExporter
from typing import Dict, Any, List
import yaml
from datetime import datetime

class ObsidianExporter(BaseExporter):
    """Obsidian 格式导出器"""

    name = "obsidian"

    def __init__(self, client=None):
        """
        Args:
            client: ObsidianClient 实例，用于调用 zhiwei-obsidian 服务
        """
        self.client = client

    def export_paper(self, paper: Dict[str, Any]) -> str:
        """导出单篇论文为 Obsidian Markdown"""
        frontmatter = self._build_frontmatter(paper)
        body = self._build_body(paper)
        return f"---\n{frontmatter}\n---\n\n{body}"

    def _build_frontmatter(self, paper: Dict[str, Any]) -> str:
        """构建 YAML frontmatter"""
        meta = {
            "title": paper.get("title", ""),
            "arxiv_id": paper.get("arxiv_id", ""),
            "authors": paper.get("authors", []),
            "date": paper.get("publish_date", ""),
            "categories": paper.get("categories", []),
            "tags": paper.get("tags", []),
            "tier": paper.get("tier", "C"),
            "url": f"https://arxiv.org/abs/{paper.get('arxiv_id', '')}",
        }

        if paper.get("institutions"):
            meta["institutions"] = paper["institutions"]

        if paper.get("methodology"):
            meta["methodology"] = paper["methodology"]

        return yaml.dump(meta, allow_unicode=True, sort_keys=False)

    def _build_body(self, paper: Dict[str, Any]) -> str:
        """构建正文"""
        sections = []

        # 摘要
        if paper.get("summary"):
            sections.append(f"## AI 摘要\n\n{paper['summary']}\n")
        elif paper.get("abstract"):
            sections.append(f"## 原始摘要\n\n{paper['abstract']}\n")

        # 核心贡献
        if paper.get("key_contributions"):
            sections.append("## 核心贡献\n")
            for c in paper["key_contributions"]:
                sections.append(f"- {c}")
            sections.append("")

        # 行动项
        if paper.get("action_items"):
            sections.append("## 行动项\n")
            for item in paper["action_items"]:
                sections.append(f"- [ ] {item}")
            sections.append("")

        # 知识链接
        if paper.get("knowledge_links"):
            sections.append("## 相关知识\n")
            for link in paper["knowledge_links"]:
                sections.append(f"- [[{link}]]")
            sections.append("")

        return "\n".join(sections)

    async def export_to_vault(
        self,
        paper: Dict[str, Any],
        folder: str = "Inbox"
    ) -> Dict[str, Any]:
        """导出到 Obsidian Vault（通过 zhiwei-obsidian 服务）"""
        if not self.client:
            raise ValueError("ObsidianClient 未配置")

        content = self.export_paper(paper)
        filename = self._sanitize_filename(paper.get("title", "untitled"))

        return await self.client.export_note(
            title=filename,
            content=content,
            folder=folder
        )

    def _sanitize_filename(self, title: str) -> str:
        """清理文件名"""
        # 移除不允许的字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            title = title.replace(char, "")
        # 限制长度
        return title[:100].strip()
```

---

## 七、配置管理

### 7.1 配置文件结构

```
backend/
├── config/
│   ├── default.yaml           # 默认配置
│   ├── development.yaml       # 开发环境
│   ├── production.yaml        # 生产环境
│   ├── mcp_config.yaml        # MCP 权限配置
│   └── publishers_config.yaml # 发布器配置
```

### 7.2 环境变量映射

```yaml
# config/default.yaml
database:
  url: "${DATABASE_URL}"

ai:
  model: "${AI_MODEL:-qwen-max}"
  api_key: "${AI_API_KEY}"

obsidian:
  service_url: "${OBSIDIAN_SERVICE_URL:-http://127.0.0.1:8766}"

mcp:
  config_path: "config/mcp_config.yaml"

publishers:
  config_path: "config/publishers_config.yaml"
```

---

## 八、测试策略

### 8.1 测试覆盖

| 模块 | 单元测试 | 集成测试 |
|------|----------|----------|
| MCP Server | ✅ Tools 逻辑测试 | ✅ 端到端协议测试 |
| CLI | ✅ 命令解析测试 | ✅ 实际执行测试 |
| Publisher | ✅ Mock HTTP 测试 | ✅ 真实 API 测试（可选）|
| Exporter | ✅ 格式验证测试 | ✅ 端到端导出测试 |

### 8.2 测试文件结构

```
tests/
├── unit/
│   ├── test_mcp_tools.py
│   ├── test_cli_commands.py
│   ├── test_publishers.py
│   └── test_exporters.py
├── integration/
│   ├── test_mcp_server.py
│   ├── test_cli_flow.py
│   └── test_publish_flow.py
└── fixtures/
    ├── papers.json
    └── config.yaml
```

---

## 九、部署方案

### 9.1 开发环境

```bash
# 启动后端
cd backend && uvicorn app.main:app --reload

# 启动 MCP Server (stdio)
python -m app.mcp.server

# 启动 MCP Server (SSE)
python -m app.mcp.server --transport sse --port 8001
```

### 9.2 生产环境

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - AI_API_KEY=${AI_API_KEY}

  mcp-server:
    build: ./backend
    command: python -m app.mcp.server --transport sse
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=${DATABASE_URL}
```

---

## 十、实施计划

### Phase 1: 基础架构 (Week 1)

1. 创建模块目录结构
2. 实现 BaseExporter 和 BasePublisher 基类
3. 实现 BibTeXExporter
4. 重构 ObsidianExporter
5. 编写单元测试

### Phase 2: MCP Server (Week 2)

1. 实现 MCP Server 框架
2. 实现 7 个 Tools
3. 实现 stdio 和 SSE 传输
4. 实现权限控制
5. 编写集成测试

### Phase 3: CLI 工具 (Week 3)

1. 实现 CLI 框架
2. 实现 7 个命令
3. 实现输出格式化
4. 编写测试

### Phase 4: Publisher 模块 (Week 4)

1. 实现微信公众号发布器
2. 实现飞书发布器
3. 实现邮件发布器
4. 实现 Webhook 发布器
5. 实现模板系统
6. 编写测试

### Phase 5: 集成测试 (Week 5)

1. 端到端测试
2. 性能测试
3. 文档编写
4. 部署验证

---

## 十一、风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 微信 API 限制 | 高 | 实现 rate limiting，队列化发布 |
| 数据库直连性能 | 中 | 添加查询缓存，使用连接池 |
| MCP 协议变更 | 中 | 抽象传输层，适配器模式 |
| 配置泄露 | 高 | 环境变量注入，不提交密钥 |

---

## 附录 A: API 端点清单

现有端点保持不变，新增：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/mcp/sse` | GET | MCP SSE 传输 |
| `/api/publish` | POST | 发布内容 |
| `/api/export/bibtex` | POST | 导出 BibTeX |

## 附录 B: 依赖清单

新增依赖：

```
click>=8.0.0           # CLI
mcp>=0.1.0             # MCP 协议
aiosmtplib>=3.0.0      # 邮件
jinja2>=3.0.0          # 模板
pyyaml>=6.0            # 配置
```