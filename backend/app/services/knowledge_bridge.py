"""NotebookLM 知识桥接服务。

实现数据清洗、聚合与传输的抽象层，支持分阶段演进联动方案。
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
    
    定义数据如何“到达”目标平台的交付方式。
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
            target_dir = self.export_root / f"{metadata.get('id', '0')}_{safe_title}"
            target_dir.mkdir(exist_ok=True)
            
            # 拷贝清洗后的 Markdown (已经是 data_path 指向的临时文件)
            shutil.copy2(data_path, target_dir / "analysis.md")
            
            # 拷贝关联的 PDF (如果元数据中提供了本地路径)
            pdf_path = metadata.get("pdf_local_path")
            if pdf_path and os.path.exists(pdf_path):
                shutil.copy2(pdf_path, target_dir / os.path.basename(pdf_path))
                logger.info(f"成功拷贝 PDF 附件: {pdf_path}")
            else:
                logger.warning(f"未找到 PDF 附件或路径为空: {pdf_path}")
                
            return True
        except Exception as e:
            logger.error(f"本地传输失败: {e}")
            return False


class KnowledgeBridgeService:
    """知识桥接中枢服务。"""
    
    def __init__(
        self, 
        normalizer: IDataNormalizer = None, 
        transport: ITransportStrategy = None
    ):
        self.normalizer = normalizer or PaperNormalizer()
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
            "pdf_local_path": paper_obj.pdf_local_path
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
