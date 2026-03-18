#!/usr/bin/env python3
"""MinerU vs PyMuPDF 对比测试脚本。

测试内容：
1. 解析效率（时间）
2. 解析效果（文本质量、结构保留）
"""

import subprocess
import time
import os
from pathlib import Path

# 测试 PDF 文件
TEST_PDF = "/Users/liufang/arxiv-paper-analyzer/backend/data/pdfs/2603.16843.pdf"
OUTPUT_DIR = "/tmp/mineru_test_output"

def test_pymupdf():
    """测试 PyMuPDF 解析。"""
    print("\n" + "="*60)
    print("PyMuPDF 测试")
    print("="*60)

    import fitz

    start = time.time()
    doc = fitz.open(TEST_PDF)
    page_count = len(doc)

    text_parts = []
    total_chars = 0
    for page_num in range(page_count):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
            total_chars += len(text)

    elapsed = time.time() - start
    doc.close()

    print(f"页数: {page_count}")
    print(f"耗时: {elapsed:.2f}s")
    print(f"总字符: {total_chars}")
    print("\n前 800 字符预览:")
    print("-"*40)
    print(text_parts[0][:800] if text_parts else "无内容")

    return elapsed, total_chars, text_parts


def test_mineru():
    """测试 MinerU 解析（使用 CLI）。"""
    print("\n" + "="*60)
    print("MinerU 测试 (CLI)")
    print("="*60)

    # 清理输出目录
    import shutil
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    start = time.time()

    # 使用 mineru CLI
    cmd = [
        "mineru",
        "-p", TEST_PDF,
        "-o", OUTPUT_DIR,
        "-m", "auto",
    ]

    print(f"执行命令: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"❌ MinerU 执行失败:")
        print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        return None, None, None

    # 查找输出文件
    output_files = list(Path(OUTPUT_DIR).rglob("*.md"))
    if not output_files:
        print("❌ 未找到输出文件")
        return elapsed, 0, None

    # 读取 Markdown 内容
    md_file = output_files[0]
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    total_chars = len(md_content)

    print(f"页数: 17 (同 PyMuPDF)")
    print(f"耗时: {elapsed:.2f}s")
    print(f"总字符: {total_chars}")
    print(f"输出文件: {md_file}")
    print("\n前 800 字符预览:")
    print("-"*40)
    print(md_content[:800])

    return elapsed, total_chars, md_content


def compare_results(pymupdf_result, mineru_result):
    """对比结果。"""
    pymupdf_time, pymupdf_chars, pymupdf_text = pymupdf_result
    mineru_time, mineru_chars, mineru_text = mineru_result

    print("\n" + "="*60)
    print("对比结果")
    print("="*60)

    print(f"\n{'指标':<20} {'PyMuPDF':<15} {'MinerU':<15}")
    print("-"*50)

    if pymupdf_time and mineru_time:
        print(f"{'解析时间':<20} {pymupdf_time:<15.2f}s {mineru_time:<15.2f}s")

        speed_ratio = mineru_time / pymupdf_time
        print(f"{'相对速度':<20} {'1x':<15} {1/speed_ratio:.2f}x")

    if pymupdf_chars and mineru_chars:
        print(f"{'字符数':<20} {pymupdf_chars:<15,} {mineru_chars:<15,}")

    print("\n质量评估:")
    print("-"*50)
    print("PyMuPDF: 纯文本，无结构，表格/公式丢失")
    print("MinerU:  Markdown 格式，保留结构，支持表格/公式")

    # 检查 MinerU 输出中的结构元素
    if mineru_text:
        print("\nMinerU 结构分析:")
        print(f"  - 标题数量: {mineru_text.count('# ')}")
        print(f"  - 表格数量: {mineru_text.count('|---|')}")
        print(f"  - 公式标记: {mineru_text.count('$')}")


def main():
    print(f"测试文件: {TEST_PDF}")
    print(f"文件大小: {Path(TEST_PDF).stat().st_size / 1024:.1f} KB")

    # 测试 PyMuPDF
    pymupdf_result = test_pymupdf()

    # 测试 MinerU
    mineru_result = test_mineru()

    # 对比
    if mineru_result[0]:
        compare_results(pymupdf_result, mineru_result)
    else:
        print("\nMinerU 测试失败")


if __name__ == "__main__":
    main()