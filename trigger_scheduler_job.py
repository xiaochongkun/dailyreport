#!/usr/bin/env python3
"""
测试脚本：通过 APScheduler 触发报告生成以验证重试装饰器
"""
import asyncio
from datetime import datetime
from scheduler import TaskScheduler
import config

async def trigger_job():
    """通过 APScheduler 手动触发任务"""
    print("=" * 60)
    print("通过 APScheduler 触发报告生成任务")
    print("=" * 60)
    print()

    # 创建调度器实例
    scheduler = TaskScheduler()
    scheduler.setup()
    scheduler.start()

    print("调度器已启动，等待 2 秒...")
    await asyncio.sleep(2)

    # 手动触发 daily_report_generate 任务
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 手动触发任务 'daily_report_generate'...")
    job = scheduler.scheduler.get_job('daily_report_generate')

    if job:
        print(f"✓ 找到任务: {job.name}")
        print(f"  当前下次执行时间: {job.next_run_time}")

        # 立即执行（将 next_run_time 设为 None 会立即触发）
        job.modify(next_run_time=datetime.now())
        print(f"✓ 已修改为立即执行")

        # 等待任务执行完成（给足够时间）
        print("\n等待任务执行...")
        await asyncio.sleep(10)
    else:
        print("✗ 未找到任务 'daily_report_generate'")
        scheduler.list_jobs()

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 测试完成")
    scheduler.stop()

if __name__ == '__main__':
    asyncio.run(trigger_job())
