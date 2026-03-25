"""
搜索 Obsidian Vault 工具
"""

from typing import Any, Dict, Optional, List
import httpx

from .base import BaseTool, ToolDefinition, ToolResult


class SearchObsidianTool(BaseTool):
    """搜索 Obsidian Vault 工具"""

    name = "search_obsidian"
    description = "全文检索 Obsidian 笔记内容"

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "folder": {
                        "type": "string",
                        "description": "可选文件夹（相对路径）",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "返回结果数量限制",
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """执行搜索"""
        query = arguments.get("query")
        folder = arguments.get("folder")
        limit = arguments.get("limit", 10)

        obsidian_url = getattr(config, "obsidian_service_url", "http://127.0.0.1:8766")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{obsidian_url}/vault/search",
                    json={"query": query, "folder": folder, "limit": limit},
                    timeout=15.0
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("total", 0) == 0:
                    return ToolResult(
                        success=True,
                        data={"message": f"未找到包含 '{query}' 的笔记"},
                    )
                
                return ToolResult(
                    success=True,
                    data=data,
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"搜索 Obsidian 失败: {str(e)}",
            )
