"""论文分析任务处理器。

处理深度分析任务，避免阻塞 API 响应。
使用写入队列服务避免数据库锁竞争。
"""

import logging
import os
from typing import Dict, Any

from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from app.services.pdf_service import pdf_service, PDFService
from app.services.write_service import db_write_service, WriteTask
from app.services.guardrails import analysis_guardrail
from app.tasks.task_queue import TaskQueue, TaskStatus
from app.outputs.markdown_generator import MarkdownGenerator
from sqlalchemy import select
import json as json_module


def validate_analysis_result(analysis_json: dict, report: str) -> tuple[bool, list]:
    """验证分析结果是否完整

    Returns:
        (is_valid, missing_fields)
    """
    if not analysis_json:
        return False, ["analysis_json为空"]

    if not report or len(report) < 500:
        return False, [f"报告太短({len(report) if report else 0}字符)"]

    missing = []

    # 检查JSON长度
    json_str = json_module.dumps(analysis_json, ensure_ascii=False)
    if len(json_str) < 500:
        missing.append(f"JSON太短({len(json_str)}字符)")

    # 检查关键字段
    required_fields = {
        "tier": lambda x: x in ["A", "B", "C"],
        "one_line_summary": lambda x: x and len(x) > 10,
        "outline": lambda x: x and len(x) > 0,
        "key_contributions": lambda x: x and len(x) > 0,
    }

    for field, validator in required_fields.items():
        value = analysis_json.get(field)
        if not value or not validator(value):
            missing.append(field)

    return len(missing) == 0, missing

logger = logging.getLogger(__name__)


class AnalysisTaskHandler:
    """分析任务处理器"""

    @staticmethod
    def _update_frontmatter_field(filepath: str, field: str, value: Any) -> None:
        """更新 Obsidian Markdown 文件的 frontmatter 字段

        Args:
            filepath: Markdown 文件路径
            field: 字段名
            value: 字段值
        """
        import re

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否有 frontmatter
        if not content.startswith('---'):
            return

        # 找到 frontmatter 结束位置
        fm_end = content.find('---', 3)
        if fm_end == -1:
            return

        frontmatter = content[3:fm_end]

        # 格式化值
        if isinstance(value, bool):
            value_str = str(value).lower()
        elif isinstance(value, str):
            value_str = f'"{value}"'
        else:
            value_str = str(value)

        # 检查字段是否已存在
        pattern = rf'^{field}:\s*.+$'
        if re.search(pattern, frontmatter, re.MULTILINE):
            # 更新现有字段
            new_frontmatter = re.sub(
                pattern,
                f'{field}: {value_str}',
                frontmatter,
                flags=re.MULTILINE
            )
        else:
            # 添加新字段
            new_frontmatter = frontmatter.rstrip() + f'\n{field}: {value_str}'

        # 重新组装文件
        new_content = '---' + new_frontmatter + '---' + content[fm_end + 3:]

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

    @staticmethod
    async def handle(task, queue: TaskQueue) -> Dict[str, Any]:
        """处理分析任务

        流程：
        1. 读取论文信息（当前 session）
        2. 下载/解析 PDF
        3. 调用 AI 生成分析
        4. 导出到 Obsidian
        5. 提交到写入队列（异步写入数据库）
        """
        payload = task.payload
        paper_id = payload.get("paper_id")
        use_mineru = payload.get("use_mineru", False)
        force_refresh = payload.get("force_refresh", False)
        quick_mode = payload.get("quick_mode", False)  # 快速模式：只用摘要

        if not paper_id:
            raise ValueError("缺少 paper_id")

        # ========== 阶段1: 读取论文信息 ==========
        async with async_session_maker() as db:
            result = await db.execute(select(Paper).where(Paper.id == paper_id))
            paper = result.scalar_one_or_none()

            if not paper:
                raise ValueError(f"论文不存在: {paper_id}")

            # 如果已有分析且不强制刷新，跳过
            if paper.has_analysis and paper.analysis_report and not force_refresh:
                return {
                    "paper_id": paper_id,
                    "status": "skipped",
                    "message": "已有分析",
                }

            # 提取论文信息（只读，不修改）
            paper_title = paper.title
            paper_authors = paper.authors or []
            paper_institutions = paper.institutions or []
            paper_publish_date = str(paper.publish_date) if paper.publish_date else ""
            paper_categories = paper.categories or []
            paper_arxiv_url = paper.arxiv_url or ""
            paper_pdf_url = paper.pdf_url or ""
            paper_arxiv_id = paper.arxiv_id
            paper_abstract = paper.abstract or ""
            paper_full_text = paper.full_text
            paper_pdf_local_path = paper.pdf_local_path
            paper_content_type = paper.content_type or "paper"
            paper_tags = paper.tags

        # ========== 阶段2: 获取内容 ==========
        queue.update_task(task.id, progress=10, message="准备内容...")

        content = paper_full_text
        content_metadata = {}

        # 快速模式：直接使用摘要
        if quick_mode:
            logger.info(f"快速模式: 使用摘要分析 {paper_arxiv_id}")
            content = paper_abstract
            if not content:
                content = paper_full_text  # 回退到全文
        # 常规模式：下载 PDF 并解析
        elif not content and paper_pdf_url and paper_arxiv_id:
            try:
                logger.info(f"下载 PDF: {paper_arxiv_id}")
                pdf_path = await pdf_service.download_pdf(
                    pdf_url=paper_pdf_url,
                    arxiv_id=paper_arxiv_id,
                )
                paper_pdf_local_path = pdf_path

                queue.update_task(task.id, progress=20, message="解析 PDF...")

                if use_mineru:
                    logger.info(f"使用 MinerU 深度解析: {paper_arxiv_id}")
                    content, content_metadata = await pdf_service.extract_markdown(pdf_path)
                else:
                    logger.info(f"使用 PyMuPDF 提取: {paper_arxiv_id}")
                    content = await PDFService.get_paper_text(
                        pdf_url=paper_pdf_url,
                        arxiv_id=paper_arxiv_id,
                    )
                    logger.info(f"提取完成: {len(content)} 字符")

            except Exception as e:
                logger.warning(f"PDF 解析失败，使用摘要: {e}")
                paper_pdf_local_path = None

        # 如果内容不足，使用摘要
        if not content or len(content) < 500:
            content = paper_abstract

        if not content:
            raise ValueError("论文缺少摘要和全文内容，无法分析")

        # ========== 阶段3: AI 分析（可并行） ==========
        queue.update_task(task.id, progress=30, message="生成深度分析报告...")
        logger.info(f"开始 AI 分析: {paper_arxiv_id}")

        analysis_result = await ai_service.generate_deep_analysis(
            title=paper_title,
            authors=paper_authors,
            institutions=paper_institutions,
            publish_date=paper_publish_date,
            categories=paper_categories,
            arxiv_url=paper_arxiv_url,
            pdf_url=paper_pdf_url,
            content=content,
            quick_mode=quick_mode,  # 传递快速模式参数
        )

        queue.update_task(task.id, progress=80, message="保存分析结果...")

        analysis_report = analysis_result.get("report", "")
        analysis_json = analysis_result.get("analysis_json", {})

        logger.info(f"分析结果生成完成，准备保存")

        # ========== 防护层：Tier A 二次确认 ==========
        if analysis_json.get("tier") == "A":
            logger.warning(f"⚠️ Tier A 论文检测: {paper_arxiv_id}")
            # 记录 Tier A 论文信息，供人工复查
            logger.warning(
                f"Tier A 详细信息:\n"
                f"  - 标题: {paper_title[:50]}...\n"
                f"  - 贡献数: {len(analysis_json.get('key_contributions', []))}\n"
                f"  - 标签: {analysis_json.get('tags', [])}\n"
                f"  - 一句话总结: {analysis_json.get('one_line_summary', '')[:80]}..."
            )
            # 可以在这里添加自动告警机制
            # 例如：发送飞书通知、记录到告警日志等

        # ========== 防护层：最终验证 ==========
        if analysis_json:
            # 确保 tier 存在且合理
            tier = analysis_json.get("tier", "B")
            if tier not in ["A", "B", "C"]:
                logger.warning(f"无效 tier '{tier}'，降级为 B")
                analysis_json["tier"] = "B"

            # 确保必要字段存在
            required_fields = ["tier", "tags", "one_line_summary"]
            for field in required_fields:
                if field not in analysis_json or not analysis_json.get(field):
                    logger.warning(f"缺少必要字段 '{field}'，将使用默认值")
                    if field == "tier":
                        analysis_json[field] = "B"
                    elif field == "tags":
                        analysis_json[field] = []
                    elif field == "one_line_summary":
                        analysis_json[field] = paper_abstract[:100] if paper_abstract else ""

        # ========== 阶段4: 导出到 Obsidian ==========
        export_result = None
        md_output_path = None

        # ========== 验证分析结果完整性 ==========
        is_valid, missing_fields = validate_analysis_result(analysis_json, analysis_report)
        if not is_valid:
            logger.error(f"❌ 分析结果验证失败: {missing_fields}")
            # 验证失败，不写入结果，返回失败状态
            return {
                "paper_id": paper_id,
                "status": "failed",
                "reason": f"验证失败: {missing_fields}",
                "has_analysis": False,
            }

        logger.info(f"✅ 分析结果验证通过")

        try:
            generator = MarkdownGenerator()
            export_result = generator._local_generate_paper_md(
                paper_data={
                    "title": paper_title,
                    "authors": paper_authors,
                    "institutions": paper_institutions,
                    "publish_date": paper_publish_date,
                    "arxiv_url": paper_arxiv_url,
                    "arxiv_id": paper_arxiv_id,
                    "tags": analysis_json.get("tags") or paper_tags,
                    "content_type": paper_content_type,
                    # 联动字段（v1.1 状态同步）
                    "paper_id": paper_id,
                    "has_analysis": True,  # 分析完成后为 True
                    "rag_indexed": False,  # 初始为 False，RAG 同步后更新
                    "analysis_mode": "quick" if quick_mode else "full",
                    "pdf_local_path": paper_pdf_local_path,
                },
                analysis_json=analysis_json or {},
                report=analysis_report or "",
                pdf_path=paper_pdf_local_path,
            )
            md_output_path = export_result.get("md_path")
            logger.info(f"导出到 Obsidian 成功: {md_output_path}")
        except Exception as e:
            logger.warning(f"导出到 Obsidian 失败: {e}")

        # ========== 阶段5: 提交到写入队列 ==========
        write_task = WriteTask(
            paper_id=paper_id,
            analysis_report=analysis_report,
            analysis_json=analysis_json,
            tier=analysis_json.get("tier") if analysis_json else None,
            summary=analysis_json.get("one_line_summary") if analysis_json else None,
            action_items=analysis_json.get("action_items") if analysis_json else None,
            knowledge_links=analysis_json.get("knowledge_links") if analysis_json else None,
            tags=analysis_json.get("tags") if analysis_json else None,
            md_output_path=md_output_path,
            has_analysis=True,
            analysis_mode="quick" if quick_mode else "full",  # 记录分析模式
        )

        success = await db_write_service.submit(write_task)

        if not success:
            raise RuntimeError(f"数据库写入失败: paper_id={paper_id}")

        logger.info(f"✅ 论文 {paper_id} 分析完成")

        # ========== 阶段6: 同步到 RAG (异步，不阻塞主流程) ==========
        rag_indexed = False
        lancedb_id = None
        if md_output_path and paper_arxiv_id:
            try:
                import subprocess
                from pathlib import Path as PathLib

                rag_venv = PathLib.home() / "zhiwei-rag" / "venv" / "bin" / "python3"
                rag_script = PathLib.home() / "zhiwei-rag" / "scripts" / "ingest_incremental.py"

                if rag_venv.exists() and rag_script.exists():
                    result = subprocess.run(
                        [str(rag_venv), str(rag_script),
                         "--file", md_output_path,
                         "--prefix", f"arxiv:{paper_arxiv_id}:",
                         "--no-vlm"],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(PathLib.home() / "zhiwei-rag"),
                    )
                    if result.returncode == 0:
                        rag_indexed = True
                        lancedb_id = f"arxiv:{paper_arxiv_id}"
                        logger.info(f"✅ RAG 同步成功: {lancedb_id}")
                    else:
                        logger.warning(f"RAG 同步失败: {result.stderr[:100]}")
            except Exception as e:
                logger.warning(f"RAG 同步异常: {e}")

        # 更新写入任务，包含 RAG 状态
        if rag_indexed:
            # 更新数据库
            async with async_session_maker() as db:
                from sqlalchemy import update
                await db.execute(
                    update(Paper).where(Paper.id == paper_id).values(
                        rag_indexed=True,
                        lancedb_id=lancedb_id
                    )
                )
                await db.commit()

            # 更新 Obsidian 文件的 rag_indexed 字段
            if md_output_path and os.path.exists(md_output_path):
                try:
                    AnalysisTaskHandler._update_frontmatter_field(md_output_path, "rag_indexed", True)
                    logger.info(f"✅ Obsidian frontmatter 已更新: rag_indexed=True")
                except Exception as e:
                    logger.warning(f"更新 Obsidian frontmatter 失败: {e}")

        return {
            "paper_id": paper_id,
            "status": "completed",
            "has_analysis": True,
            "has_outline": bool(analysis_json.get("outline")),
            "has_contributions": bool(analysis_json.get("key_contributions")),
            "md_path": md_output_path,
            "rag_indexed": rag_indexed,
        }


def register_analysis_handler(queue: TaskQueue):
    """注册分析任务处理器"""
    queue.register_handler("analysis", AnalysisTaskHandler.handle)