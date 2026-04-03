#!/usr/bin/env python3
"""
Vault 扫描同步脚本

扫描 Obsidian Vault 全库 PAPER 文件，与 papers.db 匹配并更新 vault_locations 字段。
支持将 Vault 中存在但数据库中缺失的论文导入为新记录。

用法:
    # 仅同步路径（不导入新论文）
    python scripts/sync_vault_locations.py

    # 同步路径 + 导入缺失论文
    python scripts/sync_vault_locations.py --import-mode

    # 干运行（查看变更预览）
    python scripts/sync_vault_locations.py --dry-run

    # 指定 Vault 根目录
    python scripts/sync_vault_locations.py --vault ~/Documents/ZhiweiVault
"""

import argparse
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_VAULT_ROOT = Path("~/Documents/ZhiweiVault").expanduser()
DEFAULT_DB_PATH = Path("~/arxiv-paper-analyzer/backend/data/papers.db").expanduser()

# 排除目录
EXCLUDE_DIRS = {".obsidian", "attachments", "extracted", "backup", ".duplicate_archive_backup"}


def extract_arxiv_id_from_content(filepath: Path) -> Optional[str]:
    """从 Markdown 文件的 YAML frontmatter 或内容中提取 arxiv_id"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048)  # 只读取前 2KB

        # 检查 YAML frontmatter
        if content.startswith("---"):
            # 提取 YAML 部分
            yaml_end = content.find("---", 3)
            if yaml_end > 0:
                yaml_content = content[3:yaml_end]

                # 尝试多种 arxiv_id 字段格式
                patterns = [
                    r"arxiv_id:\s*['\"]?([^'\"\n]+)['\"]?",
                    r"source_url:\s*['\"]?https://arxiv\.org/abs/([^'\"\n]+)['\"]?",
                    r"url:\s*['\"]?https://arxiv\.org/abs/([^'\"\n]+)['\"]?",
                ]

                for pattern in patterns:
                    match = re.search(pattern, yaml_content)
                    if match:
                        return match.group(1).strip()

        # 从文件名提取（格式：PAPER_YYYY-MM-DD_Title）
        # 文件名通常不包含 arxiv_id，但可以从内容中提取
        # 尝试从正文中提取 arxiv.org 链接
        arxiv_url_match = re.search(r"https://arxiv\.org/abs/(\d{4}\.\d{4,5}|[a-z-]+/\d+)", content)
        if arxiv_url_match:
            return arxiv_url_match.group(1)

    except Exception as e:
        logger.warning(f"读取文件失败: {filepath.name}: {e}")

    return None


def extract_paper_metadata(filepath: Path) -> Dict:
    """从 Markdown 文件提取论文元数据"""
    metadata = {
        "arxiv_id": None,
        "title": None,
        "date": None,
        "tags": [],
        "tier": None,
        "vault_path": str(filepath),
    }

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(4096)

        # 提取 YAML frontmatter
        if content.startswith("---"):
            yaml_end = content.find("---", 3)
            if yaml_end > 0:
                yaml_content = content[3:yaml_end]

                # arxiv_id
                arxiv_patterns = [
                    r"arxiv_id:\s*['\"]?([^'\"\n]+)['\"]?",
                    r"source_url:\s*['\"]?https://arxiv\.org/abs/([^'\"\n]+)['\"]?",
                ]
                for pattern in arxiv_patterns:
                    match = re.search(pattern, yaml_content)
                    if match:
                        metadata["arxiv_id"] = match.group(1).strip()
                        break

                # title
                title_match = re.search(r"title:\s*['\"]?([^'\"\n]+)['\"]?", yaml_content)
                if title_match:
                    metadata["title"] = title_match.group(1).strip()

                # date
                date_match = re.search(r"date:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?", yaml_content)
                if date_match:
                    metadata["date"] = date_match.group(1)

                # tags
                tags_match = re.search(r"tags:\s*\[([^\]]+)\]", yaml_content)
                if tags_match:
                    tags_str = tags_match.group(1)
                    metadata["tags"] = [t.strip().strip("'\"") for t in tags_str.split(",")]

                # tier
                tier_match = re.search(r"tier:\s*['\"]?([ABC])['\"]?", yaml_content)
                if tier_match:
                    metadata["tier"] = tier_match.group(1)

        # 从文件名提取日期（格式：PAPER_YYYY-MM-DD_Title）
        filename_date_match = re.search(r"PAPER_(\d{4}-\d{2}-\d{2})_", filepath.name)
        if filename_date_match and not metadata["date"]:
            metadata["date"] = filename_date_match.group(1)

        # 从正文标题提取
        if not metadata["title"]:
            title_heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if title_heading_match:
                metadata["title"] = title_heading_match.group(1).strip()

    except Exception as e:
        logger.warning(f"提取元数据失败: {filepath.name}: {e}")

    return metadata


def scan_vault_papers(vault_root: Path) -> List[Dict]:
    """扫描 Vault 中所有 PAPER 文件"""
    papers = []

    logger.info(f"扫描 Vault: {vault_root}")

    for md_file in vault_root.rglob("*.md"):
        # 跳过排除目录
        if any(part in EXCLUDE_DIRS for part in md_file.parts):
            continue

        # 只处理 PAPER 前缀的文件
        if not md_file.name.startswith("PAPER_"):
            continue

        # 提取相对路径（相对于 Vault 根目录）
        rel_path = md_file.relative_to(vault_root)

        # 提取元数据
        metadata = extract_paper_metadata(md_file)
        metadata["vault_path"] = str(rel_path)
        metadata["full_path"] = str(md_file)

        papers.append(metadata)

    logger.info(f"扫描完成: {len(papers)} 篇论文")
    return papers


def match_and_sync(
    vault_papers: List[Dict],
    db_path: Path,
    dry_run: bool = False,
    import_mode: bool = False,
) -> Tuple[int, int, int]:
    """匹配 Vault 论文与数据库记录，更新 vault_locations 字段

    匹配策略：
    1. 通过 arxiv_id 精确匹配
    2. 通过文件名匹配（后备）

    Returns:
        (matched_count, imported_count, unmatched_count)
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 获取数据库中所有论文
    c.execute("SELECT id, arxiv_id, title, vault_locations, md_output_path FROM papers")

    # 构建 arxiv_id -> db_info 映射
    db_by_arxiv_id = {}
    # 构建 filename -> db_info 映射（用于后备匹配）
    db_by_filename = {}
    # 记录无 vault_locations 的论文
    papers_need_update = []

    for row in c.fetchall():
        db_id, arxiv_id, title, locations_json, md_path = row
        info = {
            "id": db_id,
            "arxiv_id": arxiv_id,
            "title": title,
            "locations": json.loads(locations_json) if locations_json else [],
            "md_path": md_path,
        }

        if arxiv_id:
            db_by_arxiv_id[arxiv_id] = info

        # 通过 md_output_path 提取文件名
        if md_path:
            filename = os.path.basename(md_path)
            db_by_filename[filename] = info

    matched_count = 0
    imported_count = 0
    unmatched_count = 0

    # 按 arxiv_id 分组：arxiv_id -> [paths]
    vault_by_arxiv_id: Dict[str, List[str]] = {}
    vault_by_filename: Dict[str, Dict] = {}  # filename -> {path, arxiv_id, metadata}

    for paper in vault_papers:
        arxiv_id = paper.get("arxiv_id")
        vault_path = paper["vault_path"]
        filename = os.path.basename(vault_path)

        if arxiv_id:
            if arxiv_id not in vault_by_arxiv_id:
                vault_by_arxiv_id[arxiv_id] = []
            vault_by_arxiv_id[arxiv_id].append(vault_path)

        vault_by_filename[filename] = {
            "path": vault_path,
            "arxiv_id": arxiv_id,
            "metadata": paper,
        }

    # 策略 1：通过 arxiv_id 匹配
    updates = []

    for arxiv_id, paths in vault_by_arxiv_id.items():
        if arxiv_id in db_by_arxiv_id:
            db_paper = db_by_arxiv_id[arxiv_id]
            existing_locations = db_paper["locations"]

            # 合并路径
            new_locations = list(set(existing_locations + paths))

            if new_locations != existing_locations:
                updates.append((db_paper["id"], json.dumps(new_locations)))
                matched_count += 1
        else:
            # Vault 中有但数据库中没有
            if import_mode and not dry_run:
                vault_paper = vault_by_arxiv_id[arxiv_id][0]  # 取第一个路径的元数据
                # 从 vault_papers 中找到对应的元数据
                metadata = None
                for p in vault_papers:
                    if p.get("arxiv_id") == arxiv_id:
                        metadata = p
                        break

                c.execute(
                    """
                    INSERT INTO papers (
                        arxiv_id, title, vault_locations,
                        has_analysis, rag_indexed, full_analysis,
                        view_count, is_featured, popularity_score,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0.0, ?, ?)
                    """,
                    (
                        arxiv_id,
                        metadata.get("title", "Unknown") if metadata else "Unknown",
                        json.dumps(paths),
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )
                imported_count += 1
            else:
                unmatched_count += 1
                logger.info(f"未匹配论文: {arxiv_id} -> {paths}")

    # 策略 2：通过文件名匹配（仅针对没有 vault_locations 的论文）
    filename_matches = 0
    for filename, vault_info in vault_by_filename.items():
        if filename in db_by_filename:
            db_paper = db_by_filename[filename]

            # 只更新还没有 vault_locations 的论文
            if not db_paper["locations"]:
                new_location = vault_info["path"]
                updates.append((db_paper["id"], json.dumps([new_location])))
                filename_matches += 1

    # 执行批量更新
    if updates and not dry_run:
        c.executemany(
            "UPDATE papers SET vault_locations = ?, updated_at = ? WHERE id = ?",
            [(u[1], datetime.now().isoformat(), u[0]) for u in updates],
        )
        logger.info(f"更新 {len(updates)} 条记录的 vault_locations (其中 {filename_matches} 条通过文件名匹配)")

    conn.commit()
    conn.close()

    return matched_count, imported_count, unmatched_count


def main():
    parser = argparse.ArgumentParser(description="Vault 扫描同步脚本")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT_ROOT), help="Vault 根目录")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="papers.db 路径")
    parser.add_argument("--dry-run", action="store_true", help="干运行（不执行更新）")
    parser.add_argument("--import-mode", action="store_true", help="导入缺失论文到数据库")

    args = parser.parse_args()

    vault_root = Path(args.vault).expanduser()
    db_path = Path(args.db).expanduser()

    if not vault_root.exists():
        logger.error(f"Vault 目录不存在: {vault_root}")
        return

    if not db_path.exists():
        logger.error(f"数据库不存在: {db_path}")
        return

    logger.info("=" * 60)
    logger.info("Vault 扫描同步")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Vault: {vault_root}")
    logger.info(f"数据库: {db_path}")
    logger.info(f"模式: {'干运行' if args.dry_run else '执行'}")
    if args.import_mode:
        logger.info("导入模式: 启用（将导入缺失论文）")
    logger.info("=" * 60)

    # 扫描 Vault
    vault_papers = scan_vault_papers(vault_root)

    # 匹配并同步
    matched, imported, unmatched = match_and_sync(
        vault_papers,
        db_path,
        dry_run=args.dry_run,
        import_mode=args.import_mode,
    )

    logger.info("")
    logger.info("=" * 60)
    logger.info("同步结果:")
    logger.info(f"  Vault 论文: {len(vault_papers)} 篇")
    logger.info(f"  匹配更新: {matched} 篇")
    logger.info(f"  新导入: {imported} 篇")
    logger.info(f"  未匹配: {unmatched} 篇")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()