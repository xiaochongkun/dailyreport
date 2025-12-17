#!/usr/bin/env python3
"""
生成并发送昨天的日报
"""
import asyncio
from datetime import datetime, timedelta
from scheduler import generate_daily_report_with_retry

async def main():
    # 计算昨天的日期
    yesterday = datetime.now() - timedelta(days=1)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始生成昨天的日报: {yesterday.strftime('%Y-%m-%d')}")

    try:
        result = await generate_daily_report_with_retry(target_date=yesterday)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 日报生成并发送成功！")
        if result:
            print(f"报告数据: {result}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ 日报生成失败: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
