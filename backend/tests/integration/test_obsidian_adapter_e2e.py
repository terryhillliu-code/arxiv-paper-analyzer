#!/usr/bin/env python3
"""
ObsidianAdapter 端到端测试

测试场景：
1. 创建模拟的 MinerU 输出（Markdown + 图片目录）
2. 调用 MarkdownGenerator 生成 Obsidian Markdown
3. 验证图片复制到 Assets/
4. 验证图片路径转换为 Obsidian 格式
"""

import sys
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

# 添加 backend 到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.obsidian_adapter import ObsidianAdapter
from app.outputs.markdown_generator import MarkdownGenerator


def test_end_to_end():
    """端到端测试：模拟 MinerU 输出到 Obsidian 导出"""

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 1. 模拟 Vault 目录结构
        vault_path = tmpdir / "TestVault"
        vault_path.mkdir()
        (vault_path / "Inbox").mkdir()
        (vault_path / "Assets").mkdir()

        # 2. 模拟 MinerU 输出
        images_dir = tmpdir / "mineru_output_images"
        images_dir.mkdir()

        # 创建模拟图片
        (images_dir / "figure1.png").write_bytes(b"fake png content 1")
        (images_dir / "figure2.jpg").write_bytes(b"fake jpg content")
        (images_dir / "diagram.svg").write_bytes(b"<svg>test</svg>")

        # 模拟 MinerU 生成的 Markdown（带图片语法）
        mineru_markdown = """# Test Paper

## Abstract

This is a test paper with images.

## Method

As shown in Figure 1:

![Method Overview](figure1.png)

And Figure 2 shows the results:

![Results Comparison](figure2.jpg)

The architecture is shown below:

<img src="diagram.svg" alt="Architecture">

## Conclusion

![Network URL](https://example.com/remote.png) should be skipped.
"""

        # 3. 测试 ObsidianAdapter
        print("=== 测试 ObsidianAdapter ===")
        adapter = ObsidianAdapter(vault_path)
        result, conversions = adapter.adapt_images(mineru_markdown, images_dir, arxiv_id="2404.12345")

        print(f"转换结果: {len(conversions)} 张图片")
        for c in conversions:
            status = "✅" if c.success else "❌"
            print(f"  {status} {c.original_path} → {c.new_path}")
            if c.error:
                print(f"      错误: {c.error}")

        # 验证
        assert len(conversions) == 3, f"预期 3 张图片，实际 {len(conversions)}"
        assert sum(1 for c in conversions if c.success) == 3, "所有图片应该成功"

        # 检查 Assets 目录
        assets_files = list((vault_path / "Assets").glob("*"))
        print(f"\nAssets 目录文件: {[f.name for f in assets_files]}")
        assert len(assets_files) == 3, f"Assets 应有 3 个文件，实际 {len(assets_files)}"

        # 检查路径转换
        assert "![[Assets/figure1.png|Method Overview]]" in result, "figure1 应转换为 Obsidian 格式"
        assert "![[Assets/figure2.jpg|Results Comparison]]" in result, "figure2 应转换为 Obsidian 格式"
        assert "![[Assets/diagram.svg]]" in result, "diagram 应转换为 Obsidian 格式"
        assert "https://example.com/remote.png" in result, "网络 URL 应保留原样"

        print("\n✅ ObsidianAdapter 测试通过")

        # 4. 测试 MarkdownGenerator
        print("\n=== 测试 MarkdownGenerator ===")
        generator = MarkdownGenerator(
            output_dir=str(vault_path / "Inbox"),
            attachments_dir=str(vault_path / "attachments"),
            prefer_service=False,  # 使用本地实现
        )
        generator.vault_path = vault_path  # 覆盖默认路径

        export_result = generator._local_generate_paper_md(
            paper_data={
                "title": "Test Paper with Images",
                "arxiv_id": "2404.12345",
                "arxiv_url": "https://arxiv.org/abs/2404.12345",
                "authors": ["Test Author"],
                "publish_date": "2024-04-01",
                "content_type": "paper",
            },
            analysis_json={
                "tier": "B",
                "tags": ["test"],
                "one_line_summary": "A test paper",
            },
            report=mineru_markdown,
            pdf_path=None,
            images_dir=str(images_dir),
        )

        print(f"导出结果: {export_result}")

        # 验证
        assert export_result.get("md_path"), "应有 md_path"
        assert export_result.get("images_copied", 0) == 3, f"应复制 3 张图片，实际 {export_result.get('images_copied')}"

        # 检查生成的 Markdown 文件
        md_path = Path(export_result["md_path"])
        assert md_path.exists(), f"Markdown 文件应存在: {md_path}"
        content = md_path.read_text()
        print(f"\n生成的 Markdown 文件: {md_path.name}")
        print(f"包含 Obsidian 图片链接: {'![[Assets/' in content}")

        assert "![[Assets/" in content, "Markdown 应包含 Obsidian 图片链接"

        print("\n✅ MarkdownGenerator 测试通过")

        # 5. 检查最终 Assets 目录
        final_assets = list((vault_path / "Assets").glob("*.*"))
        print(f"\n最终 Assets 目录: {len(final_assets)} 个文件")
        for f in final_assets:
            print(f"  - {f.name}")

        return True


def test_filename_conflict():
    """测试文件名冲突处理"""

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        vault_path = tmpdir / "Vault"
        vault_path.mkdir()
        assets_path = vault_path / "Assets"
        assets_path.mkdir()

        images_dir = tmpdir / "images"
        images_dir.mkdir()
        (images_dir / "test.png").write_bytes(b"content")

        adapter = ObsidianAdapter(vault_path)

        # 第一次复制
        content1 = "![Test](test.png)"
        result1, conv1 = adapter.adapt_images(content1, images_dir)
        assert conv1[0].filename == "test.png"

        # 第二次复制（同文件名）
        content2 = "![Test Again](test.png)"
        result2, conv2 = adapter.adapt_images(content2, images_dir)
        assert conv2[0].filename == "test_1.png", f"应为 test_1.png，实际 {conv2[0].filename}"

        # 第三次复制
        content3 = "![Test Third](test.png)"
        result3, conv3 = adapter.adapt_images(content3, images_dir)
        assert conv3[0].filename == "test_2.png", f"应为 test_2.png，实际 {conv3[0].filename}"

        print("✅ 文件名冲突测试通过")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("ObsidianAdapter 端到端测试")
    print("=" * 60)

    try:
        test_end_to_end()
        print("\n" + "=" * 60)
        test_filename_conflict()
        print("=" * 60)
        print("\n🎉 所有测试通过！")
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)