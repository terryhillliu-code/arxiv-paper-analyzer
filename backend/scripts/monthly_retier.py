#!/usr/bin/env python3
"""每月 Tier 重新评估任务（带重试机制）。

每月第一天自动执行，失败后重试。
Tier 升级后自动创建 Full Mode 重新分析任务。

用法：
    python scripts/monthly_retier.py
    python scripts/monthly_retier.py --retry  # 手动重试
"""

import asyncio
import json
import logging
import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Paper
from app.services.ai_service import ai_service
from app.tasks.task_queue import TaskQueue, TASK_DB_PATH

# 日志配置
log_dir = Path.home() / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "monthly_retier.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# 状态文件
STATUS_FILE = Path(__file__).parent.parent / "data" / "retier_status.json"

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 300  # 5分钟


def check_reanalyze_needed(old_tier: str, new_tier: str, analysis_mode: str) -> bool:
    """检查是否需要重新分析（Full Mode）

    条件：Tier 升级且当前是 Quick Mode
    """
    if analysis_mode == "full":
        return False  # 已是 Full Mode，无需重新分析

    tier_upgrade = (old_tier == "C" and new_tier in ["A", "B"]) or \
                   (old_tier == "B" and new_tier == "A")
    return tier_upgrade


def create_reanalysis_task(paper_id: int) -> bool:
    """创建 Full Mode 重新分析任务"""
    try:
        task_queue = TaskQueue(db_path=TASK_DB_PATH, max_concurrent=6)
        task = task_queue.create_task(
            task_type="analysis",
            payload={
                "paper_id": paper_id,
                "quick_mode": False,  # Full Mode
                "force_refresh": True,
            },
        )
        if task:
            logger.info(f"创建 Full Mode 重新分析任务: paper_id={paper_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        return False


def load_status() -> dict:
    """加载状态"""
    if STATUS_FILE.exists():
        with open(STATUS_FILE) as f:
            return json.load(f)
    return {"last_run": None, "status": "never", "retries": 0, "error": None}


def save_status(status: dict):
    """保存状态"""
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2, default=str)


# Tier 评估 Prompt
TIER_PROMPT = """你是一位学术论文评审专家。根据以下标准重新评估论文的Tier。

## 论文信息
标题: {title}
摘要: {abstract}
当前Tier: {current_tier}
引用数: {citation_count}
发布日期: {publish_date}
机构: {institutions}

## Tier 评估标准（严格执行）

⚠️ **目标分布: A=15%, B=35%, C=50%**

### A 类（顶尖创新）- 占比应 < 20%
必须同时满足以下至少 2 条：
- 提出全新的方法范式或理论框架（非增量改进）
- 在主流基准上取得显著突破（提升 >10% 或首次解决关键难题）
- 顶级机构（OpenAI/DeepMind/Google/Stanford/MIT）的标志性工作
- 开创全新研究方向或解决长期未解决的难题

### B 类（有价值贡献）- 占比应 30-40%
**需要同时满足以下至少 2 条**：
- 有明确的方法创新（非简单组合或调参）
- 在特定场景下取得良好效果（有具体数据支撑）
- 提供有价值的实证研究或工具（已被验证）
- 热门方向的合理改进（有创新点）

**注意：只有 1 条满足的应评为 C 类**

### C 类（一般参考）- 占比应 40-55%
- 增量式改进（方法组合、参数调优、小范围应用）
- 应用导向研究（场景适配、系统集成）
- 初步探索或概念验证
- 工具/数据集构建
- 只有 1 条满足 B 类条件

## 输出格式
直接输出 JSON:
{{"tier": "A/B/C", "reason": "简短理由（20字内）"}}
"""


async def retier_paper(paper: Paper) -> tuple[str, str]:
    """重新评估单篇论文的Tier

    Returns:
        (new_tier, reason)
    """
    try:
        title = paper.title or ""
        abstract = paper.abstract or ""

        if len(abstract) < 100:
            return paper.tier or "B", "摘要过短"

        prompt = TIER_PROMPT.format(
            title=title[:200],
            abstract=abstract[:1500],
            current_tier=paper.tier or "B",
            citation_count=paper.citation_count or "未知",
            publish_date=str(paper.publish_date) if paper.publish_date else "未知",
            institutions=", ".join(paper.institutions) if paper.institutions else "未知",
        )

        response = await asyncio.to_thread(ai_service._call_api, prompt, 200)
        result = ai_service._parse_json(response)

        new_tier = result.get("tier", paper.tier or "B")
        reason = result.get("reason", "")

        if new_tier not in ["A", "B", "C"]:
            new_tier = paper.tier or "B"

        return new_tier, reason

    except Exception as e:
        logger.warning(f"评估失败 paper_id={paper.id}: {e}")
        return paper.tier or "B", f"评估失败: {str(e)[:30]}"


async def run_retier(batch_size: int = 50) -> dict:
    """执行重新评估

    Returns:
        {"success": bool, "processed": int, "changes": dict, "reanalyze_count": int, "error": str}
    """
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Paper)
                .where(Paper.has_analysis == True)
                .where(Paper.tier != None)
                .where(Paper.abstract != None)
                .order_by(Paper.id)
            )
            papers = result.scalars().all()

            total = len(papers)
            logger.info(f"开始重新评估 {total} 篇论文")

            changes = {"A": 0, "B": 0, "C": 0}
            new_tiers = {"A": 0, "B": 0, "C": 0}
            processed = 0
            reanalyze_count = 0
            tier_upgrades = []

            for i in range(0, total, batch_size):
                batch = papers[i:i + batch_size]

                for paper in batch:
                    old_tier = paper.tier
                    analysis_mode = paper.analysis_mode or "quick"  # 获取当前分析模式
                    new_tier, reason = await retier_paper(paper)

                    if new_tier != old_tier:
                        changes[old_tier] = changes.get(old_tier, 0) - 1
                        changes[new_tier] = changes.get(new_tier, 0) + 1
                        logger.info(f"变更: {old_tier}→{new_tier} | {paper.title[:40]}... | {reason}")

                        # 检查是否需要重新分析（Tier 升级 + Quick Mode）
                        if check_reanalyze_needed(old_tier, new_tier, analysis_mode):
                            tier_upgrades.append({
                                "paper_id": paper.id,
                                "arxiv_id": paper.arxiv_id,
                                "old_tier": old_tier,
                                "new_tier": new_tier,
                            })

                    new_tiers[new_tier] = new_tiers.get(new_tier, 0) + 1
                    processed += 1

                    if new_tier != old_tier:
                        paper.tier = new_tier

                # 提交批次
                await db.commit()

                logger.info(f"进度: {processed}/{total} | A:{new_tiers['A']} B:{new_tiers['B']} C:{new_tiers['C']}")

                # 避免API限流
                await asyncio.sleep(1)

            # 创建重新分析任务
            for upgrade in tier_upgrades:
                if create_reanalysis_task(upgrade["paper_id"]):
                    reanalyze_count += 1
                    logger.info(f"Tier 升级 {upgrade['old_tier']}→{upgrade['new_tier']}: "
                               f"{upgrade['arxiv_id']} 需要重新分析")

            logger.info(f"完成: A={new_tiers['A']} ({new_tiers['A']/total*100:.1f}%), "
                       f"B={new_tiers['B']} ({new_tiers['B']/total*100:.1f}%), "
                       f"C={new_tiers['C']} ({new_tiers['C']/total*100:.1f}%)")
            logger.info(f"Tier 升级需重新分析: {reanalyze_count} 篇")

            return {
                "success": True,
                "processed": processed,
                "changes": changes,
                "distribution": new_tiers,
                "reanalyze_count": reanalyze_count,
                "tier_upgrades": tier_upgrades,
                "error": None,
            }

    except Exception as e:
        logger.error(f"重新评估失败: {e}", exc_info=True)
        return {
            "success": False,
            "processed": 0,
            "changes": {},
            "reanalyze_count": 0,
            "error": str(e),
        }


async def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="每月 Tier 重新评估")
    parser.add_argument("--retry", action="store_true", help="强制重试（忽略重试次数）")
    parser.add_argument("--batch-size", type=int, default=50, help="批处理大小")
    args = parser.parse_args()

    status = load_status()
    now = datetime.now()

    logger.info("=" * 50)
    logger.info(f"每月 Tier 重新评估 - {now.strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"上次运行: {status.get('last_run', '从未')}")
    logger.info(f"上次状态: {status.get('status', '未知')}")
    logger.info("=" * 50)

    # 检查是否需要重试
    if status.get("status") == "failed" and not args.retry:
        if status.get("retries", 0) >= MAX_RETRIES:
            logger.error(f"已达到最大重试次数 {MAX_RETRIES}，放弃")
            return 1

    # 执行重新评估
    result = await run_retier(batch_size=args.batch_size)

    # 更新状态
    if result["success"]:
        status = {
            "last_run": now.isoformat(),
            "status": "success",
            "retries": 0,
            "processed": result["processed"],
            "changes": result["changes"],
            "distribution": result["distribution"],
            "reanalyze_count": result.get("reanalyze_count", 0),
            "error": None,
        }
        save_status(status)
        logger.info("✅ 重新评估成功")
        if result.get("reanalyze_count", 0) > 0:
            logger.info(f"📝 已创建 {result['reanalyze_count']} 个 Full Mode 重新分析任务")
        return 0
    else:
        retries = status.get("retries", 0) + 1
        status = {
            "last_run": now.isoformat(),
            "status": "failed",
            "retries": retries,
            "error": result["error"],
        }
        save_status(status)
        logger.error(f"❌ 重新评估失败 (重试 {retries}/{MAX_RETRIES})")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)