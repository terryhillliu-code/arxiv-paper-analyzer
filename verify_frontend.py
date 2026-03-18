#!/usr/bin/env python3
"""
前端功能验证脚本
用于自动化测试 ArXiv 论文分析平台前端各项功能

使用方法：python3 verify_frontend.py
"""

import httpx
from collections import Counter

# 配置
FRONTEND_URL = "http://localhost:5173"
BACKEND_URL = "http://localhost:8000"
TIMEOUT = 10

# 颜色输出
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(title):
    """打印标题"""
    print(f"\n{BOLD}{BLUE}{'=' * 50}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 50}{RESET}\n")


def print_result(passed, message):
    """打印测试结果"""
    status = f"{GREEN}✅{RESET}" if passed else f"{RED}❌{RESET}"
    print(f"  {status} {message}")


def check_frontend_service(client):
    """检查前端服务是否运行"""
    print_header("1. 前端服务检查")

    try:
        response = client.get(FRONTEND_URL, follow_redirects=True)
        if response.status_code == 200:
            print_result(True, f"前端服务运行正常 ({FRONTEND_URL})")
            return True
        else:
            print_result(False, f"前端服务返回状态码: {response.status_code}")
            return False
    except httpx.ConnectError:
        print_result(False, f"无法连接前端服务 ({FRONTEND_URL})")
        return False
    except Exception as e:
        print_result(False, f"前端服务检查失败: {e}")
        return False


def check_backend_apis(client):
    """检查后端 API 连通性"""
    print_header("2. 后端 API 连通性检查")

    endpoints = [
        ("/health", "健康检查"),
        ("/api/papers", "论文列表"),
        ("/api/stats", "统计数据"),
        ("/api/tags", "标签列表"),
        ("/api/categories", "分类列表"),
    ]

    all_passed = True

    for endpoint, name in endpoints:
        try:
            response = client.get(f"{BACKEND_URL}{endpoint}")
            if response.status_code == 200:
                print_result(True, f"GET {endpoint} - {name}")
            else:
                print_result(False, f"GET {endpoint} - 返回 {response.status_code}")
                all_passed = False
        except httpx.ConnectError:
            print_result(False, f"GET {endpoint} - 无法连接")
            all_passed = False
        except Exception as e:
            print_result(False, f"GET {endpoint} - 错误: {e}")
            all_passed = False

    return all_passed


def check_paper_data_integrity(client):
    """检查论文数据完整性"""
    print_header("3. 论文数据完整性检查")

    try:
        # 获取论文列表
        response = client.get(f"{BACKEND_URL}/api/papers", params={"page_size": 100})
        if response.status_code != 200:
            print_result(False, "无法获取论文列表")
            return None

        data = response.json()
        papers = data.get("papers", [])
        total = data.get("total", 0)

        print(f"  论文总数: {total}")

        if not papers:
            print_result(False, "论文列表为空")
            return None

        # 必需字段检查
        required_fields = ["id", "arxiv_id", "title", "authors", "categories"]

        papers_with_summary = 0
        papers_with_tags = 0
        papers_with_analysis = 0
        category_counts = Counter()
        tag_counts = Counter()
        missing_fields = []

        for paper in papers:
            # 检查必需字段
            for field in required_fields:
                if field not in paper or paper[field] is None:
                    missing_fields.append(f"论文 {paper.get('id', '?')} 缺少字段: {field}")

            # 统计摘要
            if paper.get("summary"):
                papers_with_summary += 1

            # 统计标签
            tags = paper.get("tags", [])
            if tags and len(tags) > 0:
                papers_with_tags += 1
                for tag in tags:
                    tag_counts[tag] += 1

            # 统计分析状态
            if paper.get("has_analysis"):
                papers_with_analysis += 1

            # 统计分类
            categories = paper.get("categories", [])
            for cat in categories:
                category_counts[cat] += 1

        # 打印结果
        if missing_fields:
            print_result(False, f"发现 {len(missing_fields)} 个字段缺失问题")
            for msg in missing_fields[:5]:  # 只显示前5个
                print(f"       {YELLOW}⚠{RESET} {msg}")
        else:
            print_result(True, f"所有论文必需字段完整 (检查了 {len(papers)} 篇)")

        print_result(True, f"有摘要的论文: {papers_with_summary}/{len(papers)}")
        print_result(True, f"有标签的论文: {papers_with_tags}/{len(papers)}")
        print_result(True, f"已分析的论文: {papers_with_analysis}/{len(papers)}")

        return {
            "total": total,
            "checked": len(papers),
            "papers_with_summary": papers_with_summary,
            "papers_with_tags": papers_with_tags,
            "papers_with_analysis": papers_with_analysis,
            "category_counts": category_counts,
            "tag_counts": tag_counts,
        }

    except Exception as e:
        print_result(False, f"数据完整性检查失败: {e}")
        return None


def check_paper_detail(client, paper_id):
    """检查详情页数据"""
    print_header("4. 论文详情数据检查")

    try:
        response = client.get(f"{BACKEND_URL}/api/papers/{paper_id}")
        if response.status_code != 200:
            print_result(False, f"获取论文详情失败，状态码: {response.status_code}")
            return None

        paper = response.json()

        # 检查详情页字段
        detail_fields = [
            "id", "arxiv_id", "title", "authors", "categories",
            "publish_date", "arxiv_url", "pdf_url", "summary"
        ]

        missing = []
        for field in detail_fields:
            if field not in paper or paper[field] is None:
                missing.append(field)

        if missing:
            print_result(False, f"详情页缺少字段: {', '.join(missing)}")
        else:
            print_result(True, f"详情页字段完整 (论文 ID: {paper_id})")

        # 显示详情信息
        print(f"\n  论文标题: {paper.get('title', 'N/A')[:60]}...")
        print(f"  作者数量: {len(paper.get('authors', []))}")
        print(f"  分类: {', '.join(paper.get('categories', []))}")
        print(f"  有摘要: {'是' if paper.get('summary') else '否'}")
        print(f"  已分析: {'是' if paper.get('has_analysis') else '否'}")

        return paper

    except Exception as e:
        print_result(False, f"详情页检查失败: {e}")
        return None


def print_verification_report(frontend_ok, backend_ok, paper_stats):
    """打印验证报告"""
    print_header("5. 验证报告")

    # 服务状态
    print(f"{BOLD}服务状态:{RESET}")
    print(f"  前端服务: {GREEN}正常{RESET}" if frontend_ok else f"  前端服务: {RED}异常{RESET}")
    print(f"  后端服务: {GREEN}正常{RESET}" if backend_ok else f"  后端服务: {RED}异常{RESET}")

    if not paper_stats:
        print(f"\n{YELLOW}无法生成完整报告，论文数据获取失败{RESET}")
        return

    # 论文统计
    print(f"\n{BOLD}论文统计:{RESET}")
    print(f"  论文总数: {paper_stats['total']}")
    print(f"  本次检查: {paper_stats['checked']} 篇")
    print(f"  有摘要: {paper_stats['papers_with_summary']} 篇")
    print(f"  有标签: {paper_stats['papers_with_tags']} 篇")
    print(f"  已分析: {paper_stats['papers_with_analysis']} 篇")

    # 分类统计
    if paper_stats["category_counts"]:
        print(f"\n{BOLD}分类统计 (Top 10):{RESET}")
        for cat, count in paper_stats["category_counts"].most_common(10):
            print(f"  {cat}: {count} 篇")

    # 标签统计
    if paper_stats["tag_counts"]:
        print(f"\n{BOLD}标签统计 (Top 10):{RESET}")
        for tag, count in paper_stats["tag_counts"].most_common(10):
            print(f"  {tag}: {count} 篇")

    # 总体评估
    print(f"\n{BOLD}总体评估:{RESET}")
    issues = []

    if not frontend_ok:
        issues.append("前端服务异常")
    if not backend_ok:
        issues.append("后端服务异常")
    if paper_stats["papers_with_summary"] < paper_stats["checked"] * 0.5:
        issues.append("摘要覆盖率低于50%")
    if paper_stats["papers_with_analysis"] == 0:
        issues.append("暂无已分析论文")

    if issues:
        print(f"  {YELLOW}发现问题:{RESET}")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print(f"  {GREEN}系统运行正常，各项指标良好{RESET}")


def main():
    """主函数"""
    print(f"\n{BOLD}ArXiv 论文分析平台 - 前端功能验证{RESET}")
    print(f"时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 创建 HTTP 客户端
    with httpx.Client(timeout=TIMEOUT) as client:
        # 1. 检查前端服务
        frontend_ok = check_frontend_service(client)

        # 2. 检查后端 API
        backend_ok = check_backend_apis(client)

        # 3. 检查论文数据完整性
        paper_stats = check_paper_data_integrity(client)

        # 4. 检查详情页数据
        if paper_stats and paper_stats.get("total", 0) > 0:
            # 获取第一篇论文的 ID
            response = client.get(f"{BACKEND_URL}/api/papers", params={"page_size": 1})
            if response.status_code == 200:
                papers = response.json().get("papers", [])
                if papers:
                    check_paper_detail(client, papers[0]["id"])

        # 5. 打印验证报告
        print_verification_report(frontend_ok, backend_ok, paper_stats)

    print(f"\n{BOLD}{BLUE}{'=' * 50}{RESET}")
    print(f"{BOLD}验证完成{RESET}\n")


if __name__ == "__main__":
    main()