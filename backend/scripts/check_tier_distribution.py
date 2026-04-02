"""
Tier 分布监控脚本
每日运行，检测异常并报警

使用方法:
    python scripts/check_tier_distribution.py
    python scripts/check_tier_distribution.py --alert  # 启用飞书告警

预期分布:
    A: 0-20%
    B: 30-40%
    C: 40-55%
"""
import sys
sys.path.insert(0, '/Users/liufang/arxiv-paper-analyzer/backend')

import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy import text
from app.database import async_session_maker
from app.services.guardrails import analysis_guardrail

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def send_alert(message: str, alert_type: str = "tier_distribution"):
    """发送告警通知

    Args:
        message: 告警内容
        alert_type: 告警类型

    可以扩展为：
    - 飞书通知
    - 钉钉通知
    - 邮件通知
    """
    # 记录到告警日志
    alert_log_path = "/Users/liufang/logs/tier_alerts.log"
    try:
        with open(alert_log_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [{alert_type}] {message}\n")
        logger.info(f"告警已记录到: {alert_log_path}")
    except Exception as e:
        logger.warning(f"告警日志写入失败: {e}")

    # TODO: 添加飞书/钉钉通知
    # 可以调用 ~/zhiwei-bot 的飞书接口


async def check_tier_distribution():
    """检查 Tier 分布是否符合预期"""
    async with async_session_maker() as db:
        result = await db.execute(text("""
            SELECT tier, COUNT(*) as count
            FROM papers
            WHERE tier IS NOT NULL
            GROUP BY tier
            ORDER BY tier
        """))

        tiers = {row.tier: row.count for row in result}
        total = sum(tiers.values())

        if total == 0:
            print("⚠️ 暂无 Tier 数据")
            return True

        print("=== Tier 分布报告 ===")
        print(f"总样本数: {total}")
        print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # 使用防护层进行 Tier 分布检查
        guard_result = analysis_guardrail.tier_distribution_check(tiers, total)

        expected = {'A': (0, 20), 'B': (30, 40), 'C': (40, 55)}

        for tier in ['A', 'B', 'C']:
            count = tiers.get(tier, 0)
            pct = count / total * 100
            low, high = expected[tier]

            status = "✅" if low <= pct <= high else "⚠️"
            print(f"Tier {tier}: {pct:.1f}% ({count}/{total}) {status} 预期 {low}-{high}%")

        # 打印详细信息
        print()
        print("=== 详细统计 ===")
        for tier in ['A', 'B', 'C']:
            count = tiers.get(tier, 0)
            print(f"  {tier} 类论文: {count} 篇")

        # 处理警告
        if guard_result.warnings:
            print()
            print("🚨 异常警报:")
            for warning in guard_result.warnings:
                print(f"  - {warning}")

            # 发送告警
            alert_message = "\n".join(guard_result.warnings)
            send_alert(alert_message, "tier_distribution")

            print()
            print("建议操作:")
            print("  1. 检查 Prompt 中的 Tier 标准")
            print("  2. 抽查异常论文的 Tier 评估")
            print("  3. 调整 Prompt 量化指标")
            print("  4. 查看 ~/logs/tier_alerts.log 了解历史告警")

            return False
        else:
            print()
            print("✅ 分布正常")
            return True


async def check_data_quality():
    """抽查数据质量，检测是否有捏造"""
    async with async_session_maker() as db:
        # 检查 outline 是否过于简单（可能是捏造）
        result = await db.execute(text("""
            SELECT id, arxiv_id, analysis_json
            FROM papers
            WHERE analysis_json IS NOT NULL
            ORDER BY id DESC
            LIMIT 5
        """))

        print("\n=== 数据质量抽查 ===")
        print("检查最近 5 条记录的 outline...")

        issues = []
        for row in result:
            analysis_json = row.analysis_json
            # 检查是否有明显的捏造特征
            if analysis_json:
                # 解析 JSON（可能是字符串或字典）
                if isinstance(analysis_json, str):
                    try:
                        analysis_json = json.loads(analysis_json)
                    except json.JSONDecodeError:
                        continue

                outline = analysis_json.get('outline', '') if isinstance(analysis_json, dict) else ''

                # 检查是否包含公式符号（摘要模式不应有）
                if outline and ('$' in str(outline) or '\\[' in str(outline)):
                    issues.append(f"ID {row.id}: 包含公式符号（可能是捏造）")

                # 检查 outline 结构是否过于简单
                if outline and len(str(outline)) < 100:
                    issues.append(f"ID {row.id}: outline 过短 ({len(str(outline))} 字符)")

        if issues:
            print("⚠️ 发现潜在问题:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("✅ 数据质量正常")

        return len(issues) == 0


async def main():
    """主函数"""
    print("=" * 50)
    print("Tier 通胀与数据质量监控")
    print("=" * 50)

    tier_ok = await check_tier_distribution()
    data_ok = await check_data_quality()

    print()
    print("=" * 50)
    if tier_ok and data_ok:
        print("✅ 所有检查通过")
    else:
        print("⚠️ 存在问题，需要人工检查")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())