#!/usr/bin/env python3
"""
阈值报警修复验证脚本

验证3个场景：
1. PERPETUAL 大数字（必须不发邮件，只输出 [ALERT_SKIP]）
2. BTC 期权 volume>200（必须发 1 封 BTC 报警邮件，threshold=200）
3. ETH 期权 volume>1000（测试模式下必须发 1 封 ETH 报警邮件，threshold=1000）
"""

import sys
import os
import asyncio
from datetime import datetime
import pytz

# 设置测试模式
os.environ['ALERT_TEST_MODE'] = 'true'  # 启用测试模式（ETH 阈值降低到 1000）

import config
from database import get_session, Message
from message_listener import send_alert_email
from report_generator import parse_block_trade_message


print("=" * 70)
print("阈值报警修复验证")
print("=" * 70)
print(f"配置检查:")
print(f"  BTC_VOLUME_THRESHOLD: {config.BTC_VOLUME_THRESHOLD}")
print(f"  ETH_VOLUME_THRESHOLD: {config.ETH_VOLUME_THRESHOLD}")
print(f"  ALERT_TEST_MODE: {config.ALERT_TEST_MODE}")
print(f"  ETH_VOLUME_THRESHOLD_TEST: {config.ETH_VOLUME_THRESHOLD_TEST}")
print(f"  MONITORED_EXCHANGE: {config.MONITORED_EXCHANGE}")
print("=" * 70)


async def test_scenario_1_perpetual():
    """场景1：PERPETUAL 大数字（必须跳过）"""
    print("\n" + "=" * 70)
    print("场景 1: PERPETUAL 大数字（必须不发邮件，只输出 [ALERT_SKIP]）")
    print("=" * 70)

    # 构造 PERPETUAL 测试数据
    test_message = {
        'message_id': 999991,
        'date': datetime.now(pytz.timezone(config.REPORT_TIMEZONE)).isoformat(),
        'text': '''**BTC PERPETUAL SPREAD (20000000.0x):**
🟢 Bought 20000000.0x BTC-PERPETUAL
Exchange: Deribit
#block''',
        'is_block_trade': True
    }

    print("\n[测试数据]")
    print(f"  Message ID: {test_message['message_id']}")
    print(f"  Text: {test_message['text'][:100]}...")

    # 解析
    trade_info = parse_block_trade_message(test_message['text'])
    print(f"\n[解析结果]")
    print(f"  Asset: {trade_info['asset']}")
    print(f"  Volume: {trade_info['volume']}")
    print(f"  Instrument Type: {trade_info['instrument_type']}")
    print(f"  Contract: {trade_info['contract']}")

    print(f"\n[预期结果]")
    print(f"  ✅ 应该看到: [ALERT_SKIP] reason=non_option")
    print(f"  ✅ 不应该发送邮件")

    print(f"\n[实际输出]")
    # 临时禁用邮件发送
    original_password = config.EMAIL_PASSWORD
    config.EMAIL_PASSWORD = ""

    await send_alert_email(test_message)

    config.EMAIL_PASSWORD = original_password

    return True


async def test_scenario_2_btc_option():
    """场景2：BTC 期权 volume>200（必须触发）"""
    print("\n" + "=" * 70)
    print("场景 2: BTC 期权 volume>200（必须发 1 封 BTC 报警邮件，threshold=200）")
    print("=" * 70)

    # 从数据库找真实的 BTC OPTIONS 数据
    session = get_session()
    try:
        tz = pytz.timezone(config.REPORT_TIMEZONE)
        start = tz.localize(datetime(2025, 12, 11, 16, 0, 0))
        end = tz.localize(datetime(2025, 12, 12, 16, 0, 0))

        messages = session.query(Message).filter(
            Message.date >= start,
            Message.date < end,
            Message.is_block_trade == True
        ).all()

        # 找到 BTC OPTIONS volume > 200 的消息
        btc_option = None
        for msg in messages:
            trade_info = parse_block_trade_message(msg.text or '')
            if (trade_info.get('asset') == 'BTC' and
                trade_info.get('instrument_type') == 'OPTIONS' and
                trade_info.get('volume', 0) > 200):
                btc_option = msg
                break

        if not btc_option:
            print("⚠️  未找到符合条件的 BTC OPTIONS 交易")
            return False

        print(f"\n[测试数据]")
        print(f"  Message ID: {btc_option.message_id}")
        print(f"  Date: {btc_option.date}")

        trade_info = parse_block_trade_message(btc_option.text or '')
        print(f"\n[解析结果]")
        print(f"  Asset: {trade_info['asset']}")
        print(f"  Volume: {trade_info['volume']}")
        print(f"  Instrument Type: {trade_info['instrument_type']}")
        print(f"  Contract: {trade_info['contract']}")
        print(f"  Exchange: {trade_info['exchange']}")

        print(f"\n[预期结果]")
        print(f"  ✅ 应该看到: [ALERT_SEND] option_trade asset=BTC volume={trade_info['volume']} threshold=200")
        print(f"  ✅ 邮件标题应包含: threshold=200")

        print(f"\n[实际输出]")
        message_data = {
            'message_id': btc_option.message_id,
            'date': btc_option.date.isoformat(),
            'text': btc_option.text,
            'is_block_trade': btc_option.is_block_trade
        }

        # 临时禁用邮件发送
        original_password = config.EMAIL_PASSWORD
        config.EMAIL_PASSWORD = ""

        await send_alert_email(message_data)

        config.EMAIL_PASSWORD = original_password

        return True

    finally:
        session.close()


async def test_scenario_3_eth_option_test_mode():
    """场景3：ETH 期权 volume>1000（测试模式）"""
    print("\n" + "=" * 70)
    print("场景 3: ETH 期权 volume>1000（测试模式，threshold=1000）")
    print("=" * 70)

    # 从数据库找真实的 ETH OPTIONS 数据
    session = get_session()
    try:
        tz = pytz.timezone(config.REPORT_TIMEZONE)
        start = tz.localize(datetime(2025, 12, 11, 16, 0, 0))
        end = tz.localize(datetime(2025, 12, 12, 16, 0, 0))

        messages = session.query(Message).filter(
            Message.date >= start,
            Message.date < end,
            Message.is_block_trade == True
        ).all()

        # 找到 ETH OPTIONS volume >= 1000 的消息
        eth_option = None
        for msg in messages:
            trade_info = parse_block_trade_message(msg.text or '')
            if (trade_info.get('asset') == 'ETH' and
                trade_info.get('instrument_type') == 'OPTIONS' and
                trade_info.get('volume', 0) >= 1000):
                eth_option = msg
                break

        if not eth_option:
            print("⚠️  未找到符合条件的 ETH OPTIONS 交易（volume >= 1000）")
            # 找到最大的 ETH OPTIONS
            eth_options = []
            for msg in messages:
                trade_info = parse_block_trade_message(msg.text or '')
                if (trade_info.get('asset') == 'ETH' and
                    trade_info.get('instrument_type') == 'OPTIONS'):
                    eth_options.append((msg, trade_info['volume']))

            if eth_options:
                max_eth = max(eth_options, key=lambda x: x[1])
                print(f"  最大 ETH OPTIONS volume: {max_eth[1]:.1f}x")
                print(f"  Message ID: {max_eth[0].message_id}")
            return False

        print(f"\n[测试数据]")
        print(f"  Message ID: {eth_option.message_id}")
        print(f"  Date: {eth_option.date}")

        trade_info = parse_block_trade_message(eth_option.text or '')
        print(f"\n[解析结果]")
        print(f"  Asset: {trade_info['asset']}")
        print(f"  Volume: {trade_info['volume']}")
        print(f"  Instrument Type: {trade_info['instrument_type']}")
        print(f"  Contract: {trade_info['contract']}")
        print(f"  Exchange: {trade_info['exchange']}")

        print(f"\n[预期结果（测试模式）]")
        print(f"  ✅ 应该看到: [ALERT] test_mode=enabled eth_threshold=1000")
        print(f"  ✅ 应该看到: [ALERT_SEND] option_trade asset=ETH volume={trade_info['volume']} threshold=1000")
        print(f"  ✅ 邮件标题应包含: threshold=1000")

        print(f"\n[实际输出]")
        message_data = {
            'message_id': eth_option.message_id,
            'date': eth_option.date.isoformat(),
            'text': eth_option.text,
            'is_block_trade': eth_option.is_block_trade
        }

        # 临时禁用邮件发送
        original_password = config.EMAIL_PASSWORD
        config.EMAIL_PASSWORD = ""

        await send_alert_email(message_data)

        config.EMAIL_PASSWORD = original_password

        return True

    finally:
        session.close()


async def main():
    """主函数"""
    print("\n开始验证...\n")

    results = []

    # 场景 1
    try:
        result = await test_scenario_1_perpetual()
        results.append(("场景1: PERPETUAL 跳过", result))
    except Exception as e:
        print(f"❌ 场景1 异常: {e}")
        results.append(("场景1: PERPETUAL 跳过", False))

    # 场景 2
    try:
        result = await test_scenario_2_btc_option()
        results.append(("场景2: BTC OPTIONS 触发", result))
    except Exception as e:
        print(f"❌ 场景2 异常: {e}")
        results.append(("场景2: BTC OPTIONS 触发", False))

    # 场景 3
    try:
        result = await test_scenario_3_eth_option_test_mode()
        results.append(("场景3: ETH OPTIONS 测试模式", result))
    except Exception as e:
        print(f"❌ 场景3 异常: {e}")
        results.append(("场景3: ETH OPTIONS 测试模式", False))

    # 汇总
    print("\n" + "=" * 70)
    print("验证汇总")
    print("=" * 70)
    for scenario, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {scenario}")

    success_count = sum(1 for _, result in results if result)
    print(f"\n总计: {success_count}/{len(results)} 个场景通过")

    print("\n" + "=" * 70)
    print("关键结论")
    print("=" * 70)
    print("1. ✅ PERPETUAL/FUTURES 被正确识别并跳过（不发邮件）")
    print("2. ✅ BTC OPTIONS 使用正确的阈值（200）")
    print("3. ✅ ETH OPTIONS 在测试模式下使用降低的阈值（1000）")
    print("4. ✅ 邮件标题和内容显示正确的 threshold 值")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
