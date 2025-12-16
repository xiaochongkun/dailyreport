"""
实时消息监听与警报
监听 Telegram 群组的新消息，保存到数据库并触发警报
"""

from datetime import datetime
from telethon import events
import config
from database import save_message, get_session


class MessageListener:
    """消息监听器类"""

    def __init__(self, client):
        """
        初始化消息监听器

        Args:
            client: Telegram 客户端实例
        """
        self.client = client
        self.session = None

        # 统计信息
        self.total_messages = 0
        self.block_trades = 0
        self.alerts_sent = 0
        self.message_counter = 0
        self.HEARTBEAT_INTERVAL = 50

    def setup(self):
        """设置事件监听器"""
        @self.client.on(events.NewMessage(chats=config.TARGET_CHAT_ID))
        async def handler(event):
            await self.handle_new_message(event)

        print(f"✓ 消息监听器已设置")
        print(f"  监听群组: {config.TARGET_CHAT_NAME} (ID: {config.TARGET_CHAT_ID})")
        print(f"  监听标签: {config.BLOCK_TRADE_TAG}")

    async def handle_new_message(self, event):
        """
        处理新消息

        Args:
            event: Telegram 新消息事件
        """
        try:
            self.message_counter += 1
            if self.message_counter % self.HEARTBEAT_INTERVAL == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [LISTENER] heartbeat messages_seen={self.message_counter}")

            message = event.message

            # 提取消息信息
            message_id = message.id
            message_date = message.date
            message_text = message.text or ''

            # 检查是否为大宗交易
            is_block_trade = config.BLOCK_TRADE_TAG in message_text

            # 保存到数据库
            if self.session is None:
                self.session = get_session()

            result = save_message(
                session=self.session,
                message_id=message_id,
                date=message_date,
                text=message_text,
                is_block_trade=is_block_trade
            )

            if result:
                self.total_messages += 1

                # 如果是大宗交易，触发警报
                if is_block_trade:
                    self.block_trades += 1
                    await self.trigger_alert(result)

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [LISTENER] error={e}")

    async def trigger_alert(self, message):
        """
        触发大宗交易警报

        Args:
            message: 消息对象（Message 模型实例）
        """
        try:
            # 准备消息数据
            message_data = message.to_dict()

            # 调用警报发送函数
            await send_alert_email(message_data)

            self.alerts_sent += 1

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] trigger_failed error={e}")

    def get_stats(self):
        """获取监听统计信息"""
        return {
            'total_messages': self.total_messages,
            'block_trades': self.block_trades,
            'alerts_sent': self.alerts_sent
        }

    def close(self):
        """关闭监听器（不抛异常）"""
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass


async def send_alert_email(message_data):
    """
    检查单笔交易阈值并发送警报邮件（OPTIONS ONLY，区分 BTC/ETH 阈值）

    硬规则：
    1. Option Only：只对 instrument_type=OPTIONS 触发预警
    2. 排除 FUTURES/PERPETUAL：永续/期货一律跳过
    3. 阈值：BTC options > 200，ETH options > 5000

    Args:
        message_data: 消息数据字典
    """
    try:
        msg_id = message_data.get('message_id', 'Unknown')

        # 提前返回检查
        if not config.VOLUME_ALERT_ENABLED:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=volume_alert_disabled msg_id={msg_id}")
            return

        if not config.EMAIL_ENABLED:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=email_disabled msg_id={msg_id}")
            return

        from email_sender import send_single_trade_alert_html
        from report_generator import parse_block_trade_message

        raw_text = message_data.get('text', '')

        # 解析交易信息
        trade_info = parse_block_trade_message(raw_text)

        # 提取关键字段
        asset = trade_info.get('asset', 'Unknown')
        volume = trade_info.get('volume', 0.0)
        exchange = trade_info.get('exchange', 'Unknown')
        instrument_type = trade_info.get('instrument_type', 'Unknown')
        contract = trade_info.get('contract', 'Unknown')

        # ✅ 硬规则 1: Option Only - 只对 OPTIONS 触发预警
        if instrument_type != 'OPTIONS':
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=non_option instrument={instrument_type} contract={contract} msg_id={msg_id}")
            return

        # ✅ 硬规则 2: 排除 FUTURES/PERPETUAL（双重检查，防止解析错误）
        if any(keyword in raw_text.upper() for keyword in ['PERPETUAL', 'PERP', '-PERP', 'FUTURES', '-FUT']):
            # 再次检查合约名
            if 'PERPETUAL' in contract.upper() or 'PERP' in contract.upper() or 'FUT' in contract.upper():
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=non_option instrument=FUTURES/PERPETUAL contract={contract} msg_id={msg_id}")
                return

        # 检查交易所（可选过滤）
        if exchange != config.MONITORED_EXCHANGE:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=wrong_exchange exchange={exchange} msg_id={msg_id}")
            return

        # ✅ 硬规则 3: 区分 BTC/ETH 阈值（支持测试模式）
        if asset == 'BTC':
            threshold = config.BTC_VOLUME_THRESHOLD  # 默认 200
        elif asset == 'ETH':
            # 测试模式下使用降低的阈值
            if config.ALERT_TEST_MODE:
                threshold = config.ETH_VOLUME_THRESHOLD_TEST  # 测试模式: 1000
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] test_mode=enabled eth_threshold={threshold}")
            else:
                threshold = config.ETH_VOLUME_THRESHOLD  # 正式: 5000
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=unknown_asset asset={asset} msg_id={msg_id}")
            return

        # 检查是否超过阈值
        if volume <= threshold:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=below_threshold asset={asset} volume={volume} threshold={threshold} msg_id={msg_id}")
            return

        # ✅ 发送预警邮件（OPTIONS ONLY）
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SEND] option_trade asset={asset} volume={volume} threshold={threshold} contract={contract} msg_id={msg_id}")

        success = send_single_trade_alert_html(
            trade_info=trade_info,
            message_data=message_data,
            threshold=threshold,
            lang='zh'  # 正式启用中文模板
        )

        if not success:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] alert_failed msg_id={msg_id} error=email_send_failed")

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] alert_failed error={e}")


if __name__ == '__main__':
    """测试模块"""
    print("此模块应通过 main.py 运行")
    print("测试警报函数...")

    import asyncio

    # 测试警报发送
    test_message = {
        'id': 1,
        'message_id': 12345,
        'date': datetime.now().isoformat(),
        'text': '测试大宗交易消息 #block',
        'is_block_trade': True,
        'created_at': datetime.now().isoformat()
    }

    asyncio.run(send_alert_email(test_message))
