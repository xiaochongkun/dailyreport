"""
定时任务调度器
使用 APScheduler 管理定时任务（如每日报告）
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import asyncio
from datetime import datetime
from functools import wraps
import sqlite3
import config
from report_generator import generate_daily_report, send_pending_daily_reports


def retry_on_db_lock(max_retries=5, initial_delay=60):
    """
    装饰器：在数据库锁定时重试
    用于处理 DELETE journal mode 下的并发写入冲突

    Args:
        max_retries: 最大重试次数（默认5次，覆盖约7分钟）
        initial_delay: 初始延迟秒数（默认60秒，指数退避：1min, 2min, 4min）

    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Debug: 验证 wrapper 是否被调用
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER_RETRY] wrapper_invoked func={func.__name__} args={args} kwargs={kwargs}")

            delay = initial_delay
            last_error = None

            for attempt in range(1, max_retries + 1):
                try:
                    result = await func(*args, **kwargs)

                    # 如果之前有重试，记录成功
                    if attempt > 1:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER_RETRY] success attempt={attempt}/{max_retries}")

                    return result

                except Exception as e:
                    last_error = e

                    # 检查是否为数据库锁定错误
                    error_str = str(e).lower()
                    is_lock_error = (
                        isinstance(e, sqlite3.OperationalError) or
                        'readonly database' in error_str or
                        'database is locked' in error_str or
                        'attempt to write a readonly database' in error_str or
                        'operationalerror' in error_str
                    )

                    if is_lock_error and attempt < max_retries:
                        # 记录重试信息
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER_RETRY] db_lock_detected attempt={attempt}/{max_retries} retry_in={delay}s error={type(e).__name__}")

                        # 等待后重试
                        await asyncio.sleep(delay)
                        delay *= 2  # 指数退避
                    else:
                        # 非锁定错误或达到最大重试次数
                        if is_lock_error:
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER_RETRY] max_retries_reached attempts={max_retries} error={type(e).__name__}")
                        raise

            # 理论上不应该到这里，但为了保险
            if last_error:
                raise last_error

        return wrapper
    return decorator


# 包装报告生成函数，添加数据库锁重试逻辑
@retry_on_db_lock(max_retries=5, initial_delay=60)
async def generate_daily_report_with_retry(target_date=None):
    """
    生成每日报告（带数据库锁重试）

    Args:
        target_date: 目标日期（可选）

    Returns:
        报告数据字典
    """
    return await generate_daily_report(target_date)


# 包装邮件发送函数，添加数据库锁重试逻辑
@retry_on_db_lock(max_retries=5, initial_delay=60)
async def send_pending_daily_reports_with_retry():
    """
    发送待发送的每日报告（带数据库锁重试）- 策略 B（体验优先）

    ⚠️ 策略变更（2025-12-21）：
    - 每天最多发送 1 封日报（只发最新 report_date）
    - 历史未发送日报不自动补发（只记录告警日志）

    Returns:
        发送结果
    """
    # 记录 job 启动
    import inspect
    from datetime import datetime
    module = send_pending_daily_reports.__module__
    file = inspect.getfile(send_pending_daily_reports)
    line = inspect.getsourcelines(send_pending_daily_reports)[1]
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHED_JOB] id=daily_report_send func=send_pending_daily_reports module={module} file={file} line={line}")

    return await send_pending_daily_reports()


class TaskScheduler:
    """任务调度器类"""

    def __init__(self):
        """初始化调度器"""
        self.scheduler = AsyncIOScheduler(timezone=config.REPORT_TIMEZONE)
        self.jobs = []

    def setup(self):
        """设置定时任务"""
        # 任务 1: 每日报告生成（东八区 16:00）
        daily_report_job = self.scheduler.add_job(
            func=generate_daily_report_with_retry,
            trigger=CronTrigger(
                hour=config.REPORT_HOUR,
                minute=config.REPORT_MINUTE,
                timezone=pytz.timezone(config.REPORT_TIMEZONE)
            ),
            id='daily_report_generate',
            name='每日报告生成',
            replace_existing=True
        )

        self.jobs.append(daily_report_job)

        # 任务 2: 每日报告邮件发送（东八区 16:05）
        # 解析 EMAIL_SEND_TIME 配置 (格式: HH:MM)
        send_hour, send_minute = map(int, config.EMAIL_SEND_TIME.split(':'))

        daily_email_job = self.scheduler.add_job(
            func=send_pending_daily_reports_with_retry,
            trigger=CronTrigger(
                hour=send_hour,
                minute=send_minute,
                timezone=pytz.timezone(config.REPORT_TIMEZONE)
            ),
            id='daily_report_send',
            name='每日报告邮件发送',
            replace_existing=True
        )

        self.jobs.append(daily_email_job)

        # 任务 3: 系统心跳（每 5 分钟）
        def system_heartbeat():
            from datetime import datetime
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SYSTEM] alive")

        heartbeat_job = self.scheduler.add_job(
            func=system_heartbeat,
            trigger='interval',
            minutes=5,
            id='system_heartbeat',
            name='系统心跳',
            replace_existing=True
        )

        self.jobs.append(heartbeat_job)

        # 结构化日志：任务注册证据
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] setup_start jobs_count={len(self.jobs)}")

        for job in self.jobs:
            # 提取触发器关键信息
            trigger_str = str(job.trigger)
            func_name = job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)

            # 提取时间信息（如果是 CronTrigger）
            if hasattr(job.trigger, 'hour') and hasattr(job.trigger, 'minute'):
                time_info = f"{job.trigger.hour:02d}:{job.trigger.minute:02d}"
            else:
                time_info = "interval"

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] job_registered id={job.id} func={func_name} trigger={trigger_str} time={time_info}")

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] setup_complete jobs_count={len(self.jobs)}")

    def start(self):
        """启动调度器"""
        self.scheduler.start()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] started")

        for job in self.jobs:
            next_run = job.next_run_time
            if next_run:
                next_run_str = next_run.strftime('%Y-%m-%d %H:%M:%S %Z')
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] job_next_run id={job.id} name={job.name} next_run={next_run_str}")

    def stop(self):
        """停止调度器（幂等）"""
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] stopped")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] stop_error err={str(e)}")

    def list_jobs(self):
        """列出所有任务"""
        print("\n当前定时任务:")
        print("=" * 60)
        for job in self.scheduler.get_jobs():
            print(f"ID: {job.id}")
            print(f"名称: {job.name}")
            print(f"触发器: {job.trigger}")
            print(f"下次执行: {job.next_run_time}")
            print("-" * 60)

    def trigger_daily_report_now(self):
        """立即触发每日报告（用于测试）"""
        print("\n手动触发每日报告...")
        job = self.scheduler.get_job('daily_report')
        if job:
            job.modify(next_run_time=None)  # 立即执行
            print("✓ 报告将在几秒内生成")
        else:
            print("✗ 找不到每日报告任务")


if __name__ == '__main__':
    """测试调度器"""
    import asyncio
    from datetime import datetime

    async def test_scheduler():
        """测试调度器功能"""
        print("=" * 60)
        print("测试定时任务调度器")
        print("=" * 60)

        # 创建调度器
        scheduler = TaskScheduler()
        scheduler.setup()
        scheduler.start()

        # 列出任务
        scheduler.list_jobs()

        # 保持运行 10 秒
        print("\n调度器将运行 10 秒...")
        await asyncio.sleep(10)

        # 停止调度器
        scheduler.stop()

    asyncio.run(test_scheduler())
