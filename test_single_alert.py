"""
测试单笔大宗预警邮件（多腿解析）
从数据库查询指定消息并发送测试预警邮件
"""

from datetime import datetime
import argparse
import asyncio
from database import get_session, Message
from report_generator import parse_block_trade_message
from email_sender import send_single_trade_alert_html
import config


async def test_single_alert(msg_id: int = None, send_test: bool = False):
    """
    测试单笔预警邮件

    Args:
        msg_id: 消息ID（如果未指定，查找最近的多腿消息）
        send_test: 是否发送测试邮件
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TEST_ALERT] start msg_id={msg_id} send_test={send_test}")

    session = get_session()
    try:
        # 查询消息
        if msg_id:
            message = session.query(Message).filter_by(message_id=msg_id).first()
            if not message:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TEST_ALERT] error='message not found' msg_id={msg_id}")
                return
        else:
            # 查找最近的包含多个"Bought"/"Sold"的消息（多腿）
            messages = session.query(Message).filter(Message.is_block_trade == True).order_by(Message.date.desc()).limit(50).all()
            message = None
            for msg in messages:
                if msg.text and msg.text.count('Bought') + msg.text.count('Sold') >= 2:
                    message = msg
                    break

            if not message:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TEST_ALERT] error='no multi-leg message found'")
                return

        print(f"\n" + "=" * 60)
        print(f"测试消息: message_id={message.message_id}")
        print(f"时间: {message.date}")
        print("=" * 60)

        # 解析消息
        trade_info = parse_block_trade_message(message.text or '')

        # 提取腿信息
        options_legs = trade_info.get('options_legs', [])
        non_options_legs = trade_info.get('non_options_legs', [])

        print(f"\n解析结果:")
        print(f"  资产: {trade_info['asset']}")
        print(f"  交易所: {trade_info['exchange']}")
        print(f"  期权腿数: {len(options_legs)}")
        print(f"  非期权腿数: {len(non_options_legs)}")

        print(f"\n期权腿详情:")
        for i, leg in enumerate(options_legs, 1):
            print(f"  腿 #{i}:")
            print(f"    合约: {leg.get('contract')}")
            print(f"    方向: {leg.get('side')}")
            print(f"    数量: {leg.get('volume')}x")
            print(f"    价格: {leg.get('price_btc')} ₿ (${leg.get('price_usd')})")
            print(f"    Total: {leg.get('total_btc')} ₿ (${leg.get('total_usd')})")
            print(f"    IV: {leg.get('iv')}%")
            print(f"    Ref: ${leg.get('ref_spot_usd')}")

        if non_options_legs:
            print(f"\n非期权腿详情:")
            for i, leg in enumerate(non_options_legs, 1):
                print(f"  腿 #{i}:")
                print(f"    合约: {leg.get('contract')}")
                print(f"    类型: {leg.get('instrument_type')}")
                print(f"    方向: {leg.get('side')}")
                print(f"    数量: {leg.get('volume')}x")

        # 计算最大volume
        options_max_volume = max([leg.get('volume', 0) for leg in options_legs], default=0)
        print(f"\n期权最大数量: {options_max_volume}x")

        # 确定阈值
        asset = trade_info['asset']
        if asset == 'BTC':
            threshold = config.BTC_VOLUME_THRESHOLD
        elif asset == 'ETH':
            threshold = config.ETH_VOLUME_THRESHOLD_TEST if config.ALERT_TEST_MODE else config.ETH_VOLUME_THRESHOLD
        else:
            threshold = 200

        print(f"阈值: {threshold}x")
        print(f"触发: {'✅ YES' if options_max_volume > threshold else '❌ NO'}")

        # 发送测试邮件
        if send_test:
            print(f"\n发送测试预警邮件...")
            message_data = {
                'message_id': message.message_id,
                'date': message.date.isoformat(),
                'text': message.text,
                'is_block_trade': True
            }

            success = send_single_trade_alert_html(
                trade_info=trade_info,
                message_data=message_data,
                threshold=threshold,
                lang='zh',
                test_mode=True
            )

            if success:
                print(f"\n✅ 测试邮件发送成功！")
                print(f"  主题: 【TEST】单笔大宗期权预警 - {asset} - ...")
                print(f"  请检查邮箱收件！")
            else:
                print(f"\n❌ 测试邮件发送失败")
        else:
            print(f"\n提示: 使用 --send-test 参数发送测试邮件")

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TEST_ALERT] error={e}")
        import traceback
        traceback.print_exc()

    finally:
        session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='测试单笔大宗预警邮件')
    parser.add_argument('--msg-id', type=int, help='消息ID（可选，不指定则自动查找多腿消息）')
    parser.add_argument('--send-test', action='store_true', help='发送测试邮件')

    args = parser.parse_args()

    asyncio.run(test_single_alert(msg_id=args.msg_id, send_test=args.send_test))
