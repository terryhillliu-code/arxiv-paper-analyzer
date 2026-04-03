#!/usr/bin/env python3
"""
Obsidian 属性同步脚本

扫描 Obsidian Vault 中的 PAPER_*.md 文件，将属性变更同步到 Paper Analyzer 数据库。

同步字段：
- tier: 论文等级 (A/B/C)
- tags: 标签
- personal_rating: 个人评分 (1-5)
- personal_notes: 个人笔记

用法:
    # 同步所有变更
    python scripts/sync_obsidian_properties.py

    # 干运行（预览变更）
    python scripts/sync_obsidian_properties.py --dry-run

    # 仅同步特定字段
    python scripts/sync_obsidian_properties.py --fields tier,tags
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
EXCLUDE_DIRS = {".obsidian", "attachments", "extracted", "backup", ".duplicate_archive_backup", ".duplicate_cleanup_backup"}

# 可同步的字段
SYNC_FIELDS = {"tier", "tags", "personal_rating", "personal_notes"}


def parse_frontmatter(content: str) -> Tuple[Dict[str, any], str]:
    """解析 Markdown 文件的 YAML frontmatter

    Args:
        content: 文件内容

    Returns:
        (frontmatter_dict, body_content)
    """
    if not content.startswith("---"):
        return {}, content

    fm_end = content.find("---", 3)
    if fm_end == -1:
        return {}, content

    frontmatter_text = content[3:fm_end].strip()
    body = content[fm_end + 3:].strip()

    # 简单的 YAML 解析（不依赖 PyYAML）
    frontmatter = {}
    current_key = None
    current_list = []

    for line in frontmatter_text.split('\n'):
        line = line.rstrip()

        # 跳过注释行
        if line.strip().startswith('#'):
            continue

        # 键值对
        if ':' in line and not line.startswith(' '):
            # 保存之前的列表
            if current_key and current_list:
                frontmatter[current_key] = current_list
                current_list = []

            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()

            # 解析值
            if value.startswith('[') and value.endswith(']'):
                # 列表格式 ['a', 'b']
                items = re.findall(r"'([^']*)'|\"([^\"]*)\"", value)
                frontmatter[key] = [i[0] or i[1] for i in items]
            elif value.startswith('"') and value.endswith('"'):
                frontmatter[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                frontmatter[key] = value[1:-1]
            elif value.lower() in ('true', 'false'):
                frontmatter[key] = value.lower() == 'true'
            elif value.isdigit():
                frontmatter[key] = int(value)
            elif value:
                frontmatter[key] = value
            else:
                current_key = key
                current_list = []

        # 列表项
        elif line.strip().startswith('- ') and current_key:
            item = line.strip()[2:].strip()
            if item.startswith("'") and item.endswith("'"):
                item = item[1:-1]
            elif item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            current_list.append(item)

    # 保存最后的列表
    if current_key and current_list:
        frontmatter[current_key] = current_list

    return frontmatter, body


def extract_paper_id(frontmatter: Dict) -> Optional[int]:
    """从 frontmatter 提取 paper_id"""
    paper_id = frontmatter.get("paper_id")
    if paper_id:
        try:
            return int(paper_id)
        except (ValueError, TypeError):
            return None
    return None


def scan_obsidian_papers(vault_root: Path) -> List[Dict]:
    """扫描 Vault 中所有 PAPER 文件

    Returns:
        [{filepath, paper_id, frontmatter}]
    """
    logger.info(f"扫描 Vault: {vault_root}")
    papers = []

    for md_file in vault_root.rglob("*.md"):
        # 跳过排除目录
        if any(part in EXCLUDE_DIRS for part in md_file.parts):
            continue

        # 只处理 PAPER 前缀的文件
        if not md_file.name.startswith("PAPER_"):
            continue

        try:
            with open(md_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            frontmatter, _ = parse_frontmatter(content)
            paper_id = extract_paper_id(frontmatter)

            if paper_id:
                papers.append({
                    "filepath": str(md_file),
                    "paper_id": paper_id,
                    "frontmatter": frontmatter,
                    "mtime": md_file.stat().st_mtime,
                })

        except Exception as e:
            logger.warning(f"解析失败: {md_file.name}: {e}")

    logger.info(f"扫描完成: {len(papers)} 篇有 paper_id 的论文")
    return papers


def get_db_papers(db_path: Path) -> Dict[int, Dict]:
    """从数据库获取论文数据

    Returns:
        {paper_id: {tier, tags, ...}}
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 检查表结构，确定哪些字段存在
    c.execute("PRAGMA table_info(papers)")
    columns = {col[1]: col[2] for col in c.fetchall()}

    # 基础字段
    select_fields = ["id", "tier", "tags"]

    # 可选字段
    if "personal_rating" in columns:
        select_fields.append("personal_rating")
    if "personal_notes" in columns:
        select_fields.append("personal_notes")
    if "updated_at" in columns:
        select_fields.append("updated_at")

    c.execute(f"SELECT {', '.join(select_fields)} FROM papers")
    papers = {}

    for row in c.fetchall():
        paper_id = row[0]
        data = {
            "tier": row[1],
            "tags": json.loads(row[2]) if row[2] else [],
        }
        idx = 3
        if "personal_rating" in select_fields:
            data["personal_rating"] = row[idx]
            idx += 1
        if "personal_notes" in select_fields:
            data["personal_notes"] = row[idx]
            idx += 1
        if "updated_at" in select_fields:
            data["updated_at"] = row[idx]
            idx += 1

        papers[paper_id] = data

    conn.close()
    return papers


def compare_and_sync(
    obsidian_papers: List[Dict],
    db_papers: Dict[int, Dict],
    db_path: Path,
    dry_run: bool = False,
    fields: Set[str] = None,
) -> Tuple[int, int]:
    """比较并同步属性变更

    Returns:
        (updated_count, skipped_count)
    """
    if fields is None:
        fields = SYNC_FIELDS

    updates = []

    for obs_paper in obsidian_papers:
        paper_id = obs_paper["paper_id"]
        obs_fm = obs_paper["frontmatter"]

        if paper_id not in db_papers:
            continue

        db_paper = db_papers[paper_id]
        changes = {}

        # 比较 tier
        if "tier" in fields:
            obs_tier = obs_fm.get("tier")
            db_tier = db_paper.get("tier")
            if obs_tier and obs_tier != db_tier:
                changes["tier"] = obs_tier
                logger.info(f"Paper {paper_id}: tier {db_tier} → {obs_tier}")

        # 比较 tags
        if "tags" in fields:
            obs_tags = obs_fm.get("tags", [])
            db_tags = db_paper.get("tags", [])
            if obs_tags and set(obs_tags) != set(db_tags):
                # 合并策略：取并集
                merged_tags = list(set(obs_tags) | set(db_tags))
                changes["tags"] = json.dumps(merged_tags, ensure_ascii=False)
                logger.info(f"Paper {paper_id}: tags 合并 → {len(merged_tags)} 个")

        # personal_rating (仅 Obsidian → DB)
        if "personal_rating" in fields and "personal_rating" in obs_fm:
            obs_rating = obs_fm.get("personal_rating")
            db_rating = db_paper.get("personal_rating")
            if obs_rating and obs_rating != db_rating:
                changes["personal_rating"] = obs_rating
                logger.info(f"Paper {paper_id}: personal_rating → {obs_rating}")

        # personal_notes (仅 Obsidian → DB)
        if "personal_notes" in fields and "personal_notes" in obs_fm:
            obs_notes = obs_fm.get("personal_notes")
            db_notes = db_paper.get("personal_notes")
            if obs_notes and obs_notes != db_notes:
                changes["personal_notes"] = obs_notes
                logger.info(f"Paper {paper_id}: personal_notes 已更新")

        if changes:
            updates.append((paper_id, changes))

    # 执行更新
    if updates and not dry_run:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        for paper_id, changes in updates:
            set_clauses = []
            values = []
            for field, value in changes.items():
                set_clauses.append(f"{field} = ?")
                values.append(value)

            values.append(datetime.now().isoformat())
            values.append(paper_id)

            sql = f"UPDATE papers SET {', '.join(set_clauses)}, updated_at = ? WHERE id = ?"
            c.execute(sql, values)

        conn.commit()
        conn.close()
        logger.info(f"已更新 {len(updates)} 篇论文")

    return len(updates), len(obsidian_papers) - len(updates)


def main():
    parser = argparse.ArgumentParser(description="Obsidian 属性同步")
    parser.add_argument("--dry-run", action="store_true", help="干运行（预览变更）")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT_ROOT))
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--fields", type=str, default="tier,tags,personal_rating,personal_notes",
                        help="要同步的字段，逗号分隔")

    args = parser.parse_args()

    vault_root = Path(args.vault).expanduser()
    db_path = Path(args.db).expanduser()
    fields = set(args.fields.split(",")) if args.fields else SYNC_FIELDS

    if not vault_root.exists():
        logger.error(f"Vault 目录不存在: {vault_root}")
        return

    if not db_path.exists():
        logger.error(f"数据库不存在: {db_path}")
        return

    logger.info("=" * 60)
    logger.info("Obsidian 属性同步")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"模式: {'干运行' if args.dry_run else '执行'}")
    logger.info(f"字段: {fields}")
    logger.info("=" * 60)

    # 扫描 Obsidian
    obsidian_papers = scan_obsidian_papers(vault_root)

    # 获取数据库数据
    db_papers = get_db_papers(db_path)

    # 比较并同步
    updated, skipped = compare_and_sync(
        obsidian_papers,
        db_papers,
        db_path,
        dry_run=args.dry_run,
        fields=fields,
    )

    logger.info("")
    logger.info("=" * 60)
    logger.info("同步结果:")
    logger.info(f"  扫描论文: {len(obsidian_papers)}")
    logger.info(f"  更新论文: {updated}")
    logger.info(f"  无变更: {skipped}")
    if args.dry_run:
        logger.info("\n💡 这是预览模式，实际未执行任何操作")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()