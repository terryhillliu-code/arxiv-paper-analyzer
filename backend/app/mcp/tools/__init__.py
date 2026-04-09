"""
MCP Tools 工具定义

实现所有 MCP Server 支持的工具。
"""

from .base import BaseTool, ToolResult, ToolRegistry
from .search import SearchPapersTool
from .paper import GetPaperTool
from .trending import GetTrendingTool
from .analyze import AnalyzePaperTool
from .summary import GenerateSummaryTool
from .export_obsidian import ExportToObsidianTool
from .export_bibtex import ExportToBibtexTool
from .search_obsidian import SearchObsidianTool
from .read_obsidian import ReadObsidianTool
from .fetch_transcript import FetchVideoTranscriptTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "SearchPapersTool",
    "GetPaperTool",
    "GetTrendingTool",
    "AnalyzePaperTool",
    "GenerateSummaryTool",
    "ExportToObsidianTool",
    "ExportToBibtexTool",
    "SearchObsidianTool",
    "ReadObsidianTool",
    "FetchVideoTranscriptTool",
]

# 自动注册工具
ToolRegistry.register("search_papers", SearchPapersTool)
ToolRegistry.register("get_paper", GetPaperTool)
ToolRegistry.register("get_trending", GetTrendingTool)
ToolRegistry.register("analyze_paper", AnalyzePaperTool)
ToolRegistry.register("generate_summary", GenerateSummaryTool)
ToolRegistry.register("export_to_obsidian", ExportToObsidianTool)
ToolRegistry.register("export_to_bibtex", ExportToBibtexTool)
ToolRegistry.register("search_obsidian", SearchObsidianTool)
ToolRegistry.register("read_obsidian", ReadObsidianTool)
ToolRegistry.register("fetch_video_transcript", FetchVideoTranscriptTool)