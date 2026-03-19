"""
MCP (Model Context Protocol) Server 模块

提供 AI 助手集成能力，支持 Claude Desktop 等客户端连接。
"""

from .server import MCPServer
from .config import MCPConfig, PermissionMode

__all__ = [
    "MCPServer",
    "MCPConfig",
    "PermissionMode",
]