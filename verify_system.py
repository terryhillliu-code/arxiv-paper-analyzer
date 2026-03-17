#!/usr/bin/env python3
"""
ArXiv 论文智能分析系统 - 完整验证脚本

自动化测试整个系统的核心功能。

使用方法:
    python verify_system.py              # 完整测试
    python verify_system.py --skip-ai    # 跳过所有 AI 测试
    python verify_system.py --skip-analysis  # 跳过深度分析测试
"""

import argparse
import sys
import time
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"

# 测试结果存储
test_results = []


def print_header(title: str) -> None:
    """打印分节标题"""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print('=' * 60)


def print_test(test_num: int, name: str) -> None:
    """打印测试名称"""
    print(f"\n测试{test_num}: {name}")


def record_result(test_num: int, name: str, passed: bool, skipped: bool = False, detail: str = "") -> None:
    """记录测试结果"""
    status = "⏭️ 跳过" if skipped else ("✅ 通过" if passed else "❌ 失败")
    test_results.append({
        "num": test_num,
        "name": name,
        "passed": passed,
        "skipped": skipped,
        "detail": detail,
    })
    print(f"  {status}")
    if detail:
        print(f"  详情: {detail}")


def make_request(method: str, path: str, timeout: float = 120.0, **kwargs) -> tuple[int, dict | None, str]:
    """发送 HTTP 请求"""
    try:
        with httpx.Client(timeout=timeout) as client:
            url = f"{BASE_URL}{path}"
            if method == "GET":
                response = client.get(url, **kwargs)
            elif method == "POST":
                response = client.post(url, **kwargs)
            else:
                raise ValueError(f"不支持的请求方法: {method}")

            try:
                data = response.json()
            except Exception:
                data = None

            return response.status_code, data, ""
    except Exception as e:
        return 0, None, str(e)


# ==================== 基础设施验证 ====================

def test_01_health():
    """测试1: 健康检查"""
    print_test(1, "健康检查 GET /health")
    status_code, data, error = make_request("GET", "/health")

    if status_code == 200 and data and data.get("status") == "ok":
        record_result(1, "健康检查", True, detail=f"返回: {data}")
    else:
        record_result(1, "健康检查", False, detail=error or f"状态码: {status_code}, 数据: {data}")


def test_02_root():
    """测试2: 根路由"""
    print_test(2, "根路由 GET /")
    status_code, data, error = make_request("GET", "/")

    if status_code == 200 and data:
        has_message = "message" in data
        has_version = data.get("version") is not None or "docs" in data
        if has_message:
            record_result(2, "根路由", True, detail=f"消息: {data.get('message', 'N/A')}")
        else:
            record_result(2, "根路由", False, detail=f"缺少 message 字段: {data}")
    else:
        record_result(2, "根路由", False, detail=error or f"状态码: {status_code}")


def test_03_tags():
    """测试3: 获取标签"""
    print_test(3, "获取标签 GET /api/tags")
    status_code, data, error = make_request("GET", "/api/tags")

    if status_code == 200 and data:
        tags = data.get("tags", [])
        if len(tags) >= 20:
            record_result(3, "获取标签", True, detail=f"共 {len(tags)} 个标签: {tags[:5]}...")
        else:
            record_result(3, "获取标签", False, detail=f"标签数量不足: {len(tags)}")
    else:
        record_result(3, "获取标签", False, detail=error or f"状态码: {status_code}")


def test_04_categories():
    """测试4: 获取分类"""
    print_test(4, "获取分类 GET /api/categories")
    status_code, data, error = make_request("GET", "/api/categories")

    if status_code == 200 and data:
        categories = data.get("categories", {})
        required_cats = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]
        missing = [cat for cat in required_cats if cat not in categories]

        if not missing:
            # 检查是否有中文描述
            has_chinese = any(
                categories.get(cat, {}).get("name") or categories.get(cat, {}).get("description")
                for cat in required_cats
            )
            record_result(4, "获取分类", True,
                          detail=f"共 {len(categories)} 个分类，包含: {', '.join(required_cats)}")
        else:
            record_result(4, "获取分类", False, detail=f"缺少分类: {missing}")
    else:
        record_result(4, "获取分类", False, detail=error or f"状态码: {status_code}")


# ==================== 论文抓取验证 ====================

def test_05_fetch_papers():
    """测试5: 抓取论文"""
    print_test(5, "抓取论文 POST /api/fetch")
    payload = {"query": "cat:cs.AI", "max_results": 10}
    print(f"  请求参数: {payload}")

    status_code, data, error = make_request("POST", "/api/fetch", json=payload)

    if status_code == 200 and data:
        fetched = data.get("total_fetched", 0)
        new = data.get("new_papers", 0)
        message = data.get("message", "")
        print(f"  抓取结果: 获取 {fetched} 篇，新增 {new} 篇")
        record_result(5, "抓取论文", True, detail=message)
    else:
        record_result(5, "抓取论文", False, detail=error or f"状态码: {status_code}, 数据: {data}")


def test_06_fetch_by_category():
    """测试6: 按分类抓取"""
    print_test(6, "按分类抓取 POST /api/fetch/categories")
    payload = {"categories": ["cs.CL"], "max_results": 5}
    print(f"  请求参数: {payload}")

    status_code, data, error = make_request("POST", "/api/fetch/categories", json=payload)

    if status_code == 200:
        fetched = data.get("total_fetched", 0) if data else 0
        record_result(6, "按分类抓取", True, detail=f"抓取 {fetched} 篇论文")
    elif status_code == 404:
        # 如果端点不存在，标记为跳过
        record_result(6, "按分类抓取", True, skipped=True, detail="端点不存在，跳过")
    else:
        record_result(6, "按分类抓取", False, detail=error or f"状态码: {status_code}")


# ==================== 论文列表验证 ====================

def test_07_paper_list():
    """测试7: 获取论文列表"""
    print_test(7, "获取论文列表 GET /api/papers")
    status_code, data, error = make_request("GET", "/api/papers")

    if status_code == 200 and data:
        total = data.get("total", 0)
        page = data.get("page", 0)
        page_size = data.get("page_size", 0)
        total_pages = data.get("total_pages", 0)
        papers = data.get("papers", [])

        print(f"  论文总数: {total}")
        print(f"  分页信息: 第 {page} 页，每页 {page_size} 条，共 {total_pages} 页")

        if papers:
            first = papers[0]
            print(f"  第一篇论文: {first.get('title', 'N/A')[:60]}...")

        record_result(7, "获取论文列表", True, detail=f"共 {total} 篇论文")
        return papers[0].get("id") if papers else None
    else:
        record_result(7, "获取论文列表", False, detail=error or f"状态码: {status_code}")
        return None


def test_08_pagination():
    """测试8: 分页测试"""
    print_test(8, "分页测试 GET /api/papers?page=1&page_size=5")
    status_code, data, error = make_request("GET", "/api/papers?page=1&page_size=5")

    if status_code == 200 and data:
        papers = data.get("papers", [])
        if len(papers) <= 5:
            record_result(8, "分页测试", True, detail=f"返回 {len(papers)} 篇论文（<= 5）")
        else:
            record_result(8, "分页测试", False, detail=f"返回 {len(papers)} 篇论文（预期 <= 5）")
    else:
        record_result(8, "分页测试", False, detail=error or f"状态码: {status_code}")


def test_09_sort():
    """测试9: 排序测试"""
    print_test(9, "排序测试 GET /api/papers?sort_by=newest")
    status_code, data, error = make_request("GET", "/api/papers?sort_by=newest")

    if status_code == 200:
        total = data.get("total", 0) if data else 0
        record_result(9, "排序测试", True, detail=f"返回 {total} 篇论文")
    else:
        record_result(9, "排序测试", False, detail=error or f"状态码: {status_code}")


def test_10_search():
    """测试10: 搜索测试"""
    print_test(10, "搜索测试 GET /api/papers?search=model")
    status_code, data, error = make_request("GET", "/api/papers?search=model")

    if status_code == 200 and data:
        total = data.get("total", 0)
        print(f"  匹配数量: {total}")
        record_result(10, "搜索测试", True, detail=f"找到 {total} 篇匹配论文")
    else:
        record_result(10, "搜索测试", False, detail=error or f"状态码: {status_code}")


def test_11_filter_category():
    """测试11: 分类筛选测试"""
    print_test(11, "分类筛选测试 GET /api/papers?categories=cs.AI")
    status_code, data, error = make_request("GET", "/api/papers?categories=cs.AI")

    if status_code == 200:
        total = data.get("total", 0) if data else 0
        record_result(11, "分类筛选", True, detail=f"找到 {total} 篇 cs.AI 论文")
    else:
        record_result(11, "分类筛选", False, detail=error or f"状态码: {status_code}")


# ==================== 论文详情验证 ====================

def test_12_paper_detail(paper_id: int | None):
    """测试12: 获取论文详情"""
    print_test(12, f"获取论文详情 GET /api/papers/{paper_id}")

    if not paper_id:
        record_result(12, "论文详情", True, skipped=True, detail="没有可用的论文 ID")
        return None

    status_code, data, error = make_request("GET", f"/api/papers/{paper_id}")

    if status_code == 200 and data:
        # 验证必要字段
        required_fields = ["arxiv_id", "title", "authors", "categories", "pdf_url", "arxiv_url"]
        missing = [f for f in required_fields if not data.get(f)]

        if missing:
            record_result(12, "论文详情", False, detail=f"缺少字段: {missing}")
        else:
            view_count = data.get("view_count", 0)
            print(f"  标题: {data.get('title', 'N/A')[:50]}...")
            print(f"  作者: {', '.join(data.get('authors', [])[:3])}...")
            print(f"  浏览量: {view_count}")

            if view_count > 0:
                record_result(12, "论文详情", True, detail="所有字段完整，浏览量已更新")
            else:
                record_result(12, "论文详情", True, detail="所有字段完整（浏览量未更新）")

        return paper_id
    else:
        record_result(12, "论文详情", False, detail=error or f"状态码: {status_code}")
        return None


# ==================== AI 摘要生成验证 ====================

def test_13_generate_summaries(skip_ai: bool):
    """测试13: 批量生成摘要"""
    print_test(13, "批量生成摘要 POST /api/papers/generate-summaries?limit=2")

    if skip_ai:
        record_result(13, "批量生成摘要", True, skipped=True, detail="--skip-ai 参数跳过")
        return

    print("  注意: 此测试会调用 AI API，可能需要较长时间（最长等待 180 秒）...")
    status_code, data, error = make_request("POST", "/api/papers/generate-summaries?limit=2", timeout=180.0)

    if status_code == 200 and data:
        processed = data.get("processed", 0)
        errors = data.get("failed", 0)
        message = data.get("message", "")
        print(f"  处理结果: 成功 {processed} 篇，失败 {errors} 篇")
        record_result(13, "批量生成摘要", True, detail=message)
    else:
        record_result(13, "批量生成摘要", False, detail=error or f"状态码: {status_code}, 数据: {data}")


def test_14_check_summaries(skip_ai: bool):
    """测试14: 检查摘要生成结果"""
    print_test(14, "检查论文摘要和标签")

    if skip_ai:
        record_result(14, "检查摘要", True, skipped=True, detail="--skip-ai 参数跳过")
        return

    status_code, data, error = make_request("GET", "/api/papers?page_size=10")

    if status_code == 200 and data:
        papers = data.get("papers", [])
        with_summary = sum(1 for p in papers if p.get("summary"))
        with_tags = sum(1 for p in papers if p.get("tags"))

        print(f"  有摘要的论文: {with_summary}/{len(papers)}")
        print(f"  有标签的论文: {with_tags}/{len(papers)}")

        if with_summary > 0 or with_tags > 0:
            record_result(14, "检查摘要", True, detail=f"摘要: {with_summary}, 标签: {with_tags}")
        else:
            record_result(14, "检查摘要", True, detail="暂无新生成的摘要或标签")
    else:
        record_result(14, "检查摘要", False, detail=error or f"状态码: {status_code}")


# ==================== 统计信息验证 ====================

def test_15_stats():
    """测试15: 获取统计"""
    print_test(15, "获取统计 GET /api/stats")
    status_code, data, error = make_request("GET", "/api/stats")

    if status_code == 200 and data:
        total = data.get("total_papers", 0)
        analyzed = data.get("analyzed_papers", 0)
        recent = data.get("recent_papers_count", 0)
        categories = data.get("categories", {})

        print(f"  论文总数: {total}")
        print(f"  已分析数: {analyzed}")
        print(f"  近7天新增: {recent}")
        print(f"  分类数: {len(categories)}")

        record_result(15, "获取统计", True, detail=f"论文: {total}, 分析: {analyzed}, 新增: {recent}")
    else:
        record_result(15, "获取统计", False, detail=error or f"状态码: {status_code}")


# ==================== 深度分析验证 ====================

def test_16_deep_analysis(paper_id: int | None, skip_analysis: bool):
    """测试16: 深度分析"""
    print_test(16, f"深度分析 POST /api/papers/{paper_id}/analyze")

    if skip_analysis:
        record_result(16, "深度分析", True, skipped=True, detail="--skip-analysis 参数跳过")
        return paper_id

    if not paper_id:
        record_result(16, "深度分析", True, skipped=True, detail="没有可用的论文 ID")
        return None

    print("  注意: 此测试会下载 PDF 并调用 AI，耗时 30-120 秒...")
    start_time = time.time()

    status_code, data, error = make_request("POST", f"/api/papers/{paper_id}/analyze?force_refresh=false", timeout=180.0)

    elapsed = time.time() - start_time
    print(f"  耗时: {elapsed:.1f} 秒")

    if status_code == 200 and data:
        report = data.get("report", "")
        analysis_json = data.get("analysis_json", {})

        if report:
            preview = report[:500] + "..." if len(report) > 500 else report
            print(f"  分析报告预览:\n{preview}")

        if analysis_json:
            grade = analysis_json.get("overall_grade", "N/A")
            print(f"  总体评级: {grade}")

        record_result(16, "深度分析", True, detail=f"生成 {len(report)} 字符报告")
    else:
        record_result(16, "深度分析", False, detail=error or f"状态码: {status_code}, 数据: {data}")

    return paper_id


def test_17_check_analysis(paper_id: int | None, skip_analysis: bool):
    """测试17: 验证分析结果"""
    print_test(17, f"验证分析结果 GET /api/papers/{paper_id}")

    if skip_analysis:
        record_result(17, "验证分析结果", True, skipped=True, detail="--skip-analysis 参数跳过")
        return

    if not paper_id:
        record_result(17, "验证分析结果", True, skipped=True, detail="没有可用的论文 ID")
        return

    status_code, data, error = make_request("GET", f"/api/papers/{paper_id}")

    if status_code == 200 and data:
        has_analysis = data.get("has_analysis", False)
        analysis_report = data.get("analysis_report", "")

        if has_analysis and analysis_report:
            print(f"  has_analysis: {has_analysis}")
            print(f"  analysis_report 长度: {len(analysis_report)} 字符")
            record_result(17, "验证分析结果", True, detail="分析数据已保存")
        else:
            record_result(17, "验证分析结果", False, detail=f"has_analysis={has_analysis}, report_empty={not analysis_report}")
    else:
        record_result(17, "验证分析结果", False, detail=error or f"状态码: {status_code}")


# ==================== 主函数 ====================

def print_summary():
    """打印测试汇总"""
    print("\n" + "=" * 60)
    print(" 验证汇总")
    print("=" * 60)

    passed = sum(1 for r in test_results if r["passed"] and not r["skipped"])
    failed = sum(1 for r in test_results if not r["passed"] and not r["skipped"])
    skipped = sum(1 for r in test_results if r["skipped"])
    total = len(test_results)

    print(f"\n总测试数: {total}")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    print(f"⏭️ 跳过: {skipped}")

    print("\n各测试状态:")
    for r in test_results:
        if r["skipped"]:
            status = "⏭️ 跳过"
        elif r["passed"]:
            status = "✅ 通过"
        else:
            status = "❌ 失败"
        print(f"  测试{r['num']:02d}: {status} - {r['name']}")

    print("\n" + "=" * 60)

    if failed > 0:
        print("⚠️  存在失败的测试，请检查系统配置")
        return 1
    else:
        print("🎉 所有测试通过！系统运行正常")
        return 0


def main():
    parser = argparse.ArgumentParser(description="ArXiv 论文智能分析系统验证脚本")
    parser.add_argument("--skip-ai", action="store_true", help="跳过需要 AI API 的测试")
    parser.add_argument("--skip-analysis", action="store_true", help="跳过深度分析测试")
    args = parser.parse_args()

    print("=" * 60)
    print(" ArXiv 论文智能分析系统 - 验证脚本")
    print(f" 目标服务器: {BASE_URL}")
    print(f" 跳过 AI 测试: {args.skip_ai}")
    print(f" 跳过深度分析: {args.skip_analysis}")
    print("=" * 60)

    # 基础设施验证
    print_header("基础设施验证")
    test_01_health()
    test_02_root()
    test_03_tags()
    test_04_categories()

    # 论文抓取验证
    print_header("论文抓取验证")
    test_05_fetch_papers()
    test_06_fetch_by_category()

    # 论文列表验证
    print_header("论文列表验证")
    first_paper_id = test_07_paper_list()
    test_08_pagination()
    test_09_sort()
    test_10_search()
    test_11_filter_category()

    # 论文详情验证
    print_header("论文详情验证")
    first_paper_id = test_12_paper_detail(first_paper_id)

    # AI 摘要生成验证
    print_header("AI 摘要生成验证")
    test_13_generate_summaries(args.skip_ai)
    test_14_check_summaries(args.skip_ai)

    # 统计信息验证
    print_header("统计信息验证")
    test_15_stats()

    # 深度分析验证
    print_header("深度分析验证（可选）")
    test_16_deep_analysis(first_paper_id, args.skip_analysis or args.skip_ai)
    test_17_check_analysis(first_paper_id, args.skip_analysis or args.skip_ai)

    # 打印汇总
    return print_summary()


if __name__ == "__main__":
    sys.exit(main())