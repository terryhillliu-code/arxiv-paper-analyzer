#!/usr/bin/env python3
"""OAI-PMH 批量抓取脚本。

使用 ArXiv 的 OAI-PMH 接口批量抓取历史论文。
比 REST API 更稳定，支持日期范围查询。
"""

import asyncio
import logging
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode
import aiohttp

# 添加项目路径
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

# OAI-PMH 端点
OAI_PMH_URL = "https://export.arxiv.org/oai2"

# 默认抓取的分类
DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]


async def fetch_oai_records(
    session: aiohttp.ClientSession,
    date_from: datetime,
    date_to: datetime,
    metadata_prefix: str = "arXiv",
    resumption_token: Optional[str] = None,
) -> tuple[List[dict], Optional[str]]:
    """从 OAI-PMH 获取记录。

    Args:
        session: aiohttp 会话
        date_from: 开始日期
        date_to: 结束日期
        metadata_prefix: 元数据格式
        resumption_token: 分页 token

    Returns:
        (记录列表, 下一页 token)
    """
    params = {
        "verb": "ListRecords",
    }

    if resumption_token:
        params["resumptionToken"] = resumption_token
    else:
        params.update({
            "metadataPrefix": metadata_prefix,
            "from": date_from.strftime("%Y-%m-%d"),
            "until": date_to.strftime("%Y-%m-%d"),
            "set": "cs",  # 计算机科学
        })

    url = f"{OAI_PMH_URL}?{urlencode(params)}"
    logger.info(f"请求: {url[:100]}...")

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
            if response.status != 200:
                text = await response.text()
                logger.warning(f"HTTP {response.status}: {text[:200]}")
                return [], None

            content = await response.text()

            # 解析 XML
            root = ET.fromstring(content)

            # 检查错误
            error = root.find(".//{http://www.openarchives.org/OAI/2.0/}error")
            if error is not None:
                logger.warning(f"OAI-PMH 错误: {error.text}")
                return [], None

            # 提取记录
            records = []
            ns = {"oai": "http://www.openarchives.org/OAI/2.0/", "arxiv": "http://arxiv.org/OAI/arXiv/"}

            for record in root.findall(".//oai:record", ns):
                try:
                    header = record.find("oai:header", ns)
                    metadata = record.find("oai:metadata/arxiv:arXiv", ns)

                    if header is None or metadata is None:
                        continue

                    # 检查是否被删除
                    if header.get("status") == "deleted":
                        continue

                    # 提取字段
                    arxiv_id = header.find("oai:identifier", ns)
                    if arxiv_id is None:
                        continue
                    arxiv_id = arxiv_id.text.replace("oai:arXiv.org:", "")

                    title_elem = metadata.find("arxiv:title", ns)
                    abstract_elem = metadata.find("arxiv:abstract", ns)
                    authors_elem = metadata.find("arxiv:authors", ns)
                    categories_elem = metadata.find("arxiv:categories", ns)
                    created_elem = metadata.find("arxiv:created", ns)

                    title = title_elem.text if title_elem is not None else ""
                    abstract = abstract_elem.text if abstract_elem is not None else ""

                    # 解析作者
                    authors = []
                    if authors_elem is not None:
                        for author in authors_elem.findall("arxiv:author", ns):
                            name = author.find("arxiv:keyname", ns)
                            forename = author.find("arxiv:forenames", ns)
                            if name is not None:
                                author_name = name.text
                                if forename is not None:
                                    author_name = f"{forename.text} {author_name}"
                                authors.append(author_name)

                    # 解析分类
                    categories = []
                    if categories_elem is not None and categories_elem.text:
                        categories = categories_elem.text.split()

                    # 解析日期
                    publish_date = None
                    if created_elem is not None and created_elem.text:
                        try:
                            publish_date = datetime.strptime(created_elem.text, "%Y-%m-%d")
                        except ValueError:
                            pass

                    # 筛选分类
                    if categories:
                        if not any(cat in DEFAULT_CATEGORIES for cat in categories):
                            continue

                    records.append({
                        "arxiv_id": arxiv_id,
                        "title": title.strip(),
                        "abstract": abstract.strip(),
                        "authors": authors,
                        "categories": categories,
                        "publish_date": publish_date,
                    })

                except Exception as e:
                    logger.warning(f"解析记录失败: {e}")
                    continue

            # 获取 resumption token
            resumption = root.find(".//oai:resumptionToken", ns)
            next_token = resumption.text if resumption is not None and resumption.text else None

            return records, next_token

    except asyncio.TimeoutError:
        logger.warning("请求超时")
        return [], None
    except Exception as e:
        logger.error(f"请求失败: {e}")
        return [], None


async def fetch_date_range(
    date_from: datetime,
    date_to: datetime,
    dry_run: bool = True,
) -> List[dict]:
    """抓取指定日期范围的所有论文。

    Args:
        date_from: 开始日期
        date_to: 结束日期
        dry_run: 是否只检查不入库

    Returns:
        抓取的论文列表
    """
    logger.info(f"抓取日期范围: {date_from.strftime('%Y-%m-%d')} 到 {date_to.strftime('%Y-%m-%d')}")
    logger.info(f"模式: {'仅检查' if dry_run else '实际入库'}")

    all_records = []
    resumption_token = None
    page = 0

    async with aiohttp.ClientSession() as session:
        while True:
            page += 1
            logger.info(f"获取第 {page} 页...")

            records, resumption_token = await fetch_oai_records(
                session,
                date_from,
                date_to,
                resumption_token=resumption_token,
            )

            if records:
                all_records.extend(records)
                logger.info(f"  获取 {len(records)} 条记录，累计 {len(all_records)} 条")

            if not resumption_token:
                break

            # 等待避免限流
            await asyncio.sleep(3)

    logger.info(f"总计获取 {len(all_records)} 条记录")

    # 检查数据库中已有论文
    async with async_session_maker() as db:
        arxiv_ids = [r["arxiv_id"] for r in all_records]
        if arxiv_ids:
            result = await db.execute(
                select(Paper.arxiv_id).where(Paper.arxiv_id.in_(arxiv_ids))
            )
            existing_ids = set(row[0] for row in result.fetchall())
        else:
            existing_ids = set()

    logger.info(f"数据库已有: {len(existing_ids)} 篇")

    # 筛选新论文并评分
    new_papers = []
    for record in all_records:
        if record["arxiv_id"] in existing_ids:
            continue

        # 评分
        score = PaperScorer.score(
            record["title"],
            record["abstract"],
            record["authors"],
        )

        if PaperScorer.should_fetch(
            record["title"],
            record["abstract"],
            record["authors"],
        ):
            record["score"] = score
            new_papers.append(record)

    logger.info(f"高质量新论文: {len(new_papers)} 篇")

    # 入库
    if not dry_run and new_papers:
        async with async_session_maker() as db:
            added = 0
            for record in new_papers:
                # 计算初始 Tier
                if record["score"] >= 60:
                    tier = "A"
                elif record["score"] >= 40:
                    tier = "B"
                else:
                    tier = "C"

                paper = Paper(
                    arxiv_id=record["arxiv_id"],
                    title=record["title"],
                    authors=record["authors"],
                    abstract=record["abstract"],
                    categories=record["categories"],
                    publish_date=record["publish_date"],
                    pdf_url=f"https://arxiv.org/pdf/{record['arxiv_id']}",
                    arxiv_url=f"https://arxiv.org/abs/{record['arxiv_id']}",
                    tier=tier,
                )
                db.add(paper)
                added += 1

            await db.commit()
            logger.info(f"成功入库 {added} 篇论文")

    return new_papers


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="OAI-PMH 批量抓取")
    parser.add_argument(
        "--date-from",
        type=str,
        required=True,
        help="开始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--date-to",
        type=str,
        required=True,
        help="结束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="实际入库（默认只检查）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OAI-PMH 批量抓取脚本")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    date_from = datetime.strptime(args.date_from, "%Y-%m-%d")
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d")

    await fetch_date_range(date_from, date_to, dry_run=not args.commit)

    logger.info("\n抓取完成!")


if __name__ == "__main__":
    asyncio.run(main())