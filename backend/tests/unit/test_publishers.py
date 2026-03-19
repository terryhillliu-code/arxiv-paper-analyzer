"""
发布器单元测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from app.publishers.base import BasePublisher, PublishResult, PublisherRegistry
from app.publishers.feishu import FeishuPublisher
from app.publishers.webhook import WebhookPublisher


class TestFeishuPublisher:
    """飞书发布器测试"""

    def test_validate_config_success(self):
        """测试配置验证成功"""
        config = {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"}
        publisher = FeishuPublisher(config)
        assert publisher.config == config

    def test_validate_config_missing_url(self):
        """测试缺少 webhook_url"""
        config = {}
        with pytest.raises(ValueError, match="webhook_url"):
            FeishuPublisher(config)

    def test_build_text_message(self):
        """测试文本消息构建"""
        config = {"webhook_url": "https://open.feishu.cn/hook/xxx"}
        publisher = FeishuPublisher(config)

        message = publisher._build_text_message("Hello")

        assert message["msg_type"] == "text"
        assert message["content"]["text"] == "Hello"

    def test_build_card_message(self):
        """测试卡片消息构建"""
        config = {"webhook_url": "https://open.feishu.cn/hook/xxx"}
        publisher = FeishuPublisher(config)

        message = publisher._build_card_message("Content", "Title", "blue")

        assert message["msg_type"] == "interactive"
        assert message["card"]["header"]["title"]["content"] == "Title"
        assert message["card"]["header"]["template"] == "blue"

    @pytest.mark.asyncio
    async def test_publish_success(self):
        """测试发布成功"""
        config = {"webhook_url": "https://open.feishu.cn/hook/xxx"}
        publisher = FeishuPublisher(config)

        # Mock aiohttp.ClientSession
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value={"StatusCode": 0})

            mock_post = AsyncMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = MagicMock()
            mock_session_instance.post.return_value = mock_post
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)

            mock_session.return_value = mock_session_instance

            result = await publisher.publish("Test content", title="Test")

            assert result.success
            assert result.platform == "feishu"

    @pytest.mark.asyncio
    async def test_publish_failure(self):
        """测试发布失败"""
        config = {"webhook_url": "https://open.feishu.cn/hook/xxx"}
        publisher = FeishuPublisher(config)

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value={"StatusCode": 1, "msg": "Invalid token"})

            mock_post = AsyncMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = MagicMock()
            mock_session_instance.post.return_value = mock_post
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)

            mock_session.return_value = mock_session_instance

            result = await publisher.publish("Test content")

            assert not result.success
            assert result.error


class TestWebhookPublisher:
    """Webhook 发布器测试"""

    def test_validate_config_success(self):
        """测试配置验证成功"""
        config = {"url": "https://example.com/webhook"}
        publisher = WebhookPublisher(config)
        assert publisher.config["url"] == "https://example.com/webhook"

    def test_validate_config_missing_url(self):
        """测试缺少 URL"""
        config = {}
        with pytest.raises(ValueError, match="url"):
            WebhookPublisher(config)

    def test_validate_config_invalid_url(self):
        """测试无效 URL"""
        config = {"url": "not-a-url"}
        with pytest.raises(ValueError, match="http"):
            WebhookPublisher(config)

    def test_build_payload_default(self):
        """测试默认负载构建"""
        config = {"url": "https://example.com/webhook"}
        publisher = WebhookPublisher(config)

        payload = publisher._build_payload("Content", "Title", None, {})

        assert payload["title"] == "Title"
        assert payload["content"] == "Content"
        assert payload["source"] == "arxiv-paper-analyzer"

    def test_build_payload_with_papers(self):
        """测试带论文的负载构建"""
        config = {"url": "https://example.com/webhook"}
        publisher = WebhookPublisher(config)

        papers = [
            {"id": 1, "title": "Paper 1", "arxiv_id": "1234.5678", "authors": ["A"]}
        ]

        payload = publisher._build_payload("Content", None, papers, {})

        assert "papers" in payload
        assert len(payload["papers"]) == 1
        assert payload["papers"][0]["title"] == "Paper 1"

    def test_build_payload_with_template(self):
        """测试自定义模板"""
        config = {
            "url": "https://example.com/webhook",
            "payload_template": {
                "message": "{title}",
                "body": "{content}"
            }
        }
        publisher = WebhookPublisher(config)

        payload = publisher._build_payload("Body content", "My Title", None, {})

        assert payload["message"] == "My Title"
        assert payload["body"] == "Body content"

    def test_get_headers(self):
        """测试请求头获取"""
        config = {
            "url": "https://example.com/webhook",
            "headers": {
                "Authorization": "Bearer token123"
            }
        }
        publisher = WebhookPublisher(config)

        headers = publisher._get_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer token123"

    @pytest.mark.asyncio
    async def test_publish_success(self):
        """测试发布成功"""
        config = {"url": "https://example.com/webhook"}
        publisher = WebhookPublisher(config)

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"status": "ok"})

            mock_post = AsyncMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = MagicMock()
            mock_session_instance.post.return_value = mock_post
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)

            mock_session.return_value = mock_session_instance

            result = await publisher.publish("Test")

            assert result.success

    @pytest.mark.asyncio
    async def test_publish_failure(self):
        """测试发布失败"""
        config = {"url": "https://example.com/webhook"}
        publisher = WebhookPublisher(config)

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")

            mock_post = AsyncMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = MagicMock()
            mock_session_instance.post.return_value = mock_post
            mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_instance.__aexit__ = AsyncMock(return_value=None)

            mock_session.return_value = mock_session_instance

            result = await publisher.publish("Test")

            assert not result.success
            assert "500" in result.error


class TestPublisherRegistry:
    """发布器注册表测试"""

    def test_register(self):
        """测试注册"""
        class DummyPublisher(BasePublisher):
            name = "dummy"
            def _validate_config(self): pass
            async def publish(self, content, title=None, papers=None, **kwargs): pass
            async def test_connection(self): return True

        PublisherRegistry.register("dummy", DummyPublisher)
        assert PublisherRegistry.get("dummy") == DummyPublisher

    def test_list_available(self):
        """测试列出可用发布器"""
        publishers = PublisherRegistry.list_available()
        assert "feishu" in publishers
        assert "webhook" in publishers

    def test_create(self):
        """测试创建实例"""
        publisher = PublisherRegistry.create("feishu", {"webhook_url": "https://test.com"})
        assert isinstance(publisher, FeishuPublisher)

    def test_create_unknown(self):
        """测试创建未知发布器"""
        publisher = PublisherRegistry.create("unknown", {})
        assert publisher is None


class TestPublishResult:
    """发布结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        result = PublishResult(
            success=True,
            platform="feishu",
            message_id="msg_123"
        )

        assert result.success
        assert result.platform == "feishu"
        assert result.message_id == "msg_123"
        assert result.error is None

    def test_failure_result(self):
        """测试失败结果"""
        result = PublishResult(
            success=False,
            platform="email",
            error="SMTP connection failed"
        )

        assert not result.success
        assert result.error == "SMTP connection failed"