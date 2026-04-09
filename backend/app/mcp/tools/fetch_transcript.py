"""
视频转录稿获取工具

支持从抖音和 Bilibili 获取视频转录稿。
"""

import re
import logging
import shutil
import asyncio
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from .base import BaseTool, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# 允许的视频平台域名
ALLOWED_DOMAINS = {
    "bilibili.com",
    "b23.tv",
    "douyin.com",
    "iesdouyin.com",
    "youtube.com",
    "youtu.be",
}

# 平台检测规则
PLATFORM_PATTERNS = {
    "bilibili": ["bilibili.com", "b23.tv"],
    "douyin": ["douyin.com", "iesdouyin.com"],
    "youtube": ["youtube.com", "youtu.be"],
}


class FetchVideoTranscriptTool(BaseTool):
    """获取视频转录稿工具"""

    name = "fetch_video_transcript"
    description = "从 YouTube、Bilibili 或抖音获取视频转录稿并创建内容记录"

    _yt_dlp_available: bool = False

    def __init__(self):
        """初始化工具，检查依赖"""
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """检查 yt-dlp 是否安装"""
        self._yt_dlp_available = shutil.which("yt-dlp") is not None
        if not self._yt_dlp_available:
            logger.warning("yt-dlp 未安装，视频转录功能不可用")

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "视频 URL（支持 YouTube、Bilibili 和抖音）",
                    },
                    "title": {
                        "type": "string",
                        "description": "视频标题（可选，自动获取）",
                    },
                    "speaker": {
                        "type": "string",
                        "description": "创作者（可选）",
                    },
                    "create_record": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否创建数据库记录",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        config: Any,
        db_session: Optional[Any] = None,
    ) -> ToolResult:
        """执行转录稿获取"""
        url = arguments.get("url")
        title = arguments.get("title")
        speaker = arguments.get("speaker")
        create_record = arguments.get("create_record", True)

        # 验证 URL
        if not url:
            return ToolResult(success=False, error="URL 不能为空")

        # 验证 URL 安全性
        if not self._validate_url(url):
            return ToolResult(
                success=False,
                error=f"不支持的视频域名，目前支持: {', '.join(ALLOWED_DOMAINS)}",
            )

        # 检查依赖
        if not self._yt_dlp_available:
            return ToolResult(
                success=False,
                error="yt-dlp 未安装，请先安装: pip install yt-dlp 或 brew install yt-dlp",
            )

        # 检测平台
        platform = self._detect_platform(url)
        if not platform:
            return ToolResult(
                success=False,
                error="无法识别视频平台",
            )

        try:
            logger.info(f"[video] 开始获取转录稿: platform={platform}, url={url[:50]}...")

            # 获取转录稿
            transcript, metadata = await self._fetch_transcript(url, platform)

            if not transcript:
                return ToolResult(
                    success=False,
                    error="无法获取视频转录稿，视频可能没有字幕",
                )

            # 补充元数据
            if title:
                metadata["title"] = title
            if speaker:
                metadata["speaker"] = speaker
            metadata["platform"] = platform
            metadata["video_url"] = url

            logger.info(f"[video] 转录稿获取成功: length={len(transcript)}, title={metadata.get('title', '')[:30]}")

            # 创建数据库记录
            if create_record:
                video_id = await self._create_video_record(
                    metadata=metadata,
                    transcript=transcript,
                    db_session=db_session,
                )
                metadata["video_id"] = video_id
                logger.info(f"[video] 数据库记录已创建: video_id={video_id}")

            return ToolResult(
                success=True,
                data={
                    "transcript": transcript[:500] + "..." if len(transcript) > 500 else transcript,
                    "transcript_length": len(transcript),
                    "metadata": metadata,
                },
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"[video] 获取视频转录稿失败: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"获取失败: {str(e)}",
            )

    def _validate_url(self, url: str) -> bool:
        """验证 URL 是否在允许的域名列表中"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # 移除 www. 前缀
            if domain.startswith("www."):
                domain = domain[4:]

            # 检查是否在允许列表中（精确匹配或子域名）
            for allowed in ALLOWED_DOMAINS:
                # 精确匹配
                if domain == allowed:
                    return True
                # 子域名匹配（如 www.bilibili.com, v.douyin.com）
                if domain.endswith("." + allowed):
                    return True

            return False
        except Exception:
            return False

    def _detect_platform(self, url: str) -> Optional[str]:
        """检测视频平台"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            for platform, patterns in PLATFORM_PATTERNS.items():
                for pattern in patterns:
                    if pattern in domain:
                        return platform

            return None
        except Exception:
            return None

    async def _fetch_transcript(self, url: str, platform: str) -> Tuple[str, Dict[str, Any]]:
        """获取转录稿"""
        if platform == "youtube":
            return await self._fetch_youtube_transcript(url)
        elif platform == "bilibili":
            return await self._fetch_bilibili_transcript(url)
        elif platform == "douyin":
            return await self._fetch_douyin_transcript(url)
        else:
            raise ValueError(f"不支持的平台: {platform}")

    async def _fetch_youtube_transcript(self, url: str) -> Tuple[str, Dict[str, Any]]:
        """获取 YouTube 转录稿"""
        import json

        try:
            # 使用 yt-dlp 获取字幕（异步执行，不阻塞事件循环）
            process = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "zh-Hans,zh-Hant,zh-CN,zh-TW,en",
                "--skip-download",
                "--print", "json",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120
            )

            if process.returncode != 0:
                # 尝试只获取视频信息
                return await self._fetch_video_info_only(url)

            video_info = json.loads(stdout.decode())

            # 尝试获取字幕
            subtitle = self._extract_subtitle_from_info(video_info)

            return subtitle, {
                "title": video_info.get("title", ""),
                "duration": video_info.get("duration", 0),
                "speaker": video_info.get("uploader", "") or video_info.get("channel", ""),
                "video_id": video_info.get("id", ""),
                "description": video_info.get("description", "")[:500] if video_info.get("description") else "",
            }

        except asyncio.TimeoutError:
            raise RuntimeError("获取 YouTube 视频超时")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析 YouTube 响应失败: {e}")

    async def _fetch_bilibili_transcript(self, url: str) -> Tuple[str, Dict[str, Any]]:
        """获取 Bilibili 转录稿"""
        import json

        try:
            process = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "zh-Hans,zh-Hant,zh-CN,zh-TW",
                "--skip-download",
                "--print", "json",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120
            )

            if process.returncode != 0:
                logger.warning(f"yt-dlp 获取 Bilibili 失败: {stderr.decode()[:200]}")
                return await self._fetch_video_info_only(url)

            video_info = json.loads(stdout.decode())
            subtitle = self._extract_subtitle_from_info(video_info)

            # Bilibili 特有字段
            bv_match = re.search(r"BV[a-zA-Z0-9]+", url)
            bv_id = bv_match.group(0) if bv_match else video_info.get("id", "")

            return subtitle, {
                "title": video_info.get("title", ""),
                "duration": video_info.get("duration", 0),
                "speaker": video_info.get("uploader", ""),
                "video_id": bv_id,
                "description": video_info.get("description", "")[:500] if video_info.get("description") else "",
            }

        except asyncio.TimeoutError:
            raise RuntimeError("获取 Bilibili 视频超时")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析 Bilibili 响应失败: {e}")

    async def _fetch_douyin_transcript(self, url: str) -> Tuple[str, Dict[str, Any]]:
        """获取抖音转录稿"""
        import json

        try:
            process = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--skip-download",
                "--print", "json",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60
            )

            if process.returncode != 0:
                logger.warning(f"yt-dlp 获取抖音失败: {stderr.decode()[:200]}")
                raise RuntimeError("无法获取抖音视频信息")

            video_info = json.loads(stdout.decode())

            # 抖音视频通常没有字幕，使用描述
            title = video_info.get("title", "") or video_info.get("fulltitle", "")
            description = video_info.get("description", "") or video_info.get("title", "")
            transcript = description or f"标题: {title}"

            return transcript, {
                "title": title,
                "duration": video_info.get("duration", 0),
                "speaker": video_info.get("uploader", "") or video_info.get("channel", ""),
                "video_id": video_info.get("id", ""),
                "description": description,
            }

        except asyncio.TimeoutError:
            raise RuntimeError("获取抖音视频超时")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析抖音响应失败: {e}")

    async def _fetch_video_info_only(self, url: str) -> Tuple[str, Dict[str, Any]]:
        """仅获取视频信息（无字幕时回退）"""
        import json

        process = await asyncio.create_subprocess_exec(
            "yt-dlp", "--skip-download", "--print", "json", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=60
        )

        if process.returncode != 0:
            raise RuntimeError(f"获取视频信息失败: {stderr.decode()[:100]}")

        video_info = json.loads(stdout.decode())
        title = video_info.get("title", "")
        description = video_info.get("description", "") or title

        return description, {
            "title": title,
            "duration": video_info.get("duration", 0),
            "speaker": video_info.get("uploader", ""),
            "video_id": video_info.get("id", ""),
        }

    def _extract_subtitle_from_info(self, video_info: Dict[str, Any]) -> str:
        """从视频信息中提取字幕"""
        # 尝试自动生成的字幕
        automatic_captions = video_info.get("automatic_captions", {})
        subtitles = video_info.get("subtitles", {})

        # 优先级: zh-Hans > zh-CN > zh > en
        lang_priority = ["zh-Hans", "zh-CN", "zh", "en"]

        for lang in lang_priority:
            if automatic_captions.get(lang):
                return self._parse_subtitle_data(automatic_captions[lang])
            if subtitles.get(lang):
                return self._parse_subtitle_data(subtitles[lang])

        return ""

    def _parse_subtitle_data(self, subtitle_data: Any) -> str:
        """解析字幕数据"""
        if isinstance(subtitle_data, str):
            return self._parse_subtitle_text(subtitle_data)
        elif isinstance(subtitle_data, list):
            # 可能是字幕对象列表
            texts = []
            for item in subtitle_data:
                if isinstance(item, dict):
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return " ".join(texts)
        return ""

    def _parse_subtitle_text(self, content: str) -> str:
        """解析字幕文件内容（VTT/SRT 格式）"""
        lines = content.split("\n")
        text_lines = []

        for line in lines:
            line = line.strip()
            # 跳过时间轴、序号和空行
            if not line:
                continue
            if re.match(r"^\d+$", line):
                continue
            if re.match(r"\d{2}:\d{2}:\d{2}", line):
                continue
            if "-->" in line:
                continue
            if line.startswith("WEBVTT"):
                continue
            if line.startswith("NOTE"):
                continue
            text_lines.append(line)

        return " ".join(text_lines)

    async def _create_video_record(
        self,
        metadata: Dict[str, Any],
        transcript: str,
        db_session: Optional[Any] = None,
    ) -> int:
        """创建视频记录"""
        from app.models import Video
        from app.database import async_session_maker

        async with async_session_maker() as session:
            video = Video(
                title=metadata.get("title", "未命名视频"),
                video_id=metadata.get("video_id"),
                platform=metadata.get("platform"),
                video_url=metadata.get("video_url"),
                speaker=metadata.get("speaker"),
                duration=metadata.get("duration"),
                transcript=transcript,
                description=metadata.get("description"),
            )

            session.add(video)
            await session.commit()
            await session.refresh(video)

            return video.id