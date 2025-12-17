#!/usr/bin/env python3
"""
测试脚本：手动触发报告生成以验证重试装饰器是否被调用
"""
import asyncio
from datetime import datetime, timedelta
from scheduler import generate_daily_report_with_retry

async def test_report_generation():
    """测试报告生成（使用昨天的日期以避免冲突）"""
    print("=" * 60)
    print("测试重试装饰器")
    print("=" * 60)

    # 使用昨天的日期进行测试
    target_date = datetime.now() - timedelta(days=1)
    print(f"目标日期: {target_date.strftime('%Y-%m-%d')}")
    print()

    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始调用 generate_daily_report_with_retry()...")
        result = await generate_daily_report_with_retry(target_date=target_date)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ 报告生成成功")
        print(f"结果: {result}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ 报告生成失败")
        print(f"错误: {type(e).__name__}: {e}")

if __name__ == '__main__':
    asyncio.run(test_report_generation())
