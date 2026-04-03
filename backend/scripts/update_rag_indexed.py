#!/usr/bin/env python3
"""
RAG 同步状态更新脚本

从 LanceDB 获取已入库论文，更新 papers.db 的 rag_indexed 字段。
支持通过 vault_locations 多路径匹配，不依赖单一 md_output_path。

用法:
    python scripts/update_rag_indexed.py
    python scripts/update_rag_indexed.py --dry-run
"""

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 路径配置
PAPERS_DB = Path("~/arxiv-paper-analyzer/backend/data/papers.db").expanduser()
RAG_VENV = Path.home() / "zhiwei-rag" / "venv" / "bin" / "python3"
RAG_DB_PATH = Path.home() / "zhiwei-rag" / "data" / "lance_db"


def get_lancedb_sources() -> set:
    """从 LanceDB 获取所有论文的 source 路径"""
    try:
        result = subprocess.run(
            [
                str(RAG_VENV), "-c", '''
import lancedb
import os
import json

db = lancedb.connect(os.path.expanduser("~/zhiwei-rag/data/lance_db"))
if "documents" not in db.table_names():
    print(json.dumps([]))
    exit(0)

tbl = db.open_table("documents")

# 获取所有唯一 source
data = tbl.to_arrow()
if "source" in data.column_names:
    sources = set(data.column("source").to_pylist())
    # 只保留 PAPER 论文
    paper_sources = [s for s in sources if "PAPER_" in s]
    print(json.dumps(paper_sources))
else:
    print(json.dumps([]))
'''
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.home() / "zhiwei-rag"),
        )

        if result.returncode == 0:
            sources = json.loads(result.stdout.strip())
            logger.info(f"LanceDB 中有 {len(sources)} 篇论文")
            return set(sources)
        else:
            logger.error(f"获取 LanceDB 数据失败: {result.stderr}")
            return set()

    except Exception as e:
        logger.error(f"LanceDB 查询异常: {e}")
        return set()


def extract_arxiv_id_from_path(path: str) -> str | None:
    """从文件路径或内容中提取 arxiv_id（用于后备匹配）"""
    # 从 LanceDB 的 prefix 提取（格式：arxiv:2301.12345:）
    if "arxiv:" in path:
        parts = path.split(":")
        if len(parts) >= 2:
            return parts[1]

    # 从文件名提取（通常不包含 arxiv_id）
    return None


def match_papers(
    lancedb_sources: set,
    dry_run: bool = False,
) -> tuple[int, int]:
    """匹配 LanceDB 论文与数据库记录，更新 rag_indexed

    匹配策略：
    1. 通过 vault_locations 多路径匹配
    2. 通过 md_output_path 单路径匹配（后备）
    3. 通过 arxiv_id 匹配（最后手段）

    Returns:
        (updated_count, unmatched_count)
    """
    conn = sqlite3.connect(PAPERS_DB)
    c = conn.cursor()

    # 获取所有论文
    c.execute("""
        SELECT id, arxiv_id, md_output_path, vault_locations, rag_indexed
        FROM papers
    """)
    papers = c.fetchall()

    logger.info(f"数据库中有 {len(papers)} 篇论文")

    updated_count = 0
    already_indexed = 0
    unmatched_sources = []

    # 构建 arxiv_id -> db_id 映射（用于后备匹配）
    c.execute("SELECT id, arxiv_id FROM papers WHERE arxiv_id IS NOT NULL")
    arxiv_id_map = {row[1]: row[0] for row in c.fetchall()}

    # 构建 LanceDB source -> relative_path 映射
    # LanceDB source 是完整路径，需要转换为相对路径进行匹配
    lancedb_relative_paths = {}
    for source in lancedb_sources:
        # 提取文件名
        filename = os.path.basename(source)
        # 也存储完整路径
        lancedb_relative_paths[filename] = source
        lancedb_relative_paths[source] = source

    for paper_id, arxiv_id, md_output_path, vault_locations_json, rag_indexed in papers:
        if rag_indexed:
            already_indexed += 1
            continue

        matched = False
        matched_source = None

        # 策略 1：通过 vault_locations 匹配
        if vault_locations_json:
            try:
                vault_locations = json.loads(vault_locations_json)
                for loc in vault_locations:
                    # 检查完整路径
                    full_path = str(Path("~/Documents/ZhiweiVault").expanduser() / loc)
                    if full_path in lancedb_sources:
                        matched = True
                        matched_source = full_path
                        break
                    # 检查文件名
                    filename = os.path.basename(loc)
                    if filename in lancedb_relative_paths:
                        matched = True
                        matched_source = lancedb_relative_paths[filename]
                        break
            except json.JSONDecodeError:
                pass

        # 策略 2：通过 md_output_path 匹配
        if not matched and md_output_path:
            if md_output_path in lancedb_sources:
                matched = True
                matched_source = md_output_path
            else:
                filename = os.path.basename(md_output_path)
                if filename in lancedb_relative_paths:
                    matched = True
                    matched_source = lancedb_relative_paths[filename]

        # 策略 3：通过 arxiv_id 匹配（检查 LanceDB prefix）
        if not matched and arxiv_id:
            prefix = f"arxiv:{arxiv_id}"
            for source in lancedb_sources:
                if source.startswith(prefix) or f":{arxiv_id}:" in source:
                    matched = True
                    matched_source = source
                    break

        if matched:
            if not dry_run:
                lancedb_id = f"source:{matched_source}"
                c.execute(
                    "UPDATE papers SET rag_indexed = 1, lancedb_id = ? WHERE id = ?",
                    (lancedb_id, paper_id),
                )
            updated_count += 1
            logger.debug(f"匹配成功: paper_id={paper_id}, source={matched_source[:50]}...")

    if not dry_run:
        conn.commit()

    conn.close()

    return updated_count, already_indexed


def main():
    parser = argparse.ArgumentParser(description="更新 RAG 同步状态")
    parser.add_argument("--dry-run", action="store_true", help="干运行（不更新数据库）")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("RAG 同步状态更新")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"模式: {'干运行' if args.dry_run else '执行'}")
    logger.info("=" * 60)

    # 获取 LanceDB 论文
    lancedb_sources = get_lancedb_sources()

    if not lancedb_sources:
        logger.warning("LanceDB 中没有论文，跳过更新")
        return

    # 匹配并更新
    updated, already_indexed = match_papers(lancedb_sources, dry_run=args.dry_run)

    logger.info("")
    logger.info("=" * 60)
    logger.info("更新结果:")
    logger.info(f"  LanceDB 论文: {len(lancedb_sources)} 篇")
    logger.info(f"  本次更新: {updated} 篇")
    logger.info(f"  已标记: {already_indexed} 篇")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()