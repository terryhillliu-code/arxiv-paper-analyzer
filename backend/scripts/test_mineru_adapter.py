#!/usr/bin/env python3
"""
MinerU + ObsidianAdapter 集成测试

手动测试流程：
1. 选择一个 PDF
2. 用 MinerU 解析（提取图片）
3. 用 ObsidianAdapter 处理图片
4. 验证结果
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.pdf_service import pdf_service
from app.adapters.obsidian_adapter import ObsidianAdapter


async def test_mineru_with_images():
    """测试 MinerU 提取图片 + ObsidianAdapter 处理"""

    # 选择一个 PDF
    pdf_path = Path.home() / "arxiv-paper-analyzer/backend/data/pdfs/2603.01253.pdf"

    if not pdf_path.exists():
        print(f"❌ PDF 不存在: {pdf_path}")
        return False

    print(f"PDF: {pdf_path}")
    print(f"大小: {pdf_path.stat().st_size / 1024 / 1024:.1f} MB")

    # 1. 用 MinerU 解析
    print("\n=== Step 1: MinerU 解析 ===")
    try:
        markdown, metadata = await pdf_service.extract_markdown(str(pdf_path))
        print(f"✅ 解析成功")
        print(f"   Markdown 长度: {len(markdown)} 字符")
        print(f"   元数据: {metadata}")
    except Exception as e:
        print(f"❌ MinerU 解析失败: {e}")
        return False

    # 检查是否有图片
    images_dir = metadata.get("images_dir")
    if images_dir:
        images_path = Path(images_dir)
        if images_path.exists():
            images = list(images_path.glob("*"))
            print(f"   图片目录: {images_path}")
            print(f"   图片数量: {len(images)}")
            for img in images[:5]:
                print(f"      - {img.name}")
        else:
            print(f"   ⚠️ 图片目录不存在: {images_path}")
    else:
        print("   ⚠️ 没有提取到图片")

    # 检查 Markdown 中的图片语法
    import re
    image_patterns = re.findall(r'!\[.*?\]\([^)]+\)', markdown)
    print(f"\n   Markdown 图片语法: {len(image_patterns)} 个")
    for p in image_patterns[:5]:
        print(f"      {p[:60]}...")

    # 2. 用 ObsidianAdapter 处理
    print("\n=== Step 2: ObsidianAdapter 处理 ===")
    vault_path = Path.home() / "Documents/ZhiweiVault"

    adapter = ObsidianAdapter(vault_path)

    result, conversions = adapter.adapt_images(
        markdown,
        Path(images_dir) if images_dir else None,
        arxiv_id="2603.01253"
    )

    print(f"转换结果: {len(conversions)} 张图片")
    for c in conversions:
        status = "✅" if c.success else "❌"
        print(f"  {status} {c.original_path} → {c.new_path}")
        if c.error:
            print(f"      错误: {c.error}")

    # 检查 Assets 目录
    assets_files = list((vault_path / "Assets").glob("2603.01253/*.*"))
    print(f"\nAssets/2603.01253/ 目录: {len(assets_files)} 个文件")

    # 3. 验证结果
    print("\n=== Step 3: 验证 ===")

    # 检查转换后的 Markdown
    if "![[Assets/" in result:
        print("✅ Markdown 包含 Obsidian 图片链接")
    else:
        print("⚠️ Markdown 不包含 Obsidian 图片链接")

    # 检查网络 URL 是否保留
    if "http" in markdown and "http" in result:
        print("✅ 网络 URL 保留原样")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("MinerU + ObsidianAdapter 集成测试")
    print("=" * 60)

    asyncio.run(test_mineru_with_images())