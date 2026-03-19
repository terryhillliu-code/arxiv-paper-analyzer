"""
Webhook 发布器

通过 HTTP Webhook 发送消息。
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class WebhookPublisher(BasePublisher):
    """通用 Webhook 发布器"""

    name = "webhook"
    requires_auth = False  # 认证通过 headers 配置

    def _validate_config(self) -> None:
        """验证配置"""
        if "url" not in self.config:
            raise ValueError("缺少必需配置: url")

        # 验证 URL 格式
        url = self.config["url"]
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL 必须以 http:// 或 https:// 开头")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> PublishResult:
        """
        发送 Webhook 请求

        Args:
            content: 消息内容
            title: 消息标题
            papers: 相关论文列表
            **kwargs: 额外参数
                - payload_template: 自定义负载模板
                - extra: 额外负载字段

        Returns:
            PublishResult 对象
        """
        try:
            # 构建负载
            payload = self._build_payload(content, title, papers, kwargs)

            # 获取请求配置
            headers = self._get_headers()
            timeout = self.config.get("timeout", 30)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config["url"],
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status < 400:
                        try:
                            data = await resp.json()
                        except:
                            data = await resp.text()

                        logger.info(f"Webhook 发送成功: status={resp.status}")
                        return PublishResult(
                            success=True,
                            platform=self.name,
                            metadata={
                                "status": resp.status,
                                "response": data if isinstance(data, dict) else {"raw": str(data)[:500]}
                            }
                        )
                    else:
                        error_text = await resp.text()
                        error_msg = f"HTTP {resp.status}: {error_text[:500]}"
                        logger.error(f"Webhook 发送失败: {error_msg}")
                        return PublishResult(
                            success=False,
                            platform=self.name,
                            error=error_msg
                        )

        except aiohttp.ClientError as e:
            logger.error(f"Webhook 请求异常: {e}")
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"网络错误: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Webhook 发送异常: {e}")
            return PublishResult(
                success=False,
                platform=self.name,
                error=str(e)
            )

    async def test_connection(self) -> bool:
        """
        测试连接

        发送一个测试请求。

        Returns:
            True 如果连接成功
        """
        try:
            headers = self._get_headers()
            test_payload = {
                "test": True,
                "message": "Webhook 连接测试",
                "source": "arxiv-paper-analyzer"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config["url"],
                    json=test_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status < 500  # 4xx 可能是业务错误，但连接正常
        except Exception as e:
            logger.warning(f"Webhook 连接测试失败: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "arxiv-paper-analyzer/1.0"
        }

        # 添加配置的 headers
        config_headers = self.config.get("headers", {})
        headers.update(config_headers)

        return headers

    def _build_payload(
        self,
        content: str,
        title: Optional[str],
        papers: Optional[List[Dict[str, Any]]],
        kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        构建请求负载

        支持自定义模板或默认格式。
        """
        # 检查是否有自定义模板
        template = self.config.get("payload_template") or kwargs.get("payload_template")

        if template:
            # 使用模板
            import json
            payload_str = json.dumps(template)
            # 简单变量替换
            payload_str = payload_str.replace("{content}", content)
            payload_str = payload_str.replace("{title}", title or "")
            payload_str = payload_str.replace("{paper_count}", str(len(papers) if papers else 0))
            return json.loads(payload_str)

        # 默认格式
        payload = {
            "title": title,
            "content": content,
            "timestamp": self._get_timestamp(),
            "source": "arxiv-paper-analyzer"
        }

        # 添加论文信息
        if papers:
            payload["papers"] = [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "arxiv_id": p.get("arxiv_id"),
                    "url": p.get("arxiv_url") or f"https://arxiv.org/abs/{p.get('arxiv_id', '')}",
                    "authors": p.get("authors", [])[:5],
                    "summary": (p.get("summary") or p.get("abstract", ""))[:500],
                }
                for p in papers[:10]  # 最多 10 篇
            ]
            payload["paper_count"] = len(papers)

        # 添加额外字段
        extra = kwargs.get("extra", {})
        if extra:
            payload["extra"] = extra

        # 添加配置的默认字段
        default_fields = self.config.get("default_fields", {})
        if default_fields:
            payload.update(default_fields)

        return payload

    def _get_timestamp(self) -> str:
        """获取 ISO 格式时间戳"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()