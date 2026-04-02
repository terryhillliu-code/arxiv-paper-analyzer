#!/usr/bin/env python3
"""使用 OAI-PMH 协议回填历史论文。

OAI-PMH 可以获取 ArXiv 历史数据，突破 API 的日期限制。
"""

import asyncio
import logging
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.services.paper_scorer import PaperScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OAI_BASE_URL = "http://export.arxiv.org/oai2"


@dataclass
class OaiPaper:
    """OAI-PMH 论文数据"""
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    publish_date: datetime
    pdf_url: str


async def fetch_oai_records(
    date_from: str,
    date_to: str,
    set_spec: str = "cs",
    delay: float = 3.0,
) -> List[OaiPaper]:
    """从 OAI-PMH 获取论文记录。

    Args:
        date_from: 开始日期 (YYYY-MM-DD)
        date_to: 结束日期 (YYYY-MM-DD)
        set_spec: 分类集合 (cs = 计算机科学)
        delay: 请求间隔

    Returns:
        论文列表
    """
    papers = []
    resumption_token = None

    params = {
        "verb": "ListRecords",
        "from": date_from,
        "until": date_to,
        "set": set_spec,
        "metadataPrefix": "arXiv",
    }

    page = 0
    total_records = 0

    while True:
        page += 1

        if resumption_token:
            params = {
                "verb": "ListRecords",
                "resumptionToken": resumption_token,
            }

        logger.info(f"获取第 {page} 页...")

        try:
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(OAI_BASE_URL, params=params) as resp:
                    if resp.status != 200:
                        logger.error(f"HTTP 错误: {resp.status}")
                        break

                    text = await resp.text()
                    root = ET.fromstring(text)

                    # 检查错误
                    error = root.find('.//{http://www.openarchives.org/OAI/2.0/}error')
                    if error is not None:
                        logger.error(f"OAI 错误: {error.text}")
                        break

                    # 解析记录
                    records = root.findall('.//{http://www.openarchives.org/OAI/2.0/}record')

                    for record in records:
                        try:
                            paper = parse_oai_record(record)
                            if paper:
                                papers.append(paper)
                                total_records += 1
                        except Exception as e:
                            logger.debug(f"解析记录失败: {e}")

                    logger.info(f"本页 {len(records)} 条，累计 {total_records} 条")

                    # 获取下一页 token
                    token_elem = root.find('.//{http://www.openarchives.org/OAI/2.0/}resumptionToken')
                    if token_elem is not None and token_elem.text:
                        resumption_token = token_elem.text
                        logger.info(f"等待 {delay} 秒后继续...")
                        await asyncio.sleep(delay)
                    else:
                        logger.info("所有数据获取完成")
                        break

        except asyncio.TimeoutError:
            logger.error("请求超时")
            break
        except Exception as e:
            logger.error(f"请求失败: {e}")
            break

    return papers


def parse_oai_record(record: ET.Element) -> Optional[OaiPaper]:
    """解析 OAI-PMH 记录"""
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "arxiv": "http://arxiv.org/OAI/arXiv/",
    }

    # 获取 arXiv ID
    identifier = record.find(".//oai:identifier", ns)
    if identifier is None or not identifier.text:
        return None

    arxiv_id = identifier.text.replace("oai:arXiv.org:", "")

    # 获取元数据
    metadata = record.find(".//arxiv:arXiv", ns)
    if metadata is None:
        return None

    # 标题
    title_elem = metadata.find("arxiv:title", ns)
    title = title_elem.text if title_elem is not None else ""

    # 作者
    authors = []
    for author in metadata.findall(".//arxiv:author", ns):
        name = author.find("arxiv:keyname", ns)
        forenames = author.find("arxiv:forenames", ns)
        if name is not None:
            author_name = name.text
            if forenames is not None and forenames.text:
                author_name = f"{forenames.text} {author_name}"
            authors.append(author_name)

    # 摘要
    abstract_elem = metadata.find("arxiv:abstract", ns)
    abstract = abstract_elem.text.strip() if abstract_elem is not None and abstract_elem.text else ""

    # 分类
    categories = []
    for cat in metadata.findall("arxiv:categories", ns):
        if cat.text:
            categories.extend(cat.text.split())

    # 创建日期
    created = metadata.find("arxiv:created", ns)
    publish_date = None
    if created is not None and created.text:
        try:
            publish_date = datetime.strptime(created.text, "%Y-%m-%d")
        except ValueError:
            pass

    # PDF URL
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    return OaiPaper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        categories=categories,
        publish_date=publish_date,
        pdf_url=pdf_url,
    )


async def save_papers(papers: List[OaiPaper], prefilter: bool = True) -> int:
    """保存论文到数据库

    Args:
        papers: 论文列表
        prefilter: 是否启用预筛选（默认 True）
    """
    if not papers:
        return 0

    async with async_session_maker() as db:
        added = 0
        skipped = 0

        for paper in papers:
            # 检查是否已存在
            existing = await db.execute(
                select(Paper).where(Paper.arxiv_id == paper.arxiv_id)
            )
            if existing.scalar_one_or_none():
                continue

            # 预筛选：评估论文重要性
            if prefilter:
                if not PaperScorer.should_fetch(paper.title, paper.abstract, paper.authors):
                    skipped += 1
                    logger.debug(f"跳过低分论文: {paper.title[:40]}...")
                    continue

            # 计算评分和 Tier
            score = PaperScorer.score(paper.title, paper.abstract, paper.authors)
            initial_tier = PaperScorer.get_initial_tier(score)

            # 创建论文记录
            db_paper = Paper(
                arxiv_id=paper.arxiv_id,
                title=paper.title.strip(),
                authors=paper.authors,
                abstract=paper.abstract,
                categories=paper.categories,
                publish_date=paper.publish_date,
                pdf_url=paper.pdf_url,
                arxiv_url=f"https://arxiv.org/abs/{paper.arxiv_id}",
                tier=initial_tier,
            )

            db.add(db_paper)
            added += 1

        await db.commit()
        logger.info(f"新增 {added} 篇论文，预筛选跳过 {skipped} 篇")

    return added


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="OAI-PMH 回填历史论文")
    parser.add_argument("--from-date", default="2026-03-01", help="开始日期")
    parser.add_argument("--to-date", default="2026-03-09", help="结束日期")
    parser.add_argument("--delay", type=float, default=3.0, help="请求间隔")
    parser.add_argument("--no-prefilter", action="store_true", help="禁用预筛选（全量抓取）")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OAI-PMH 论文回填")
    logger.info(f"日期范围: {args.from_date} ~ {args.to_date}")
    logger.info(f"预筛选: {'禁用' if args.no_prefilter else '启用'}")
    logger.info("=" * 60)

    papers = await fetch_oai_records(
        date_from=args.from_date,
        date_to=args.to_date,
        delay=args.delay,
    )

    logger.info(f"获取到 {len(papers)} 篇论文")

    if papers:
        added = await save_papers(papers, prefilter=not args.no_prefilter)
        logger.info(f"入库 {added} 篇")


if __name__ == "__main__":
    asyncio.run(main())