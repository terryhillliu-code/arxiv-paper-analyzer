"""
SSE (Server-Sent Events) 传输层

实现 MCP 协议的 SSE 传输。
适用于远程服务集成场景。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import Request
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)


@dataclass
class SSESession:
    """SSE 会话"""

    session_id: str
    """会话 ID"""

    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    """消息队列"""


class SSETransport:
    """
    SSE 传输层

    通过 Server-Sent Events 实现 MCP 协议通信。
    适用于 Web 客户端和远程集成。
    """

    def __init__(self, server: Any):
        """
        初始化传输层

        Args:
            server: MCP Server 实例
        """
        self.server = server
        self.sessions: Dict[str, SSESession] = {}

    async def handle_sse(self, request: Request) -> EventSourceResponse:
        """
        处理 SSE 连接

        Args:
            request: FastAPI 请求

        Returns:
            EventSourceResponse
        """
        import uuid

        session_id = str(uuid.uuid4())
        session = SSESession(session_id=session_id)
        self.sessions[session_id] = session

        logger.info(f"SSE 会话创建: {session_id}")

        async def event_generator():
            try:
                # 发送初始化消息
                yield {
                    "event": "endpoint",
                    "data": json.dumps({"session_id": session_id}),
                }

                # 消息循环
                while True:
                    if await request.is_disconnected():
                        break

                    try:
                        # 等待消息（带超时）
                        message = await asyncio.wait_for(
                            session.queue.get(),
                            timeout=30.0
                        )
                        yield {
                            "event": "message",
                            "data": json.dumps(message, ensure_ascii=False),
                        }
                    except asyncio.TimeoutError:
                        # 发送心跳
                        yield {"event": "ping", "data": ""}

            finally:
                # 清理会话
                if session_id in self.sessions:
                    del self.sessions[session_id]
                logger.info(f"SSE 会话结束: {session_id}")

        return EventSourceResponse(event_generator())

    async def handle_post(self, session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 POST 请求

        Args:
            session_id: 会话 ID
            message: 消息内容

        Returns:
            响应消息
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            response = await self._handle_message(message)

            # 如果有响应，发送到 SSE 队列
            if response:
                session = self.sessions[session_id]
                await session.queue.put(response)

            return {"status": "ok"}

        except Exception as e:
            logger.error(f"处理消息错误: {e}")
            return {"error": str(e)}

    async def _handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理消息"""
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
                logger.info("客户端初始化完成")
                return None

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"未知方法: {method}"},
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def get_session_count(self) -> int:
        """获取活跃会话数"""
        return len(self.sessions)