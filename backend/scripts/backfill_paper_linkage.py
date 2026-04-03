#!/usr/bin/env python3
"""
批量回填论文联动字段

为现有论文的 Obsidian 文件添加 Paper Analyzer 联动字段：
- paper_id: 数据库 ID
- arxiv_id: arXiv ID
- analyzed: 是否已分析
- rag_indexed: 是否已同步 RAG
- analysis_mode: 分析模式
- has_pdf: 是否有本地 PDF

用法:
    # 干运行（预览）
    python scripts/backfill_paper_linkage.py --dry-run

    # 执行回填
    python scripts/backfill_paper_linkage.py

    # 仅处理 Inbox 目录
    python scripts/backfill_paper_linkage.py --folder Inbox

    # 处理指定数量的文件
    python scripts/backfill_paper_linkage.py --limit 100
"""

import argparse
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def extract_arxiv_id_from_content(content: str) -> Optional[str]:
    """从内容中提取 arxiv_id"""
    # 从 frontmatter 提取
    if 'arxiv_id:' in content[:2000]:
        match = re.search(r'arxiv_id:\s*["\']?([^"\'\n]+)["\']?', content[:2000])
        if match:
            return match.group(1).strip()

    # 从 source_url 提取
    if 'source_url:' in content[:2000]:
        match = re.search(r'arxiv\.org/abs/([^"\'\n]+)', content[:2000])
        if match:
            arxiv_id = match.group(1).strip()
            # 移除版本号
            if 'v' in arxiv_id and arxiv_id[-2].isdigit():
                arxiv_id = arxiv_id.rsplit('v', 1)[0]
            return arxiv_id

    return None


def get_db_paper_info(db_path: Path) -> Dict[str, Dict]:
    """从数据库获取论文信息，按 arxiv_id 索引

    Returns:
        {arxiv_id: {id, has_analysis, rag_indexed, analysis_mode, pdf_local_path}}
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        SELECT id, arxiv_id, has_analysis, rag_indexed, analysis_mode, pdf_local_path
        FROM papers
        WHERE arxiv_id IS NOT NULL
    """)

    papers = {}
    for row in c.fetchall():
        paper_id, arxiv_id, has_analysis, rag_indexed, analysis_mode, pdf_local_path = row
        papers[arxiv_id] = {
            "paper_id": paper_id,
            "has_analysis": bool(has_analysis),
            "rag_indexed": bool(rag_indexed),
            "analysis_mode": analysis_mode or "",
            "has_pdf": pdf_local_path is not None,
        }

    conn.close()
    return papers


def build_linkage_block(paper_info: Dict) -> str:
    """构建联动字段块"""
    lines = [
        "\n# === Paper Analyzer 联动字段 ===",
        f"paper_id: {paper_info['paper_id']}",
    ]

    # arxiv_id 已在 frontmatter 中，不需要重复

    lines.extend([
        f"analyzed: {str(paper_info['has_analysis']).lower()}",
        f"rag_indexed: {str(paper_info['rag_indexed']).lower()}",
    ])

    if paper_info['analysis_mode']:
        lines.append(f"analysis_mode: \"{paper_info['analysis_mode']}\"")

    lines.append(f"has_pdf: {str(paper_info['has_pdf']).lower()}")

    return "\n".join(lines)


def update_frontmatter(content: str, linkage_block: str) -> str:
    """更新文件内容，添加联动字段

    Args:
        content: 原始文件内容
        linkage_block: 联动字段块

    Returns:
        更新后的文件内容
    """
    if not content.startswith("---"):
        return content

    fm_end = content.find("---", 3)
    if fm_end == -1:
        return content

    # 检查是否已有联动字段
    if "Paper Analyzer 联动字段" in content[:fm_end]:
        # 已有联动字段，跳过
        return content

    # 在 frontmatter 结束前插入联动字段
    new_content = content[:fm_end] + linkage_block + "\n" + content[fm_end:]
    return new_content


def process_file(
    filepath: Path,
    db_papers: Dict[str, Dict],
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """处理单个文件

    Returns:
        (updated, reason)
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 提取 arxiv_id
        arxiv_id = extract_arxiv_id_from_content(content)
        if not arxiv_id:
            return False, "无 arxiv_id"

        # 查找数据库信息
        if arxiv_id not in db_papers:
            return False, f"数据库中无此论文: {arxiv_id}"

        paper_info = db_papers[arxiv_id]

        # 检查是否已有联动字段
        if "paper_id:" in content[:2000]:
            return False, "已有联动字段"

        # 构建联动字段
        linkage_block = build_linkage_block(paper_info)

        # 更新内容
        new_content = update_frontmatter(content, linkage_block)

        if new_content == content:
            return False, "无需更新"

        if not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

        return True, f"paper_id={paper_info['paper_id']}"

    except Exception as e:
        return False, f"处理失败: {e}"


def main():
    parser = argparse.ArgumentParser(description="批量回填论文联动字段")
    parser.add_argument("--dry-run", action="store_true", help="干运行（预览变更）")
    parser.add_argument("--vault", type=str, default=str(DEFAULT_VAULT_ROOT))
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--folder", type=str, help="仅处理指定目录")
    parser.add_argument("--limit", type=int, default=0, help="处理文件数量限制")
    parser.add_argument("--force", action="store_true", help="强制更新已有联动字段的文件")

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
    logger.info("批量回填论文联动字段")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"模式: {'干运行' if args.dry_run else '执行'}")
    if args.folder:
        logger.info(f"目录: {args.folder}")
    if args.limit:
        logger.info(f"限制: {args.limit} 个文件")
    logger.info("=" * 60)

    # 获取数据库信息
    logger.info("加载数据库论文信息...")
    db_papers = get_db_paper_info(db_path)
    logger.info(f"数据库中有 {len(db_papers)} 篇论文")

    # 扫描文件
    logger.info("扫描 Obsidian Vault...")
    files = []

    search_root = vault_root / args.folder if args.folder else vault_root

    for md_file in search_root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in md_file.parts):
            continue

        if not md_file.name.startswith("PAPER_"):
            continue

        files.append(md_file)

        if args.limit and len(files) >= args.limit:
            break

    logger.info(f"找到 {len(files)} 个论文文件")

    # 处理文件
    stats = {"updated": 0, "skipped": 0, "failed": 0}
    reasons = {}

    for i, filepath in enumerate(files):
        if (i + 1) % 100 == 0:
            logger.info(f"进度: {i + 1}/{len(files)}")

        updated, reason = process_file(filepath, db_papers, dry_run=args.dry_run)

        if updated:
            stats["updated"] += 1
        elif "失败" in reason:
            stats["failed"] += 1
        else:
            stats["skipped"] += 1

        # 统计原因
        reason_key = reason.split(":")[0] if ":" in reason else reason
        reasons[reason_key] = reasons.get(reason_key, 0) + 1

    # 输出结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("回填结果:")
    logger.info(f"  更新: {stats['updated']}")
    logger.info(f"  跳过: {stats['skipped']}")
    logger.info(f"  失败: {stats['failed']}")
    logger.info("")
    logger.info("跳过原因:")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        logger.info(f"  {reason}: {count}")
    if args.dry_run:
        logger.info("\n💡 这是预览模式，实际未执行任何操作")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()