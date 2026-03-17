#!/usr/bin/env python3
"""
后端 API 测试脚本
测试 ArXiv 论文分析系统的核心流程
"""

import httpx

BASE_URL = "http://localhost:8000"


def test_health():
    """测试健康检查端点"""
    print("\n" + "=" * 50)
    print("1. 测试健康检查 GET /health")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            response = client.get(f"{BASE_URL}/health", timeout=10)
            print(f"状态码: {response.status_code}")
            print(f"返回数据: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"请求失败: {e}")
            return False


def test_fetch_papers():
    """测试抓取论文"""
    print("\n" + "=" * 50)
    print("2. 测试抓取论文 POST /api/fetch")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            payload = {
                "query": "cat:cs.AI",
                "max_results": 5
            }
            print(f"请求参数: {payload}")
            response = client.post(
                f"{BASE_URL}/api/fetch",
                json=payload,
                timeout=60  # 抓取可能需要较长时间
            )
            print(f"状态码: {response.status_code}")
            data = response.json()
            print(f"抓取数量: {data.get('fetched_count', 0)}")
            print(f"消息: {data.get('message', '')}")
            return response.status_code == 200, data
        except Exception as e:
            print(f"请求失败: {e}")
            return False, None


def test_get_papers():
    """测试获取论文列表"""
    print("\n" + "=" * 50)
    print("3. 测试获取论文列表 GET /api/papers")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            response = client.get(
                f"{BASE_URL}/api/papers",
                params={"page": 1, "page_size": 10},
                timeout=30
            )
            print(f"状态码: {response.status_code}")
            data = response.json()
            print(f"总数: {data.get('total', 0)}")
            print(f"页数: {data.get('pages', 0)}")
            print(f"当前页: {data.get('page', 0)}")

            items = data.get('items', [])
            print(f"返回论文数: {len(items)}")
            if items:
                print(f"第一篇论文: {items[0].get('title', 'N/A')[:50]}...")

            return response.status_code == 200, items
        except Exception as e:
            print(f"请求失败: {e}")
            return False, []


def test_get_stats():
    """测试获取统计信息"""
    print("\n" + "=" * 50)
    print("4. 测试获取统计信息 GET /api/stats")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            response = client.get(f"{BASE_URL}/api/stats", timeout=10)
            print(f"状态码: {response.status_code}")
            data = response.json()
            print(f"论文总数: {data.get('total_papers', 0)}")
            print(f"已分析数: {data.get('analyzed_papers', 0)}")
            print(f"近7天新增: {data.get('recent_papers', 0)}")
            print(f"分类数: {data.get('category_count', 0)}")
            return response.status_code == 200
        except Exception as e:
            print(f"请求失败: {e}")
            return False


def test_get_tags():
    """测试获取标签列表"""
    print("\n" + "=" * 50)
    print("5. 测试获取标签列表 GET /api/tags")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            response = client.get(f"{BASE_URL}/api/tags", timeout=10)
            print(f"状态码: {response.status_code}")
            data = response.json()
            tags = data.get('tags', [])
            print(f"标签数量: {len(tags)}")
            if tags:
                print(f"前5个标签: {tags[:5]}")
            return response.status_code == 200
        except Exception as e:
            print(f"请求失败: {e}")
            return False


def test_get_categories():
    """测试获取分类列表"""
    print("\n" + "=" * 50)
    print("5b. 测试获取分类列表 GET /api/categories")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            response = client.get(f"{BASE_URL}/api/categories", timeout=10)
            print(f"状态码: {response.status_code}")
            data = response.json()
            categories = data.get('categories', [])
            print(f"分类数量: {len(categories)}")
            if categories:
                print(f"分类列表: {categories}")
            return response.status_code == 200
        except Exception as e:
            print(f"请求失败: {e}")
            return False


def test_paper_detail(paper_id):
    """测试获取论文详情"""
    print("\n" + "=" * 50)
    print(f"6. 测试获取论文详情 GET /api/papers/{paper_id}")
    print("=" * 50)

    with httpx.Client() as client:
        try:
            response = client.get(f"{BASE_URL}/api/papers/{paper_id}", timeout=10)
            print(f"状态码: {response.status_code}")
            data = response.json()
            print(f"标题: {data.get('title', 'N/A')}")
            print(f"作者: {', '.join(data.get('authors', [])[:3])}...")
            print(f"分类: {data.get('categories', [])}")
            print(f"标签: {data.get('tags', [])}")
            print(f"已分析: {data.get('has_deep_analysis', False)}")
            return response.status_code == 200
        except Exception as e:
            print(f"请求失败: {e}")
            return False


def main():
    """运行所有测试"""
    print("=" * 50)
    print("ArXiv 论文分析系统 API 测试")
    print(f"目标服务器: {BASE_URL}")
    print("=" * 50)

    results = []

    # 1. 健康检查
    results.append(("健康检查", test_health()))

    # 2. 抓取论文
    success, fetch_data = test_fetch_papers()
    results.append(("抓取论文", success))

    # 3. 获取论文列表
    success, papers = test_get_papers()
    results.append(("获取论文列表", success))

    # 4. 获取统计信息
    results.append(("获取统计信息", test_get_stats()))

    # 5. 获取标签和分类
    results.append(("获取标签列表", test_get_tags()))
    results.append(("获取分类列表", test_get_categories()))

    # 6. 获取论文详情（如果有论文）
    if papers:
        paper_id = papers[0].get('id')
        if paper_id:
            results.append(("获取论文详情", test_paper_detail(paper_id)))
    else:
        print("\n" + "=" * 50)
        print("6. 跳过论文详情测试（没有论文数据）")
        print("=" * 50)

    # 打印测试结果汇总
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")

    passed = sum(1 for _, s in results if s)
    total = len(results)
    print(f"\n总计: {passed}/{total} 测试通过")

    return passed == total


if __name__ == "__main__":
    main()