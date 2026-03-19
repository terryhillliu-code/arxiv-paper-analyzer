"""
MCP Server 配置

定义权限控制和配置管理。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml


class PermissionMode(str, Enum):
    """权限模式"""

    READ_ONLY = "read_only"
    """只读模式：只能查询和导出"""

    FULL_ACCESS = "full_access"
    """完全访问：可以执行分析和修改操作"""


@dataclass
class MCPConfig:
    """MCP Server 配置"""

    permission_mode: PermissionMode = PermissionMode.READ_ONLY
    """权限模式"""

    read_only_tools: Set[str] = field(
        default_factory=lambda: {
            "search_papers",
            "get_paper",
            "get_trending",
            "export_to_bibtex",
        }
    )
    """只读模式允许的工具"""

    full_access_tools: Set[str] = field(
        default_factory=lambda: {
            "analyze_paper",
            "generate_summary",
            "export_to_obsidian",
        }
    )
    """完全访问模式额外允许的工具"""

    database_url: Optional[str] = None
    """数据库连接 URL"""

    api_base_url: str = "http://localhost:8000"
    """后端 API 基础 URL"""

    obsidian_service_url: str = "http://127.0.0.1:8766"
    """Obsidian 服务 URL"""

    @property
    def allowed_tools(self) -> Set[str]:
        """获取当前权限模式允许的所有工具"""
        tools = self.read_only_tools.copy()
        if self.permission_mode == PermissionMode.FULL_ACCESS:
            tools.update(self.full_access_tools)
        return tools

    def is_tool_allowed(self, tool_name: str) -> bool:
        """检查工具是否被允许"""
        return tool_name in self.allowed_tools

    @classmethod
    def from_yaml(cls, path: str) -> "MCPConfig":
        """从 YAML 文件加载配置"""
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        permission = data.get("permission", {})
        mode_str = permission.get("mode", "read_only")

        config = cls(
            permission_mode=PermissionMode(mode_str),
            api_base_url=data.get("api_base_url", "http://localhost:8000"),
            obsidian_service_url=data.get("obsidian_service_url", "http://127.0.0.1:8766"),
        )

        # 自定义工具列表
        if "read_only_tools" in permission:
            config.read_only_tools = set(permission["read_only_tools"])
        if "full_access_tools" in permission:
            config.full_access_tools = set(permission["full_access_tools"])

        return config

    def to_yaml(self, path: str) -> None:
        """保存配置到 YAML 文件"""
        data = {
            "permission": {
                "mode": self.permission_mode.value,
                "read_only_tools": list(self.read_only_tools),
                "full_access_tools": list(self.full_access_tools),
            },
            "api_base_url": self.api_base_url,
            "obsidian_service_url": self.obsidian_service_url,
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


# 默认配置文件路径
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "mcp_config.yaml"