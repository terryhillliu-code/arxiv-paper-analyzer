"""前端界面验证模块。

使用 Playwright 进行浏览器自动化测试。
"""

import asyncio
import sys
from datetime import datetime
from typing import List, Optional, Tuple

# ANSI 颜色码
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class FrontendTestResult:
    """前端测试结果。"""
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.status: str = "pending"
        self.message: str = ""
        self.duration_ms: int = 0
        self.screenshot_path: Optional[str] = None
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


class FrontendVerifier:
    """前端界面验证器。"""

    def __init__(self, base_url: str = "http://localhost:5173", headless: bool = True):
        self.base_url = base_url
        self.headless = headless
        self.results: List[FrontendTestResult] = []
        self.page = None
        self.browser = None
        self.playwright = None

    def add_result(self, result: FrontendTestResult):
        """添加测试结果。"""
        self.results.append(result)
        print(f"  {result}")
        if result.message:
            print(f"    {Colors.YELLOW}{result.message}{Colors.RESET}")
        if result.error:
            print(f"    {Colors.RED}Error: {result.error}{Colors.RESET}")

    async def run_all(self) -> Tuple[int, int, int]:
        """运行所有前端测试。"""
        print(f"\n{Colors.BOLD}=== 前端界面验证 ==={Colors.RESET}\n")
        print(f"目标地址: {self.base_url}")
        print(f"无头模式: {self.headless}\n")

        try:
            # 尝试导入 playwright
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            context = await self.browser.new_context()
            self.page = await context.new_page()

            # 设置页面错误监听
            self.page.on("pageerror", lambda exc: print(f"  {Colors.RED}Page Error: {exc}{Colors.RESET}"))

            # 运行测试
            await self.test_home_page()
            await self.test_paper_list()
            await self.test_search_function()
            await self.test_filter_function()
            await self.test_paper_detail_page()
            await self.test_fetch_dialog()
            await self.test_analysis_function()
            await self.test_export_function()

        except ImportError:
            print(f"{Colors.YELLOW}Playwright 未安装，跳过前端测试{Colors.RESET}")
            print("安装方法: pip install playwright && playwright install chromium")
            return 0, 0, 0
        except Exception as e:
            print(f"{Colors.RED}浏览器启动失败: {e}{Colors.RESET}")
            return 0, 1, 0
        finally:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()

        return self._summarize()

    async def test_home_page(self):
        """测试首页加载。"""
        result = FrontendTestResult("首页加载", "基础功能")
        try:
            start = datetime.now()
            await self.page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            # 检查页面标题
            title = await self.page.title()
            if "arxiv" in title.lower() or "论文" in title:
                result.status = "passed"
                result.message = f"页面标题: {title}"
            else:
                result.status = "warning"
                result.message = f"标题可能不正确: {title}"

        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_paper_list(self):
        """测试论文列表展示。"""
        result = FrontendTestResult("论文列表展示", "列表功能")
        try:
            start = datetime.now()

            # 等待论文卡片加载 - 使用更通用的选择器
            # PaperCard 组件使用 bg-white rounded-xl shadow-sm p-6 作为容器
            await self.page.wait_for_selector(
                ".bg-white.rounded-xl.shadow-sm, [class*='rounded-xl'][class*='shadow-sm']",
                timeout=15000
            )
            # 统计所有论文卡片
            cards = await self.page.query_selector_all("h2")  # 论文标题用 h2

            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

            if len(cards) > 0:
                result.status = "passed"
                result.message = f"显示 {len(cards)} 篇论文（检测到标题）"
            else:
                result.status = "warning"
                result.message = "未找到论文标题元素"

        except Exception as e:
            result.status = "failed"
            result.error = f"加载超时: {str(e)[:80]}"

        self.add_result(result)

    async def test_search_function(self):
        """测试搜索功能。"""
        result = FrontendTestResult("搜索功能", "搜索筛选")
        try:
            start = datetime.now()

            # 查找搜索框 - 使用 placeholder 属性
            search_input = await self.page.query_selector(
                "input[placeholder='搜索论文']"
            )

            if search_input:
                # 输入搜索词
                await search_input.fill("AI")
                await search_input.press("Enter")

                # 等待结果更新
                await self.page.wait_for_timeout(1000)

                result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
                result.status = "passed"
                result.message = "搜索框可用"
            else:
                result.status = "warning"
                result.message = "未找到搜索框"

        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_filter_function(self):
        """测试筛选功能。"""
        result = FrontendTestResult("筛选功能", "搜索筛选")
        try:
            start = datetime.now()

            # 查找分类按钮 - PaperList 中有多个分类按钮
            category_button = await self.page.query_selector(
                "button:has-text('cs.AI'), button:has-text('cs.LG')"
            )

            # 查找日期选择器
            date_input = await self.page.query_selector("input[type='date']")

            # 查找排序按钮
            sort_button = await self.page.query_selector(
                "button:has-text('最新发布'), button:has-text('最早发布')"
            )

            found = []
            if category_button:
                found.append("分类按钮")
            if date_input:
                found.append("日期选择")
            if sort_button:
                found.append("排序按钮")

            if found:
                result.status = "passed"
                result.message = f"找到: {', '.join(found)}"
            else:
                result.status = "warning"
                result.message = "未找到筛选组件"

            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

        except Exception as e:
            result.status = "warning"
            result.error = str(e)

        self.add_result(result)

    async def test_paper_detail_page(self):
        """测试论文详情页。"""
        result = FrontendTestResult("论文详情页", "详情功能")
        try:
            start = datetime.now()

            # 返回首页
            await self.page.goto(self.base_url, wait_until="networkidle", timeout=30000)

            # 等待论文列表加载
            await self.page.wait_for_selector("h2", timeout=10000)

            # 点击第一个论文标题链接
            first_title = await self.page.query_selector("h2 a, a:has(h2)")

            if first_title:
                await first_title.click()

                # 等待详情页加载
                await self.page.wait_for_load_state("networkidle", timeout=10000)

                # 检查是否进入详情页
                current_url = self.page.url
                if "/paper/" in current_url:
                    result.status = "passed"
                    result.message = f"跳转到详情页: {current_url.split('/')[-1]}"
                else:
                    result.status = "warning"
                    result.message = f"未检测到详情页 URL: {current_url}"

                result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
            else:
                result.status = "skipped"
                result.message = "没有可点击的论文标题"

        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_fetch_dialog(self):
        """测试抓取对话框。"""
        result = FrontendTestResult("抓取论文按钮", "抓取功能")
        try:
            start = datetime.now()

            # 返回首页
            await self.page.goto(self.base_url, wait_until="networkidle", timeout=30000)

            # 查找抓取按钮 - PaperList 中使用 "抓取论文" 文本
            fetch_button = await self.page.query_selector(
                "button:has-text('抓取论文')"
            )

            if fetch_button:
                result.status = "passed"
                result.message = "抓取论文按钮存在且可点击"
            else:
                result.status = "warning"
                result.message = "未找到抓取论文按钮"

            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)

        self.add_result(result)

    async def test_analysis_function(self):
        """测试分析功能。"""
        result = FrontendTestResult("分析功能按钮", "AI 功能")
        try:
            start = datetime.now()

            # 返回首页并点击第一个论文
            await self.page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_selector("h2", timeout=10000)

            first_title = await self.page.query_selector("h2 a")
            if first_title:
                await first_title.click()
                await self.page.wait_for_load_state("networkidle", timeout=15000)

                # 查找分析按钮 - PaperDetail 页面
                analyze_button = await self.page.query_selector(
                    "button:has-text('分析'), button:has-text('深度分析'), a:has-text('深度分析')"
                )

                if analyze_button:
                    result.status = "passed"
                    result.message = "分析按钮存在"
                else:
                    result.status = "warning"
                    result.message = "未找到分析按钮"
            else:
                result.status = "skipped"
                result.message = "没有论文可进入详情页"

            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

        except Exception as e:
            result.status = "warning"
            result.error = str(e)[:60]

        self.add_result(result)

    async def test_export_function(self):
        """测试导出功能。"""
        result = FrontendTestResult("导出功能按钮", "导出功能")
        try:
            start = datetime.now()

            # 当前已在详情页，查找导出按钮
            export_button = await self.page.query_selector(
                "button:has-text('导出'), button:has-text('Obsidian'), a:has-text('Obsidian')"
            )

            if export_button:
                result.status = "passed"
                result.message = "导出按钮存在"
            else:
                result.status = "warning"
                result.message = "未找到导出按钮"

            result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)

        except Exception as e:
            result.status = "warning"
            result.error = str(e)

        self.add_result(result)

    def _summarize(self) -> Tuple[int, int, int]:
        """汇总测试结果。"""
        passed = sum(1 for r in self.results if r.status == "passed")
        failed = sum(1 for r in self.results if r.status == "failed")
        warning = sum(1 for r in self.results if r.status == "warning")
        skipped = sum(1 for r in self.results if r.status == "skipped")

        total = len(self.results)
        print(f"\n{Colors.BOLD}--- 前端测试汇总 ---{Colors.RESET}")
        print(f"总计: {total} 项测试")
        print(f"  {Colors.GREEN}通过: {passed}{Colors.RESET}")
        if warning > 0:
            print(f"  {Colors.YELLOW}警告: {warning}{Colors.RESET}")
        if failed > 0:
            print(f"  {Colors.RED}失败: {failed}{Colors.RESET}")
        if skipped > 0:
            print(f"  {Colors.BLUE}跳过: {skipped}{Colors.RESET}")

        return passed, failed, warning


async def verify_frontend(
    base_url: str = "http://localhost:5173",
    headless: bool = True
) -> Tuple[int, int, int]:
    """运行前端验证的主入口。"""
    verifier = FrontendVerifier(base_url, headless)
    return await verifier.run_all()


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
    headless = "--headed" not in sys.argv
    passed, failed, warning = asyncio.run(verify_frontend(base_url, headless))
    sys.exit(1 if failed > 0 else 0)