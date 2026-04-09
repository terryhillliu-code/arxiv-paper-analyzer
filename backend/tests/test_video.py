"""视频功能单元测试。

测试 Video 模型和视频分析核心功能。
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock


class TestVideoModel:
    """Video 模型测试"""

    def test_video_creation(self):
        """测试创建视频记录"""
        from app.models import Video

        video = Video(
            title="测试视频",
            platform="bilibili",
            video_id="BV1234567890",
            speaker="测试创作者",
            duration=300,
            has_analysis=False,  # 显式设置默认值
        )

        assert video.title == "测试视频"
        assert video.platform == "bilibili"
        assert video.video_id == "BV1234567890"
        assert video.speaker == "测试创作者"
        assert video.duration == 300
        assert video.has_analysis == False

    def test_video_repr(self):
        """测试 __repr__ 方法"""
        from app.models import Video

        video = Video(title="这是一个很长的视频标题用于测试截断功能", platform="douyin")
        repr_str = repr(video)

        assert "<Video(" in repr_str
        assert "douyin" in repr_str

    def test_video_default_values(self):
        """测试默认值"""
        from app.models import Video

        video = Video(
            title="测试",
            has_analysis=False,  # 显式设置
        )

        assert video.has_analysis == False
        assert video.tier is None
        assert video.tags is None
        assert video.transcript is None


class TestVideoSchema:
    """视频 Schema 测试"""

    def test_video_base_schema(self):
        """测试 VideoBase Schema"""
        from app.schemas import VideoBase

        data = VideoBase(
            title="测试视频",
            platform="bilibili",
            speaker="创作者",
            duration=180,
        )

        assert data.title == "测试视频"
        assert data.platform == "bilibili"

    def test_video_card_schema(self):
        """测试 VideoCard Schema"""
        from app.schemas import VideoCard
        from datetime import datetime

        data = VideoCard(
            id=1,
            title="测试",
            platform="youtube",
            created_at=datetime.now(),
        )

        assert data.id == 1
        assert data.has_analysis == False

    def test_video_analysis_request(self):
        """测试 VideoAnalysisRequest Schema"""
        from app.schemas import VideoAnalysisRequest

        req = VideoAnalysisRequest(video_id=123)
        assert req.video_id == 123
        assert req.force_refresh == False

        req2 = VideoAnalysisRequest(video_id=456, force_refresh=True)
        assert req2.force_refresh == True


class TestVideoTranscriptTool:
    """视频转录稿工具测试"""

    def test_detect_platform_bilibili(self):
        """测试 Bilibili 平台检测"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._detect_platform("https://www.bilibili.com/video/BV123") == "bilibili"
        assert tool._detect_platform("https://b23.tv/abc123") == "bilibili"

    def test_detect_platform_douyin(self):
        """测试抖音平台检测"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._detect_platform("https://www.douyin.com/video/123") == "douyin"
        assert tool._detect_platform("https://v.douyin.com/abc") == "douyin"

    def test_detect_platform_youtube(self):
        """测试 YouTube 平台检测"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
        assert tool._detect_platform("https://youtu.be/abc") == "youtube"

    def test_detect_platform_unknown(self):
        """测试未知平台"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._detect_platform("https://example.com/video") is None

    def test_validate_url_allowed(self):
        """测试 URL 白名单验证 - 允许的域名"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._validate_url("https://www.bilibili.com/video/BV123") == True
        assert tool._validate_url("https://www.douyin.com/video/123") == True
        assert tool._validate_url("https://www.youtube.com/watch?v=abc") == True

    def test_validate_url_blocked(self):
        """测试 URL 白名单验证 - 阻止的域名"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._validate_url("https://malicious-site.com/video") == False
        assert tool._validate_url("https://evil.com/fake-bilibili") == False


class TestMarkdownGenerator:
    """Markdown 生成器测试"""

    def test_generate_video_md(self):
        """测试视频 Markdown 生成"""
        from app.outputs.markdown_generator import MarkdownGenerator
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            generator = MarkdownGenerator(output_dir=tmpdir)

            result = generator.generate_video_md(
                video_data={
                    "title": "测试视频标题",
                    "platform": "bilibili",
                    "speaker": "测试创作者",
                    "duration": 180,
                    "video_url": "https://www.bilibili.com/video/BV123",
                },
                analysis_json={
                    "tier": "B",
                    "tags": ["技术", "教程"],
                    "knowledge_links": ["[[Python]]", "[[AI]]"],
                    "action_items": ["学习基础", "动手实践"],
                },
                report="## 测试报告\n\n这是测试内容。",
            )

            assert "md_path" in result
            assert os.path.exists(result["md_path"])

            # 验证文件内容
            with open(result["md_path"], "r") as f:
                content = f.read()
                assert "测试视频标题" in content
                assert "bilibili" in content
                assert "测试创作者" in content


class TestVideoAnalysisPrompt:
    """视频分析 Prompt 测试"""

    def test_prompt_imports(self):
        """测试 Prompt 导入"""
        from app.prompts.templates import VIDEO_ANALYSIS_PROMPT, VIDEO_JSON_PROMPT

        assert len(VIDEO_ANALYSIS_PROMPT) > 100
        assert len(VIDEO_JSON_PROMPT) > 100
        assert "{title}" in VIDEO_ANALYSIS_PROMPT
        assert "{transcript}" in VIDEO_ANALYSIS_PROMPT


class TestVideoAnalysisTaskHandler:
    """视频分析任务处理器测试"""

    @pytest.mark.asyncio
    async def test_handler_missing_video_id(self):
        """测试缺少 video_id 时抛出异常"""
        from app.tasks.video_analysis_task import VideoAnalysisTaskHandler
        from unittest.mock import MagicMock

        # 创建假任务
        task = MagicMock()
        task.id = "test-task-1"
        task.payload = {}  # 缺少 video_id

        queue = MagicMock()

        # 应该抛出 ValueError
        with pytest.raises(ValueError, match="缺少 video_id"):
            await VideoAnalysisTaskHandler.handle(task, queue)

    @pytest.mark.asyncio
    async def test_handler_video_not_found(self):
        """测试视频不存在时抛出异常"""
        from app.tasks.video_analysis_task import VideoAnalysisTaskHandler
        from unittest.mock import MagicMock, AsyncMock, patch

        task = MagicMock()
        task.id = "test-task-2"
        task.payload = {"video_id": 999}  # 不存在的 ID

        queue = MagicMock()
        queue.update_task = MagicMock()

        # Mock 数据库查询返回 None
        with patch("app.tasks.video_analysis_task.async_session_maker") as mock_session:
            mock_conn = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_conn

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_conn.execute.return_value = mock_result

            with pytest.raises(ValueError, match="视频不存在"):
                await VideoAnalysisTaskHandler.handle(task, queue)

    @pytest.mark.asyncio
    async def test_handler_existing_analysis_skip(self):
        """测试已有分析时跳过"""
        from app.tasks.video_analysis_task import VideoAnalysisTaskHandler
        from unittest.mock import MagicMock, AsyncMock, patch
        from app.models import Video

        task = MagicMock()
        task.id = "test-task-3"
        task.payload = {"video_id": 1, "force_refresh": False}

        queue = MagicMock()
        queue.update_task = MagicMock()

        # 创建已有分析的视频
        video = Video(
            id=1,
            title="已有分析的视频",
            has_analysis=True,
            analysis_report="已有报告",
        )

        with patch("app.tasks.video_analysis_task.async_session_maker") as mock_session:
            mock_conn = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_conn

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = video
            mock_conn.execute.return_value = mock_result

            result = await VideoAnalysisTaskHandler.handle(task, queue)

            assert result["status"] == "skipped"
            assert result["message"] == "已有分析"


class TestVideoRouter:
    """视频 API 路由测试"""

    def test_video_base_schema(self):
        """测试 VideoBase Schema"""
        from app.schemas import VideoBase

        data = VideoBase(
            title="测试视频",
            platform="bilibili",
            speaker="创作者",
            duration=180,
        )

        assert data.title == "测试视频"
        assert data.platform == "bilibili"
        assert data.duration == 180

    def test_video_analysis_request(self):
        """测试 VideoAnalysisRequest Schema"""
        from app.schemas import VideoAnalysisRequest

        req = VideoAnalysisRequest(video_id=123)
        assert req.video_id == 123
        assert req.force_refresh == False

        req2 = VideoAnalysisRequest(video_id=456, force_refresh=True)
        assert req2.force_refresh == True

    def test_video_list_response(self):
        """测试 VideoListResponse Schema"""
        from app.schemas import VideoListResponse, VideoCard
        from datetime import datetime

        videos = [
            VideoCard(
                id=1,
                title="视频1",
                platform="youtube",
                created_at=datetime.now(),
            )
        ]

        response = VideoListResponse(
            videos=videos,
            total=1,
            page=1,
            page_size=10,
            total_pages=1,
        )

        assert response.total == 1
        assert len(response.videos) == 1


class TestFetchTranscriptToolSecurity:
    """视频转录工具安全测试"""

    def test_url_whitelist_allowed(self):
        """测试 URL 白名单 - 允许的域名"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._validate_url("https://www.bilibili.com/video/BV123") == True
        assert tool._validate_url("https://b23.tv/abc123") == True
        assert tool._validate_url("https://www.douyin.com/video/123") == True
        assert tool._validate_url("https://www.youtube.com/watch?v=abc") == True
        assert tool._validate_url("https://youtu.be/abc") == True

    def test_url_whitelist_blocked(self):
        """测试 URL 白名单 - 阻止的域名"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._validate_url("https://malicious-site.com/video") == False
        assert tool._validate_url("https://evil.com/fake-bilibili") == False
        assert tool._validate_url("https://fake-youtube.com/watch") == False

    def test_platform_detection(self):
        """测试平台检测"""
        from app.mcp.tools.fetch_transcript import FetchVideoTranscriptTool

        tool = FetchVideoTranscriptTool()
        assert tool._detect_platform("https://www.bilibili.com/video/BV123") == "bilibili"
        assert tool._detect_platform("https://b23.tv/abc123") == "bilibili"
        assert tool._detect_platform("https://www.douyin.com/video/123") == "douyin"
        assert tool._detect_platform("https://v.douyin.com/abc") == "douyin"
        assert tool._detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
        assert tool._detect_platform("https://youtu.be/abc") == "youtube"
        assert tool._detect_platform("https://example.com/video") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])