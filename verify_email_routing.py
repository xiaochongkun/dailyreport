#!/usr/bin/env python3
"""
邮件路由验证脚本

验证 TEST 和 PROD 模式的收件人路由是否正确
"""

import os
import sys

# 设置环境变量（在 import config 之前）
test_mode = sys.argv[1] if len(sys.argv) > 1 else 'test'
os.environ['EMAIL_MODE'] = test_mode
os.environ['EMAIL_DRY_RUN'] = os.getenv('EMAIL_DRY_RUN', 'false')

import config
from email_sender import send_daily_report_email_simple, send_single_trade_alert_html
from datetime import datetime
import pytz

def test_daily_email():
    """测试日报邮件路由"""
    print("\n" + "=" * 80)
    print("测试日报邮件路由")
    print("=" * 80)

    # 打印邮件配置
    config.print_email_config()

    # 准备测试日期
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    test_date = datetime.now(tz).strftime('%Y-%m-%d')

    # 发送测试日报
    print(f"\n尝试发送测试日报: {test_date}")
    success = send_daily_report_email_simple(test_date)

    if success:
        print(f"\n✅ 日报邮件发送成功")
    else:
        print(f"\n❌ 日报邮件发送失败")

    return success


def test_alert_email():
    """测试预警邮件路由"""
    print("\n" + "=" * 80)
    print("测试预警邮件路由")
    print("=" * 80)

    # 打印邮件配置
    config.print_email_config()

    # 准备测试数据（模拟净权利金预警）
    test_message_data = {
        'message_id': 999999,
        'date': datetime.now(pytz.timezone(config.REPORT_TIMEZONE)).isoformat(),
        'text': 'TEST ALERT MESSAGE - BTC OPTIONS',
    }

    test_trade_info = {
        'asset': 'BTC',
        'exchange': 'Deribit',
        'strategy': 'TEST',
        'options_count': 2,
        'options_sum': 50.0,
        'options_legs': [
            {
                'contract': 'BTC-TEST-100000-C',
                'side': 'LONG',
                'volume': 25.0,
                'price_btc': 0.05,
                'total_btc': 1.25,
                'total_usd': 100000,
                'iv': 50.0,
                'ref_spot_usd': 80000,
            },
            {
                'contract': 'BTC-TEST-90000-P',
                'side': 'SHORT',
                'volume': 25.0,
                'price_btc': 0.04,
                'total_btc': 1.0,
                'total_usd': 80000,
                'iv': 48.0,
                'ref_spot_usd': 80000,
            }
        ],
        'non_options_legs': [],
        'spot_price_derived': '$80,000',
        'ref_price_usd': 80000,
        # 净权利金字段
        'premium_paid_usd': 100000,
        'premium_received_usd': 80000,
        'net_premium_usd': -20000,
        'abs_net_premium_usd': 20000,
    }

    # 发送测试预警（模拟 premium 预警）
    print(f"\n尝试发送测试预警邮件")
    success = send_single_trade_alert_html(
        trade_info=test_trade_info,
        message_data=test_message_data,
        threshold=200,  # BTC 张数阈值
        alert_reasons=['premium'],  # 权利金预警
        lang='zh',
        test_mode=(config.EMAIL_MODE == 'test')  # 根据当前模式设置 test_mode
    )

    if success:
        print(f"\n✅ 预警邮件发送成功")
    else:
        print(f"\n❌ 预警邮件发送失败")

    return success


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("邮件路由验证脚本")
    print("=" * 80)
    print(f"\nCurrent EMAIL_MODE: {config.EMAIL_MODE}")
    print(f"Current EMAIL_DRY_RUN: {config.EMAIL_DRY_RUN}")
    print(f"Current TEST_RECIPIENTS: {config.TEST_RECIPIENTS}")
    print(f"Current PROD_RECIPIENTS: {config.PROD_RECIPIENTS}")

    # 检查邮件是否启用
    if not config.EMAIL_ENABLED:
        print("\n⚠️ 邮件发送未启用 (EMAIL_ENABLED=false)")
        print("请设置 EMAIL_ENABLED=true 后再测试")
        return

    # 测试日报邮件
    test_daily_email()

    # 测试预警邮件
    test_alert_email()

    print("\n" + "=" * 80)
    print("验证完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
