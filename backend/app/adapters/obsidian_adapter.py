"""
Obsidian 多模态适配器

将 PDF 解析出的图片转换为 Obsidian 兼容格式：
1. 复制图片到 Obsidian Assets/ 目录
2. 转换 Markdown 图片语法为 Obsidian wiki-link 格式
"""

import re
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImageConversion:
    """图片转换结果"""

    original_path: str
    new_path: str
    filename: str
    success: bool
    error: Optional[str] = None


class ObsidianAdapter:
    """多模态资产适配器

    职责：将 PDF 解析出的图片转换为 Obsidian 兼容格式

    支持的图片语法：
    - 标准 Markdown: ![alt](path)
    - Obsidian wiki-link: ![[path]]
    - HTML img: <img src="path">
    """

    # 图片语法正则模式
    IMAGE_PATTERNS = {
        "standard": re.compile(r"!\[([^\]]*)\]\(([^)]+)\)"),
        "obsidian": re.compile(r"!\[\[([^\]]+)\]\]"),
        "html": re.compile(r'<img[^>]+src=["\']([^"\']+)["\']'),
    }

    # 支持的图片格式
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}

    def __init__(
        self,
        vault_path: Path,
        assets_dir: str = "Assets",
        preserve_structure: bool = False,
    ):
        """初始化适配器

        Args:
            vault_path: Obsidian Vault 根目录
            assets_dir: 资产目录名称（相对于 Vault 根目录）
            preserve_structure: 是否保留源目录结构
        """
        self.vault_path = Path(vault_path)
        self.assets_path = self.vault_path / assets_dir
        self.preserve_structure = preserve_structure

        # 确保资产目录存在
        self.assets_path.mkdir(parents=True, exist_ok=True)

    def adapt_images(
        self,
        content: str,
        source_images_dir: Optional[Path] = None,
        arxiv_id: Optional[str] = None,
    ) -> Tuple[str, List[ImageConversion]]:
        """转换图片路径并复制文件

        Args:
            content: Markdown 内容
            source_images_dir: 图片源目录
            arxiv_id: 论文 ID（用于组织图片子目录）

        Returns:
            (转换后的内容, 转换结果列表)
        """
        conversions = []

        # 源目录不存在，直接返回原内容
        if source_images_dir and not source_images_dir.exists():
            logger.warning(f"图片源目录不存在: {source_images_dir}")
            return content, conversions

        # 目标目录（可选子目录）
        target_dir = self.assets_path
        if arxiv_id and self.preserve_structure:
            target_dir = self.assets_path / arxiv_id
            target_dir.mkdir(parents=True, exist_ok=True)

        # 转换标准 Markdown 图片语法
        content, std_conversions = self._convert_standard_images(
            content, source_images_dir, target_dir
        )
        conversions.extend(std_conversions)

        # 转换 HTML img 标签
        content, html_conversions = self._convert_html_images(
            content, source_images_dir, target_dir
        )
        conversions.extend(html_conversions)

        # Obsidian 格式已正确，跳过处理

        return content, conversions

    def _convert_standard_images(
        self,
        content: str,
        source_dir: Optional[Path],
        target_dir: Path,
    ) -> Tuple[str, List[ImageConversion]]:
        """转换标准 Markdown 图片语法

        ![alt](path) → ![[Assets/filename]]
        """
        conversions = []

        def replace_image(match: re.Match) -> str:
            alt_text = match.group(1)
            image_path = match.group(2)

            # 跳过网络 URL
            if image_path.startswith(("http://", "https://", "data:")):
                return match.group(0)

            # 复制图片
            conversion = self._copy_and_convert_image(
                image_path, source_dir, target_dir, alt_text
            )
            conversions.append(conversion)

            if conversion.success:
                # 转换为 Obsidian 格式
                if alt_text:
                    return f"![[{conversion.new_path}|{alt_text}]]"
                return f"![[{conversion.new_path}]]"
            else:
                # 失败时保留原样
                return match.group(0)

        pattern = self.IMAGE_PATTERNS["standard"]
        new_content = pattern.sub(replace_image, content)

        return new_content, conversions

    def _convert_html_images(
        self,
        content: str,
        source_dir: Optional[Path],
        target_dir: Path,
    ) -> Tuple[str, List[ImageConversion]]:
        """转换 HTML img 标签

        <img src="path"> → ![[Assets/filename]]
        """
        conversions = []

        def replace_html(match: re.Match) -> str:
            image_path = match.group(1)

            # 跳过网络 URL
            if image_path.startswith(("http://", "https://", "data:")):
                return match.group(0)

            # 复制图片
            conversion = self._copy_and_convert_image(
                image_path, source_dir, target_dir
            )
            conversions.append(conversion)

            if conversion.success:
                return f"![[{conversion.new_path}]]"
            else:
                return match.group(0)

        pattern = self.IMAGE_PATTERNS["html"]
        new_content = pattern.sub(replace_html, content)

        return new_content, conversions

    def _copy_and_convert_image(
        self,
        image_path: str,
        source_dir: Optional[Path],
        target_dir: Path,
        alt_text: str = "",
    ) -> ImageConversion:
        """复制图片并返回转换信息

        Args:
            image_path: 原始图片路径（可能是相对路径）
            source_dir: 图片源目录
            target_dir: 目标目录
            alt_text: 替代文本

        Returns:
            ImageConversion 对象
        """
        # 解析源文件路径
        src_path = self._resolve_image_path(image_path, source_dir)

        if not src_path or not src_path.exists():
            return ImageConversion(
                original_path=image_path,
                new_path="",
                filename="",
                success=False,
                error=f"图片文件不存在: {image_path}",
            )

        # 检查是否是支持的图片格式
        if src_path.suffix.lower() not in self.IMAGE_EXTENSIONS:
            return ImageConversion(
                original_path=image_path,
                new_path="",
                filename="",
                success=False,
                error=f"不支持的图片格式: {src_path.suffix}",
            )

        # 生成唯一文件名
        filename = self._get_unique_filename(target_dir, src_path.name)

        # 复制文件
        dest_path = target_dir / filename
        try:
            shutil.copy2(src_path, dest_path)
            logger.debug(f"复制图片: {src_path} → {dest_path}")

            # 计算相对路径（相对于 Vault 根目录）
            relative_path = dest_path.relative_to(self.vault_path)

            return ImageConversion(
                original_path=image_path,
                new_path=str(relative_path),
                filename=filename,
                success=True,
            )
        except Exception as e:
            logger.error(f"复制图片失败: {e}")
            return ImageConversion(
                original_path=image_path,
                new_path="",
                filename="",
                success=False,
                error=str(e),
            )

    def _resolve_image_path(
        self, image_path: str, source_dir: Optional[Path]
    ) -> Optional[Path]:
        """解析图片路径

        尝试多种路径解析策略：
        1. 绝对路径
        2. 相对于 source_dir
        3. 相对于当前工作目录
        """
        path = Path(image_path)

        # 绝对路径
        if path.is_absolute() and path.exists():
            return path

        # 相对于 source_dir
        if source_dir:
            relative_path = source_dir / image_path
            if relative_path.exists():
                return relative_path

            # 尝试只取文件名
            filename_only = source_dir / path.name
            if filename_only.exists():
                return filename_only

        # 相对于当前工作目录
        if path.exists():
            return path

        return None

    def _get_unique_filename(self, target_dir: Path, filename: str) -> str:
        """生成唯一文件名，避免覆盖

        如果目标文件已存在，添加数字后缀：
        fig1.png → fig1_1.png → fig1_2.png
        """
        dest_path = target_dir / filename

        if not dest_path.exists():
            return filename

        # 文件名冲突，生成新名称
        stem = dest_path.stem
        suffix = dest_path.suffix
        counter = 1

        while dest_path.exists():
            new_filename = f"{stem}_{counter}{suffix}"
            dest_path = target_dir / new_filename
            counter += 1

        return dest_path.name

    def get_stats(self) -> Dict[str, int]:
        """获取资产目录统计信息"""
        if not self.assets_path.exists():
            return {"total": 0, "by_extension": {}}

        total = 0
        by_extension: Dict[str, int] = {}

        for file_path in self.assets_path.rglob("*"):
            if file_path.is_file():
                total += 1
                ext = file_path.suffix.lower()
                by_extension[ext] = by_extension.get(ext, 0) + 1

        return {"total": total, "by_extension": by_extension}