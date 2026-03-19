"""
MCP Tool 基类和注册表
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    """是否成功"""

    data: Any = None
    """返回数据"""

    error: Optional[str] = None
    """错误信息"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """额外元数据"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "success": self.success,
        }
        if self.data is not None:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class ToolDefinition:
    """工具定义（用于 MCP 协议）"""

    name: str
    """工具名称"""

    description: str
    """工具描述"""

    input_schema: Dict[str, Any]
    """输入参数 JSON Schema"""


class BaseTool(ABC):
    """
    MCP Tool 基类

    所有工具必须继承此类并实现 execute 和 get_definition 方法。
    """

    name: str = "base"
    """工具名称"""

    description: str = "基础工具"
    """工具描述"""

    @classmethod
    @abstractmethod
    def get_definition(cls) -> ToolDefinition:
        """
        获取工具定义

        Returns:
            ToolDefinition 对象，包含名称、描述和输入 schema
        """
        pass

    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """
        执行工具

        Args:
            arguments: 工具参数
            config: MCP 配置
            db_session: 数据库会话（可选）

        Returns:
            ToolResult 对象
        """
        pass

    def validate_arguments(self, arguments: Dict[str, Any]) -> Optional[str]:
        """
        验证参数

        Args:
            arguments: 工具参数

        Returns:
            错误信息，如果验证通过则返回 None
        """
        definition = self.get_definition()
        schema = definition.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # 检查必需参数
        for key in required:
            if key not in arguments:
                return f"缺少必需参数: {key}"

        # 检查参数类型
        for key, value in arguments.items():
            if key in properties:
                prop = properties[key]
                expected_type = prop.get("type")

                if expected_type == "string" and not isinstance(value, str):
                    return f"参数 {key} 应为字符串"
                elif expected_type == "integer" and not isinstance(value, int):
                    return f"参数 {key} 应为整数"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return f"参数 {key} 应为布尔值"
                elif expected_type == "array" and not isinstance(value, list):
                    return f"参数 {key} 应为数组"

        return None


class ToolRegistry:
    """工具注册表"""

    _tools: Dict[str, Type[BaseTool]] = {}

    @classmethod
    def register(cls, name: str, tool_class: Type[BaseTool]) -> None:
        """注册工具"""
        cls._tools[name] = tool_class
        logger.debug(f"注册工具: {name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseTool]]:
        """获取工具类"""
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> List[str]:
        """列出所有工具"""
        return list(cls._tools.keys())

    @classmethod
    def create(cls, name: str) -> Optional[BaseTool]:
        """创建工具实例"""
        tool_class = cls.get(name)
        if tool_class:
            return tool_class()
        return None

    @classmethod
    def get_all_definitions(cls) -> List[ToolDefinition]:
        """获取所有工具定义"""
        definitions = []
        for name, tool_class in cls._tools.items():
            definitions.append(tool_class.get_definition())
        return definitions

    @classmethod
    def get_allowed_definitions(cls, allowed_tools: set) -> List[ToolDefinition]:
        """获取允许的工具定义"""
        definitions = []
        for name, tool_class in cls._tools.items():
            if name in allowed_tools:
                definitions.append(tool_class.get_definition())
        return definitions