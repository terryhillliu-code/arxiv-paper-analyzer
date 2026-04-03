#!/usr/bin/env python3
"""
重复论文检测脚本

检测 Obsidian Vault 和 papers.db 中的重复论文。

用法:
    # 检测 Vault 中的重复
    python scripts/detect_duplicates.py --vault

    # 检测数据库中的重复
    python scripts/detect_duplicates.py --db

    # 检测 Vault 与 数据库 之间的重复
    python scripts/detect_duplicates.py --cross
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

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


def compute_content_hash(filepath: Path, max_chars: int = 200) -> str:
    """计算文件内容 hash（基于前 N 个字符）"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_chars)
        return hashlib.md5(content.encode()).hexdigest()
    except Exception:
        return ""


def extract_arxiv_id(filepath: Path) -> str | None:
    """从文件提取 arxiv_id"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048)

        # 从 YAML frontmatter 提取
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

        # 从正文提取
        arxiv_url_match = re.search(r"https://arxiv\.org/abs/(\d{4}\.\d{4,5}|[a-z-]+/\d+)", content)
        if arxiv_url_match:
            return arxiv_url_match.group(1)

    except Exception:
        pass

    return None


def detect_vault_duplicates(vault_root: Path) -> Dict[str, List[str]]:
    """检测 Vault 中的重复论文

    Returns:
        {arxiv_id: [file_paths]} 重复项字典
    """
    logger.info(f"扫描 Vault: {vault_root}")

    # 按 arxiv_id 分组
    by_arxiv_id: Dict[str, List[str]] = defaultdict(list)
    # 按内容 hash 分组（用于检测无 arxiv_id 的重复）
    by_hash: Dict[str, List[str]] = defaultdict(list)

    for md_file in vault_root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in md_file.parts):
            continue

        if not md_file.name.startswith("PAPER_"):
            continue

        arxiv_id = extract_arxiv_id(md_file)
        if arxiv_id:
            by_arxiv_id[arxiv_id].append(str(md_file.relative_to(vault_root)))
        else:
            # 使用内容 hash
            content_hash = compute_content_hash(md_file)
            if content_hash:
                by_hash[content_hash].append(str(md_file.relative_to(vault_root)))

    # 找出重复项
    duplicates = {}

    for arxiv_id, paths in by_arxiv_id.items():
        if len(paths) > 1:
            duplicates[f"arxiv:{arxiv_id}"] = paths

    for content_hash, paths in by_hash.items():
        if len(paths) > 1:
            duplicates[f"hash:{content_hash[:8]}"] = paths

    return duplicates


def detect_db_duplicates(db_path: Path) -> Dict[str, List[int]]:
    """检测数据库中的重复论文

    Returns:
        {arxiv_id: [paper_ids]} 重复项字典
    """
    logger.info(f"检查数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 检查 arxiv_id 重复
    c.execute("""
        SELECT arxiv_id, GROUP_CONCAT(id) as ids, COUNT(*) as cnt
        FROM papers
        WHERE arxiv_id IS NOT NULL
        GROUP BY arxiv_id
        HAVING cnt > 1
    """)

    duplicates = {}
    for row in c.fetchall():
        arxiv_id, ids_str, count = row
        ids = [int(id) for id in ids_str.split(",")]
        duplicates[arxiv_id] = ids

    conn.close()
    return duplicates


def detect_cross_duplicates(vault_root: Path, db_path: Path) -> Dict[str, Dict]:
    """检测 Vault 与数据库之间的重复

    Returns:
        {arxiv_id: {"vault": [paths], "db": [ids]}} 重复项字典
    """
    logger.info("检测 Vault 与数据库交叉重复")

    # 获取 Vault 论文
    vault_papers: Dict[str, List[str]] = defaultdict(list)
    for md_file in vault_root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in md_file.parts):
            continue
        if not md_file.name.startswith("PAPER_"):
            continue

        arxiv_id = extract_arxiv_id(md_file)
        if arxiv_id:
            vault_papers[arxiv_id].append(str(md_file.relative_to(vault_root)))

    # 获取数据库论文
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, arxiv_id, md_output_path FROM papers WHERE arxiv_id IS NOT NULL")
    db_papers = {row[1]: {"id": row[0], "path": row[2]} for row in c.fetchall()}
    conn.close()

    # 找出交叉重复
    cross_duplicates = {}
    for arxiv_id in set(vault_papers.keys()) & set(db_papers.keys()):
        vault_paths = vault_papers[arxiv_id]
        db_info = db_papers[arxiv_id]

        # 检查是否路径不同（即同一论文在多个位置）
        db_path_rel = None
        if db_info["path"]:
            try:
                db_path_rel = str(Path(db_info["path"]).relative_to(vault_root))
            except ValueError:
                db_path_rel = db_info["path"]

        if db_path_rel not in vault_paths:
            cross_duplicates[arxiv_id] = {
                "vault": vault_paths,
                "db_id": db_info["id"],
                "db_path": db_path_rel,
            }

    return cross_duplicates


def main():
    parser = argparse.ArgumentParser(description="重复论文检测")
    parser.add_argument("--vault", action="store_true", help="检测 Vault 内重复")
    parser.add_argument("--db", action="store_true", help="检测数据库内重复")
    parser.add_argument("--cross", action="store_true", help="检测 Vault 与数据库交叉重复")
    parser.add_argument("--all", action="store_true", help="检测所有类型的重复")
    parser.add_argument("--vault-path", type=str, default=str(DEFAULT_VAULT_ROOT))
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH))

    args = parser.parse_args()

    vault_root = Path(args.vault_path).expanduser()
    db_path = Path(args.db_path).expanduser()

    if args.all:
        args.vault = args.db = args.cross = True

    if not (args.vault or args.db or args.cross):
        parser.print_help()
        return

    logger.info("=" * 60)
    logger.info("重复论文检测")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    total_duplicates = 0

    if args.vault:
        logger.info("\n--- Vault 内重复 ---")
        vault_dups = detect_vault_duplicates(vault_root)
        if vault_dups:
            for key, paths in vault_dups.items():
                logger.info(f"{key}: {len(paths)} 份")
                for p in paths:
                    logger.info(f"  - {p}")
                total_duplicates += 1
        else:
            logger.info("无重复")

    if args.db:
        logger.info("\n--- 数据库内重复 ---")
        db_dups = detect_db_duplicates(db_path)
        if db_dups:
            for arxiv_id, ids in db_dups.items():
                logger.info(f"{arxiv_id}: IDs {ids}")
                total_duplicates += 1
        else:
            logger.info("无重复")

    if args.cross:
        logger.info("\n--- Vault 与数据库交叉重复 ---")
        cross_dups = detect_cross_duplicates(vault_root, db_path)
        if cross_dups:
            for arxiv_id, info in cross_dups.items():
                logger.info(f"{arxiv_id}:")
                logger.info(f"  Vault: {info['vault']}")
                logger.info(f"  DB: ID={info['db_id']}, Path={info['db_path']}")
                total_duplicates += 1
        else:
            logger.info("无交叉重复")

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"检测完成: 发现 {total_duplicates} 组重复")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()