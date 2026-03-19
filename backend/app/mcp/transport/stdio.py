"""
STDIO 传输层

实现 MCP 协议的标准输入/输出传输。
"""

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class StdioTransport:
    """
    STDIO 传输层

    通过标准输入/输出实现 MCP 协议通信。
    适用于 Claude Desktop 等本地集成场景。
    """

    def __init__(self, server: Any):
        """
        初始化传输层

        Args:
            server: MCP Server 实例
        """
        self.server = server
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.running = False

    async def start(self) -> None:
        """启动传输层"""
        self.running = True
        logger.info("STDIO 传输层启动")

        # 获取标准输入/输出
        loop = asyncio.get_event_loop()
        self.reader = asyncio.StreamReader()
        reader_protocol = asyncio.StreamReaderProtocol(self.reader)
        await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

        # 处理消息循环
        await self._message_loop()

    async def stop(self) -> None:
        """停止传输层"""
        self.running = False
        logger.info("STDIO 传输层停止")

    async def _message_loop(self) -> None:
        """消息处理循环"""
        while self.running:
            try:
                # 读取一行消息
                line = await self.reader.readline()
                if not line:
                    # EOF
                    break

                # 解析消息
                try:
                    message = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 解析错误: {e}")
                    continue

                # 处理消息
                response = await self._handle_message(message)

                # 发送响应
                if response:
                    await self._send_response(response)

            except Exception as e:
                logger.error(f"消息处理错误: {e}")

    async def _handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理消息

        Args:
            message: 接收到的消息

        Returns:
            响应消息
        """
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        try:
            if method == "initialize":
                result = await self.server.handle_initialize(params)
                return {"jsonrpc": "2.0", "id": msg_id, "result": result}

            elif method == "tools/list":
                result = await self.server.handle_tools_list(params)
                return {"jsonrpc": "2.0", "id": msg_id, "result": result}

            elif method == "tools/call":
                result = await self.server.handle_tools_call(params)
                return {"jsonrpc": "2.0", "id": msg_id, "result": result}

            elif method == "notifications/initialized":
                # 客户端初始化完成通知
                logger.info("客户端初始化完成")
                return None

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"未知方法: {method}"},
                }

        except Exception as e:
            logger.error(f"处理消息错误: {e}")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(e)},
            }

    async def _send_response(self, response: Dict[str, Any]) -> None:
        """
        发送响应

        Args:
            response: 响应消息
        """
        try:
            content = json.dumps(response, ensure_ascii=False)
            sys.stdout.write(content + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"发送响应错误: {e}")