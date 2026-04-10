"""
适配器模块

提供多模态资产转换工具，支持将外部资源转换为 Obsidian 兼容格式。
"""

from .obsidian_adapter import ObsidianAdapter, ImageConversion

__all__ = ["ObsidianAdapter", "ImageConversion"]