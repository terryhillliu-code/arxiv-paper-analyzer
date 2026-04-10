"""
ObsidianAdapter 单元测试
"""

import pytest
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from app.adapters.obsidian_adapter import ObsidianAdapter, ImageConversion


class TestObsidianAdapter:
    """ObsidianAdapter 测试"""

    @pytest.fixture
    def setup_vault(self):
        """创建临时 Vault 目录"""
        with TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir) / "TestVault"
            vault_path.mkdir(parents=True)

            # 创建 Assets 目录
            assets_path = vault_path / "Assets"
            assets_path.mkdir()

            # 创建测试图片目录
            images_path = Path(tmpdir) / "images"
            images_path.mkdir()

            # 创建测试图片文件
            (images_path / "fig1.png").write_bytes(b"fake png content 1")
            (images_path / "fig2.jpg").write_bytes(b"fake jpg content")
            (images_path / "diagram.svg").write_bytes(b"<svg>fake svg</svg>")

            yield {
                "vault_path": vault_path,
                "assets_path": assets_path,
                "images_path": images_path,
            }

    def test_standard_markdown_image(self, setup_vault):
        """标准 Markdown 图片语法转换"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = "![Figure 1](images/fig1.png)"

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"]
        )

        assert len(conversions) == 1
        assert conversions[0].success
        # 注意：有 alt 文本时格式为 ![[path|alt]]
        assert "[[Assets/fig1.png|Figure 1]]" in result

    def test_standard_with_alt_text(self, setup_vault):
        """带 alt 文本的图片转换"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = "![这是一张图片](fig1.png)"

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"]
        )

        assert len(conversions) == 1
        assert conversions[0].success
        assert "[[Assets/fig1.png|这是一张图片]]" in result

    def test_obsidian_format_passthrough(self, setup_vault):
        """已是 Obsidian 格式，不重复处理"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])

        # 预先放入一个图片
        existing = setup_vault["assets_path"] / "existing.png"
        existing.write_bytes(b"existing content")

        content = "![[Assets/existing.png]]"

        result, conversions = adapter.adapt_images(content, None)

        # Obsidian 格式不触发转换
        assert len(conversions) == 0
        assert content in result

    def test_html_img_tag(self, setup_vault):
        """HTML img 标签转换"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = '<img src="fig2.jpg" alt="diagram">'

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"]
        )

        assert len(conversions) == 1
        assert conversions[0].success
        assert "[[Assets/fig2.jpg]]" in result

    def test_network_url_skipped(self, setup_vault):
        """网络 URL 跳过处理"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = "![Online](https://example.com/image.png)"

        result, conversions = adapter.adapt_images(content, None)

        assert len(conversions) == 0
        assert content in result

    def test_filename_conflict(self, setup_vault):
        """文件名冲突处理"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])

        # 先复制一次
        content1 = "![Figure 1](fig1.png)"
        adapter.adapt_images(content1, setup_vault["images_path"])

        # 再复制一次，应该生成 fig1_1.png
        content2 = "![Figure 1 again](fig1.png)"
        result, conversions = adapter.adapt_images(
            content2, setup_vault["images_path"]
        )

        assert len(conversions) == 1
        assert conversions[0].success
        assert "fig1_1.png" in conversions[0].filename

    def test_missing_image_directory(self, setup_vault):
        """图片目录不存在时正常降级"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = "![Figure 1](fig1.png)"

        # 传入不存在的目录
        result, conversions = adapter.adapt_images(
            content, Path("/nonexistent/path")
        )

        # 目录不存在时返回原内容
        assert len(conversions) == 0
        assert content in result

    def test_missing_image_file(self, setup_vault):
        """图片文件不存在时记录错误"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = "![Missing](nonexistent.png)"

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"]
        )

        assert len(conversions) == 1
        assert not conversions[0].success
        assert "不存在" in conversions[0].error
        assert content in result  # 原样保留

    def test_unsupported_format(self, setup_vault):
        """不支持的图片格式"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = "![Document](document.pdf)"  # PDF 不是图片

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"]
        )

        # 应该没有转换（PDF 不在支持列表中）
        # 但如果 PDF 文件存在，会尝试转换并失败
        # 这里测试没有这个文件的情况
        assert len(conversions) == 1
        assert not conversions[0].success or "pdf" in conversions[0].error.lower()

    def test_multiple_images(self, setup_vault):
        """多图片转换"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])
        content = """
# Document

![Figure 1](fig1.png)

Some text here.

![Figure 2](fig2.jpg)

And a diagram:

<img src="diagram.svg">
"""

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"]
        )

        assert len(conversions) == 3
        assert all(c.success for c in conversions)
        # 注意：有 alt 文本时格式为 ![[path|alt]]
        assert "[[Assets/fig1.png|Figure 1]]" in result
        assert "[[Assets/fig2.jpg|Figure 2]]" in result
        assert "[[Assets/diagram.svg]]" in result

    def test_preserve_structure(self, setup_vault):
        """保留目录结构"""
        adapter = ObsidianAdapter(
            setup_vault["vault_path"], preserve_structure=True
        )
        content = "![Figure 1](fig1.png)"

        result, conversions = adapter.adapt_images(
            content, setup_vault["images_path"], arxiv_id="2301.12345"
        )

        assert len(conversions) == 1
        assert conversions[0].success
        assert "2301.12345" in conversions[0].new_path

    def test_get_stats(self, setup_vault):
        """统计信息"""
        adapter = ObsidianAdapter(setup_vault["vault_path"])

        # 复制一些图片
        content = "![Fig](fig1.png) and ![Fig2](fig2.jpg)"
        adapter.adapt_images(content, setup_vault["images_path"])

        stats = adapter.get_stats()

        assert stats["total"] == 2
        assert ".png" in stats["by_extension"]
        assert ".jpg" in stats["by_extension"]


class TestImageConversion:
    """ImageConversion 测试"""

    def test_success_conversion(self):
        """成功转换"""
        conv = ImageConversion(
            original_path="images/fig1.png",
            new_path="Assets/fig1.png",
            filename="fig1.png",
            success=True,
        )

        assert conv.success
        assert conv.error is None

    def test_failed_conversion(self):
        """失败转换"""
        conv = ImageConversion(
            original_path="missing.png",
            new_path="",
            filename="",
            success=False,
            error="文件不存在",
        )

        assert not conv.success
        assert conv.error == "文件不存在"