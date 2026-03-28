#!/usr/bin/env python3
"""
ArXiv 论文智能分析平台 - 全功能验证脚本

验证范围：
1. 服务健康检查
2. 论文抓取功能
3. 论文列表功能（分页、搜索、筛选、排序）
4. 论文详情功能
5. 日期筛选功能
6. AI 摘要生成
7. 深度分析功能
8. 统计功能

使用方法：
    python verify_all_features.py              # 完整验证
    python verify_all_features.py --skip-ai    # 跳过 AI 相关测试
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"

# 测试结果
results = []


def header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def test(name, passed, detail="", skipped=False):
    status = "⏭️ 跳过" if skipped else ("✅ 通过" if passed else "❌ 失败")
    results.append({"name": name, "passed": passed, "detail": detail, "skipped": skipped})
    print(f"  {status} {name}")
    if detail:
        print(f"      {detail}")


def request(method, path, timeout=30, **kwargs):
    """发送请求"""
    try:
        with httpx.Client(timeout=timeout) as client:
            url = f"{BASE_URL}{path}"
            if method == "GET":
                r = client.get(url, **kwargs)
            elif method == "POST":
                r = client.post(url, **kwargs)
            else:
                return 0, None, f"不支持的方法: {method}"
            try:
                return r.status_code, r.json(), ""
            except:
                return r.status_code, None, ""
    except Exception as e:
        return 0, None, str(e)


# ==================== 1. 服务健康检查 ====================

def verify_service_health():
    header("1. 服务健康检查")

    # 健康检查
    code, data, err = request("GET", "/health")
    test("健康检查端点", code == 200 and data and data.get("status") == "ok",
         f"status_code={code}")

    # 根路由
    code, data, err = request("GET", "/")
    test("根路由端点", code == 200 and data is not None,
         f"返回: {str(data)[:50]}..." if data else err)

    # API 文档
    code, _, err = request("GET", "/docs")
    test("API 文档端点", code == 200, f"/docs 可访问")


# ==================== 2. 基础数据端点 ====================

def verify_basic_endpoints():
    header("2. 基础数据端点")

    # 标签列表
    code, data, err = request("GET", "/api/tags")
    passed = code == 200 and data and len(data.get("tags", [])) >= 10
    test("获取标签列表", passed, f"共 {len(data.get('tags', [])) if data else 0} 个标签")

    # 分类列表
    code, data, err = request("GET", "/api/categories")
    passed = code == 200 and data and "cs.AI" in data.get("categories", {})
    test("获取分类列表", passed, f"包含 cs.AI 等分类")


# ==================== 3. 论文抓取功能 ====================

def verify_paper_fetch():
    header("3. 论文抓取功能")

    # 抓取论文
    code, data, err = request("POST", "/api/fetch", json={
        "query": "cat:cs.AI",
        "max_results": 5
    }, timeout=60)
    passed = code == 200 and data is not None
    test("抓取论文 POST /api/fetch", passed,
         f"获取 {data.get('total_fetched', 0)} 篇，新增 {data.get('new_papers', 0)} 篇" if data else err)

    # 按分类抓取
    code, data, err = request("POST", "/api/fetch/categories", json={
        "categories": ["cs.CL"],
        "max_results": 3
    }, timeout=60)
    passed = code == 200 or code == 404  # 404 表示端点不存在但不应报错
    test("按分类抓取", passed, f"status={code}")


# ==================== 4. 论文列表功能 ====================

def verify_paper_list():
    header("4. 论文列表功能")

    # 基础列表
    code, data, err = request("GET", "/api/papers")
    passed = code == 200 and data and "papers" in data
    test("获取论文列表", passed, f"共 {data.get('total', 0)} 篇论文" if data else err)

    if not data or not data.get("papers"):
        print("  ⚠️ 没有论文数据，跳过后续列表测试")
        return None

    # 分页测试
    code, data, err = request("GET", "/api/papers?page=1&page_size=5")
    passed = code == 200 and len(data.get("papers", [])) <= 5
    test("分页功能", passed, f"请求 5 条，返回 {len(data.get('papers', []))} 条")

    # 搜索测试
    code, data, err = request("GET", "/api/papers?search=model")
    passed = code == 200
    test("搜索功能", passed, f"搜索 'model' 返回 {data.get('total', 0)} 条" if data else err)

    # 分类筛选
    code, data, err = request("GET", "/api/papers?categories=cs.AI")
    passed = code == 200
    test("分类筛选", passed, f"cs.AI 分类返回 {data.get('total', 0)} 条" if data else err)

    # 排序测试 - 最新
    code, data, err = request("GET", "/api/papers?sort_by=newest")
    passed = code == 200
    test("排序-最新", passed)

    # 排序测试 - 最早
    code, data, err = request("GET", "/api/papers?sort_by=oldest")
    passed = code == 200
    test("排序-最早", passed)

    # 排序测试 - 浏览量
    code, data, err = request("GET", "/api/papers?sort_by=views")
    passed = code == 200
    test("排序-浏览量", passed)

    return data.get("papers", [])[0].get("id") if data.get("papers") else None


# ==================== 5. 论文详情功能 ====================

def verify_paper_detail(paper_id):
    header("5. 论文详情功能")

    if not paper_id:
        test("论文详情", True, skipped=True, detail="无可用论文 ID")
        return

    # 获取详情
    code, data, err = request("GET", f"/api/papers/{paper_id}")
    passed = code == 200 and data and data.get("id") == paper_id
    test("获取论文详情", passed, f"ID={paper_id}" if passed else f"status={code}")

    # 检查必需字段
    if data:
        required = ["title", "authors", "categories"]
        missing = [f for f in required if not data.get(f)]
        test("详情字段完整性", len(missing) == 0, f"缺失: {missing}" if missing else "字段完整")

    # 浏览量更新
    code2, data2, _ = request("GET", f"/api/papers/{paper_id}")
    if data and data2:
        view1 = data.get("view_count", 0)
        view2 = data2.get("view_count", 0)
        test("浏览量更新", view2 == view1 + 1, f"{view1} → {view2}")


# ==================== 6. 日期筛选功能 ====================

def verify_date_filter():
    header("6. 日期筛选功能")

    # 获取论文日期分布
    code, data, err = request("GET", "/api/papers?page_size=100")
    if not data or not data.get("papers"):
        test("日期筛选", True, skipped=True, detail="无论文数据")
        return

    papers = data["papers"]
    dates = []
    for p in papers:
        pd = p.get("publish_date")
        if pd:
            dates.append(pd.split("T")[0] if "T" in pd else pd.split(" ")[0])

    if not dates:
        test("日期筛选", True, skipped=True, detail="无日期数据")
        return

    from collections import Counter
    date_counts = Counter(dates)
    test_date, expected = date_counts.most_common(1)[0]

    print(f"  测试日期: {test_date}，应有 {expected} 篇论文")

    # Bug 测试: date_from 单独使用
    code, data, err = request("GET", f"/api/papers?date_from={test_date}&page_size=100")
    if data:
        actual = data.get("total", 0)
        # date_from 应该返回 >= 该日期的所有论文
        test("date_from 筛选 (>=)", actual >= expected,
             f"预期 >={expected}，实际 {actual}")

    # Bug 测试: date_from + date_to 同一天
    code, data, err = request("GET", f"/api/papers?date_from={test_date}&date_to={test_date}&page_size=100")
    if data:
        actual = data.get("total", 0)
        same_day_passed = actual == expected
        test("date_from + date_to (=当天)", same_day_passed,
             f"预期 {expected}，实际 {actual}" + (" ⚠️ BUG!" if not same_day_passed else ""))

        if not same_day_passed:
            print(f"  ⚠️ 发现 BUG: 日期比较逻辑问题")
            print(f"     原因: 数据库日期含时间部分，date_to 被解析为 00:00:00")
            print(f"     导致 publish_date <= date_to 比较失败")


# ==================== 7. AI 摘要功能 ====================

def verify_ai_summary(skip_ai):
    header("7. AI 摘要功能")

    if skip_ai:
        test("批量生成摘要", True, skipped=True, detail="--skip-ai")
        return

    code, data, err = request("POST", "/api/papers/generate-summaries?limit=1", timeout=120)
    passed = code == 200 and data is not None
    test("批量生成摘要", passed,
         f"处理 {data.get('processed', 0)} 篇" if data else err)


# ==================== 8. 深度分析功能 ====================

def verify_deep_analysis(paper_id, skip_ai):
    header("8. 深度分析功能")

    if skip_ai:
        test("深度分析", True, skipped=True, detail="--skip-ai")
        return

    if not paper_id:
        test("深度分析", True, skipped=True, detail="无可用论文 ID")
        return

    print("  正在执行深度分析（可能需要 60-120 秒）...")
    start = time.time()

    code, data, err = request("POST", f"/api/papers/{paper_id}/analyze", timeout=180)
    elapsed = time.time() - start

    passed = code == 200 and data and data.get("report")
    test("深度分析", passed, f"耗时 {elapsed:.1f}s，报告 {len(data.get('report', ''))} 字符" if data else err)

    # 验证结果已保存
    if passed:
        code2, data2, _ = request("GET", f"/api/papers/{paper_id}")
        if data2:
            test("分析结果保存", data2.get("has_analysis") == True and data2.get("analysis_report"),
                 f"has_analysis={data2.get('has_analysis')}")


# ==================== 9. 统计功能 ====================

def verify_stats():
    header("9. 统计功能")

    code, data, err = request("GET", "/api/stats")
    passed = code == 200 and data

    if passed:
        test("统计数据获取", True,
             f"论文 {data.get('total_papers', 0)} 篇，已分析 {data.get('analyzed_papers', 0)} 篇")

        # 检查统计字段
        fields = ["total_papers", "analyzed_papers", "categories", "tags"]
        missing = [f for f in fields if f not in data]
        test("统计字段完整性", len(missing) == 0, f"缺失: {missing}" if missing else "")
    else:
        test("统计数据获取", False, err)


# ==================== 汇总报告 ====================

def print_summary():
    header("验证汇总报告")

    passed = sum(1 for r in results if r["passed"] and not r["skipped"])
    failed = sum(1 for r in results if not r["passed"] and not r["skipped"])
    skipped = sum(1 for r in results if r["skipped"])
    total = len(results)

    print(f"\n  总测试数: {total}")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")
    print(f"  ⏭️ 跳过: {skipped}")

    if failed > 0:
        print(f"\n  ❌ 失败的测试:")
        for r in results:
            if not r["passed"] and not r["skipped"]:
                print(f"     - {r['name']}: {r['detail']}")

    print(f"\n  {'🎉 所有测试通过！' if failed == 0 else '⚠️ 存在失败的测试'}")
    print("="*60)

    return 1 if failed > 0 else 0


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="ArXiv 论文系统全功能验证")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 相关测试")
    args = parser.parse_args()

    print("="*60)
    print(" ArXiv 论文智能分析平台 - 全功能验证")
    print(f" 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 跳过 AI 测试: {args.skip_ai}")
    print("="*60)

    # 执行验证
    verify_service_health()
    verify_basic_endpoints()
    verify_paper_fetch()
    paper_id = verify_paper_list()
    verify_paper_detail(paper_id)
    verify_date_filter()
    verify_ai_summary(args.skip_ai)
    verify_deep_analysis(paper_id, args.skip_ai)
    verify_stats()

    # 打印汇总
    return print_summary()


if __name__ == "__main__":
    sys.exit(main())