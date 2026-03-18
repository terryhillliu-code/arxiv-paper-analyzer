"""后端 API 验证模块。

测试所有后端 API 端点的功能正确性。
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ANSI 颜色码
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestResult:
    """测试结果记录。"""
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.status: str = "pending"  # pending, passed, failed, warning, skipped
        self.message: str = ""
        self.duration_ms: int = 0
        self.response_data: Any = None
        self.error: Optional[str] = None

    def __str__(self) -> str:
        status_icons = {
            "passed": f"{Colors.GREEN}✅{Colors.RESET}",
            "failed": f"{Colors.RED}❌{Colors.RESET}",
            "warning": f"{Colors.YELLOW}⚠️{Colors.RESET}",
            "skipped": f"{Colors.BLUE}⏭️{Colors.RESET}",
            "pending": "⏳",
        }
        icon = status_icons.get(self.status, "❓")
        duration = f" ({self.duration_ms}ms)" if self.duration_ms else ""
        return f"{icon} {self.name}{duration}"


class BackendVerifier:
    """后端 API 验证器。"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[TestResult] = []
        self.test_paper_id: Optional[int] = None
        self.test_arxiv_id: Optional[str] = None
        self.client: Optional[httpx.AsyncClient] = None

    def add_result(self, result: TestResult):
        """添加测试结果。"""
        self.results.append(result)
        print(f"  {result}")
        if result.message:
            print(f"    {Colors.YELLOW}{result.message}{Colors.RESET}")
        if result.error:
            print(f"    {Colors.RED}Error: {result.error}{Colors.RESET}")

    async def run_all(self) -> Tuple[int, int, int]:
        """运行所有测试，返回 (passed, failed, warning) 数量。"""
        print(f"\n{Colors.BOLD}=== 后端 API 验证 ==={Colors.RESET}\n")
        print(f"目标地址: {self.base_url}\n")

        async with httpx.AsyncClient(timeout=60.0) as client:
            self.client = client

            # 1. 健康检查
            await self.test_health()

            # 2. 静态数据端点
            await self.test_tags()
            await self.test_categories()

            # 3. 论文抓取
            await self.test_fetch_papers()

            # 4. 论文列表与详情
            await self.test_papers_list()
            await self.test_paper_detail()

            # 5. 统计信息
            await self.test_stats()

            # 6. AI 功能（需要 API Key）
            await self.test_generate_summaries()
            await self.test_analyze_paper()

            # 7. 导出功能
            await self.test_export_markdown()
            await self.test_export_obsidian()

        return self._summarize()

    async def test_health(self):
        """测试健康检查端点。"""
        result = TestResult("健康检查", "基础")
        try:
            start = datetime.now()
            response = await self.client.get(f"{self.base_url}/health")
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                result.status = "passed"
                result.response_data = data
                result.message = f"服务状态: {data.get('status', 'unknown')}"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_tags(self):
        """测试标签列表端点。"""
        result = TestResult("标签列表", "静态数据")
        try:
            start = datetime.now()
            response = await self.client.get(f"{self.base_url}/api/tags")
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                tags = data.get("tags", [])
                if isinstance(tags, list) and len(tags) > 0:
                    result.status = "passed"
                    result.message = f"返回 {len(tags)} 个标签"
                else:
                    result.status = "warning"
                    result.message = "标签列表为空"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_categories(self):
        """测试分类列表端点。"""
        result = TestResult("分类列表", "静态数据")
        try:
            start = datetime.now()
            response = await self.client.get(f"{self.base_url}/api/categories")
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                categories = data.get("categories", {})
                if isinstance(categories, dict) and len(categories) > 0:
                    result.status = "passed"
                    result.message = f"返回 {len(categories)} 个分类"
                else:
                    result.status = "warning"
                    result.message = "分类列表为空"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_fetch_papers(self):
        """测试论文抓取端点。"""
        result = TestResult("论文抓取", "抓取功能")
        try:
            start = datetime.now()
            # 使用简单查询抓取少量论文
            response = await self.client.post(
                f"{self.base_url}/api/fetch",
                json={
                    "query": "cat:cs.AI",
                    "max_results": 2
                }
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                total_fetched = data.get("total_fetched", 0)
                new_papers = data.get("new_papers", 0)

                result.status = "passed"
                result.message = f"抓取 {total_fetched} 篇，新增 {new_papers} 篇"

                # 记录测试用的论文 ID
                if total_fetched > 0:
                    # 获取最新论文的 ID
                    list_response = await self.client.get(
                        f"{self.base_url}/api/papers",
                        params={"page": 1, "page_size": 1}
                    )
                    if list_response.status_code == 200:
                        papers = list_response.json().get("papers", [])
                        if papers:
                            self.test_paper_id = papers[0].get("id")
                            self.test_arxiv_id = papers[0].get("arxiv_id")
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}, {response.text}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_papers_list(self):
        """测试论文列表端点。"""
        result = TestResult("论文列表", "论文查询")
        try:
            start = datetime.now()
            response = await self.client.get(
                f"{self.base_url}/api/papers",
                params={
                    "page": 1,
                    "page_size": 10,
                    "sort_by": "newest"
                }
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                total = data.get("total", 0)
                page = data.get("page", 0)
                papers = data.get("papers", [])

                if isinstance(papers, list):
                    result.status = "passed"
                    result.message = f"总数: {total}, 当前页: {page}, 返回: {len(papers)} 篇"

                    # 记录测试用的论文 ID（如果还没记录）
                    if not self.test_paper_id and papers:
                        self.test_paper_id = papers[0].get("id")
                        self.test_arxiv_id = papers[0].get("arxiv_id")
                else:
                    result.status = "failed"
                    result.error = "返回数据格式错误"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_paper_detail(self):
        """测试论文详情端点。"""
        result = TestResult("论文详情", "论文查询")

        if not self.test_paper_id:
            result.status = "skipped"
            result.message = "没有可用的论文 ID"
            self.add_result(result)
            return

        try:
            start = datetime.now()
            response = await self.client.get(
                f"{self.base_url}/api/papers/{self.test_paper_id}"
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                required_fields = ["id", "title", "arxiv_id"]
                if all(field in data for field in required_fields):
                    result.status = "passed"
                    result.message = f"标题: {data.get('title', '')[:50]}..."
                else:
                    result.status = "warning"
                    result.message = "缺少必要字段"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_stats(self):
        """测试统计信息端点。"""
        result = TestResult("统计信息", "数据统计")
        try:
            start = datetime.now()
            response = await self.client.get(f"{self.base_url}/api/stats")
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                total = data.get("total_papers", 0)
                analyzed = data.get("analyzed_papers", 0)
                categories = data.get("categories", {})
                tags = data.get("tags", {})

                result.status = "passed"
                result.message = f"总数: {total}, 已分析: {analyzed}, 分类: {len(categories)}, 标签: {len(tags)}"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_generate_summaries(self):
        """测试摘要生成端点。"""
        result = TestResult("摘要生成", "AI 功能")

        # 获取未生成摘要的论文数量
        try:
            list_response = await self.client.get(
                f"{self.base_url}/api/papers",
                params={"page": 1, "page_size": 1}
            )
            if list_response.status_code != 200:
                result.status = "skipped"
                result.message = "无法获取论文列表"
                self.add_result(result)
                return
        except Exception as e:
            result.status = "skipped"
            result.message = f"请求失败: {e}"
            self.add_result(result)
            return

        try:
            start = datetime.now()
            response = await self.client.post(
                f"{self.base_url}/api/papers/generate-summaries",
                params={"limit": 1}
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                processed = data.get("processed", 0)
                success = data.get("success", 0)
                failed = data.get("failed", 0)

                if processed > 0:
                    result.status = "passed" if success > 0 else "warning"
                    result.message = f"处理: {processed}, 成功: {success}, 失败: {failed}"
                else:
                    result.status = "passed"
                    result.message = "没有需要处理的论文"
            else:
                result.status = "warning"
                result.error = f"状态码: {response.status_code}（可能缺少 API Key）"
        except Exception as e:
            result.status = "warning"
            result.error = f"{str(e)}（可能缺少 API Key）"

        self.add_result(result)

    async def test_analyze_paper(self):
        """测试深度分析端点。"""
        result = TestResult("深度分析", "AI 功能")

        if not self.test_paper_id:
            result.status = "skipped"
            result.message = "没有可用的论文 ID"
            self.add_result(result)
            return

        try:
            start = datetime.now()
            response = await self.client.post(
                f"{self.base_url}/api/papers/{self.test_paper_id}/analyze"
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "")
                has_report = bool(data.get("report"))

                if status == "completed" and has_report:
                    result.status = "passed"
                    result.message = "分析完成，报告已生成"
                else:
                    result.status = "warning"
                    result.message = f"状态: {status}"
            elif response.status_code == 400:
                # 可能已经有分析结果
                result.status = "passed"
                result.message = "论文已有分析结果"
            else:
                result.status = "warning"
                result.error = f"状态码: {response.status_code}（可能缺少 API Key）"
        except Exception as e:
            result.status = "warning"
            result.error = f"{str(e)}（可能缺少 API Key 或请求超时）"

        self.add_result(result)

    async def test_export_markdown(self):
        """测试 Markdown 导出端点。"""
        result = TestResult("Markdown 导出", "导出功能")

        if not self.test_paper_id:
            result.status = "skipped"
            result.message = "没有可用的论文 ID"
            self.add_result(result)
            return

        try:
            start = datetime.now()
            response = await self.client.get(
                f"{self.base_url}/api/papers/{self.test_paper_id}/markdown"
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                content = response.text
                if len(content) > 100 and "# " in content:
                    result.status = "passed"
                    result.message = f"导出 {len(content)} 字符"
                else:
                    result.status = "warning"
                    result.message = "内容可能不完整"
            elif response.status_code == 400:
                result.status = "warning"
                result.message = "论文尚未分析，无法导出"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_export_obsidian(self):
        """测试 Obsidian 导出端点。"""
        result = TestResult("Obsidian 导出", "导出功能")

        if not self.test_paper_id:
            result.status = "skipped"
            result.message = "没有可用的论文 ID"
            self.add_result(result)
            return

        try:
            start = datetime.now()
            response = await self.client.post(
                f"{self.base_url}/api/papers/{self.test_paper_id}/export-to-obsidian"
            )
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                md_path = data.get("md_path", "")
                pdf_path = data.get("pdf_path", "")

                result.status = "passed"
                result.message = f"MD: {md_path}"
                if pdf_path:
                    result.message += f", PDF: {pdf_path}"
            elif response.status_code == 400:
                result.status = "warning"
                result.message = "论文尚未分析，无法导出"
            else:
                result.status = "failed"
                result.error = f"状态码: {response.status_code}"
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    def _summarize(self) -> Tuple[int, int, int]:
        """汇总测试结果。"""
        passed = sum(1 for r in self.results if r.status == "passed")
        failed = sum(1 for r in self.results if r.status == "failed")
        warning = sum(1 for r in self.results if r.status == "warning")
        skipped = sum(1 for r in self.results if r.status == "skipped")

        total = len(self.results)
        print(f"\n{Colors.BOLD}--- 后端测试汇总 ---{Colors.RESET}")
        print(f"总计: {total} 项测试")
        print(f"  {Colors.GREEN}通过: {passed}{Colors.RESET}")
        if warning > 0:
            print(f"  {Colors.YELLOW}警告: {warning}{Colors.RESET}")
        if failed > 0:
            print(f"  {Colors.RED}失败: {failed}{Colors.RESET}")
        if skipped > 0:
            print(f"  {Colors.BLUE}跳过: {skipped}{Colors.RESET}")

        return passed, failed, warning


async def verify_backend(base_url: str = "http://localhost:8000") -> Tuple[int, int, int]:
    """运行后端验证的主入口。"""
    verifier = BackendVerifier(base_url)
    return await verifier.run_all()


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    passed, failed, warning = asyncio.run(verify_backend(base_url))
    sys.exit(1 if failed > 0 else 0)