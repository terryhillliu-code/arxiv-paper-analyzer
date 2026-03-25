"""
读取 Obsidian 笔记内容工具
"""

from typing import Any, Dict, Optional
import httpx

from .base import BaseTool, ToolDefinition, ToolResult


class ReadObsidianTool(BaseTool):
    """读取 Obsidian 笔记内容工具"""

    name = "read_obsidian"
    description = "读取指定的 Obsidian 笔记 Markdown 内容"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "笔记相对路径（从 search_obsidian 获取）",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """执行读取"""
        path = arguments.get("path")

        obsidian_url = getattr(config, "obsidian_service_url", "http://127.0.0.1:8766")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{obsidian_url}/vault/read",
                    json={"path": path},
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get("success"):
                    return ToolResult(
                        success=False,
                        error=data.get("error", "读取失败"),
                    )
                
                return ToolResult(
                    success=True,
                    data=data,
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"读取 Obsidian 失败: {str(e)}",
            )
