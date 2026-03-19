"""
发布器模块

提供多平台内容发布功能。
"""

from .base import BasePublisher, PublishResult
from .wechat_mp import WeChatMPPublisher
from .feishu import FeishuPublisher
from .email import EmailPublisher
from .webhook import WebhookPublisher

__all__ = [
    "BasePublisher",
    "PublishResult",
    "WeChatMPPublisher",
    "FeishuPublisher",
    "EmailPublisher",
    "WebhookPublisher",
]