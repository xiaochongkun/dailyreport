#!/usr/bin/env python3
"""
测试脚本：发送中文预警邮件（使用历史数据）

功能：
1. 从 reports.db 查询历史数据（2025-12-11 16:00 → 2025-12-12 16:00）
2. 选择最大的 BTC 和 ETH OPTIONS 交易
3. 发送 2 封【TEST】中文预警邮件

注意：仅用于测试，不影响生产环境
"""

import sys
import os
from datetime import datetime
import pytz

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from database import get_session, Message
from report_generator import parse_block_trade_message
from email_sender import send_single_trade_alert_html


def find_largest_options_trades(start_date, end_date):
    """
    从历史数据中找到最大的 BTC 和 ETH OPTIONS 交易

    Args:
        start_date: 开始时间（timezone-aware datetime）
        end_date: 结束时间（timezone-aware datetime）

    Returns:
        (btc_trade, eth_trade) 元组，每个是 (Message对象, trade_info字典, volume)
    """
    session = get_session()
    try:
        # 查询指定时间范围内的 block trade 消息
        messages = session.query(Message).filter(
            Message.date >= start_date,
            Message.date < end_date,
            Message.is_block_trade == True
        ).all()

        print(f"\n查询到 {len(messages)} 条 block trade 消息")

        # 找到最大的 BTC 和 ETH OPTIONS 交易
        btc_options = []
        eth_options = []

        for msg in messages:
            trade_info = parse_block_trade_message(msg.text or '')

            asset = trade_info.get('asset', 'Unknown')
            instrument_type = trade_info.get('instrument_type', 'Unknown')
            volume = trade_info.get('volume', 0.0)
            exchange = trade_info.get('exchange', 'Unknown')

            # 只收集 OPTIONS 且来自 Deribit 的交易
            if instrument_type == 'OPTIONS' and exchange == config.MONITORED_EXCHANGE:
                if asset == 'BTC':
                    btc_options.append((msg, trade_info, volume))
                elif asset == 'ETH':
                    eth_options.append((msg, trade_info, volume))

        print(f"  BTC OPTIONS: {len(btc_options)} 笔")
        print(f"  ETH OPTIONS: {len(eth_options)} 笔")

        # 找到最大的 BTC OPTIONS
        btc_trade = None
        if btc_options:
            btc_trade = max(btc_options, key=lambda x: x[2])
            print(f"  最大 BTC OPTIONS: {btc_trade[2]:.1f}x (msg_id={btc_trade[0].message_id})")
        else:
            print(f"  ⚠️  未找到 BTC OPTIONS 交易")

        # 找到最大的 ETH OPTIONS
        eth_trade = None
        if eth_options:
            eth_trade = max(eth_options, key=lambda x: x[2])
            print(f"  最大 ETH OPTIONS: {eth_trade[2]:.1f}x (msg_id={eth_trade[0].message_id})")
        else:
            print(f"  ⚠️  未找到 ETH OPTIONS 交易")

        return btc_trade, eth_trade

    finally:
        session.close()


def send_test_email(msg: Message, trade_info: dict, volume: float, asset: str):
    """
    发送单个测试邮件

    Args:
        msg: Message 对象
        trade_info: 解析后的交易信息
        volume: 交易量
        asset: 资产类型 (BTC/ETH)
    """
    print(f"\n{'='*70}")
    print(f"准备发送【TEST】中文预警邮件 - {asset}")
    print(f"{'='*70}")

    print(f"\n[交易信息]")
    print(f"  Message ID: {msg.message_id}")
    print(f"  Asset: {asset}")
    print(f"  Volume: {volume:.1f}x")
    print(f"  Contract: {trade_info.get('contract', 'Unknown')}")
    print(f"  Side: {trade_info.get('side', 'Unknown')}")
    print(f"  Exchange: {trade_info.get('exchange', 'Unknown')}")
    print(f"  Date: {msg.date}")

    # 准备消息数据
    message_data = {
        'message_id': msg.message_id,
        'date': msg.date.isoformat(),
        'text': msg.text,
        'is_block_trade': msg.is_block_trade
    }

    # 设置阈值（用于显示）
    if asset == 'BTC':
        threshold = config.BTC_VOLUME_THRESHOLD
    elif asset == 'ETH':
        threshold = config.ETH_VOLUME_THRESHOLD_TEST if config.ALERT_TEST_MODE else config.ETH_VOLUME_THRESHOLD
    else:
        threshold = 0

    print(f"\n[邮件配置]")
    print(f"  语言: 中文 (lang='zh')")
    print(f"  测试模式: True (主题包含【TEST】)")
    print(f"  阈值: {threshold}x")
    print(f"  收件人: {', '.join(config.EMAIL_RECIPIENTS)}")

    # 发送邮件
    print(f"\n[发送邮件]")
    success = send_single_trade_alert_html(
        trade_info=trade_info,
        message_data=message_data,
        threshold=threshold,
        lang='zh',  # 使用中文模板
        test_mode=True  # 测试模式，添加【TEST】标记
    )

    if success:
        print(f"✅ {asset} 测试邮件发送成功")
    else:
        print(f"❌ {asset} 测试邮件发送失败")

    return success


def main():
    """主函数"""
    print("="*70)
    print("中文预警邮件测试脚本")
    print("="*70)

    # 检查邮件配置
    print(f"\n[配置检查]")
    print(f"  EMAIL_ENABLED: {config.EMAIL_ENABLED}")
    print(f"  EMAIL_SENDER: {config.EMAIL_SENDER}")
    print(f"  EMAIL_PASSWORD: {'已设置' if config.EMAIL_PASSWORD else '未设置'}")
    print(f"  EMAIL_RECIPIENTS: {', '.join(config.EMAIL_RECIPIENTS)}")
    print(f"  MONITORED_EXCHANGE: {config.MONITORED_EXCHANGE}")
    print(f"  BTC_VOLUME_THRESHOLD: {config.BTC_VOLUME_THRESHOLD}")
    print(f"  ETH_VOLUME_THRESHOLD: {config.ETH_VOLUME_THRESHOLD}")

    if not config.EMAIL_ENABLED:
        print("\n❌ 错误: EMAIL_ENABLED = False")
        print("请设置环境变量: EMAIL_ENABLED=true")
        return False

    if not config.EMAIL_PASSWORD:
        print("\n❌ 错误: EMAIL_PASSWORD 未设置")
        print("请设置环境变量或在 .env 文件中配置 Gmail 应用专用密码")
        return False

    # 定义时间范围（2025-12-11 16:00 → 2025-12-12 16:00）
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    start_date = tz.localize(datetime(2025, 12, 11, 16, 0, 0))
    end_date = tz.localize(datetime(2025, 12, 12, 16, 0, 0))

    print(f"\n[数据范围]")
    print(f"  开始: {start_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  结束: {end_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # 查找最大的 BTC 和 ETH OPTIONS 交易
    print(f"\n[查询历史数据]")
    btc_trade, eth_trade = find_largest_options_trades(start_date, end_date)

    if not btc_trade and not eth_trade:
        print("\n❌ 错误: 未找到任何符合条件的 OPTIONS 交易")
        return False

    # 发送测试邮件
    results = []

    if btc_trade:
        msg, trade_info, volume = btc_trade
        success = send_test_email(msg, trade_info, volume, 'BTC')
        results.append(('BTC', success))
    else:
        print(f"\n⚠️  跳过 BTC 测试邮件（未找到数据）")
        results.append(('BTC', None))

    if eth_trade:
        msg, trade_info, volume = eth_trade
        success = send_test_email(msg, trade_info, volume, 'ETH')
        results.append(('ETH', success))
    else:
        print(f"\n⚠️  跳过 ETH 测试邮件（未找到数据）")
        results.append(('ETH', None))

    # 汇总结果
    print(f"\n{'='*70}")
    print(f"测试结果汇总")
    print(f"{'='*70}")

    for asset, success in results:
        if success is None:
            status = "⚠️  跳过（无数据）"
        elif success:
            status = "✅ 成功"
        else:
            status = "❌ 失败"
        print(f"  {asset}: {status}")

    success_count = sum(1 for _, s in results if s is True)
    total_count = sum(1 for _, s in results if s is not None)

    if total_count > 0:
        print(f"\n总计: {success_count}/{total_count} 封邮件发送成功")

    print(f"\n{'='*70}")
    print(f"提示：请检查邮箱收件箱，查看【TEST】中文预警邮件")
    print(f"{'='*70}")

    return success_count == total_count


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
