"""视频分析任务处理器。

处理视频内容的深度分析任务。
"""

import logging
from typing import Dict, Any

from app.database import async_session_maker
from app.models import Video
from app.services.ai_service import ai_service
from app.tasks.task_queue import TaskQueue
from app.outputs.markdown_generator import MarkdownGenerator
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


class VideoAnalysisTaskHandler:
    """视频分析任务处理器"""

    @staticmethod
    async def handle(task, queue: TaskQueue) -> Dict[str, Any]:
        """处理视频分析任务

        流程：
        1. 读取视频信息
        2. 调用 AI 生成视频分析
        3. 导出到 Obsidian
        4. 保存到数据库
        """
        payload = task.payload
        video_id = payload.get("video_id")
        force_refresh = payload.get("force_refresh", False)

        if not video_id:
            raise ValueError("缺少 video_id")

        # ========== 阶段1: 读取视频信息 ==========
        async with async_session_maker() as db:
            result = await db.execute(select(Video).where(Video.id == video_id))
            video = result.scalar_one_or_none()

            if not video:
                raise ValueError(f"视频不存在: {video_id}")

            # 如果已有分析且不强制刷新，跳过
            if video.has_analysis and video.analysis_report and not force_refresh:
                return {
                    "video_id": video_id,
                    "status": "skipped",
                    "message": "已有分析",
                }

            # 提取视频信息
            video_title = video.title
            video_transcript = video.transcript or ""
            video_duration = video.duration
            video_speaker = video.speaker
            video_platform = video.platform
            video_video_url = video.video_url
            video_platform_id = video.video_id  # 平台视频ID（BV号等）
            video_publish_date = str(video.publish_date) if video.publish_date else ""
            video_description = video.description or ""

        # ========== 阶段2: 准备内容 ==========
        queue.update_task(task.id, progress=10, message="准备内容...")

        # 使用转录稿作为分析内容
        content = video_transcript
        if not content and video_description:
            content = video_description
            logger.info(f"[video_id={video_id}] 使用视频描述作为内容")

        if not content:
            return {
                "video_id": video_id,
                "status": "failed",
                "error": "视频缺少转录稿和描述",
            }

        # ========== 阶段3: AI 分析 ==========
        queue.update_task(task.id, progress=30, message="生成视频分析报告...")
        logger.info(f"[video_id={video_id}] 开始视频分析: {video_title[:30]}")

        analysis_result = await ai_service.generate_video_analysis(
            title=video_title,
            transcript=content,
            duration=video_duration,
            speaker=video_speaker,
            platform=video_platform,
            publish_date=video_publish_date,
            video_url=video_video_url,
        )

        queue.update_task(task.id, progress=80, message="保存分析结果...")

        analysis_report = analysis_result.get("report", "")
        analysis_json = analysis_result.get("analysis_json", {})

        if not analysis_json:
            return {
                "video_id": video_id,
                "status": "failed",
                "error": "分析结果为空",
            }

        logger.info(f"[video_id={video_id}] 分析完成, tier={analysis_json.get('tier', 'B')}")

        # ========== 阶段4: 导出到 Obsidian ==========
        md_output_path = None
        try:
            generator = MarkdownGenerator()
            export_result = generator.generate_video_md(
                video_data={
                    "title": video_title,
                    "video_id": video_platform_id,
                    "platform": video_platform,
                    "speaker": video_speaker,
                    "duration": video_duration,
                    "video_url": video_video_url,
                    "publish_date": video_publish_date,
                },
                analysis_json=analysis_json,
                report=analysis_report,
            )
            md_output_path = export_result.get("md_path")
            logger.info(f"[video_id={video_id}] 导出成功: {md_output_path}")
        except Exception as e:
            logger.warning(f"[video_id={video_id}] 导出失败: {e}")

        # ========== 阶段5: 保存到数据库 ==========
        async with async_session_maker() as db:
            await db.execute(
                update(Video).where(Video.id == video_id).values(
                    has_analysis=True,
                    analysis_report=analysis_report,
                    analysis_json=analysis_json,
                    tier=analysis_json.get("tier"),
                    tags=analysis_json.get("tags"),
                    knowledge_links=analysis_json.get("knowledge_links"),
                    action_items=analysis_json.get("action_items"),
                    md_output_path=md_output_path,
                )
            )
            await db.commit()

        logger.info(f"[video_id={video_id}] 分析完成")

        return {
            "video_id": video_id,
            "status": "completed",
            "has_analysis": True,
            "md_path": md_output_path,
        }


def register_video_analysis_handler(queue: TaskQueue):
    """注册视频分析任务处理器"""
    queue.register_handler("video_analysis", VideoAnalysisTaskHandler.handle)