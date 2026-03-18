# MinerU 集成方案

> 日期: 2026-03-18
> 状态: ✅ 已实现

## 一、背景

### 当前实现

项目使用 PyMuPDF (fitz) 进行 PDF 文本提取：

```python
# backend/app/services/pdf_service.py
def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    for page in doc:
        text += page.get_text()
```

**问题**：
- 无法保留文档结构（标题、章节、列表）
- 表格提取为乱序文本
- 数学公式丢失或乱码
- 图片无法处理
- 无语义理解

### MinerU 优势

基于对比测试（见 `scripts/test_mineru.py`）：

| 指标 | PyMuPDF | MinerU |
|------|---------|--------|
| 解析时间 | 0.12s | ~5min |
| 文本结构 | 无 | Markdown 完整结构 |
| 表格 | 丢失 | 保留为 Markdown 表格 |
| 公式 | 乱码 | LaTeX 格式 |
| 图片 | 忽略 | 提取并保存 |
| 标题识别 | 无 | 自动识别层级 |

**结论**：MinerU 适合深度分析场景，PyMuPDF 适合快速预览。

## 二、集成架构

### 2.1 双轨策略

```
┌─────────────────────────────────────────────────────────────┐
│                      PDF 处理请求                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  判断处理模式    │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   快速模式       │             │   深度模式       │
    │   (PyMuPDF)      │             │   (MinerU)       │
    └─────────────────┘             └─────────────────┘
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │  纯文本预览      │             │  结构化 Markdown │
    │  列表页摘要      │             │  深度分析输入     │
    │  搜索索引        │             │  Obsidian 导出    │
    └─────────────────┘             └─────────────────┘
```

### 2.2 配置项

```python
# backend/app/config.py
class Settings(BaseSettings):
    # PDF 解析配置
    pdf_parser: str = "pymupdf"  # pymupdf | mineru | auto
    mineru_cache_dir: str = "./data/mineru_cache"
    mineru_timeout: int = 600  # 10 分钟超时
```

```env
# backend/.env
PDF_PARSER=auto  # auto = 深度分析时用 MinerU，其他用 PyMuPDF
MINERU_CACHE_DIR=./data/mineru_cache
```

## 三、代码实现

### 3.1 PDF 服务重构

```python
# backend/app/services/pdf_service.py

import asyncio
import subprocess
import hashlib
from pathlib import Path
from typing import Optional, Tuple
import fitz  # PyMuPDF
from app.config import get_settings

class PDFService:
    """PDF 处理服务，支持双轨策略。"""

    def __init__(self):
        self.settings = get_settings()
        self.cache_dir = Path(self.settings.mineru_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def extract_text_fast(self, pdf_path: str) -> str:
        """快速提取纯文本（PyMuPDF）。

        用途：列表预览、搜索索引、快速浏览。
        """
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
        doc.close()
        return "\n\n".join(text_parts)

    async def extract_markdown(
        self,
        pdf_path: str,
        use_cache: bool = True
    ) -> Tuple[str, dict]:
        """提取结构化 Markdown（MinerU）。

        用途：深度分析、Obsidian 导出。

        Args:
            pdf_path: PDF 文件路径
            use_cache: 是否使用缓存

        Returns:
            (markdown_content, metadata)
        """
        pdf_path = Path(pdf_path)
        cache_key = self._get_cache_key(pdf_path)
        cache_file = self.cache_dir / f"{cache_key}.md"
        meta_file = self.cache_dir / f"{cache_key}.json"

        # 检查缓存
        if use_cache and cache_file.exists():
            return cache_file.read_text(), self._load_meta(meta_file)

        # 运行 MinerU
        output_dir = self.cache_dir / f"temp_{cache_key}"
        cmd = [
            "mineru",
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "-m", "auto",
        ]

        try:
            # 异步执行
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                result.communicate(),
                timeout=self.settings.mineru_timeout
            )

            if result.returncode != 0:
                raise RuntimeError(f"MinerU failed: {stderr.decode()}")

            # 查找输出文件
            md_files = list(output_dir.rglob("*.md"))
            if not md_files:
                raise RuntimeError("No markdown output found")

            md_content = md_files[0].read_text()

            # 保存缓存
            cache_file.write_text(md_content)
            metadata = {
                "source": str(pdf_path),
                "headings": md_content.count("# "),
                "tables": md_content.count("|---|"),
                "formulas": md_content.count("$"),
                "images": len(list(output_dir.rglob("*.png"))),
            }
            meta_file.write_text(json.dumps(metadata))

            # 清理临时文件
            shutil.rmtree(output_dir, ignore_errors=True)

            return md_content, metadata

        except asyncio.TimeoutError:
            raise RuntimeError("MinerU timeout")
        except Exception as e:
            # 失败时回退到 PyMuPDF
            logger.warning(f"MinerU failed, fallback to PyMuPDF: {e}")
            return self.extract_text_fast(str(pdf_path)), {}

    def _get_cache_key(self, pdf_path: Path) -> str:
        """基于文件内容生成缓存 key。"""
        content = pdf_path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]

    def _load_meta(self, meta_file: Path) -> dict:
        """加载元数据。"""
        if meta_file.exists():
            return json.loads(meta_file.read_text())
        return {}
```

### 3.2 分析路由更新

```python
# backend/app/routers/papers.py

@router.post("/{paper_id}/analyze")
async def analyze_paper(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    pdf_service: PDFService = Depends(get_pdf_service),
):
    """深度分析论文。"""
    paper = await get_paper_or_404(db, paper_id)

    # 判断 PDF 是否存在
    if not paper.pdf_path or not Path(paper.pdf_path).exists():
        raise HTTPException(400, "PDF not available")

    # 使用 MinerU 提取结构化内容
    content, metadata = await pdf_service.extract_markdown(paper.pdf_path)

    # 调用 AI 分析
    result = await ai_service.generate_deep_analysis(
        title=paper.title,
        authors=paper.authors,
        institutions=paper.institutions or [],
        publish_date=str(paper.published_date),
        categories=paper.categories or [],
        arxiv_url=paper.arxiv_url,
        pdf_url=paper.pdf_url,
        content=content,  # 结构化 Markdown
    )

    # 保存分析结果...
```

### 3.3 依赖安装

```txt
# backend/requirements.txt 追加
# MinerU PDF 解析（可选，用于深度分析）
# magic-pdf[full]>=0.6.0  # 完整安装，含模型
```

**安装命令**：
```bash
# 方式 1: 完整安装（推荐，首次需要下载模型）
pip install magic-pdf[full]

# 方式 2: 最小安装（使用在线 API）
pip install magic-pdf

# 配置 HuggingFace 镜像（国内）
export HF_ENDPOINT=https://hf-mirror.com
```

## 四、缓存策略

### 4.1 缓存结构

```
data/mineru_cache/
├── abc123def456.md          # Markdown 缓存
├── abc123def456.json        # 元数据
├── abc123def456_images/     # 提取的图片
│   ├── image_001.png
│   └── image_002.png
└── ...
```

### 4.2 缓存清理

```python
# backend/app/services/cache_service.py

async def cleanup_mineru_cache(max_age_days: int = 30):
    """清理过期缓存。"""
    cache_dir = Path(settings.mineru_cache_dir)
    cutoff = datetime.now() - timedelta(days=max_age_days)

    for md_file in cache_dir.glob("*.md"):
        if datetime.fromtimestamp(md_file.stat().st_mtime) < cutoff:
            md_file.unlink()
            meta_file = md_file.with_suffix(".json")
            if meta_file.exists():
                meta_file.unlink()
```

## 五、API 变更

### 5.1 新增端点

```
POST /api/papers/{id}/extract
  - force_refresh: bool = false
  - 返回: { markdown, metadata }
```

### 5.2 现有端点变更

```
POST /api/papers/{id}/analyze
  - 自动使用 MinerU 提取结构化内容
  - 超时自动回退到 PyMuPDF

GET /api/papers/{id}/markdown
  - 优先使用 MinerU 缓存
  - 缓存不存在时按需生成
```

## 六、部署注意事项

### 6.1 资源需求

| 资源 | 要求 |
|------|------|
| 内存 | >= 8GB（模型加载） |
| 磁盘 | >= 5GB（模型文件） |
| CPU/GPU | GPU 推荐，CPU 可用但慢 |

### 6.2 首次部署

```bash
# 1. 安装 MinerU
pip install magic-pdf[full]

# 2. 下载模型（自动进行，约 5GB）
# 首次运行会自动下载

# 3. 配置镜像（国内）
export HF_ENDPOINT=https://hf-mirror.com

# 4. 测试
mineru -p test.pdf -o /tmp/test -m auto
```

### 6.3 监控

```python
# 添加健康检查
@router.get("/health/mineru")
async def check_mineru():
    try:
        result = subprocess.run(
            ["mineru", "--version"],
            capture_output=True,
            timeout=5
        )
        return {"status": "ok", "version": result.stdout.decode().strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

## 七、实施计划

| 阶段 | 内容 | 预估时间 |
|------|------|----------|
| Phase 1 | 添加 PDFService 类，支持双轨策略 | 2h |
| Phase 2 | 更新分析路由，集成 MinerU | 1h |
| Phase 3 | 添加缓存机制 | 1h |
| Phase 4 | 测试与文档更新 | 1h |

**总计**: 约 5 小时

## 八、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| MinerU 安装失败 | 中 | 高 | 提供回退到 PyMuPDF |
| 模型下载失败 | 中 | 高 | 使用 HF 镜像 |
| 解析超时 | 低 | 中 | 设置 10 分钟超时 |
| 内存不足 | 低 | 高 | 文档说明资源需求 |

## 九、后续优化

1. **批量处理**: 后台队列异步处理多篇论文
2. **增量更新**: 检测 PDF 变化，自动更新缓存
3. **模型优化**: 探索更轻量的模型方案
4. **云端 API**: 集成 MinerU 云服务（如有）