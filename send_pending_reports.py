#!/usr/bin/env python3
"""
手动发送待发送的日报邮件
"""
import asyncio
from datetime import datetime
from report_generator import send_pending_daily_reports

async def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始发送待发送的日报...")

    try:
        await send_pending_daily_reports()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 邮件发送完成！")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ 邮件发送失败: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
