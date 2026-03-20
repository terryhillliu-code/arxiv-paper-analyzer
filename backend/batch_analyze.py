"""批量论文分析脚本。

自动处理未分析的论文，带资源监控和限流。
支持并行处理加速，使用写入队列避免数据库锁竞争。
"""

import asyncio
import gc
import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker
from app.models import Paper
from app.services.write_service import db_write_service
from app.utils.resource_monitor import resource_monitor
from sqlalchemy import func, select

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_unanalyzed_papers(limit: int = 100) -> list[Paper]:
    """获取未分析的论文"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Paper)
            .where(Paper.has_analysis == False)
            .order_by(Paper.publish_date.desc())
            .limit(limit)
        )
        return result.scalars().all()


async def get_unanalyzed_count() -> int:
    """获取未分析论文数量"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(func.count()).select_from(Paper).where(Paper.has_analysis == False)
        )
        return result.scalar() or 0


async def get_analyzed_count() -> int:
    """获取已分析论文数量"""
    async with async_session_maker() as db:
        from sqlalchemy import func
        result = await db.execute(
            select(func.count()).select_from(Paper).where(Paper.has_analysis == True)
        )
        return result.scalar() or 0


async def continuous_analyze(check_interval: float = 30.0):
    """持续分析模式 - 并行版本（使用写入队列）

    架构：
    - 多个 Worker 并行调用 API
    - 写入队列串行化数据库提交
    - 无锁竞争，高吞吐量
    """
    from app.tasks.analysis_task import AnalysisTaskHandler
    from sqlalchemy import func

    logger.info("=" * 60)
    logger.info("持续分析模式启动（并行版 - 写入队列架构）")
    logger.info("=" * 60)

    # 启动写入服务
    await db_write_service.start()
    logger.info("✅ 写入队列服务已启动")

    total_success = 0
    total_fail = 0
    start_time = time.time()

    async def process_paper(paper):
        """处理单篇论文"""
        try:
            logger.info(f"📄 开始处理: {paper.title[:50]}...")

            # 创建模拟任务对象
            class MockTask:
                def __init__(self, paper_id):
                    self.id = f"parallel_{paper_id}_{int(time.time())}"
                    self.task_type = "analysis"
                    self.payload = {
                        "paper_id": paper_id,
                        "use_mineru": False,
                        "force_refresh": False,
                    }

            class MockQueue:
                def update_task(self, task_id, **kwargs):
                    pass  # 忽略进度更新

            task = MockTask(paper.id)
            result = await AnalysisTaskHandler.handle(task, MockQueue())

            if result.get("status") == "completed":
                logger.info(f"✅ 完成: {paper.title[:40]}")
                return True
            else:
                logger.warning(f"⚠️ 跳过: {result}")
                return False

        except Exception as e:
            logger.error(f"❌ 失败 [{paper.id}]: {e}")
            return False

    # 并行配置
    max_concurrent = 3  # 并发数（降低以减少系统负载）

    while True:
        # 获取未分析论文
        papers = await get_unanalyzed_papers(limit=max_concurrent * 2)

        if not papers:
            logger.info("🎉 所有论文已分析完成！")
            break

        # 检查资源
        status = resource_monitor.check_resources()
        unanalyzed_count = await get_unanalyzed_count()
        analyzed_count = await get_analyzed_count()
        total = analyzed_count + unanalyzed_count

        logger.info(f"\n{'='*60}")
        logger.info(f"待分析: {unanalyzed_count} 篇 | 进度: {analyzed_count}/{total} ({analyzed_count/total*100:.1f}%)")
        logger.info(f"资源: {resource_monitor.get_status_string()} | 并发: {max_concurrent}")

        if not status.is_safe:
            logger.warning(f"资源紧张，等待恢复...")
            await resource_monitor.wait_for_resources(max_wait=60.0)

        # 并行处理
        batch_start = time.time()
        tasks = [process_paper(p) for p in papers[:max_concurrent]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_success = sum(1 for r in results if r is True)
        batch_fail = len(results) - batch_success
        total_success += batch_success
        total_fail += batch_fail

        batch_time = time.time() - batch_start
        throughput = len(results) / batch_time if batch_time > 0 else 0

        # 写入服务状态
        write_stats = db_write_service.get_stats()

        logger.info(f"本轮: ✅{batch_success} ❌{batch_fail} | 吞吐: {throughput:.2f}/s | 耗时: {batch_time:.1f}s")
        logger.info(f"写入队列: {write_stats}")

        # 刷新日志
        for handler in logging.root.handlers:
            handler.flush()

        gc.collect()

        # 短暂休息
        await asyncio.sleep(0.5)

    # 统计
    total_time = time.time() - start_time
    avg_time = total_time / total_success if total_success > 0 else 0

    logger.info(f"\n{'='*60}")
    logger.info("全部完成！")
    logger.info(f"成功: {total_success}, 失败: {total_fail}")
    logger.info(f"总耗时: {total_time/3600:.1f} 小时")
    logger.info(f"平均每篇: {avg_time:.1f} 秒")
    logger.info("=" * 60)

    # 停止写入服务
    db_write_service.stop()


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="批量论文分析")
    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=10,
        help="每批处理数量 (默认: 10)",
    )
    parser.add_argument(
        "--continuous", "-c",
        action="store_true",
        help="持续分析模式",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=5.0,
        help="每篇论文处理后的休息时间 (默认: 5秒)",
    )

    args = parser.parse_args()

    if args.continuous:
        asyncio.run(continuous_analyze())
    else:
        # 批量模式也使用写入队列
        asyncio.run(batch_analyze_with_queue(batch_size=args.batch))


async def batch_analyze_with_queue(batch_size: int = 10):
    """批量分析模式（使用写入队列）"""
    from app.tasks.analysis_task import AnalysisTaskHandler

    logger.info("=" * 60)
    logger.info(f"批量分析模式启动（{batch_size} 篇）")
    logger.info("=" * 60)

    # 启动写入服务
    await db_write_service.start()

    # 获取未分析论文
    papers = await get_unanalyzed_papers(limit=batch_size)
    logger.info(f"找到 {len(papers)} 篇待分析论文")

    if not papers:
        logger.info("没有待分析的论文")
        db_write_service.stop()
        return

    async def process_paper(paper):
        class MockTask:
            def __init__(self, paper_id):
                self.id = f"batch_{paper_id}"
                self.task_type = "analysis"
                self.payload = {"paper_id": paper_id, "use_mineru": False, "force_refresh": False}

        class MockQueue:
            def update_task(self, task_id, **kwargs):
                pass

        return await AnalysisTaskHandler.handle(MockTask(paper.id), MockQueue())

    # 并行处理
    start_time = time.time()
    results = await asyncio.gather(*[process_paper(p) for p in papers], return_exceptions=True)

    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "completed")
    fail = len(results) - success

    logger.info(f"完成: ✅{success} ❌{fail} | 耗时: {time.time()-start_time:.1f}s")

    db_write_service.stop()


if __name__ == "__main__":
    main()