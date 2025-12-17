#!/usr/bin/env python3
"""
验证 PM2 重启后的 APScheduler 作业注册情况
"""
import asyncio
from datetime import datetime
from scheduler import TaskScheduler

async def main():
    print("=" * 60)
    print("验证 PM2 清理重启后的作业注册")
    print("=" * 60)
    print()

    # 创建新的调度器实例（模拟 PM2 启动行为）
    scheduler = TaskScheduler()
    scheduler.setup()
    scheduler.start()

    print(f"总计注册作业数: {len(scheduler.scheduler.get_jobs())}")
    print()

    # 检查每日报告生成作业
    job = scheduler.scheduler.get_job('daily_report_generate')
    if job:
        print("【每日报告生成作业】")
        print(f"  作业 ID: {job.id}")
        print(f"  作业名称: {job.name}")
        print(f"  作业函数: {job.func}")
        print(f"  函数名称: {job.func.__name__}")
        print(f"  函数模块: {job.func.__module__}")
        print(f"  函数限定名: {job.func.__qualname__}")
        print(f"  下次运行: {job.next_run_time}")
        print(f"  触发器: {job.trigger}")
        print()

        # 检查函数签名
        import inspect
        sig = inspect.signature(job.func)
        print(f"  函数签名: {sig}")

        # 检查函数源码位置
        try:
            source_file = inspect.getsourcefile(job.func)
            source_lines = inspect.getsourcelines(job.func)[1]
            print(f"  源码文件: {source_file}")
            print(f"  源码行号: {source_lines}")
        except Exception as e:
            print(f"  无法获取源码: {e}")

        print()

        # 关键验证：函数是否是装饰器包装后的版本
        if job.func.__name__ == 'generate_daily_report_with_retry':
            if job.func.__module__ == 'scheduler':
                print("✅ 验证通过：作业使用带重试装饰器的函数")
            else:
                print(f"⚠️  警告：函数名正确但模块错误 ({job.func.__module__})")
        else:
            print(f"❌ 验证失败：作业使用未包装的函数 ({job.func.__name__})")
    else:
        print("❌ 未找到每日报告生成作业")

    # 停止调度器
    scheduler.stop()

    print()
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(main())
