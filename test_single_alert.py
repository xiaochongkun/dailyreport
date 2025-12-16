#!/usr/bin/env python3
"""
单笔预警测试脚本（用于验证 OPTIONS ONLY 过滤逻辑）
"""

import sys
import asyncio
from datetime import datetime
import pytz

import config
from database import get_session, Message
from message_listener import send_alert_email
from report_generator import parse_block_trade_message


# 测试窗口
TZ = pytz.timezone(config.REPORT_TIMEZONE)
START_TIME = TZ.localize(datetime(2025, 12, 11, 16, 0, 0))
END_TIME = TZ.localize(datetime(2025, 12, 12, 16, 0, 0))


async def test_single_message(msg_id: int, send_email: bool = False):
    """测试单条消息的预警逻辑"""
    print("\n" + "=" * 70)
    print(f"测试单条消息 (msg_id={msg_id})")
    print("=" * 70)

    session = get_session()
    try:
        msg = session.query(Message).filter_by(message_id=msg_id).first()

        if not msg:
            print(f"❌ 未找到 msg_id={msg_id} 的消息")
            return

        # 解析消息
        trade_info = parse_block_trade_message(msg.text or '')

        print(f"\n[消息信息]")
        print(f"  Message ID: {msg.message_id}")
        print(f"  Date: {msg.date}")
        print(f"  Is Block Trade: {msg.is_block_trade}")

        print(f"\n[解析结果]")
        print(f"  Asset: {trade_info.get('asset')}")
        print(f"  Volume: {trade_info.get('volume')}")
        print(f"  Exchange: {trade_info.get('exchange')}")
        print(f"  Instrument Type: {trade_info.get('instrument_type')}")
        print(f"  Contract: {trade_info.get('contract')}")
        print(f"  Strategy: {trade_info.get('strategy')}")
        print(f"  Side: {trade_info.get('side')}")

        print(f"\n[原始消息]")
        print(msg.text[:500])

        # 测试预警逻辑
        print(f"\n[预警逻辑测试]")
        print(f"  VOLUME_ALERT_ENABLED: {config.VOLUME_ALERT_ENABLED}")
        print(f"  EMAIL_ENABLED: {config.EMAIL_ENABLED}")

        if not send_email:
            print("  ⚠️  dry-run 模式（不实际发送邮件）")
            config.EMAIL_ENABLED = False

        message_data = {
            'message_id': msg.message_id,
            'date': msg.date.isoformat(),
            'text': msg.text,
            'is_block_trade': msg.is_block_trade
        }

        print("\n开始调用 send_alert_email()...\n")
        await send_alert_email(message_data)

        print("\n✓ 测试完成")

    finally:
        session.close()


async def test_perpetual_skip():
    """测试 PERPETUAL 会被跳过"""
    print("\n" + "=" * 70)
    print("测试 PERPETUAL/FUTURES 跳过逻辑")
    print("=" * 70)

    session = get_session()
    try:
        # 查找 PERPETUAL 消息
        messages = session.query(Message).filter(
            Message.date >= START_TIME,
            Message.date < END_TIME,
            Message.is_block_trade == True
        ).all()

        perpetual_msgs = []
        for msg in messages:
            trade_info = parse_block_trade_message(msg.text or '')
            if trade_info.get('instrument_type') == 'PERPETUAL':
                perpetual_msgs.append(msg)

        if not perpetual_msgs:
            print("⚠️  未找到 PERPETUAL 消息")
            return

        print(f"\n找到 {len(perpetual_msgs)} 条 PERPETUAL 消息，测试第一条...\n")

        msg = perpetual_msgs[0]
        message_data = {
            'message_id': msg.message_id,
            'date': msg.date.isoformat(),
            'text': msg.text,
            'is_block_trade': msg.is_block_trade
        }

        print(f"Message ID: {msg.message_id}")
        print(f"应该看到: [ALERT_SKIP] reason=non_option\n")

        # 确保配置开启（但临时替换发送函数以避免实际发送邮件）
        original_volume_alert = config.VOLUME_ALERT_ENABLED
        original_email = config.EMAIL_ENABLED
        original_password = config.EMAIL_PASSWORD

        config.VOLUME_ALERT_ENABLED = True
        config.EMAIL_ENABLED = True  # 必须开启才能看到完整日志
        config.EMAIL_PASSWORD = ""  # 清空密码，阻止实际发送

        await send_alert_email(message_data)

        config.VOLUME_ALERT_ENABLED = original_volume_alert
        config.EMAIL_ENABLED = original_email
        config.EMAIL_PASSWORD = original_password

    finally:
        session.close()


async def test_btc_option_alert():
    """测试 BTC OPTIONS volume > 200 的预警"""
    print("\n" + "=" * 70)
    print("测试 BTC OPTIONS 预警（volume > 200）")
    print("=" * 70)

    session = get_session()
    try:
        messages = session.query(Message).filter(
            Message.date >= START_TIME,
            Message.date < END_TIME,
            Message.is_block_trade == True
        ).all()

        # 找到 BTC OPTIONS volume > 200 的消息
        btc_options = []
        for msg in messages:
            trade_info = parse_block_trade_message(msg.text or '')
            if (trade_info.get('asset') == 'BTC' and
                trade_info.get('instrument_type') == 'OPTIONS' and
                trade_info.get('volume', 0) > 200):
                btc_options.append((msg, trade_info))

        if not btc_options:
            print("⚠️  未找到满足条件的 BTC OPTIONS 交易")
            return

        print(f"\n找到 {len(btc_options)} 条符合条件的 BTC OPTIONS，测试第一条...\n")

        msg, trade_info = btc_options[0]
        print(f"Message ID: {msg.message_id}")
        print(f"Contract: {trade_info.get('contract')}")
        print(f"Volume: {trade_info.get('volume'):.1f}x")
        print(f"应该看到: [ALERT_SEND] option_trade\n")

        message_data = {
            'message_id': msg.message_id,
            'date': msg.date.isoformat(),
            'text': msg.text,
            'is_block_trade': msg.is_block_trade
        }

        # 确保配置开启（但临时替换发送函数以避免实际发送邮件）
        original_volume_alert = config.VOLUME_ALERT_ENABLED
        original_email = config.EMAIL_ENABLED
        original_password = config.EMAIL_PASSWORD

        config.VOLUME_ALERT_ENABLED = True
        config.EMAIL_ENABLED = True  # 必须开启才能看到完整日志
        config.EMAIL_PASSWORD = ""  # 清空密码，阻止实际发送

        await send_alert_email(message_data)

        config.VOLUME_ALERT_ENABLED = original_volume_alert
        config.EMAIL_ENABLED = original_email
        config.EMAIL_PASSWORD = original_password

    finally:
        session.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='单笔预警测试脚本')
    parser.add_argument('--msg-id', type=int, help='测试指定的 message_id')
    parser.add_argument('--test-perpetual', action='store_true', help='测试 PERPETUAL 跳过逻辑')
    parser.add_argument('--test-btc-alert', action='store_true', help='测试 BTC OPTIONS 预警')
    parser.add_argument('--send-email', action='store_true', help='实际发送邮件')

    args = parser.parse_args()

    if args.msg_id:
        asyncio.run(test_single_message(args.msg_id, send_email=args.send_email))
    elif args.test_perpetual:
        asyncio.run(test_perpetual_skip())
    elif args.test_btc_alert:
        asyncio.run(test_btc_option_alert())
    else:
        print("请使用以下参数之一:")
        print("  --msg-id <id>        测试指定消息")
        print("  --test-perpetual     测试 PERPETUAL 跳过逻辑")
        print("  --test-btc-alert     测试 BTC OPTIONS 预警")
        print("\n示例:")
        print("  python3 test_single_alert.py --test-perpetual")
        print("  python3 test_single_alert.py --test-btc-alert")
        print("  python3 test_single_alert.py --msg-id 340715 --send-email")


if __name__ == '__main__':
    main()
