"""
微信公众号发布器

通过微信公众平台 API 发布图文消息。
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class WeChatMPPublisher(BasePublisher):
    """微信公众号发布器"""

    name = "wechat_mp"
    requires_auth = True

    # API 端点
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    CREATE_NEWS_URL = "https://api.weixin.qq.com/cgi-bin/material/add_news"

    def _validate_config(self) -> None:
        """验证配置"""
        required = ["app_id", "app_secret"]
        missing = [key for key in required if key not in self.config]
        if missing:
            raise ValueError(f"缺少必需配置: {', '.join(missing)}")

    async def _get_access_token(self) -> str:
        """
        获取 access_token

        Returns:
            access_token 字符串

        Raises:
            Exception: 获取失败
        """
        params = {
            "grant_type": "client_credential",
            "appid": self.config["app_id"],
            "secret": self.config["app_secret"],
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(self.TOKEN_URL, params=params) as resp:
                data = await resp.json()

                if "access_token" in data:
                    return data["access_token"]

                error_msg = data.get("errmsg", data.get("errcode", "未知错误"))
                raise Exception(f"获取 access_token 失败: {error_msg}")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> PublishResult:
        """
        发布图文消息

        Args:
            content: Markdown 或 HTML 内容
            title: 消息标题
            papers: 相关论文列表
            **kwargs: 额外参数
                - author: 作者名
                - digest: 摘要
                - content_source_url: 原文链接
                - thumb_media_id: 封面图片 media_id

        Returns:
            PublishResult 对象
        """
        try:
            token = await self._get_access_token()

            # 构建图文消息
            article = {
                "title": title or "论文推送",
                "author": kwargs.get("author", "ArXiv Bot"),
                "digest": kwargs.get("digest", self._extract_digest(content)),
                "content": content,
            }

            # 原文链接
            if kwargs.get("content_source_url"):
                article["content_source_url"] = kwargs["content_source_url"]

            # 封面图片
            if kwargs.get("thumb_media_id"):
                article["thumb_media_id"] = kwargs["thumb_media_id"]

            # 发布
            url = f"{self.CREATE_NEWS_URL}?access_token={token}"
            payload = {"articles": [article]}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()

                    if "media_id" in data:
                        logger.info(f"微信公众号发布成功: media_id={data['media_id']}")
                        return PublishResult(
                            success=True,
                            platform=self.name,
                            message_id=data["media_id"],
                            metadata={"media_id": data["media_id"]}
                        )
                    else:
                        error_msg = data.get("errmsg", f"errcode: {data.get('errcode')}")
                        logger.error(f"微信公众号发布失败: {error_msg}")
                        return PublishResult(
                            success=False,
                            platform=self.name,
                            error=error_msg
                        )

        except Exception as e:
            logger.error(f"微信公众号发布异常: {e}")
            return PublishResult(
                success=False,
                platform=self.name,
                error=str(e)
            )

    async def test_connection(self) -> bool:
        """
        测试连接

        尝试获取 access_token 以验证配置是否正确。

        Returns:
            True 如果连接成功
        """
        try:
            await self._get_access_token()
            return True
        except Exception as e:
            logger.warning(f"微信公众号连接测试失败: {e}")
            return False

    def _extract_digest(self, content: str, max_length: int = 120) -> str:
        """
        从内容中提取摘要

        Args:
            content: 内容文本
            max_length: 最大长度

        Returns:
            摘要文本
        """
        # 移除 Markdown 标记
        import re
        text = re.sub(r"#+\s*", "", content)
        text = re.sub(r"\*+", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\n+", " ", text)

        # 截取
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text