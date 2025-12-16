"""
定时任务调度器
使用 APScheduler 管理定时任务（如每日报告）
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import config
from report_generator import generate_daily_report, send_pending_daily_reports


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
            func=generate_daily_report,
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
            func=send_pending_daily_reports,
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

        print(f"✓ 定时任务已设置")
        for idx, job in enumerate(self.jobs, 1):
            trigger_info = str(job.trigger)
            print(f"  [{idx}] {job.name}")
            print(f"      触发器: {trigger_info}")

    def start(self):
        """启动调度器"""
        self.scheduler.start()
        print(f"✓ 调度器已启动")

        for job in self.jobs:
            next_run = job.next_run_time
            if next_run:
                print(f"  {job.name}: 下次执行时间 {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    def stop(self):
        """停止调度器（幂等）"""
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                print(f"✓ 调度器已停止")
        except Exception:
            pass

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
