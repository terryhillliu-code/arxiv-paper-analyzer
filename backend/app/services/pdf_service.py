"""PDF 下载与文本提取服务模块。

提供 PDF 文件下载和文本内容提取功能。
支持双轨策略：PyMuPDF (快速) + MinerU (深度)。
"""

import asyncio
import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

import fitz  # PyMuPDF
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class PDFService:
    """PDF 处理服务。

    提供 PDF 下载和文本提取功能。
    支持双轨策略：
    - PyMuPDF: 快速提取纯文本，用于预览和搜索
    - MinerU: 深度解析，保留结构、表格、公式
    """

    def __init__(self):
        """初始化 PDF 服务。"""
        self.settings = get_settings()
        self._init_cache_dir()

    def _init_cache_dir(self):
        """初始化缓存目录。"""
        cache_dir = Path(self.settings.mineru_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"MinerU 缓存目录: {cache_dir}")

    @staticmethod
    async def download_pdf(pdf_url: str, arxiv_id: str) -> str:
        """下载 PDF 文件到本地。

        Args:
            pdf_url: PDF 下载链接
            arxiv_id: arXiv 论文 ID

        Returns:
            本地 PDF 文件路径

        Raises:
            Exception: 下载失败时抛出异常
        """
        settings = get_settings()

        # 确保存储目录存在
        storage_path = Path(settings.pdf_storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        # 将 arxiv_id 中的 / 和 : 替换为 _ 作为文件名
        safe_id = arxiv_id.replace("/", "_").replace(":", "_")
        filename = f"{safe_id}.pdf"
        pdf_path = storage_path / filename

        # 如果本地文件已存在，直接返回路径
        if pdf_path.exists():
            logger.info(f"PDF 已存在: {pdf_path}")
            return str(pdf_path)

        # 镜像源列表（优先使用国内镜像）
        mirror_urls = [
            pdf_url,  # 原始 URL
            pdf_url.replace("https://arxiv.org", "https://cn.arxiv.org"),  # 国内镜像
        ]

        try:
            # 使用 httpx 下载 PDF（增加超时和重试）
            async with httpx.AsyncClient(
                timeout=300.0,  # 5 分钟超时
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10)  # 允许更多连接
            ) as client:
                # 尝试多个镜像源
                for i, url in enumerate(mirror_urls):
                    try:
                        logger.info(f"开始下载 PDF (镜像{i+1}): {url}")

                        # 流式下载，避免内存问题
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()

                            # 保存到本地
                            with open(pdf_path, "wb") as f:
                                async for chunk in response.aiter_bytes(chunk_size=8192):
                                    f.write(chunk)

                        logger.info(f"PDF 下载成功: {pdf_path}")
                        return str(pdf_path)

                    except Exception as e:
                        logger.warning(f"镜像{i+1}下载失败: {e}")
                        if i == len(mirror_urls) - 1:
                            raise
                        continue

        except Exception as e:
            logger.error(f"下载 PDF 失败: {pdf_url}, 错误: {e}", exc_info=True)
            raise

    @staticmethod
    def extract_text(pdf_path: str, max_pages: int = 30) -> str:
        """从 PDF 文件中提取纯文本内容 (PyMuPDF)。

        用于快速预览、搜索索引、列表展示。

        Args:
            pdf_path: PDF 文件路径
            max_pages: 最大提取页数，默认 30 页

        Returns:
            提取的文本内容
        """
        try:
            # 抑制 MuPDF 警告
            import sys
            import os
            old_stderr = os.dup(2)
            devnull = os.open('/dev/null', os.O_WRONLY)
            os.dup2(devnull, 2)

            try:
                doc = fitz.open(pdf_path)
            finally:
                # 恢复 stderr
                os.dup2(old_stderr, 2)
                os.close(devnull)
                os.close(old_stderr)

            text_parts = []
            page_count = min(len(doc), max_pages)

            # 遍历页面提取文本
            for page_num in range(page_count):
                page = doc[page_num]
                text = page.get_text()

                if text.strip():
                    text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

            doc.close()

            # 合并所有文本
            full_text = "\n\n".join(text_parts)

            # 清理文本
            full_text = PDFService._clean_text(full_text)

            logger.info(f"PyMuPDF 文本提取成功: {pdf_path}, 共 {page_count} 页")
            return full_text

        except Exception as e:
            logger.error(f"提取文本失败: {pdf_path}, 错误: {e}", exc_info=True)
            return ""

    async def extract_markdown(
        self,
        pdf_path: str,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> Tuple[str, Dict]:
        """提取结构化 Markdown (MinerU)。

        用于深度分析、Obsidian 导出。
        保留文档结构、表格、公式、图片。

        Args:
            pdf_path: PDF 文件路径
            use_cache: 是否使用缓存
            force_refresh: 是否强制刷新缓存

        Returns:
            (markdown_content, metadata)
            metadata 包含: headings, tables, formulas, images 等统计
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        # 生成缓存 key
        cache_key = self._get_cache_key(pdf_path)
        cache_file = Path(self.settings.mineru_cache_dir) / f"{cache_key}.md"
        meta_file = Path(self.settings.mineru_cache_dir) / f"{cache_key}.json"

        # 检查缓存
        if use_cache and not force_refresh and cache_file.exists():
            logger.info(f"使用缓存: {cache_file}")
            md_content = cache_file.read_text(encoding="utf-8")
            metadata = self._load_meta(meta_file)
            return md_content, metadata

        # 运行 MinerU
        logger.info(f"开始 MinerU 解析: {pdf_path}")
        try:
            md_content, metadata = await self._run_mineru(pdf_path, cache_key)

            # 保存缓存
            cache_file.write_text(md_content, encoding="utf-8")
            meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            logger.info(f"MinerU 解析完成: {len(md_content)} 字符")
            return md_content, metadata

        except Exception as e:
            logger.error(f"MinerU 解析失败: {e}", exc_info=True)
            # 回退到 PyMuPDF
            logger.warning("回退到 PyMuPDF 提取纯文本")
            text = self.extract_text(str(pdf_path))
            return text, {"parser": "pymupdf_fallback", "error": str(e)}

    async def _run_mineru(self, pdf_path: Path, cache_key: str) -> Tuple[str, Dict]:
        """执行 MinerU CLI 解析。

        Args:
            pdf_path: PDF 文件路径
            cache_key: 缓存标识

        Returns:
            (markdown_content, metadata)
        """
        output_dir = Path(self.settings.mineru_cache_dir) / f"temp_{cache_key}"

        # 清理可能的旧临时目录
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)

        cmd = [
            self.settings.mineru_path,
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "-m", "auto",
        ]

        logger.info(f"执行命令: {' '.join(cmd)}")

        # 设置环境变量（HuggingFace 镜像 + 禁用 ObjC 警告）
        import os
        env = os.environ.copy()
        env["HF_ENDPOINT"] = "https://hf-mirror.com"
        # 禁用 FFmpeg 库冲突警告（cv2 和 av 版本不同导致）
        env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
        env["NO_AT_BRIDGE"] = "1"

        try:
            # 异步执行子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # 动态超时：根据文件大小调整（优先使用 MinerU，延长超时）
            file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
            if file_size_mb < 2:
                timeout = 600  # 小文件 10 分钟
            elif file_size_mb < 5:
                timeout = 900  # 中等文件 15 分钟
            elif file_size_mb < 10:
                timeout = 1500  # 较大文件 25 分钟
            else:
                timeout = 2400  # 大文件 40 分钟

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            # 检查输出文件（即使有警告也继续）
            md_files = list(output_dir.rglob("*.md"))

            # 只有在真正失败且没有输出时才报错
            if process.returncode != 0 and not md_files:
                error_msg = stderr.decode() if stderr else "Unknown error"
                # 忽略 FFmpeg 库冲突警告
                if "AVFFrameReceiver" not in error_msg and "AVFAudioReceiver" not in error_msg:
                    raise RuntimeError(f"MinerU 返回非零: {error_msg[:500]}")
                logger.warning(f"MinerU 有警告但继续: {error_msg[:200]}")
            if not md_files:
                raise RuntimeError("MinerU 未生成 Markdown 文件")

            md_file = md_files[0]
            md_content = md_file.read_text(encoding="utf-8")

            # 收集元数据
            metadata = {
                "source": str(pdf_path.name),
                "parser": "mineru",
                "headings": md_content.count("\n# "),
                "tables": md_content.count("|---|"),
                "formulas": md_content.count("$"),
                "images": len(list(output_dir.rglob("*.png"))),
                "chars": len(md_content),
            }

            # 保留图片目录（如果有的话）
            images_dir = output_dir / "images"
            if images_dir.exists():
                target_images_dir = Path(self.settings.mineru_cache_dir) / f"{cache_key}_images"
                if target_images_dir.exists():
                    shutil.rmtree(target_images_dir)
                shutil.move(str(images_dir), str(target_images_dir))
                metadata["images_dir"] = str(target_images_dir)

            # 清理临时目录
            shutil.rmtree(output_dir, ignore_errors=True)

            return md_content, metadata

        except asyncio.TimeoutError:
            raise RuntimeError(f"MinerU 解析超时 ({timeout}s, 文件 {file_size_mb:.1f}MB)")
        except FileNotFoundError:
            raise RuntimeError(f"MinerU 未找到: {self.settings.mineru_path}")

    def _get_cache_key(self, pdf_path: Path) -> str:
        """基于文件内容生成缓存 key。

        使用文件大小和修改时间生成 key，避免读取整个文件计算 hash。
        """
        stat = pdf_path.stat()
        key_str = f"{pdf_path.name}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _load_meta(self, meta_file: Path) -> Dict:
        """加载元数据文件。"""
        if meta_file.exists():
            try:
                return json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def get_cache_info(self, pdf_path: str) -> Optional[Dict]:
        """获取缓存信息。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            缓存信息字典，无缓存返回 None
        """
        cache_key = self._get_cache_key(Path(pdf_path))
        cache_file = Path(self.settings.mineru_cache_dir) / f"{cache_key}.md"
        meta_file = Path(self.settings.mineru_cache_dir) / f"{cache_key}.json"

        if cache_file.exists():
            return {
                "cached": True,
                "cache_key": cache_key,
                "cache_file": str(cache_file),
                **self._load_meta(meta_file),
            }
        return {"cached": False}

    async def clear_cache(self, pdf_path: Optional[str] = None) -> int:
        """清理缓存。

        Args:
            pdf_path: 指定 PDF 路径则只清理该文件缓存，None 则清理全部

        Returns:
            清理的缓存文件数量
        """
        cache_dir = Path(self.settings.mineru_cache_dir)
        count = 0

        if pdf_path:
            cache_key = self._get_cache_key(Path(pdf_path))
            for pattern in [f"{cache_key}.*"]:
                for f in cache_dir.glob(pattern):
                    if f.is_file():
                        f.unlink()
                        count += 1
                    elif f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
                        count += 1
        else:
            # 清理全部缓存
            for item in cache_dir.iterdir():
                if item.is_file() and item.suffix in [".md", ".json"]:
                    item.unlink()
                    count += 1
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    count += 1

        logger.info(f"清理缓存: {count} 个文件/目录")
        return count

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理提取的文本。

        清理操作：
        - 移除过多空行（4个以上换行合并为3个）
        - 移除孤立的页码行
        - 合并被换行截断的英文单词

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        if not text:
            return text

        # 移除过多空行（4个以上换行合并为3个）
        text = re.sub(r"\n{4,}", "\n\n\n", text)

        # 移除孤立的页码行（单独一行的数字）
        text = re.sub(r"\n\d+\s*\n", "\n", text)

        # 移除页眉页脚式的页码（如 "Page 123" 或 "- 123 -"）
        text = re.sub(r"\n[-–—]?\s*\d+\s*[-–—]?\s*\n", "\n", text)
        text = re.sub(r"\nPage\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)

        # 合并被换行截断的英文单词（如 "algo-\nrithm" → "algorithm"）
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

        # 移除行首行尾多余空白
        lines = text.split("\n")
        lines = [line.strip() for line in lines]
        text = "\n".join(lines)

        # 再次处理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    async def get_paper_content(
        self,
        pdf_url: str,
        arxiv_id: str,
        mode: str = "auto",
    ) -> Tuple[str, Dict]:
        """获取论文内容的完整流程。

        根据模式选择解析器：
        - pymupdf: 快速提取纯文本
        - mineru: 深度解析 Markdown
        - auto: 智能选择（默认 PyMuPDF）

        Args:
            pdf_url: PDF 下载链接
            arxiv_id: arXiv 论文 ID
            mode: 解析模式

        Returns:
            (content, metadata)
        """
        try:
            # 下载 PDF
            pdf_path = await self.download_pdf(pdf_url, arxiv_id)

            # 根据模式选择解析器
            if mode == "mineru":
                return await self.extract_markdown(pdf_path)
            elif mode == "pymupdf":
                text = await asyncio.to_thread(self.extract_text, pdf_path)
                return text, {"parser": "pymupdf"}
            else:  # auto - 默认用 PyMuPDF，深度分析时调用方会指定 mineru
                text = await asyncio.to_thread(self.extract_text, pdf_path)
                return text, {"parser": "pymupdf"}

        except Exception as e:
            logger.error(f"获取论文内容失败: {arxiv_id}, 错误: {e}", exc_info=True)
            return "", {"error": str(e)}

    @staticmethod
    async def get_paper_text(pdf_url: str, arxiv_id: str) -> str:
        """获取论文文本内容的完整流程 (兼容旧接口)。

        流程：下载 PDF → 提取文本 → 返回内容

        Args:
            pdf_url: PDF 下载链接
            arxiv_id: arXiv 论文 ID

        Returns:
            论文文本内容，失败时返回空字符串
        """
        try:
            # 下载 PDF
            pdf_path = await PDFService.download_pdf(pdf_url, arxiv_id)

            # 在线程中提取文本（避免阻塞事件循环）
            text = await asyncio.to_thread(PDFService.extract_text, pdf_path)

            return text

        except Exception as e:
            logger.error(f"获取论文文本失败: {arxiv_id}, 错误: {e}", exc_info=True)
            return ""


# 全局实例
pdf_service = PDFService()