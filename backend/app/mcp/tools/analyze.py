"""
分析论文工具（需要完全访问权限）
"""

from typing import Any, Dict, Optional

import httpx

from .base import BaseTool, ToolDefinition, ToolResult


class AnalyzePaperTool(BaseTool):
    """分析论文工具"""

    name = "analyze_paper"
    description = "对论文进行深度分析（需要完全访问权限）"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "论文 ID",
                    },
                    "force_refresh": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否强制刷新分析结果",
                    },
                    "wait": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否等待分析完成",
                    },
                },
                "required": ["paper_id"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """执行分析"""
        paper_id = arguments.get("paper_id")
        force_refresh = arguments.get("force_refresh", False)
        wait = arguments.get("wait", True)

        # 检查权限
        if not config.is_tool_allowed(self.name):
            return ToolResult(
                success=False,
                error="权限不足：此操作需要完全访问权限",
            )

        try:
            # 调用 HTTP API
            api_url = f"{config.api_base_url}/api/papers/{paper_id}/analyze"
            params = {"force_refresh": force_refresh}

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(api_url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    return ToolResult(
                        success=True,
                        data=data,
                        metadata={"paper_id": paper_id, "waited": wait},
                    )
                else:
                    error_text = response.text
                    return ToolResult(
                        success=False,
                        error=f"分析失败: HTTP {response.status_code} - {error_text}",
                    )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error="分析超时（可能正在后台处理）",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"分析异常: {str(e)}",
            )