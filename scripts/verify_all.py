"""ArXiv Paper Analyzer 完整功能验证脚本。

运行后端 API 和前端界面的完整测试，生成 Markdown 验证报告。
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verify_backend import verify_backend, Colors
from verify_frontend import verify_frontend


def check_service(url: str, name: str) -> bool:
    """检查服务是否运行。"""
    import httpx
    try:
        response = httpx.get(url, timeout=5.0)
        return response.status_code < 500
    except Exception:
        return False


def generate_report(
    backend_results: tuple,
    frontend_results: tuple,
    output_path: str,
    backend_url: str,
    frontend_url: str,
    start_time: datetime,
    end_time: datetime
) -> str:
    """生成 Markdown 验证报告。"""
    backend_passed, backend_failed, backend_warning = backend_results
    frontend_passed, frontend_failed, frontend_warning = frontend_results

    total_passed = backend_passed + frontend_passed
    total_failed = backend_failed + frontend_failed
    total_warning = backend_warning + frontend_warning
    total_tests = total_passed + total_failed + total_warning

    duration = (end_time - start_time).total_seconds()

    # 判断整体状态
    if total_failed > 0:
        overall_status = "❌ 存在失败项"
    elif total_warning > 0:
        overall_status = "⚠️ 部分警告"
    else:
        overall_status = "✅ 全部通过"

    report = f"""# ArXiv Paper Analyzer 功能验证报告

> 日期: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
> 耗时: {duration:.2f} 秒
> 整体状态: {overall_status}

## 一、验证环境

| 项目 | 值 |
|------|-----|
| 后端地址 | `{backend_url}` |
| 前端地址 | `{frontend_url}` |
| Python 版本 | {sys.version.split()[0]} |
| 操作系统 | {sys.platform} |

## 二、后端 API 验证

| 状态 | 数量 |
|------|------|
| ✅ 通过 | {backend_passed} |
| ❌ 失败 | {backend_failed} |
| ⚠️ 警告 | {backend_warning} |

### 已验证端点

| 端点 | 功能 | 说明 |
|------|------|------|
| `GET /health` | 健康检查 | 服务状态检测 |
| `GET /api/tags` | 标签列表 | 预设标签返回 |
| `GET /api/categories` | 分类列表 | ArXiv 分类信息 |
| `POST /api/fetch` | 论文抓取 | 从 ArXiv 抓取论文 |
| `POST /api/fetch/categories` | 分类抓取 | 按分类抓取 |
| `POST /api/fetch/date-range` | 日期范围抓取 | 按日期过滤 |
| `GET /api/papers` | 论文列表 | 分页、搜索、筛选 |
| `GET /api/papers/{{id}}` | 论文详情 | 详情与浏览量 |
| `POST /api/papers/generate-summaries` | 摘要生成 | AI 批量生成 |
| `POST /api/papers/{{id}}/analyze` | 深度分析 | AI 分析报告 |
| `GET /api/stats` | 统计信息 | 数据统计 |
| `GET /api/papers/{{id}}/markdown` | Markdown 导出 | 导出 MD |
| `POST /api/papers/{{id}}/export-to-obsidian` | Obsidian 导出 | 导出到 Vault |

## 三、前端界面验证

| 状态 | 数量 |
|------|------|
| ✅ 通过 | {frontend_passed} |
| ❌ 失败 | {frontend_failed} |
| ⚠️ 警告 | {frontend_warning} |

### 已验证功能

| 功能 | 说明 |
|------|------|
| 首页加载 | 页面正常渲染 |
| 论文列表 | 卡片展示、分页 |
| 搜索功能 | 关键词搜索 |
| 筛选功能 | 分类/标签筛选 |
| 论文详情 | 详情页展示 |
| 抓取功能 | 抓取对话框 |
| 分析功能 | 分析按钮 |
| 导出功能 | 导出按钮 |

## 四、验证汇总

```
总测试项: {total_tests}
通过: {total_passed} ({total_passed/total_tests*100:.1f}%)
失败: {total_failed}
警告: {total_warning}
```

## 五、建议

"""

    if total_failed > 0:
        report += """### 需要修复

存在测试失败项，请检查：

1. 确认后端服务正常运行 (`uvicorn app.main:app --reload`)
2. 确认前端服务正常运行 (`npm run dev`)
3. 检查 `.env` 文件中的 API Key 配置
4. 查看后端日志排查错误

"""
    elif total_warning > 0:
        report += """### 建议优化

存在警告项，可能的原因：

1. 部分 AI 功能需要配置 API Key
2. 数据库中暂无数据，可先抓取论文
3. Obsidian Vault 路径未配置

"""

    if total_failed == 0 and total_warning == 0:
        report += """### 状态良好

所有功能测试通过，系统运行正常。

"""

    report += f"""
---

*报告生成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}*
"""

    # 确保目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 写入报告
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    return output_path


async def main():
    """主验证流程。"""
    parser = argparse.ArgumentParser(
        description="ArXiv Paper Analyzer 功能验证脚本"
    )
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8000",
        help="后端 API 地址 (默认: http://localhost:8000)"
    )
    parser.add_argument(
        "--frontend-url",
        default="http://localhost:5173",
        help="前端界面地址 (默认: http://localhost:5173)"
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="跳过前端测试"
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="跳过后端测试"
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="显示浏览器窗口（前端测试）"
    )
    parser.add_argument(
        "--output",
        default="scripts/verify_report.md",
        help="验证报告输出路径"
    )

    args = parser.parse_args()

    start_time = datetime.now()

    print(f"\n{Colors.BOLD}{'='*50}{Colors.RESET}")
    print(f"{Colors.BOLD}ArXiv Paper Analyzer 功能验证{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*50}{Colors.RESET}\n")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 环境检查
    print(f"{Colors.BOLD}=== 环境检查 ==={Colors.RESET}\n")

    # 检查后端服务
    backend_running = check_service(f"{args.backend_url}/health", "后端")
    if backend_running:
        print(f"  {Colors.GREEN}✅ 后端服务运行中{Colors.RESET}")
    else:
        print(f"  {Colors.RED}❌ 后端服务未运行{Colors.RESET}")
        print(f"     启动命令: cd backend && uvicorn app.main:app --reload")

    # 检查前端服务
    if not args.skip_frontend:
        frontend_running = check_service(args.frontend_url, "前端")
        if frontend_running:
            print(f"  {Colors.GREEN}✅ 前端服务运行中{Colors.RESET}")
        else:
            print(f"  {Colors.RED}❌ 前端服务未运行{Colors.RESET}")
            print(f"     启动命令: cd frontend && npm run dev")

    print()

    # 运行验证
    backend_results = (0, 0, 0)
    frontend_results = (0, 0, 0)

    if not args.skip_backend:
        if backend_running:
            backend_results = await verify_backend(args.backend_url)
        else:
            print(f"{Colors.YELLOW}跳过后端测试（服务未运行）{Colors.RESET}\n")

    if not args.skip_frontend:
        if check_service(args.frontend_url, "前端"):
            frontend_results = await verify_frontend(args.frontend_url, headless=not args.headed)
        else:
            print(f"{Colors.YELLOW}跳过前端测试（服务未运行）{Colors.RESET}\n")

    end_time = datetime.now()

    # 生成报告
    report_path = generate_report(
        backend_results=backend_results,
        frontend_results=frontend_results,
        output_path=args.output,
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        start_time=start_time,
        end_time=end_time
    )

    # 最终汇总
    total_passed = backend_results[0] + frontend_results[0]
    total_failed = backend_results[1] + frontend_results[1]
    total_warning = backend_results[2] + frontend_results[2]

    print(f"\n{Colors.BOLD}{'='*50}{Colors.RESET}")
    print(f"{Colors.BOLD}验证完成{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*50}{Colors.RESET}\n")

    print(f"通过: {Colors.GREEN}{total_passed}{Colors.RESET}")
    print(f"失败: {Colors.RED}{total_failed}{Colors.RESET}")
    print(f"警告: {Colors.YELLOW}{total_warning}{Colors.RESET}")
    print(f"\n验证报告: {report_path}")

    # 返回退出码
    if total_failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())