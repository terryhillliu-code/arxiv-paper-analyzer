"""
飞书发布器

通过飞书机器人 Webhook 发送消息。
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class FeishuPublisher(BasePublisher):
    """飞书发布器"""

    name = "feishu"
    requires_auth = False  # Webhook 不需要额外认证

    def _validate_config(self) -> None:
        """验证配置"""
        if "webhook_url" not in self.config:
            raise ValueError("缺少必需配置: webhook_url")

        # 验证 URL 格式
        url = self.config["webhook_url"]
        if not url.startswith("https://open.feishu.cn"):
            logger.warning("Webhook URL 可能不是有效的飞书地址")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> PublishResult:
        """
        发送飞书消息

        支持多种消息类型：
        - text: 纯文本
        - post: 富文本
        - interactive: 卡片消息（默认）

        Args:
            content: 消息内容
            title: 消息标题
            papers: 相关论文列表
            **kwargs: 额外参数
                - msg_type: 消息类型 (text/post/interactive)
                - color: 卡片颜色 (blue/red/green/orange)

        Returns:
            PublishResult 对象
        """
        msg_type = kwargs.get("msg_type", "interactive")

        try:
            if msg_type == "text":
                message = self._build_text_message(content)
            elif msg_type == "post":
                message = self._build_post_message(content, title)
            else:
                message = self._build_card_message(content, title, kwargs.get("color", "blue"))

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config["webhook_url"],
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

                    if data.get("StatusCode") == 0 or data.get("code") == 0:
                        logger.info("飞书消息发送成功")
                        return PublishResult(
                            success=True,
                            platform=self.name,
                            metadata={"msg_type": msg_type}
                        )
                    else:
                        error_msg = data.get("msg", str(data))
                        logger.error(f"飞书消息发送失败: {error_msg}")
                        return PublishResult(
                            success=False,
                            platform=self.name,
                            error=error_msg
                        )

        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return PublishResult(
                success=False,
                platform=self.name,
                error=str(e)
            )

    async def test_connection(self) -> bool:
        """
        测试连接

        发送一条测试消息。

        Returns:
            True 如果连接成功
        """
        try:
            message = {
                "msg_type": "text",
                "content": {"text": "🔗 飞书机器人连接测试成功"}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config["webhook_url"],
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    data = await resp.json()
                    return data.get("StatusCode") == 0 or data.get("code") == 0
        except Exception as e:
            logger.warning(f"飞书连接测试失败: {e}")
            return False

    def _build_text_message(self, content: str) -> Dict[str, Any]:
        """构建文本消息"""
        return {
            "msg_type": "text",
            "content": {"text": content}
        }

    def _build_post_message(self, content: str, title: Optional[str]) -> Dict[str, Any]:
        """构建富文本消息"""
        lines = content.split("\n")
        post_content = []

        for line in lines:
            if line.strip():
                post_content.append([{"tag": "text", "text": line}])
            else:
                post_content.append([{"tag": "text", "text": ""}])

        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title or "论文推送",
                        "content": post_content
                    }
                }
            }
        }

    def _build_card_message(
        self,
        content: str,
        title: Optional[str],
        color: str = "blue"
    ) -> Dict[str, Any]:
        """构建卡片消息"""
        # 处理内容，添加分块
        elements = []

        # 内容块
        if content:
            # 截断过长内容
            display_content = content[:4000] if len(content) > 4000 else content
            elements.append({
                "tag": "markdown",
                "content": display_content
            })

        # 备注（可选）
        if self.config.get("footer"):
            elements.append({
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": self.config["footer"]}
                ]
            })

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title or "论文推送"
                    },
                    "template": color
                },
                "elements": elements
            }
        }