"""NotebookLM 知识桥接服务。

实现数据清洗、聚合与传输的抽象层，支持分阶段演进联动方案。
v2.4: 增强 Obsidian 检索策略（文件名 fallback + 目录扫描）
"""

import os
import re
import shutil
import logging
import json
import subprocess
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

import yaml
from app.config import get_settings

# 配置日志
logger = logging.getLogger(__name__)

# 获取全局配置
settings = get_settings()

# RAG 工具路径 (从配置读取，支持 Phase 3 重构)
RAG_VENV = settings.rag_python_path
RAG_BRIDGE = settings.rag_bridge_path


class IDataNormalizer(ABC):
    """数据规范化接口。"""

    @abstractmethod
    def normalize(self, content: str, metadata: Dict[str, Any]) -> str:
        pass


class ITransportStrategy(ABC):
    """传输策略接口。"""

    @abstractmethod
    async def transport(self, data_path: Path, metadata: Dict[str, Any]) -> bool:
        pass


class PaperNormalizer(IDataNormalizer):
    """针对 NotebookLM 优化的论文分析规范化器。"""

    def normalize(self, content: str, metadata: Dict[str, Any], super_prompt: str = "") -> str:
        header = ""
        if super_prompt:
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_START -->\n"
            header += f"## 💡 首席研究员指令 (超级提示词)\n\n{super_prompt}\n"
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_END -->\n\n---\n\n"

        content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', content)
        content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)

        tier = metadata.get("tier", "B")
        header += f"# {metadata.get('title', '未命名文档')}\n\n"
        header += f"> 内容等级: {tier} | 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += "---\n\n"

        content = re.sub(r'## 📄 PDF 附件.*?(?=\n##|$)', '', content, flags=re.DOTALL)
        return header + content


class GenericMarkdownNormalizer(IDataNormalizer):
    """通用 Markdown 规范化器。"""

    def normalize(self, content: str, metadata: Dict[str, Any], super_prompt: str = "") -> str:
        header = ""
        if super_prompt:
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_START -->\n"
            header += f"## 💡 研究指引\n\n{super_prompt}\n"
            header += "<!-- NOTEBOOKLM_SUPER_PROMPT_END -->\n\n---\n\n"

        content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', content)
        content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)
        content = re.sub(r'!\[\[([^\]]+)\]\]', r'[嵌入内容: \1]', content)

        frontmatter_match = re.match(r'^---\n.*?\n---\n', content, re.DOTALL)
        extracted_meta = {}
        if frontmatter_match:
            fm_content = frontmatter_match.group(0)
            content = content[frontmatter_match.end():]
            for field in ['title', 'date', 'tags', 'type', 'author']:
                match = re.search(rf'^{field}:\s*(.+)$', fm_content, re.MULTILINE)
                if match:
                    extracted_meta[field] = match.group(1).strip()

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
    """本地文件打包传输策略。"""

    def __init__(self, export_root: str = "/tmp/notebooklm_export"):
        self.export_root = Path(export_root).expanduser()
        self.ensure_dirs()

    def ensure_dirs(self):
        if not self.export_root.exists():
            self.export_root.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建导出根目录: {self.export_root}")

    async def transport(self, data_path: Path, metadata: Dict[str, Any]) -> bool:
        try:
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", metadata.get("title", "doc"))[:50]
            doc_type = metadata.get("doc_type", "PAPER")
            prefix = f"{doc_type[:3]}_{metadata.get('id', '0')}"
            target_dir = self.export_root / f"{prefix}_{safe_title}"
            target_dir.mkdir(exist_ok=True)

            shutil.copy2(data_path, target_dir / "content.md")

            if doc_type == "PAPER":
                pdf_path = metadata.get("pdf_local_path")
                if pdf_path and os.path.exists(pdf_path):
                    shutil.copy2(pdf_path, target_dir / os.path.basename(pdf_path))

            logger.info(f"成功导出: {target_dir}")
            return True
        except Exception as e:
            logger.error(f"本地传输失败: {e}")
            return False


class KnowledgeBridgeService:
    """知识桥接中枢服务。"""

    VAULT_PATH = Path.home() / "Documents" / "ZhiweiVault"
    VIDEO_NOTES_PATH = VAULT_PATH / "70-79_个人笔记_Personal" / "72_视频笔记_Video-Distill"

    # 高价值目录（按优先级排列）
    PRIORITY_FOLDERS = [
        "90-99_系统与归档_System/92_归档备份/10_KB_Backup/10_Knowledge_Base/Reports/【核心】网络与互联",
        "90-99_系统与归档_System/92_归档备份/10_KB_Backup/10_Knowledge_Base/Reports/【参考】行业报告",
        "70-79_个人笔记_Personal/71_技术学习",
    ]

    def __init__(self, normalizer=None, transport=None):
        self.normalizer = normalizer or PaperNormalizer()
        self.generic_normalizer = GenericMarkdownNormalizer()
        self.transport = transport or LocalFileTransport()
        self._templates = self._load_templates()

    def _load_templates(self) -> dict:
        template_path = Path(__file__).parent.parent / "notebooklm_templates.yaml"
        if template_path.exists():
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"加载模板失败: {e}")
        return {}

    def _build_super_prompt(self, template_key: str, persona: str = None) -> str:
        """构建超级提示词（模板 + 画像）"""
        base_prompt = self._templates.get(template_key, {}).get("prompt", "")
        if not base_prompt and template_key != "default":
            base_prompt = self._templates.get("default", {}).get("prompt", "")
        if persona:
            return f"{persona}\n\n{base_prompt}"
        return base_prompt

    async def bridge_paper(self, paper_obj: Any, custom_md: str = None,
                           template_key: str = "default", persona: str = None) -> bool:
        """将单篇论文对接到目标平台。"""
        metadata = {
            "id": paper_obj.id,
            "title": paper_obj.title,
            "tier": paper_obj.tier,
            "rating": paper_obj.analysis_json.get("overall_rating", "B") if paper_obj.analysis_json else "B",
            "source_url": paper_obj.arxiv_url or paper_obj.pdf_url,
            "pdf_local_path": paper_obj.pdf_local_path,
            "doc_type": "PAPER"
        }

        super_prompt = self._build_super_prompt(template_key, persona)
        raw_content = custom_md or paper_obj.analysis_report or ""
        normalized_content = self.normalizer.normalize(raw_content, metadata, super_prompt=super_prompt)

        temp_file = Path(f"/tmp/bridge_{paper_obj.id}.md")
        temp_file.write_text(normalized_content, encoding="utf-8")

        try:
            return await self.transport.transport(temp_file, metadata)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    async def bridge_generic_markdown(self, md_path: Path, doc_type: str = "VIDEO",
                                       template_key: str = "default", persona: str = None) -> bool:
        """将通用 Markdown 文件对接到目标平台。"""
        if not md_path.exists():
            logger.warning(f"文件不存在: {md_path}")
            return False

        content = md_path.read_text(encoding="utf-8")
        metadata = {
            "id": hash(str(md_path)) % 100000,
            "title": md_path.stem,
            "source": str(md_path.parent.name),
            "doc_type": doc_type
        }

        super_prompt = self._build_super_prompt(template_key, persona)
        normalized_content = self.generic_normalizer.normalize(content, metadata, super_prompt=super_prompt)

        temp_file = Path(f"/tmp/bridge_generic_{metadata['id']}.md")
        temp_file.write_text(normalized_content, encoding="utf-8")

        try:
            return await self.transport.transport(temp_file, metadata)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    # ==================== 检索方法 ====================

    def scan_obsidian_notes(self, query: str, limit: int = 5) -> List[Path]:
        """多策略 Obsidian 笔记检索：RAG → 文件名 grep → 目录扫描。"""
        results = []
        if not query:
            return []

        # 策略 1: RAG 语义检索
        logger.info(f"🔍 [策略1] RAG 语义检索: {query}")
        rag_results = self._rag_retrieve(query, limit * 2)
        for p in rag_results:
            if p not in results:
                results.append(p)

        # 策略 2: 文件名 grep（RAG 覆盖不到的情况）
        if len(results) < limit:
            logger.info(f"🔍 [策略2] 文件名搜索补充...")
            grep_results = self._grep_vault(query, limit - len(results))
            for p in grep_results:
                if p not in results:
                    results.append(p)

        # 策略 3: 高价值目录扫描
        if len(results) < limit:
            logger.info(f"🔍 [策略3] 高价值目录扫描...")
            folder_results = self._scan_priority_folders(query, limit - len(results))
            for p in folder_results:
                if p not in results:
                    results.append(p)

        logger.info(f"📊 Obsidian 综合检索完成: {len(results)} 个结果")
        return results[:limit]

    def scan_video_notes(self, query: str = None, limit: int = 5) -> List[Path]:
        """扫描视频笔记。"""
        if not self.VIDEO_NOTES_PATH.exists():
            return []

        results = []
        if query:
            rag_results = self._rag_retrieve(query, limit * 2)
            for p in rag_results:
                if str(self.VIDEO_NOTES_PATH) in str(p) and p not in results:
                    results.append(p)
                if len(results) >= limit:
                    break

        if len(results) < limit:
            for md_file in self.VIDEO_NOTES_PATH.glob("*.md"):
                if md_file in results:
                    continue
                if not query or query.lower() in md_file.stem.lower():
                    results.append(md_file)
                if len(results) >= limit:
                    break

        return results

    # ==================== 内部检索工具 ====================

    def _rag_retrieve(self, query: str, top_k: int = 10) -> List[Path]:
        """通过 zhiwei-rag 进行语义检索。"""
        results = []
        try:
            result = subprocess.run(
                [RAG_VENV, RAG_BRIDGE, "retrieve", query, "--top-k", str(top_k)],
                capture_output=True, text=True, timeout=20
            )
            if result.returncode == 0:
                rag_data = json.loads(result.stdout)
                for item in rag_data:
                    source_path = Path(item.get("source", ""))
                    if source_path.suffix == ".md" and source_path.exists():
                        results.append(source_path)
        except Exception as e:
            logger.error(f"⚠️ RAG 检索失败: {e}")
        return results

    def _grep_vault(self, query: str, limit: int = 5) -> List[Path]:
        """通过文件名和内容 grep 搜索 Vault。"""
        results = []
        keywords = query.split()
        if not keywords:
            return []

        # 构建 grep 模式
        pattern = "|".join(keywords)
        try:
            result = subprocess.run(
                ["grep", "-rliE", pattern, str(self.VAULT_PATH)],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    p = Path(line.strip())
                    if p.suffix == ".md" and p.exists():
                        results.append(p)
                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.error(f"⚠️ grep 搜索失败: {e}")
        return results

    def _scan_priority_folders(self, query: str, limit: int = 5) -> List[Path]:
        """扫描预定义的高价值目录。"""
        results = []
        keywords = [k.lower() for k in query.split()]

        for folder_rel in self.PRIORITY_FOLDERS:
            folder = self.VAULT_PATH / folder_rel
            if not folder.exists():
                continue
            for md_file in folder.glob("*.md"):
                name_lower = md_file.stem.lower()
                if any(kw in name_lower for kw in keywords):
                    results.append(md_file)
                if len(results) >= limit:
                    return results
        return results