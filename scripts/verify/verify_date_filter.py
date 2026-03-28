#!/usr/bin/env python3
"""
日期筛选功能验证脚本

诊断问题：
1. 数据库中论文的日期分布
2. 日期筛选参数的实际行为
3. 前端只有一个 date_from，缺少 date_to

使用方法：
    python verify_date_filter.py
"""

import httpx
from datetime import datetime, timedelta
from collections import Counter

BASE_URL = "http://localhost:8000"

def print_header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

def print_result(passed, message):
    status = "✅" if passed else "❌"
    print(f"  {status} {message}")

def main():
    print("\n🔍 ArXiv 论文系统 - 日期筛选验证")

    with httpx.Client(timeout=30) as client:
        # 1. 检查服务
        print_header("1. 服务状态检查")
        try:
            resp = client.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                print_result(True, "后端服务运行正常")
            else:
                print_result(False, f"后端服务异常: {resp.status_code}")
                return
        except Exception as e:
            print_result(False, f"无法连接后端: {e}")
            return

        # 2. 获取所有论文的日期分布
        print_header("2. 论文日期分布分析")
        try:
            resp = client.get(f"{BASE_URL}/api/papers", params={"page_size": 100})
            if resp.status_code != 200:
                print_result(False, "获取论文列表失败")
                return

            data = resp.json()
            papers = data.get("papers", [])
            total = data.get("total", 0)

            print(f"  论文总数: {total}")
            print(f"  本次检查: {len(papers)} 篇")

            # 统计日期
            dates = []
            none_dates = 0
            for p in papers:
                pd = p.get("publish_date")
                if pd:
                    # 只取日期部分
                    date_str = pd.split("T")[0] if "T" in pd else pd
                    dates.append(date_str)
                else:
                    none_dates += 1

            date_counts = Counter(dates)

            print(f"  有日期的论文: {len(dates)} 篇")
            print(f"  无日期的论文: {none_dates} 篇")

            if date_counts:
                print(f"\n  日期分布 (Top 10):")
                for date, count in date_counts.most_common(10):
                    print(f"    {date}: {count} 篇")

                # 检查今天的论文
                today = datetime.now().strftime("%Y-%m-%d")
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

                print(f"\n  今天 ({today}): {date_counts.get(today, 0)} 篇")
                print(f"  昨天 ({yesterday}): {date_counts.get(yesterday, 0)} 篇")

        except Exception as e:
            print_result(False, f"分析失败: {e}")
            return

        # 3. 测试日期筛选功能
        print_header("3. 日期筛选功能测试")

        if not date_counts:
            print("  ⚠️ 没有足够数据进行测试")
            return

        # 取一个有论文的日期
        test_date = date_counts.most_common(1)[0][0]
        expected_count = date_counts[test_date]

        print(f"\n  测试日期: {test_date}")
        print(f"  该日期应有论文: {expected_count} 篇")

        # 测试 1: 只传 date_from
        print(f"\n  测试 A: 只传 date_from={test_date}")
        try:
            resp = client.get(f"{BASE_URL}/api/papers", params={
                "date_from": test_date,
                "page_size": 100
            })
            if resp.status_code == 200:
                result = resp.json()
                actual_count = result.get("total", 0)
                print(f"    返回论文数: {actual_count} 篇")

                # 检查返回的论文日期
                papers = result.get("papers", [])
                returned_dates = set()
                for p in papers:
                    pd = p.get("publish_date")
                    if pd:
                        returned_dates.add(pd.split("T")[0] if "T" in pd else pd)

                print(f"    返回的日期范围: {sorted(returned_dates)}")

                # 问题：date_from 是 >=，所以会包含该日期及之后的所有论文
                if len(returned_dates) > 1:
                    print(f"    ⚠️ 注意: date_from 筛选的是 >= 该日期，不是 = 该日期")
                    print(f"    ⚠️ 如需筛选当天，需要同时传 date_from 和 date_to")
            else:
                print_result(False, f"请求失败: {resp.status_code}")
        except Exception as e:
            print_result(False, f"测试失败: {e}")

        # 测试 2: 传 date_from 和 date_to（当天）
        print(f"\n  测试 B: date_from={test_date}&date_to={test_date}")
        try:
            resp = client.get(f"{BASE_URL}/api/papers", params={
                "date_from": test_date,
                "date_to": test_date,
                "page_size": 100
            })
            if resp.status_code == 200:
                result = resp.json()
                actual_count = result.get("total", 0)
                print(f"    返回论文数: {actual_count} 篇")

                papers = result.get("papers", [])
                returned_dates = set()
                for p in papers:
                    pd = p.get("publish_date")
                    if pd:
                        returned_dates.add(pd.split("T")[0] if "T" in pd else pd)

                print(f"    返回的日期: {sorted(returned_dates)}")

                if actual_count == expected_count:
                    print_result(True, "date_from + date_to 可以正确筛选当天")
                else:
                    print(f"    ⚠️ 预期 {expected_count} 篇，实际 {actual_count} 篇")
            else:
                print_result(False, f"请求失败: {resp.status_code}")
        except Exception as e:
            print_result(False, f"测试失败: {e}")

        # 4. 问题诊断
        print_header("4. 问题诊断报告")

        print("""
  🔍 发现的问题:

  1. 前端只有一个日期选择器 (date_from)
     - 后端支持 date_from 和 date_to 两个参数
     - 前端缺少 date_to 选择器

  2. 筛选行为不符合预期
     - date_from 筛选的是 >= 该日期 (从该日期到现在的所有文章)
     - 用户期望: 选择某日期 = 显示该日期的文章
     - 实际行为: 选择某日期 = 显示该日期及之后的所有文章

  📋 建议修复方案:

  方案 A: 添加 date_to 选择器
     - 前端增加"结束日期"选择器
     - 用户可以选择日期范围

  方案 B: 快捷日期按钮
     - 添加"今天"、"昨天"、"本周"、"本月"等快捷按钮
     - 自动设置 date_from 和 date_to

  方案 C: 改变筛选逻辑
     - 单选日期时，自动设置 date_from = date_to
     - 或者改为"发布日期"精确匹配
""")

        print("\n" + "="*60)

if __name__ == "__main__":
    main()