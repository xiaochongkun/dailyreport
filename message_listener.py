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
        # 不再维护持久会话，改为每次操作使用新会话

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

            # 保存到数据库 - 使用新会话，操作完成后立即关闭
            session = get_session()
            try:
                result = save_message(
                    session=session,
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
            finally:
                # 确保会话被关闭，释放数据库锁
                session.close()

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
        # 由于不再维护持久会话，这里无需关闭会话
        # 每次消息处理已在 finally 块中关闭会话
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
        exchange = trade_info.get('exchange', 'Unknown')
        instrument_type = trade_info.get('instrument_type', 'Unknown')
        contract = trade_info.get('contract', 'Unknown')

        # ⚠️ 修正：提取 options legs 和 non-options legs（使用推导字段）
        options_legs = trade_info.get('options_legs', [])
        non_options_legs = trade_info.get('non_options_legs', [])
        options_sum = trade_info.get('options_sum', 0)  # 期权腿总张数（推导字段）
        options_count = trade_info.get('options_count', 0)

        # ✅ 硬规则 1: Option Only - 必须有至少一条 OPTIONS 腿
        if not options_legs or options_count == 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=no_option_legs asset={asset} options_count={options_count} msg_id={msg_id}")
            return

        # 检查交易所（可选过滤）
        if exchange != config.MONITORED_EXCHANGE:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=wrong_exchange exchange={exchange} msg_id={msg_id}")
            return

        # ✅ 硬规则 2: 区分 BTC/ETH 阈值（支持测试模式）
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

        # ⚠️ 修正：使用 options_sum（整笔订单期权腿总张数）+ 净权利金做阈值判断
        # 获取净权利金相关字段
        premium_paid_usd = trade_info.get('premium_paid_usd', None)
        premium_received_usd = trade_info.get('premium_received_usd', None)
        net_premium_usd = trade_info.get('net_premium_usd', None)
        abs_net_premium_usd = trade_info.get('abs_net_premium_usd', None)
        premium_threshold_usd = 1_000_000  # 硬编码 1,000,000 USD

        # 判断两种预警条件
        volume_trigger = options_sum > threshold
        premium_trigger = False
        if abs_net_premium_usd is not None:
            premium_trigger = abs_net_premium_usd >= premium_threshold_usd

        # 提取共享字段（用于预警）
        ref_price_usd = trade_info.get('ref_price_usd', None)
        spot_price_derived = trade_info.get('spot_price_derived', 'N/A')
        options_contracts = trade_info.get('options_contracts', [])
        contracts_str = ', '.join(options_contracts) if options_contracts else 'Unknown'

        # 打印结构化日志（包含两种预警的条件）
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_PREP] msg_id={msg_id} asset={asset} exchange={exchange} options_legs={options_count} non_options_legs={len(non_options_legs)} options_sum={options_sum} premium_paid_usd={premium_paid_usd if premium_paid_usd is not None else 'N/A'} premium_received_usd={premium_received_usd if premium_received_usd is not None else 'N/A'} net_premium_usd={net_premium_usd if net_premium_usd is not None else 'N/A'} abs_net_premium_usd={abs_net_premium_usd if abs_net_premium_usd is not None else 'N/A'} thresholds:vol={threshold} prem={premium_threshold_usd} volume_trigger={volume_trigger} premium_trigger={premium_trigger}")

        # 打印每条腿的详细信息（debug级别）
        for i, leg in enumerate(options_legs, 1):
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_LEG] leg#{i} type=OPTIONS side={leg.get('side')} contract={leg.get('contract')} volume={leg.get('volume')} price_btc={leg.get('price_btc')} total_usd={leg.get('total_usd')} ref={leg.get('ref_spot_usd')}")

        if ref_price_usd is not None:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] ref_extracted=true ref_price_usd={ref_price_usd} spot_price={spot_price_derived} contracts={contracts_str} msg_id={msg_id}")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] ref_extracted=false reason=no_ref_in_text contracts={contracts_str} msg_id={msg_id}")

        # ============================================
        # STEP 2：预警入口判断（合并邮件）
        # ============================================
        # 硬规则：如果同时满足 volume + premium 条件，合并成一封邮件
        # 否则，只发送满足条件的那一类预警

        # 判断是否需要发送预警
        should_send_alert = volume_trigger or premium_trigger

        if not should_send_alert:
            # 两种预警都未触发
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SKIP] reason=both_below_threshold asset={asset} options_sum={options_sum} volume_threshold={threshold} abs_net_premium_usd={abs_net_premium_usd if abs_net_premium_usd is not None else 'N/A'} premium_threshold={premium_threshold_usd} msg_id={msg_id}")
            return

        # 确定预警原因（reasons）
        reasons = []
        if volume_trigger:
            reasons.append('volume')
        if premium_trigger:
            reasons.append('premium')
        reasons_str = ','.join(reasons)

        # 打印触发日志
        if volume_trigger and premium_trigger:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_MULTI] asset={asset} msg_id={msg_id} reasons={reasons_str}")

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_SEND] msg_id={msg_id} reasons={reasons_str} asset={asset} options_sum={options_sum} abs_net_premium_usd={abs_net_premium_usd if abs_net_premium_usd is not None else 'N/A'} contracts={contracts_str}")

        # 发送合并预警邮件
        from email_sender import send_single_trade_alert_html

        success = send_single_trade_alert_html(
            trade_info=trade_info,
            message_data=message_data,
            threshold=threshold,
            alert_reasons=reasons,  # 传递预警原因列表
            lang='zh'
        )

        if not success:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT] alert_failed msg_id={msg_id} reasons={reasons_str} error=email_send_failed")

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
