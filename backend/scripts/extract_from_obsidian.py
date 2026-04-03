#!/usr/bin/env python3
"""从 Obsidian 文件中提取分析数据，填充历史论文数据库。

历史论文已有完整的 Markdown 分析文件，但数据库缺少 analysis_json 和 analysis_report。
这个脚本从 Markdown 文件中提取数据，更新数据库。
"""

import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def extract_frontmatter(content: str) -> dict:
    """提取 YAML frontmatter"""
    if not content.startswith('---'):
        return {}

    end_idx = content.find('---', 3)
    if end_idx == -1:
        return {}

    try:
        frontmatter_text = content[3:end_idx].strip()
        return yaml.safe_load(frontmatter_text)
    except Exception as e:
        logger.warning(f"解析 frontmatter 失败: {e}")
        return {}


def extract_one_line_summary(content: str) -> str:
    """提取一句话总结"""
    match = re.search(r'## 💡 一句话总结\s*\n+(.+?)(?=\n#|\n##|\Z)', content, re.DOTALL)
    if match:
        summary = match.group(1).strip()
        # 清理 markdown 格式
        summary = re.sub(r'\*\*(.+?)\*\*', r'\1', summary)
        return summary[:200] if len(summary) > 200 else summary
    return ""


def extract_report(content: str) -> str:
    """提取完整报告（从"学术论文深度分析报告"开始）"""
    start_marker = "# 学术论文深度分析报告"
    start_idx = content.find(start_marker)
    if start_idx > 0:
        return content[start_idx:].strip()
    return ""


def extract_tags(frontmatter: dict) -> list:
    """提取标签"""
    tags = frontmatter.get('tags', [])
    if isinstance(tags, str):
        tags = [tags]
    return tags


def build_analysis_json(frontmatter: dict, one_line_summary: str, tags: list) -> dict:
    """构建 analysis_json"""
    tier = frontmatter.get('tier', 'B')

    return {
        "tier": tier,
        "tags": tags,
        "one_line_summary": one_line_summary,
        "key_contributions": [],
        "outline": [],
        "methodology": frontmatter.get('methodology', ''),
    }


def process_historical_papers(batch_size: int = 100, dry_run: bool = False):
    """处理历史论文

    Args:
        batch_size: 每批处理数量
        dry_run: 仅检查不执行
    """
    conn = sqlite3.connect('data/papers.db')
    c = conn.cursor()

    # 查询待处理的历史论文
    c.execute('''
        SELECT id, arxiv_id, md_output_path, title
        FROM papers
        WHERE analysis_mode = "historical"
        AND analysis_json IS NULL
        AND md_output_path IS NOT NULL
        LIMIT ?
    ''', (batch_size,))

    papers = c.fetchall()
    logger.info(f"找到 {len(papers)} 篇待处理论文")

    if dry_run:
        for paper_id, arxiv_id, md_path, title in papers[:5]:
            logger.info(f"  [{arxiv_id}] {title[:40]}...")
            if md_path and os.path.exists(md_path):
                logger.info(f"    文件存在: {md_path[:50]}...")
        return

    updated = 0
    skipped = 0

    for paper_id, arxiv_id, md_path, title in papers:
        if not md_path or not os.path.exists(md_path):
            skipped += 1
            continue

        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取数据
            frontmatter = extract_frontmatter(content)
            one_line_summary = extract_one_line_summary(content)
            report = extract_report(content)
            tags = extract_tags(frontmatter)

            if not one_line_summary and not report:
                skipped += 1
                continue

            # 构建 analysis_json
            analysis_json = build_analysis_json(frontmatter, one_line_summary, tags)
            tier = frontmatter.get('tier', 'B')

            # 更新数据库
            import json
            c.execute('''
                UPDATE papers
                SET analysis_json = ?,
                    analysis_report = ?,
                    summary = ?,
                    tags = ?,
                    tier = ?,
                    abstract = ?,
                    has_analysis = 1
                WHERE id = ?
            ''', (
                json.dumps(analysis_json, ensure_ascii=False),
                report,
                one_line_summary,
                json.dumps(tags, ensure_ascii=False),
                tier,
                one_line_summary,  # 用一句话总结作为摘要的替代
                paper_id
            ))

            updated += 1

            if updated % 50 == 0:
                conn.commit()
                logger.info(f"已处理 {updated} 篇")

        except Exception as e:
            logger.warning(f"处理失败 {arxiv_id}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    logger.info(f"完成: 更新 {updated} 篇, 跳过 {skipped} 篇")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=500, help="每批处理数量")
    parser.add_argument("--dry-run", action="store_true", help="仅检查不执行")

    args = parser.parse_args()

    process_historical_papers(args.batch, args.dry_run)