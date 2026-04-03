#!/usr/bin/env python3
"""
清理 Vault 重复论文

自动处理检测到的重复论文，保留最优版本，其他移到备份目录。

策略：
1. 保留 Inbox 中的版本（如果存在）
2. 如果不在 Inbox，保留最新修改的版本
3. 其他版本移动到 .duplicate_cleanup_backup 目录

用法:
    # 干运行（预览）
    python scripts/cleanup_duplicates.py --dry-run

    # 执行清理
    python scripts/cleanup_duplicates.py
"""

import argparse
import json
import logging
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_VAULT_ROOT = Path("~/Documents/ZhiweiVault").expanduser()
BACKUP_DIR = ".duplicate_cleanup_backup"

# 排除目录
EXCLUDE_DIRS = {".obsidian", "attachments", "extracted", "backup", ".duplicate_archive_backup", BACKUP_DIR}


def extract_arxiv_id(filepath: Path) -> str | None:
    """从文件提取 arxiv_id"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048)

        if content.startswith("---"):
            yaml_end = content.find("---", 3)
            if yaml_end > 0:
                yaml_content = content[3:yaml_end]
                patterns = [
                    r"arxiv_id:\s*['\"]?([^'\"\n]+)['\"]?",
                    r"source_url:\s*['\"]?https://arxiv\.org/abs/([^'\"\n]+)['\"]?",
                ]
                for pattern in patterns:
                    match = re.search(pattern, yaml_content)
                    if match:
                        return match.group(1).strip()

        arxiv_url_match = re.search(r"https://arxiv\.org/abs/(\d{4}\.\d{4,5}|[a-z-]+/\d+)", content)
        if arxiv_url_match:
            return arxiv_url_match.group(1)

    except Exception:
        pass

    return None


def scan_vault_duplicates(vault_root: Path) -> Dict[str, List[Tuple[Path, float]]]:
    """扫描 Vault 中的重复论文

    Returns:
        {arxiv_id: [(filepath, mtime), ...]} 重复项字典（按修改时间排序）
    """
    logger.info(f"扫描 Vault: {vault_root}")

    by_arxiv_id: Dict[str, List[Tuple[Path, float]]] = defaultdict(list)

    for md_file in vault_root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in md_file.parts):
            continue

        if not md_file.name.startswith("PAPER_"):
            continue

        arxiv_id = extract_arxiv_id(md_file)
        if arxiv_id:
            mtime = md_file.stat().st_mtime
            by_arxiv_id[arxiv_id].append((md_file, mtime))

    # 找出重复项
    duplicates = {
        arxiv_id: sorted(paths, key=lambda x: x[1], reverse=True)  # 按修改时间降序
        for arxiv_id, paths in by_arxiv_id.items()
        if len(paths) > 1
    }

    return duplicates


def select_version_to_keep(paths: List[Tuple[Path, float]]) -> Path:
    """选择要保留的版本

    策略：
    1. 优先保留 Inbox 中的版本
    2. 否则保留最新修改的版本
    """
    # 检查是否有 Inbox 版本
    for path, _ in paths:
        if "Inbox" in path.parts:
            return path

    # 否则返回最新的
    return paths[0][0]


def cleanup_duplicates(
    vault_root: Path,
    duplicates: Dict[str, List[Tuple[Path, float]]],
    dry_run: bool = False,
) -> Tuple[int, int]:
    """清理重复论文

    Returns:
        (kept_count, moved_count)
    """
    backup_path = vault_root / BACKUP_DIR
    if not dry_run:
        backup_path.mkdir(exist_ok=True)

    kept_count = 0
    moved_count = 0

    for arxiv_id, paths in duplicates.items():
        keep_path = select_version_to_keep(paths)

        logger.info(f"\n{arxiv_id}:")
        logger.info(f"  保留: {keep_path.relative_to(vault_root)}")

        for path, mtime in paths:
            if path == keep_path:
                kept_count += 1
                continue

            rel_path = path.relative_to(vault_root)
            dest = backup_path / f"{arxiv_id.replace('/', '_')}_{path.name}"

            if dry_run:
                logger.info(f"  [将移动] {rel_path} -> {dest.name}")
            else:
                try:
                    shutil.move(str(path), str(dest))
                    logger.info(f"  已移动: {rel_path}")
                except Exception as e:
                    logger.error(f"  移动失败: {rel_path}: {e}")
                    continue

            moved_count += 1

    return kept_count, moved_count


def main():
    parser = argparse.ArgumentParser(description="清理 Vault 重复论文")
    parser.add_argument("--dry-run", action="store_true", help="干运行（预览变更）")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT_ROOT))

    args = parser.parse_args()

    vault_root = Path(args.vault).expanduser()

    if not vault_root.exists():
        logger.error(f"Vault 目录不存在: {vault_root}")
        return

    logger.info("=" * 60)
    logger.info("清理 Vault 重复论文")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"模式: {'干运行' if args.dry_run else '执行'}")
    logger.info("=" * 60)

    # 扫描重复
    duplicates = scan_vault_duplicates(vault_root)
    logger.info(f"发现 {len(duplicates)} 组重复论文")

    if not duplicates:
        logger.info("无需清理")
        return

    # 执行清理
    kept, moved = cleanup_duplicates(vault_root, duplicates, dry_run=args.dry_run)

    logger.info("")
    logger.info("=" * 60)
    logger.info("清理结果:")
    logger.info(f"  重复组数: {len(duplicates)}")
    logger.info(f"  保留文件: {kept}")
    logger.info(f"  移动文件: {moved}")
    if args.dry_run:
        logger.info("\n💡 这是预览模式，实际未执行任何操作")
        logger.info("运行不带 --dry-run 参数来执行清理")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()