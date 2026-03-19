"""
发布器基类

定义发布器的通用接口和结果类型。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PublishResult:
    """发布结果"""

    success: bool
    platform: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BasePublisher(ABC):
    """
    发布器基类

    所有发布器必须继承此类并实现 publish 和 test_connection 方法。
    """

    name: str = "base"
    """发布器名称"""

    requires_auth: bool = True
    """是否需要认证"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化发布器

        Args:
            config: 配置字典
        """
        self.config = config
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """
        验证配置

        子类必须实现此方法，检查必需的配置项。
        如果配置无效，应抛出 ValueError。

        Raises:
            ValueError: 配置无效
        """
        pass

    @abstractmethod
    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> PublishResult:
        """
        发布内容

        Args:
            content: 要发布的内容
            title: 标题（可选）
            papers: 相关论文列表（可选）
            **kwargs: 额外参数

        Returns:
            PublishResult 对象
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        测试连接

        Returns:
            True 如果连接成功，否则 False
        """
        pass

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        渲染模板

        Args:
            template_name: 模板文件名（相对于 templates/publishers/{name}/）
            context: 模板上下文

        Returns:
            渲染后的内容
        """
        from jinja2 import Environment, FileSystemLoader

        template_dir = Path(__file__).parent.parent.parent / "templates" / "publishers" / self.name
        if not template_dir.exists():
            # 回退到通用模板目录
            template_dir = Path(__file__).parent.parent.parent / "templates" / "publishers" / "common"

        if template_dir.exists():
            env = Environment(loader=FileSystemLoader(str(template_dir)))
            template = env.get_template(template_name)
            return template.render(**context)

        # 没有模板，返回简单的字符串格式化
        return self._default_render(content=context.get("content", ""), title=context.get("title", ""))

    def _default_render(self, content: str, title: str) -> str:
        """默认渲染方法"""
        if title:
            return f"# {title}\n\n{content}"
        return content


class PublisherRegistry:
    """发布器注册表"""

    _publishers: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, publisher_class: type) -> None:
        """注册发布器"""
        cls._publishers[name] = publisher_class

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        """获取发布器类"""
        return cls._publishers.get(name)

    @classmethod
    def list_available(cls) -> List[str]:
        """列出所有可用的发布器"""
        return list(cls._publishers.keys())

    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> Optional[BasePublisher]:
        """
        创建发布器实例

        Args:
            name: 发布器名称
            config: 配置字典

        Returns:
            发布器实例，如果名称不存在则返回 None
        """
        publisher_class = cls.get(name)
        if publisher_class:
            return publisher_class(config)
        return None


# 自动注册内置发布器
def _auto_register():
    """自动注册内置发布器"""
    try:
        from .wechat_mp import WeChatMPPublisher
        PublisherRegistry.register("wechat_mp", WeChatMPPublisher)
    except ImportError:
        pass

    try:
        from .feishu import FeishuPublisher
        PublisherRegistry.register("feishu", FeishuPublisher)
    except ImportError:
        pass

    try:
        from .email import EmailPublisher
        PublisherRegistry.register("email", EmailPublisher)
    except ImportError:
        pass

    try:
        from .webhook import WebhookPublisher
        PublisherRegistry.register("webhook", WebhookPublisher)
    except ImportError:
        pass


_auto_register()