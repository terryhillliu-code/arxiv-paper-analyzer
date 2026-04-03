#!/usr/bin/env python3
"""
导入历史论文到 Paper Analyzer 数据库

从 Obsidian Vault 扫描不在数据库中的历史论文，提取 frontmatter 元数据导入。

用法:
    # 干运行（预览）
    python scripts/import_historical_papers.py --dry-run

    # 执行导入
    python scripts/import_historical_papers.py

    # 指定目录
    python scripts/import_historical_papers.py --folder Inbox

排除目录:
    - .duplicate_archive_backup
    - .duplicate_cleanup_backup
    - .obsidian
    - attachments
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
EXCLUDE_DIRS = {
    ".obsidian",
    "attachments",
    "extracted",
    "backup",
    ".duplicate_archive_backup",  # 重复备份，跳过
    ".duplicate_cleanup_backup",
}

# 需要排除的目录（不导入）
SKIP_DIRS = {
    ".duplicate_archive_backup",
    ".duplicate_cleanup_backup",
}


def parse_frontmatter(content: str) -> Tuple[Dict[str, any], str, int]:
    """解析 Markdown 文件的 YAML frontmatter

    Returns:
        (frontmatter_dict, body_content, fm_end_position)
    """
    if not content.startswith("---"):
        return {}, content, 0

    fm_end = content.find("---", 3)
    if fm_end == -1:
        return {}, content, 0

    frontmatter_text = content[3:fm_end].strip()
    body = content[fm_end + 3:].strip()

    # 简单的 YAML 解析
    frontmatter = {}
    current_key = None
    current_list = []

    for line in frontmatter_text.split('\n'):
        line = line.rstrip()

        if line.strip().startswith('#'):
            continue

        if ':' in line and not line.startswith(' '):
            if current_key and current_list:
                frontmatter[current_key] = current_list
                current_list = []

            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()

            if value.startswith('[') and value.endswith(']'):
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

        elif line.strip().startswith('- ') and current_key:
            item = line.strip()[2:].strip()
            if item.startswith("'") and item.endswith("'"):
                item = item[1:-1]
            elif item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            current_list.append(item)

    if current_key and current_list:
        frontmatter[current_key] = current_list

    return frontmatter, body, fm_end


def extract_arxiv_id(content: str) -> Optional[str]:
    """从内容中提取 arxiv_id"""
    # 从 source_url 提取
    match = re.search(r'arxiv\.org/abs/([^"\'\n\s]+)', content[:3000])
    if match:
        arxiv_id = match.group(1).strip()
        # 移除版本号
        if 'v' in arxiv_id and arxiv_id[-2].isdigit():
            arxiv_id = arxiv_id.rsplit('v', 1)[0]
        return arxiv_id
    return None


def extract_date(date_str: str) -> Optional[str]:
    """解析日期字符串"""
    if not date_str or date_str == '未知':
        return None

    # 尝试多种格式
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            return dt.isoformat()
        except:
            pass

    return None


def get_db_arxiv_ids(db_path: Path) -> Set[str]:
    """获取数据库中已有的 arxiv_id"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT arxiv_id FROM papers WHERE arxiv_id IS NOT NULL")
    ids = {row[0] for row in c.fetchall()}
    conn.close()
    return ids


def import_paper(
    db_path: Path,
    arxiv_id: str,
    frontmatter: Dict,
    body: str,
    filepath: Path,
    dry_run: bool = False,
) -> bool:
    """导入单篇论文到数据库"""

    try:
        # 提取字段
        title = frontmatter.get('title', '')
        if not title:
            # 从文件名提取
            title = filepath.stem.replace('PAPER_', '').split('_', 2)[-1] if '_' in filepath.stem else filepath.stem

        source_url = frontmatter.get('source_url', '')
        tags = frontmatter.get('tags', [])
        tier = frontmatter.get('tier', 'B')
        institutions = frontmatter.get('institutions', [])
        overall_rating = frontmatter.get('overall_rating', tier)
        publish_date = extract_date(str(frontmatter.get('date', '')))

        # 检查是否有分析内容
        has_analysis = '## 💡 一句话总结' in body or '深度分析报告' in body

        # 构建 arxiv_url
        arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

        # vault_locations
        vault_rel_path = str(filepath.relative_to(DEFAULT_VAULT_ROOT))

        if dry_run:
            return True

        # 插入数据库
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO papers (
                arxiv_id, title, tags, tier, institutions,
                arxiv_url, has_analysis, content_type,
                publish_date, md_output_path, vault_locations,
                created_at, updated_at, view_count, is_featured,
                popularity_score, full_analysis, analysis_mode, rag_indexed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            arxiv_id,
            title,
            json.dumps(tags, ensure_ascii=False) if tags else None,
            tier,
            json.dumps(institutions, ensure_ascii=False) if institutions else None,
            arxiv_url,
            has_analysis,
            'paper',
            publish_date,
            str(filepath),
            json.dumps([vault_rel_path], ensure_ascii=False),
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            0,
            False,
            0.0,
            1 if has_analysis else 0,
            'historical',  # 标记为历史导入
            True,  # 假设已在 LanceDB 中
        ))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        logger.error(f"导入失败 {arxiv_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="导入历史论文到 Paper Analyzer")
    parser.add_argument("--dry-run", action="store_true", help="干运行（预览变更）")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT_ROOT))
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--folder", type=str, help="仅处理指定目录")
    parser.add_argument("--limit", type=int, default=0, help="处理文件数量限制")
    parser.add_argument("--skip-dirs", action="store_true", default=True,
                        help="跳过备份目录（默认启用）")

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
    logger.info("导入历史论文到 Paper Analyzer")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"模式: {'干运行' if args.dry_run else '执行'}")
    logger.info(f"跳过备份目录: {args.skip_dirs}")
    if args.folder:
        logger.info(f"目录: {args.folder}")
    if args.limit:
        logger.info(f"限制: {args.limit} 个文件")
    logger.info("=" * 60)

    # 获取已有 arxiv_id
    logger.info("加载数据库已有论文...")
    db_arxiv_ids = get_db_arxiv_ids(db_path)
    logger.info(f"数据库已有 {len(db_arxiv_ids)} 篇论文")

    # 扫描文件
    logger.info("扫描 Obsidian Vault...")
    files = []
    skipped_dirs = {}

    search_root = vault_root / args.folder if args.folder else vault_root

    for md_file in search_root.rglob("PAPER_*.md"):
        # 检查排除目录
        rel_parts = md_file.relative_to(vault_root).parts

        # 跳过备份目录
        if args.skip_dirs:
            for skip_dir in SKIP_DIRS:
                if skip_dir in rel_parts:
                    skipped_dirs[skip_dir] = skipped_dirs.get(skip_dir, 0) + 1
                    break
            else:
                if any(part in EXCLUDE_DIRS for part in rel_parts):
                    continue
                files.append(md_file)
        else:
            if any(part in EXCLUDE_DIRS for part in rel_parts):
                continue
            files.append(md_file)

        if args.limit and len(files) >= args.limit:
            break

    logger.info(f"找到 {len(files)} 个待处理文件")
    if skipped_dirs:
        logger.info(f"跳过备份目录:")
        for dir_name, count in skipped_dirs.items():
            logger.info(f"  {dir_name}: {count} 个文件")

    # 处理文件
    stats = {"imported": 0, "skipped_in_db": 0, "skipped_no_id": 0, "failed": 0}

    for i, filepath in enumerate(files):
        if (i + 1) % 500 == 0:
            logger.info(f"进度: {i + 1}/{len(files)}")

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # 提取 arxiv_id
            arxiv_id = extract_arxiv_id(content)
            if not arxiv_id:
                stats["skipped_no_id"] += 1
                continue

            # 检查是否已在数据库
            if arxiv_id in db_arxiv_ids:
                stats["skipped_in_db"] += 1
                continue

            # 解析 frontmatter
            frontmatter, body, _ = parse_frontmatter(content)

            # 导入
            success = import_paper(db_path, arxiv_id, frontmatter, body, filepath, dry_run=args.dry_run)

            if success:
                stats["imported"] += 1
                if stats["imported"] % 100 == 0:
                    logger.info(f"已导入 {stats['imported']} 篇")
            else:
                stats["failed"] += 1

        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"处理失败 {filepath.name}: {e}")

    # 输出结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("导入结果:")
    logger.info(f"  新导入: {stats['imported']}")
    logger.info(f"  已在数据库: {stats['skipped_in_db']}")
    logger.info(f"  无 arxiv_id: {stats['skipped_no_id']}")
    logger.info(f"  失败: {stats['failed']}")

    if args.dry_run:
        logger.info("\n💡 这是预览模式，实际未执行任何操作")
    else:
        # 更新数据库统计
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM papers")
        total = c.fetchone()[0]
        conn.close()
        logger.info(f"\n📊 数据库总论文: {total}")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()