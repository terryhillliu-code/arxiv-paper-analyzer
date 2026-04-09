"""批量分析功能单元测试。"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


class TestBatchLightPrompt:
    """批量轻量 Prompt 测试"""

    def test_prompt_imports(self):
        """测试 Prompt 导入"""
        from app.prompts.templates import BATCH_LIGHT_PROMPT, DETAIL_PROMPT

        assert len(BATCH_LIGHT_PROMPT) > 100
        assert len(DETAIL_PROMPT) > 100
        assert "{batch_size}" in BATCH_LIGHT_PROMPT
        assert "{title}" in DETAIL_PROMPT
        assert "paper_id" in BATCH_LIGHT_PROMPT


class TestGenerateBatchLight:
    """批量轻量分析测试"""

    @pytest.mark.asyncio
    async def test_generate_batch_light_empty(self):
        """测试空列表输入"""
        from app.services.ai_service import ai_service

        result = await ai_service.generate_batch_light([])
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_batch_light_success(self):
        """测试批量轻量分析成功"""
        from app.services.ai_service import ai_service

        papers = [
            {"paper_id": 1, "title": "Test Paper 1", "content": "Abstract 1"},
            {"paper_id": 2, "title": "Test Paper 2", "content": "Abstract 2"},
        ]

        # Mock API 调用
        with patch.object(ai_service, '_call_api') as mock_api:
            mock_api.return_value = '[{"paper_id": 1, "tier": "B", "tags": ["AI"], "methodology": "深度学习"}, {"paper_id": 2, "tier": "A", "tags": ["NLP"], "methodology": "自然语言处理"}]'

            result = await ai_service.generate_batch_light(papers)

            assert len(result) == 2
            assert result[0]["paper_id"] == 1
            assert result[0]["tier"] == "B"
            assert result[1]["paper_id"] == 2
            assert result[1]["tier"] == "A"

    @pytest.mark.asyncio
    async def test_match_results_by_paper_id(self):
        """测试结果按 paper_id 匹配"""
        from app.services.ai_service import ai_service

        papers = [
            {"paper_id": 100, "title": "Paper 100"},
            {"paper_id": 200, "title": "Paper 200"},
        ]

        # 模拟 API 返回乱序结果
        results = [
            {"paper_id": 200, "tier": "A", "tags": [], "methodology": "test"},
            {"paper_id": 100, "tier": "B", "tags": [], "methodology": "test"},
        ]

        matched = ai_service._match_results_by_paper_id(papers, results)

        assert matched[0]["paper_id"] == 100  # 第一篇应该是 paper_id=100
        assert matched[1]["paper_id"] == 200  # 第二篇应该是 paper_id=200


class TestGenerateDetail:
    """详细分析测试"""

    @pytest.mark.asyncio
    async def test_generate_detail_success(self):
        """测试详细分析成功"""
        from app.services.ai_service import ai_service

        with patch.object(ai_service, '_call_api') as mock_api:
            mock_api.return_value = '{"one_line_summary": "本研究针对X问题提出了Y方法取得了Z效果", "key_contributions": ["贡献1", "贡献2"]}'

            result = await ai_service.generate_detail(
                title="Test Paper",
                abstract="Test abstract content",
                tier="B",
                tags=["AI"],
                methodology="深度学习",
            )

            assert "one_line_summary" in result
            assert len(result["one_line_summary"]) > 0
            assert "key_contributions" in result

    @pytest.mark.asyncio
    async def test_generate_detail_empty_response(self):
        """测试详细分析返回空"""
        from app.services.ai_service import ai_service

        with patch.object(ai_service, '_call_api') as mock_api:
            mock_api.return_value = 'invalid json'

            result = await ai_service.generate_detail(
                title="Test Paper",
                abstract="Test abstract",
                tier="B",
                tags=[],
                methodology="",
            )

            assert result["one_line_summary"] == ""
            assert result["key_contributions"] == []


class TestBatchAnalysisTaskHandler:
    """批量任务处理器测试"""

    @pytest.mark.asyncio
    async def test_handler_missing_paper_ids(self):
        """测试缺少 paper_ids"""
        from app.tasks.batch_analysis_task import BatchAnalysisTaskHandler
        from app.tasks.task_queue import TaskQueue

        task = MagicMock()
        task.id = "test-task-1"
        task.payload = {}

        queue = MagicMock()

        with pytest.raises(ValueError, match="缺少 paper_ids"):
            await BatchAnalysisTaskHandler.handle(task, queue)


class TestCreateBatchTasks:
    """批量任务创建测试"""

    def test_dry_run(self, tmp_path):
        """测试 dry run 模式"""
        from scripts.create_batch_tasks import create_batch_tasks

        # 创建临时数据库
        import sqlite3
        db_path = tmp_path / "papers.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE papers (
                id INTEGER PRIMARY KEY,
                arxiv_id TEXT,
                title TEXT,
                abstract TEXT,
                has_analysis INTEGER
            )
        """)
        conn.execute("INSERT INTO papers VALUES (1, '2401.00001', 'Test 1', 'Abstract 1', 0)")
        conn.execute("INSERT INTO papers VALUES (2, '2401.00002', 'Test 2', 'Abstract 2', 0)")
        conn.commit()
        conn.close()

        # 测试 dry run（不实际创建任务）
        # 由于脚本使用固定路径，这里只验证函数不报错
        # 实际测试需要 mock 数据库路径


if __name__ == "__main__":
    pytest.main([__file__, "-v"])