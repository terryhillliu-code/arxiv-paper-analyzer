"""NotebookLM 知识桥接服务。

实现数据清洗、聚合与传输的抽象层，支持分阶段演进联动方案。
v2.2: 新增多源知识混合导出支持
"""

import os
import re
import shutil
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

import yaml
# 配置日志
logger = logging.getLogger(__name__)


class IDataNormalizer(ABC):
    """数据规范化接口。

    负责将本地存储（数据库/Markdown）的原始内容转换为目标平台（如 NotebookLM）
    最易理解的格式。
    """

    @abstractmethod
    def normalize(self, content: str, metadata: Dict[str, Any]) -> str:
        """规范化处理内容。"""
        pass


class ITransportStrategy(ABC):
    """传输策略接口。

    定义数据如何"到达"目标平台的交付方式。
    """

    @abstractmethod
    async def transport(self, data_path: Path, metadata: Dict[str, Any]) -> bool:
        """执行传输逻辑。"""
        pass


class PaperNormalizer(IDataNormalizer):
    """针对 NotebookLM 优化的论文分析规范化器。"""

    def normalize(self, content: str, metadata: Dict[str, Any], super_prompt: str = "") -> str:
        """清洗 Markdown，增加超级提示词引导。"""
        # 1. 注入超级提示词 (如果存在)
        header = ""
        if super_prompt:
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_START -->\n"
            header += f"## 💡 首席研究员指令 (超级提示词)\n\n{super_prompt}\n"
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_END -->\n\n---\n\n"

        # 2. 处理 Obsidian 双链 [[link|text]] -> text
        content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', content)
        # 3. 处理简版双链 [[link]] -> link
        content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)

        # 4. 合并核心元数据
        tier = metadata.get("tier", "B")
        header += f"# {metadata.get('title', '未命名文档')}\n\n"
        header += f"> 内容等级: {tier} | 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += "---\n\n"

        # 5. 移除正文中的本地附件引用
        content = re.sub(r'## 📄 PDF 附件.*?(?=\n##|$)', '', content, flags=re.DOTALL)

        return header + content


class GenericMarkdownNormalizer(IDataNormalizer):
    """通用 Markdown 规范化器。

    用于清洗 ZhiweiVault 中的视频笔记、行业报告等非 PAPER 类型内容。
    """

    def normalize(self, content: str, metadata: Dict[str, Any], super_prompt: str = "") -> str:
        """清洗通用 Markdown 内容。"""
        # 1. 注入超级提示词
        header = ""
        if super_prompt:
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_START -->\n"
            header += f"## 💡 研究指引\n\n{super_prompt}\n"
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_END -->\n\n---\n\n"

        # 2. 处理 Obsidian 特有语法
        # 双链 [[link|text]] -> text
        content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', content)
        # [[link]] -> link
        content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)
        # 嵌入语法 ![[link]] -> [嵌入内容: link]
        content = re.sub(r'!\[\[([^\]]+)\]\]', r'[嵌入内容: \1]', content)

        # 3. 移除 YAML frontmatter（保留关键信息）
        frontmatter_match = re.match(r'^---\n.*?\n---\n', content, re.DOTALL)
        extracted_meta = {}
        if frontmatter_match:
            fm_content = frontmatter_match.group(0)
            content = content[frontmatter_match.end():]

            # 提取关键字段
            for field in ['title', 'date', 'tags', 'type', 'author']:
                match = re.search(rf'^{field}:\s*(.+)$', fm_content, re.MULTILINE)
                if match:
                    extracted_meta[field] = match.group(1).strip()

        # 4. 构建头部元数据
        title = metadata.get('title') or extracted_meta.get('title', '未命名文档')
        doc_type = metadata.get('doc_type', 'VIDEO')
        source = metadata.get('source', 'Obsidian Vault')

        header += f"# {title}\n\n"
        header += f"> 类型: {doc_type} | 来源: {source} | 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        if extracted_meta.get('tags'):
            header += f"> 标签: {extracted_meta['tags']}\n"
        header += "---\n\n"

        return header + content


class LocalFileTransport(ITransportStrategy):
    """本地文件打包传输策略 (阶段二核心项目)。"""

    def __init__(self, export_root: str = "/tmp/notebooklm_export"):
        self.export_root = Path(export_root).expanduser()
        self.ensure_dirs()

    def ensure_dirs(self):
        """确保导出根目录存在。"""
        if not self.export_root.exists():
            self.export_root.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建导出根目录: {self.export_root}")

    async def transport(self, data_path: Path, metadata: Dict[str, Any]) -> bool:
        """将文件及相关附件拷贝到指定导出分区。"""
        try:
            # 根据 JD 目录或 ID 创建子文件夹以防冲突
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", metadata.get("title", "doc"))[:50]
            doc_type = metadata.get("doc_type", "PAPER")
            prefix = f"{doc_type[:3]}_{metadata.get('id', '0')}"
            target_dir = self.export_root / f"{prefix}_{safe_title}"
            target_dir.mkdir(exist_ok=True)

            # 拷贝清洗后的 Markdown
            shutil.copy2(data_path, target_dir / "content.md")

            # 如果是论文类型，拷贝 PDF
            if doc_type == "PAPER":
                pdf_path = metadata.get("pdf_local_path")
                if pdf_path and os.path.exists(pdf_path):
                    shutil.copy2(pdf_path, target_dir / os.path.basename(pdf_path))
                    logger.info(f"成功拷贝 PDF 附件: {pdf_path}")

            logger.info(f"成功导出: {target_dir}")
            return True
        except Exception as e:
            logger.error(f"本地传输失败: {e}")
            return False


class KnowledgeBridgeService:
    """知识桥接中枢服务。"""

    # Obsidian Vault 路径
    VAULT_PATH = Path.home() / "Documents" / "ZhiweiVault"
    VIDEO_NOTES_PATH = VAULT_PATH / "70-79_个人笔记_Personal" / "72_视频笔记_Video-Distill"

    def __init__(
        self,
        normalizer: IDataNormalizer = None,
        transport: ITransportStrategy = None
    ):
        self.normalizer = normalizer or PaperNormalizer()
        self.generic_normalizer = GenericMarkdownNormalizer()
        self.transport = transport or LocalFileTransport()
        self._templates = self._load_templates()

    def _load_templates(self) -> dict:
        """加载提示词模板。"""
        template_path = Path(__file__).parent.parent / "notebooklm_templates.yaml"
        if template_path.exists():
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"加载模板失败: {e}")
        return {}

    async def bridge_paper(self, paper_obj: Any, custom_md: str = None, template_key: str = "default") -> bool:
        """将单篇论文对接到目标平台。"""
        # 准备元数据
        metadata = {
            "id": paper_obj.id,
            "title": paper_obj.title,
            "tier": paper_obj.tier,
            "rating": paper_obj.analysis_json.get("overall_rating", "B") if paper_obj.analysis_json else "B",
            "source_url": paper_obj.arxiv_url or paper_obj.pdf_url,
            "pdf_local_path": paper_obj.pdf_local_path,
            "doc_type": "PAPER"
        }

        # 获取对应模板的提示词
        super_prompt = self._templates.get(template_key, {}).get("prompt", "")
        if not super_prompt and template_key != "default":
             super_prompt = self._templates.get("default", {}).get("prompt", "")

        # 1. 规范化清洗数据
        raw_content = custom_md or paper_obj.analysis_report or ""
        normalized_content = self.normalizer.normalize(raw_content, metadata, super_prompt=super_prompt)

        # 2. 写入临时文件
        temp_file = Path(f"/tmp/bridge_{paper_obj.id}.md")
        temp_file.write_text(normalized_content, encoding="utf-8")

        try:
            # 3. 调用传输策略
            success = await self.transport.transport(temp_file, metadata)
            return success
        finally:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()

    async def bridge_generic_markdown(
        self,
        md_path: Path,
        doc_type: str = "VIDEO",
        template_key: str = "default"
    ) -> bool:
        """将通用 Markdown 文件对接到目标平台。

        Args:
            md_path: Markdown 文件路径
            doc_type: 文档类型 (VIDEO, REPORT, NOTE)
            template_key: 模板键名

        Returns:
            是否成功
        """
        if not md_path.exists():
            logger.warning(f"文件不存在: {md_path}")
            return False

        # 读取内容
        content = md_path.read_text(encoding="utf-8")

        # 准备元数据
        metadata = {
            "id": hash(str(md_path)) % 100000,  # 简单 ID 生成
            "title": md_path.stem,
            "source": str(md_path.parent.name),
            "doc_type": doc_type
        }

        # 获取模板提示词
        super_prompt = self._templates.get(template_key, {}).get("prompt", "")

        # 规范化
        normalized_content = self.generic_normalizer.normalize(content, metadata, super_prompt=super_prompt)

        # 写入临时文件
        temp_file = Path(f"/tmp/bridge_generic_{metadata['id']}.md")
        temp_file.write_text(normalized_content, encoding="utf-8")

        try:
            success = await self.transport.transport(temp_file, metadata)
            return success
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def scan_video_notes(self, query: str = None, limit: int = 5) -> List[Path]:
        """扫描视频笔记目录，返回匹配的文件 (v2.2: 增加 RAG 语义支持)。"""
        if not self.VIDEO_NOTES_PATH.exists():
            logger.warning(f"视频笔记目录不存在: {self.VIDEO_NOTES_PATH}")
            return []

        results = []
        
        # 优先使用 RAG 进行语义检索
        if query:
            logger.info(f"🔍 正在对视频笔记执行 RAG 语义检索: {query}")
            try:
                import json
                import subprocess
                rag_venv = "/Users/liufang/zhiwei-rag/venv/bin/python3"
                bridge_script = "/Users/liufang/zhiwei-rag/bridge.py"

                # 仅筛选视频笔记目录下的结果
                result = subprocess.run(
                    [rag_venv, bridge_script, "retrieve", query, "--top-k", str(limit * 2)],
                    capture_output=True, text=True, timeout=20
                )

                if result.returncode == 0:
                    rag_data = json.loads(result.stdout)
                    for item in rag_data:
                        source_path = Path(item.get("source", ""))
                        # 确保结果在视频笔记目录内且是 .md 文件
                        if str(self.VIDEO_NOTES_PATH) in str(source_path) and source_path.suffix == ".md":
                            if source_path not in results:
                                results.append(source_path)
                        if len(results) >= limit:
                            break
                    logger.info(f"✅ RAG 召回了 {len(results)} 个相关视频笔记")
            except Exception as e:
                logger.error(f"⚠️ 视频 RAG 联动失败，回退到模糊匹配: {e}")

        # 如果 RAG 结果不足或未提供 query，回退到文件名模糊匹配
        if len(results) < limit:
            for md_file in self.VIDEO_NOTES_PATH.glob("*.md"):
                if md_file in results:
                    continue
                if query:
                    if query.lower() in md_file.stem.lower():
                        results.append(md_file)
                else:
                    results.append(md_file)

                if len(results) >= limit:
                    break

        logger.info(f"最终获取视频笔记: {len(results)} 个")
        return results