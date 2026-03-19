"""
MCP Server 主类

实现 Model Context Protocol 服务器。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Type

from .config import MCPConfig, PermissionMode
from .tools import (
    ToolRegistry,
    ToolResult,
)
from .transport.stdio import StdioTransport
from .transport.sse import SSETransport

logger = logging.getLogger(__name__)


class MCPServer:
    """
    MCP Server

    实现 Model Context Protocol，支持 AI 助手集成。
    """

    def __init__(self, config: Optional[MCPConfig] = None):
        """
        初始化服务器

        Args:
            config: MCP 配置，如果为 None 则使用默认配置
        """
        self.config = config or MCPConfig()
        self.name = "arxiv-paper-analyzer"
        self.version = "1.0.0"

        logger.info(f"MCP Server 初始化: {self.name} v{self.version}")
        logger.info(f"权限模式: {self.config.permission_mode.value}")
        logger.info(f"允许的工具: {self.config.allowed_tools}")

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 initialize 请求

        Args:
            params: 初始化参数

        Returns:
            服务器信息
        """
        client_info = params.get("clientInfo", {})
        logger.info(f"客户端连接: {client_info}")

        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }

    async def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 tools/list 请求

        Args:
            params: 请求参数

        Returns:
            工具列表
        """
        # 获取允许的工具定义
        definitions = ToolRegistry.get_allowed_definitions(self.config.allowed_tools)

        tools = []
        for defn in definitions:
            tools.append({
                "name": defn.name,
                "description": defn.description,
                "inputSchema": defn.input_schema,
            })

        return {"tools": tools}

    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 tools/call 请求

        Args:
            params: 调用参数，包含 name 和 arguments

        Returns:
            工具执行结果
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        logger.info(f"工具调用: {tool_name}")

        # 检查工具是否存在
        tool_class = ToolRegistry.get(tool_name)
        if not tool_class:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"错误：未知工具 '{tool_name}'",
                    }
                ],
                "isError": True,
            }

        # 检查权限
        if not self.config.is_tool_allowed(tool_name):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"错误：工具 '{tool_name}' 需要完全访问权限",
                    }
                ],
                "isError": True,
            }

        # 创建工具实例
        tool = tool_class()

        # 验证参数
        validation_error = tool.validate_arguments(arguments)
        if validation_error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"参数错误: {validation_error}",
                    }
                ],
                "isError": True,
            }

        # 执行工具
        try:
            result = await tool.execute(arguments, self.config)

            if result.success:
                # 格式化输出
                output = self._format_result(result)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": output,
                        }
                    ],
                    "isError": False,
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"执行失败: {result.error}",
                        }
                    ],
                    "isError": True,
                }

        except Exception as e:
            logger.error(f"工具执行异常: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"执行异常: {str(e)}",
                    }
                ],
                "isError": True,
            }

    def _format_result(self, result: ToolResult) -> str:
        """
        格式化工具结果

        Args:
            result: 工具执行结果

        Returns:
            格式化的文本
        """
        import json

        if result.data is None:
            return "操作成功"

        # 尝试格式化为 JSON
        try:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        except:
            return str(result.data)

    async def run_stdio(self) -> None:
        """以 STDIO 模式运行"""
        transport = StdioTransport(self)
        await transport.start()

    def create_sse_transport(self) -> SSETransport:
        """创建 SSE 传输"""
        return SSETransport(self)


async def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv Paper Analyzer MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="传输协议",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="SSE 模式端口",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="配置文件路径",
    )
    parser.add_argument(
        "--full-access",
        action="store_true",
        help="启用完全访问模式",
    )

    args = parser.parse_args()

    # 加载配置
    if args.config:
        config = MCPConfig.from_yaml(args.config)
    else:
        config = MCPConfig()

    # 命令行覆盖
    if args.full_access:
        config.permission_mode = PermissionMode.FULL_ACCESS

    # 创建服务器
    server = MCPServer(config)

    if args.transport == "stdio":
        # STDIO 模式
        await server.run_stdio()
    else:
        # SSE 模式 - 使用 FastAPI
        import uvicorn
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware

        app = FastAPI(title="MCP Server")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        transport = server.create_sse_transport()

        @app.get("/sse")
        async def sse_endpoint(request: Request):
            return await transport.handle_sse(request)

        @app.post("/message/{session_id}")
        async def message_endpoint(session_id: str, message: Dict[str, Any]):
            return await transport.handle_post(session_id, message)

        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    asyncio.run(main())