#!/usr/bin/env python3
"""智能调度器。

监控Tier重新评估进度，完成后启动Worker处理剩余论文。
"""

import subprocess
import time
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

LOG_FILE = Path("logs/retier.log")


def check_retier_status():
    """检查Tier重新评估是否完成"""
    if not LOG_FILE.exists():
        return False, 0, 0

    content = LOG_FILE.read_text()

    # 检查是否完成
    if "重新评估完成" in content:
        return True, 100, 0

    # 获取进度
    import re
    matches = re.findall(r"进度: (\d+)/(\d+)", content)
    if matches:
        current, total = matches[-1]
        return False, int(current), int(total)

    return False, 0, 0


def get_tier_distribution():
    """获取当前Tier分布"""
    import sqlite3
    try:
        conn = sqlite3.connect('data/papers.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tier, COUNT(*)
            FROM papers
            WHERE has_analysis = 1 AND tier IS NOT NULL
            GROUP BY tier
        ''')
        tiers = dict(cursor.fetchall())
        conn.close()
        return tiers
    except:
        return {}


def start_worker():
    """启动Worker处理剩余论文"""
    logger.info("启动Worker处理剩余论文...")
    subprocess.Popen(
        ["source venv/bin/activate && python scripts/task_worker.py --concurrent 3"],
        shell=True,
        start_new_session=True,
    )


def main():
    logger.info("=" * 50)
    logger.info("智能调度器启动")
    logger.info("=" * 50)

    last_progress = 0

    while True:
        completed, current, total = check_retier_status()
        tiers = get_tier_distribution()

        # 计算百分比
        if total > 0:
            pct = current / total * 100
        else:
            pct = 0

        # 打印进度（每10%打印一次）
        if int(pct / 10) > int(last_progress / 10):
            tier_str = ", ".join([f"{k}:{v}" for k, v in tiers.items()])
            logger.info(f"Tier评估进度: {pct:.1f}% ({current}/{total}) | 分布: {tier_str}")
            last_progress = pct

        if completed:
            logger.info("=" * 50)
            logger.info("Tier重新评估完成!")

            # 打印最终分布
            total_tier = sum(tiers.values())
            if total_tier > 0:
                logger.info("最终Tier分布:")
                for tier in ['A', 'B', 'C']:
                    count = tiers.get(tier, 0)
                    pct = count / total_tier * 100
                    logger.info(f"  Tier {tier}: {count} ({pct:.1f}%)")

            # 启动Worker
            start_worker()

            # 等待并验证
            time.sleep(5)
            result = subprocess.run(
                ["pgrep", "-f", "task_worker"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                logger.info(f"Worker已启动 (PID: {result.stdout.strip()})")
            else:
                logger.warning("Worker启动失败，请手动启动")

            break

        time.sleep(30)  # 每30秒检查一次


if __name__ == "__main__":
    main()