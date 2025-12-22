"""
邮件发送模块（最小可用版本）
提供简单的日报邮件和阈值预警邮件功能
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pytz
import argparse
import sys

import config
from database import get_session, get_messages_by_date_range
from report_generator import parse_block_trade_message


# ============================================
# 邮件收件人路由（唯一入口）
# ============================================
def resolve_recipients(email_type: str, mode: str = None) -> tuple:
    """
    统一的收件人路由函数（唯一入口）

    Args:
        email_type: 邮件类型 ('daily', 'alert')
        mode: 邮件模式 ('test', 'prod')，若为 None 则从 config.EMAIL_MODE 读取

    Returns:
        (recipients_list, resolved_mode): 收件人列表, 实际使用的模式
    """
    # 如果没有指定 mode，从 config 读取
    if mode is None:
        mode = config.EMAIL_MODE

    # 默认安全：无法识别的 mode 按 test 处理
    if mode not in ('test', 'prod'):
        print(f"[EMAIL_ROUTE] mode={mode} reason=unknown_mode fallback=test")
        mode = 'test'

    # 根据模式路由收件人
    if mode == 'test':
        # TEST 模式：只发给测试白名单
        recipients_str = config.TEST_RECIPIENTS
        recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]

        # 安全检查：TEST 模式禁止读取 PROD_RECIPIENTS
        if not recipients:
            print(f"[EMAIL_BLOCK] reason=no_test_recipients mode={mode}")
            return [], mode

        print(f"[EMAIL_ROUTE] mode={mode} email_type={email_type} recipients_count={len(recipients)} recipients={','.join(recipients)}")
        return recipients, mode

    elif mode == 'prod':
        # PROD 模式：发给正式收件人列表
        recipients_str = config.PROD_RECIPIENTS
        recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]

        if not recipients:
            print(f"[EMAIL_BLOCK] reason=no_prod_recipients mode={mode}")
            return [], mode

        print(f"[EMAIL_ROUTE] mode={mode} email_type={email_type} recipients_count={len(recipients)} recipients_sample={','.join(recipients[:2])}")
        return recipients, mode

    # 兜底：不应该到这里
    print(f"[EMAIL_ROUTE] mode={mode} reason=fallback_to_test")
    return resolve_recipients(email_type, mode='test')


def enforce_subject_prefix(subject: str, mode: str) -> tuple:
    """
    强制标题前缀规则

    Args:
        subject: 原始标题
        mode: 邮件模式 ('test', 'prod')

    Returns:
        (final_subject, is_valid): 最终标题, 是否合法
    """
    test_prefix = "🧪 [TEST] "
    has_test_prefix = test_prefix in subject or "[TEST]" in subject

    if mode == 'test':
        # TEST 模式：必须有 TEST 前缀
        if not has_test_prefix and config.FORCE_TEST_SUBJECT_PREFIX:
            # 自动添加前缀
            final_subject = test_prefix + subject
            print(f"[EMAIL_SUBJECT] mode={mode} action=add_test_prefix")
            return final_subject, True
        elif not has_test_prefix:
            # 未强制要求，但应该有
            print(f"[EMAIL_WARN] mode={mode} reason=missing_test_prefix subject={subject[:50]}")
            return subject, True
        else:
            return subject, True

    elif mode == 'prod':
        # PROD 模式：必须没有 TEST 前缀
        if has_test_prefix:
            print(f"[EMAIL_BLOCK] mode={mode} reason=test_prefix_in_prod subject={subject[:50]}")
            return subject, False  # 阻断发送
        else:
            return subject, True

    # 兜底
    return subject, True


def query_daily_stats(report_date: str) -> dict:
    """
    查询指定日期的统计数据

    Args:
        report_date: 日期字符串，格式 'YYYY-MM-DD'

    Returns:
        统计数据字典
    """
    session = get_session()
    try:
        # 解析日期
        tz = pytz.timezone(config.REPORT_TIMEZONE)
        date_obj = datetime.strptime(report_date, '%Y-%m-%d')
        date_obj = tz.localize(date_obj)

        # 查询当日 0:00 - 23:59 的所有消息
        start_date = date_obj.replace(hour=0, minute=0, second=0)
        end_date = date_obj.replace(hour=23, minute=59, second=59)

        messages = get_messages_by_date_range(session, start_date, end_date)

        # 筛选大宗交易
        block_trades = [msg for msg in messages if msg.is_block_trade]

        # 初始化统计
        btc_total_volume = 0.0
        eth_total_volume = 0.0
        btc_trade_count = 0
        eth_trade_count = 0

        # 解析每笔大宗交易
        for trade in block_trades:
            parsed = parse_block_trade_message(trade.text or '')
            asset = parsed.get('asset', 'Unknown')
            volume = parsed.get('volume', 0.0)

            if asset == 'BTC':
                btc_total_volume += volume
                btc_trade_count += 1
            elif asset == 'ETH':
                eth_total_volume += volume
                eth_trade_count += 1

        return {
            'date': report_date,
            'total_messages': len(messages),
            'total_trades': len(block_trades),
            'btc_total_volume': btc_total_volume,
            'eth_total_volume': eth_total_volume,
            'btc_trade_count': btc_trade_count,
            'eth_trade_count': eth_trade_count,
        }

    finally:
        session.close()


def create_smtp_connection(max_retries=3):
    """
    创建并返回已登录的 SMTP 连接（带重试）

    Args:
        max_retries: 最大重试次数（默认3次）

    Returns:
        SMTP 连接对象或 None（失败时）
    """
    import time
    delay = 2  # 初始延迟2秒

    for attempt in range(1, max_retries + 1):
        try:
            smtp = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=10)
            if config.SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)

            if attempt > 1:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] smtp_connected_retry attempt={attempt}/{max_retries}")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] smtp_connected")
            return smtp
        except Exception as e:
            if attempt < max_retries:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] smtp_retry attempt={attempt}/{max_retries} delay={delay}s error={type(e).__name__}")
                time.sleep(delay)
                delay *= 2  # 指数退避
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] smtp_failed max_retries_exceeded error={type(e).__name__}: {str(e)}")

    return None


def send_email(subject: str, body: str, recipients: list = None, email_type: str = 'unknown', mode: str = None, msg_id: str = None, report_date: str = None) -> bool:
    """
    通用邮件发送函数（带重试、指数退避和收件人路由）

    Args:
        subject: 邮件标题
        body: 邮件正文（纯文本）
        recipients: 收件人列表（若为 None 则使用路由）
        email_type: 邮件类型 ('daily', 'alert', 'unknown')
        mode: 邮件模式 ('test', 'prod', None=自动)
        msg_id: 消息 ID（用于日志）
        report_date: 报告日期（用于日志）

    Returns:
        True: 发送成功
        False: 发送失败
    """
    import time

    # ============================================
    # STEP 1: 收件人路由（若未提供 recipients）
    # ============================================
    if recipients is None:
        recipients, resolved_mode = resolve_recipients(email_type, mode)
        if not recipients:
            print(f"[EMAIL_BLOCK] reason=no_recipients email_type={email_type} mode={resolved_mode}")
            return False
    else:
        # 使用提供的 recipients（兼容旧代码）
        resolved_mode = mode if mode else config.EMAIL_MODE

    # ============================================
    # STEP 2: 标题前缀检查与强制
    # ============================================
    final_subject, subject_valid = enforce_subject_prefix(subject, resolved_mode)
    if not subject_valid:
        print(f"[EMAIL_BLOCK] reason=invalid_subject mode={resolved_mode} subject={subject[:50]}")
        return False

    # ============================================
    # STEP 3: 打印发送准备日志
    # ============================================
    recipients_sample = ','.join(recipients[:2]) if len(recipients) > 1 else recipients[0] if recipients else 'none'
    log_msg_id = msg_id if msg_id else 'N/A'
    log_report_date = report_date if report_date else 'N/A'

    print(f"[EMAIL_PREP] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} recipients_sample={recipients_sample} subject={final_subject[:60]} msg_id={log_msg_id} report_date={log_report_date}")

    # ============================================
    # STEP 4: DRY RUN 模式检查
    # ============================================
    if config.EMAIL_DRY_RUN:
        print(f"[EMAIL_DRY_RUN] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} recipients={','.join(recipients)} subject={final_subject}")
        return True  # Dry run 成功

    # ============================================
    # STEP 5: 实际发送（带重试）
    # ============================================
    max_retries = 3
    delay = 2  # 初始延迟2秒

    for attempt in range(1, max_retries + 1):
        try:
            msg = MIMEMultipart()
            msg['From'] = config.EMAIL_SENDER
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = final_subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            smtp = create_smtp_connection()
            if smtp is None:
                raise Exception("SMTP connection failed")
            smtp.send_message(msg)
            smtp.quit()

            if attempt > 1:
                print(f"[EMAIL_SENT] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} subject={final_subject[:60]} attempt={attempt}/{max_retries}")
            else:
                print(f"[EMAIL_SENT] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} subject={final_subject[:60]}")
            return True
        except Exception as e:
            if attempt < max_retries:
                print(f"[EMAIL_FAIL] mode={resolved_mode} email_type={email_type} attempt={attempt}/{max_retries} delay={delay}s error={type(e).__name__}")
                time.sleep(delay)
                delay *= 2  # 指数退避
            else:
                print(f"[EMAIL_GIVEUP] mode={resolved_mode} email_type={email_type} max_retries_exceeded error={type(e).__name__}: {str(e)}")

    return False


def send_html_email(subject: str, html_body: str, recipients: list = None, email_type: str = 'unknown', mode: str = None, msg_id: str = None, report_date: str = None) -> bool:
    """
    发送 HTML 格式邮件（带纯文本 fallback、重试和收件人路由）

    Args:
        subject: 邮件标题
        html_body: HTML 正文
        recipients: 收件人列表（若为 None 则使用路由）
        email_type: 邮件类型 ('daily', 'alert', 'unknown')
        mode: 邮件模式 ('test', 'prod', None=自动)
        msg_id: 消息 ID（用于日志）
        report_date: 报告日期（用于日志）

    Returns:
        True: 发送成功
        False: 发送失败
    """
    import time, re

    # ============================================
    # STEP 1: 收件人路由（若未提供 recipients）
    # ============================================
    if recipients is None:
        recipients, resolved_mode = resolve_recipients(email_type, mode)
        if not recipients:
            print(f"[EMAIL_BLOCK] reason=no_recipients email_type={email_type} mode={resolved_mode}")
            return False
    else:
        # 使用提供的 recipients（兼容旧代码）
        resolved_mode = mode if mode else config.EMAIL_MODE

    # ============================================
    # STEP 2: 标题前缀检查与强制
    # ============================================
    final_subject, subject_valid = enforce_subject_prefix(subject, resolved_mode)
    if not subject_valid:
        print(f"[EMAIL_BLOCK] reason=invalid_subject mode={resolved_mode} subject={subject[:50]}")
        return False

    # ============================================
    # STEP 3: 打印发送准备日志
    # ============================================
    recipients_sample = ','.join(recipients[:2]) if len(recipients) > 1 else recipients[0] if recipients else 'none'
    log_msg_id = msg_id if msg_id else 'N/A'
    log_report_date = report_date if report_date else 'N/A'

    print(f"[EMAIL_PREP] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} recipients_sample={recipients_sample} subject={final_subject[:60]} msg_id={log_msg_id} report_date={log_report_date}")

    # ============================================
    # STEP 4: DRY RUN 模式检查
    # ============================================
    if config.EMAIL_DRY_RUN:
        print(f"[EMAIL_DRY_RUN] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} recipients={','.join(recipients)} subject={final_subject}")
        return True  # Dry run 成功

    # ============================================
    # STEP 5: 实际发送（带重试）
    # ============================================
    max_retries = 3
    delay = 2  # 初始延迟2秒

    for attempt in range(1, max_retries + 1):
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = config.EMAIL_SENDER
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = final_subject

            text_body = re.sub(r'<[^>]+>', '', html_body)
            text_body = re.sub(r'\s+', ' ', text_body).strip()

            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            smtp = create_smtp_connection()
            if smtp is None:
                raise Exception("SMTP connection failed")
            smtp.send_message(msg)
            smtp.quit()

            if attempt > 1:
                print(f"[EMAIL_SENT] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} subject={final_subject[:60]} attempt={attempt}/{max_retries}")
            else:
                print(f"[EMAIL_SENT] mode={resolved_mode} email_type={email_type} recipients_count={len(recipients)} subject={final_subject[:60]}")
            return True
        except Exception as e:
            if attempt < max_retries:
                print(f"[EMAIL_FAIL] mode={resolved_mode} email_type={email_type} attempt={attempt}/{max_retries} delay={delay}s error={type(e).__name__}")
                time.sleep(delay)
                delay *= 2  # 指数退避
            else:
                print(f"[EMAIL_GIVEUP] mode={resolved_mode} email_type={email_type} max_retries_exceeded error={type(e).__name__}: {str(e)}")

    return False


def send_daily_report_email_simple(report_date: str) -> bool:
    """
    发送简单的日报邮件（纯文本）

    Args:
        report_date: 报告日期，格式 'YYYY-MM-DD'

    Returns:
        True: 发送成功
        False: 发送失败
    """
    print("\n" + "=" * 60)
    print(f"准备发送日报邮件: {report_date}")
    print("=" * 60)

    # 查询统计数据
    print(f"\n查询 {report_date} 的统计数据...")
    stats = query_daily_stats(report_date)

    print(f"✓ 统计完成:")
    print(f"  总消息: {stats['total_messages']}")
    print(f"  总交易: {stats['total_trades']}")
    print(f"  BTC: {stats['btc_trade_count']} 笔, {stats['btc_total_volume']:.1f}x")
    print(f"  ETH: {stats['eth_trade_count']} 笔, {stats['eth_total_volume']:.1f}x")

    # 检查是否有数据
    if stats['total_trades'] == 0:
        print(f"\n⚠ 警告: {report_date} 没有交易数据，仍然发送邮件...")

    # 构造邮件标题
    subject = f"Daily Trade Report - {report_date}"

    # 构造邮件正文（简单文本模板）
    body = f"""Daily Trade Report - {report_date}
============================================================

BTC:
  - Trades: {stats['btc_trade_count']}
  - Block Volume: {stats['btc_total_volume']:.1f}x

ETH:
  - Trades: {stats['eth_trade_count']}
  - Block Volume: {stats['eth_total_volume']:.1f}x

Total:
  - Messages: {stats['total_messages']}
  - Block Trades: {stats['total_trades']}

============================================================
This is a simple test version of the daily report email.
Generated at: {datetime.now(pytz.timezone(config.REPORT_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S %Z')}
"""

    # 发送邮件（接入路由）
    print(f"\n发送日报邮件...")
    return send_email(subject, body, recipients=None, email_type='daily', report_date=report_date)


def send_volume_threshold_alert_simple(stats: dict, triggered_assets: list, report_date: str) -> bool:
    """
    发送简单的阈值预警邮件（纯文本）

    Args:
        stats: 统计数据字典
        triggered_assets: 触发阈值的资产列表，如 ['BTC', 'ETH']
        report_date: 报告日期，格式 'YYYY-MM-DD'

    Returns:
        True: 发送成功
        False: 发送失败
    """
    print("\n" + "=" * 60)
    print(f"准备发送阈值预警邮件: {report_date}")
    print("=" * 60)

    print(f"\n触发的资产: {', '.join(triggered_assets)}")
    print(f"统计数据:")
    print(f"  BTC: {stats['btc_total_volume']:.1f}x (阈值: {config.BTC_VOLUME_THRESHOLD})")
    print(f"  ETH: {stats['eth_total_volume']:.1f}x (阈值: {config.ETH_VOLUME_THRESHOLD})")

    # 构造邮件标题
    if len(triggered_assets) == 1:
        asset = triggered_assets[0]
        threshold = config.BTC_VOLUME_THRESHOLD if asset == 'BTC' else config.ETH_VOLUME_THRESHOLD
        subject = f"⚠️ Volume Alert: {asset} > {threshold} orders on {report_date}"
    else:
        subject = f"⚠️ Volume Alert: Multiple Assets Threshold Exceeded - {report_date}"

    # 构造邮件正文
    body = f"""Volume Threshold Alert - {report_date}
============================================================

THRESHOLD CONFIGURATION:
  - BTC Threshold: {config.BTC_VOLUME_THRESHOLD} orders
  - ETH Threshold: {config.ETH_VOLUME_THRESHOLD} orders

TODAY'S STATISTICS:
  BTC:
    - Total Volume: {stats['btc_total_volume']:.1f} orders {'⚠️ EXCEEDED' if 'BTC' in triggered_assets else '✅'}
    - Trade Count: {stats['btc_trade_count']} trades

  ETH:
    - Total Volume: {stats['eth_total_volume']:.1f} orders {'⚠️ EXCEEDED' if 'ETH' in triggered_assets else '✅'}
    - Trade Count: {stats['eth_trade_count']} trades

  Total Trades: {stats['total_trades']}

TRIGGERED ASSETS:
  {', '.join(triggered_assets)}

RECOMMENDATION:
  Market activity is significantly elevated. Review the daily
  report for detailed breakdown.

============================================================
This is a simple test version of the volume alert email.
Generated at: {datetime.now(pytz.timezone(config.REPORT_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S %Z')}
"""

    # 发送邮件
    print(f"\n发送阈值预警邮件...")
    return send_email(subject, body)


def send_realtime_block_trade_alert(message_data: dict, trade_info: dict) -> bool:
    """
    发送实时大宗交易预警邮件

    Args:
        message_data: 消息数据字典
        trade_info: 解析后的交易信息字典

    Returns:
        True: 发送成功
        False: 发送失败或未启用
    """
    # 检查是否启用邮件
    if not config.EMAIL_ENABLED:
        print(f"  [跳过] 邮件发送未启用（EMAIL_ENABLED=false）")
        return False

    # 提取关键信息
    asset = trade_info.get('asset', 'Unknown')
    volume = trade_info.get('volume', 0.0)
    strategy = trade_info.get('strategy', 'Unknown')

    # 检查是否超过阈值
    if asset == 'BTC' and volume < config.BTC_VOLUME_THRESHOLD:
        print(f"  [跳过] BTC 交易量 {volume:.1f} 未超过阈值 {config.BTC_VOLUME_THRESHOLD}")
        return False
    elif asset == 'ETH' and volume < config.ETH_VOLUME_THRESHOLD:
        print(f"  [跳过] ETH 交易量 {volume:.1f} 未超过阈值 {config.ETH_VOLUME_THRESHOLD}")
        return False
    elif asset not in ['BTC', 'ETH']:
        print(f"  [跳过] 未知资产类型: {asset}")
        return False

    # 构造邮件标题
    threshold = config.BTC_VOLUME_THRESHOLD if asset == 'BTC' else config.ETH_VOLUME_THRESHOLD
    subject = f"🚨 Block Trade Alert: {asset} {volume:.1f}x (> {threshold})"

    # 构造邮件正文
    trade_time = datetime.fromisoformat(message_data['date']).strftime('%Y-%m-%d %H:%M:%S')

    body = f"""Block Trade Alert - {trade_time}
============================================================

🚨 LARGE BLOCK TRADE DETECTED

ASSET: {asset}
VOLUME: {volume:.1f}x (Threshold: {threshold})
STRATEGY: {strategy}

DETAILS:
  Exchange: {trade_info.get('exchange', 'Unknown')}
  Contract: {trade_info.get('contract', 'Unknown')}
  Price: {trade_info.get('price', 'Unknown')}
  Amount (USD): ${trade_info.get('amount_usd', 0):,.2f}

MESSAGE:
{message_data['text'][:500]}

============================================================
Generated at: {datetime.now(pytz.timezone(config.REPORT_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S %Z')}
"""

    # 发送邮件
    print(f"  [发送] 实时预警邮件: {asset} {volume:.1f}x")
    return send_email(subject, body)


def send_single_trade_alert_html(trade_info: dict, message_data: dict, threshold: int, alert_reasons: list = None, lang: str = 'en', test_mode: bool = False) -> bool:
    """
    发送单笔 OPTIONS 交易预警邮件（HTML 格式，OPTIONS ONLY）

    Args:
        trade_info: parse_block_trade_message() 解析后的交易信息
        message_data: 消息数据字典
        threshold: 触发的阈值（张数）
        alert_reasons: 预警原因列表 ['volume'] 或 ['premium'] 或 ['volume', 'premium']
        lang: 语言模式 ('en' 或 'zh')
        test_mode: 测试模式（在邮件标题添加【TEST】标记）

    Returns:
        True: 发送成功
        False: 发送失败
    """
    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print(f"  [跳过] 邮件发送未启用（EMAIL_ENABLED=false）")
        return False

    if not config.EMAIL_PASSWORD:
        print(f"  [错误] EMAIL_PASSWORD 未设置")
        return False

    # 默认预警原因
    if alert_reasons is None:
        alert_reasons = ['volume']

    # 提取关键字段
    asset = trade_info.get('asset', 'Unknown')
    exchange = trade_info.get('exchange', 'Unknown')
    strategy = trade_info.get('strategy', 'Unknown')
    greeks = trade_info.get('greeks', {})

    # ⚠️ 修正：提取 legs 信息（使用推导字段）
    options_legs = trade_info.get('options_legs', [])
    non_options_legs = trade_info.get('non_options_legs', [])

    # 使用推导字段：整笔订单期权腿总张数
    options_sum = trade_info.get('options_sum', 0)
    options_count = trade_info.get('options_count', 0)
    spot_price_derived = trade_info.get('spot_price_derived', 'N/A')

    # 净权利金相关字段
    premium_paid_usd = trade_info.get('premium_paid_usd', None)
    premium_received_usd = trade_info.get('premium_received_usd', None)
    net_premium_usd = trade_info.get('net_premium_usd', None)
    abs_net_premium_usd = trade_info.get('abs_net_premium_usd', None)

    # ⚠️ 修正：添加英文模板需要的字段定义
    # 为了向后兼容，同时定义旧字段（但优先使用推导字段）
    contract = trade_info.get('contract', 'Unknown')
    instrument_type = trade_info.get('instrument_type', 'Unknown')
    side = trade_info.get('side', 'Unknown')
    volume = trade_info.get('options_max', 0)  # 英文模板遗留：使用单腿最大值
    options_max_volume = trade_info.get('options_max', 0)  # 单腿最大张数

    # 补充其他可能需要的字段
    iv = trade_info.get('iv', 'N/A')
    price = trade_info.get('price', 'N/A')
    amount_usd = trade_info.get('amount_usd', 0.0)
    spot_price = spot_price_derived  # 别名

    # 格式化时间
    try:
        trade_time = datetime.fromisoformat(message_data['date']).strftime('%Y-%m-%d %H:%M:%S')
    except:
        trade_time = str(message_data.get('date', 'Unknown'))

    import pytz
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    generated_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

    # 根据语言模式构造邮件标题和正文
    if lang == 'zh':
        # 中文模板
        test_prefix = "【TEST】" if test_mode else ""
        subject = f"{test_prefix}单笔大宗期权预警 - {asset} - {trade_time} - {exchange}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #dc2626 0%, #f59e0b 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .alert-tag {{ display: inline-block; background: #dc2626; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 8px; margin-right: 8px; }}
        .section {{ margin: 20px 0; }}
        .section-title {{ font-size: 16px; font-weight: bold; color: #1f2937; margin-bottom: 10px; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; }}
        .field-row {{ margin: 8px 0; padding: 8px; background: #f9fafb; border-radius: 4px; }}
        .field-label {{ color: #6b7280; min-width: 100px; display: inline-block; }}
        .field-value {{ color: #1f2937; font-weight: 600; }}
        .volume-highlight {{ font-size: 20px; color: #dc2626; font-weight: bold; }}
        .greeks-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 10px; }}
        .greek-item {{ text-align: center; padding: 8px; background: #f3f4f6; border-radius: 4px; }}
        .greek-label {{ font-size: 11px; color: #6b7280; margin-bottom: 4px; }}
        .greek-value {{ font-size: 14px; color: #1f2937; font-weight: 600; }}
        .message-box {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 15px; border-radius: 6px; margin: 10px 0; font-size: 13px; color: #374151; white-space: pre-wrap; font-family: "Courier New", monospace; max-height: 400px; overflow-y: auto; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 单笔大宗期权预警</h1>
            {'<span class="alert-tag">🧪 [TEST]</span>' if test_mode else ''}
            <span class="alert-tag">OPTIONS ONLY</span>
            {'<span class="alert-tag">📊 张数预警</span>' if 'volume' in alert_reasons else ''}
            {'<span class="alert-tag">💰 净权利金预警</span>' if 'premium' in alert_reasons else ''}
        </div>

        <div class="section">
            <div class="section-title">📊 资产 / 交易所 / 时间</div>
            <div class="field-row">
                <span class="field-label">资产:</span>
                <span class="field-value">{asset}</span>
            </div>
            <div class="field-row">
                <span class="field-label">交易所:</span>
                <span class="field-value">{exchange}</span>
            </div>
            <div class="field-row">
                <span class="field-label">时间:</span>
                <span class="field-value">{trade_time}</span>
            </div>
            <div class="field-row">
                <span class="field-label">现货价 (Ref):</span>
                <span class="field-value">{spot_price_derived}</span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">🚨 预警触发信息</div>

            {'<div style="font-weight: bold; color: #dc2626; margin-bottom: 10px;">📊 张数预警</div>' if 'volume' in alert_reasons else ''}
            {'<div class="field-row">' if 'volume' in alert_reasons else ''}
            {'<span class="field-label">期权腿总张数:</span>' if 'volume' in alert_reasons else ''}
            {'<span class="field-value"><span class="volume-highlight">' + f"{options_sum:.1f}x" + '</span></span>' if 'volume' in alert_reasons else ''}
            {'</div>' if 'volume' in alert_reasons else ''}
            {'<div class="field-row">' if 'volume' in alert_reasons else ''}
            {'<span class="field-label">期权腿数量:</span>' if 'volume' in alert_reasons else ''}
            {'<span class="field-value">' + f"{options_count} 条腿" + '</span>' if 'volume' in alert_reasons else ''}
            {'</div>' if 'volume' in alert_reasons else ''}
            {'<div class="field-row">' if 'volume' in alert_reasons else ''}
            {'<span class="field-label">张数阈值:</span>' if 'volume' in alert_reasons else ''}
            {'<span class="field-value">' + f"{threshold}x" + '</span>' if 'volume' in alert_reasons else ''}
            {'</div>' if 'volume' in alert_reasons else ''}
            {'<div class="field-row">' if 'volume' in alert_reasons else ''}
            {'<span class="field-label">超出幅度:</span>' if 'volume' in alert_reasons else ''}
            {'<span class="field-value" style="color: #dc2626; font-weight: bold;">' + f"{((options_sum / threshold - 1) * 100):.1f}%" + '</span>' if 'volume' in alert_reasons and options_sum > threshold else ''}
            {'</div>' if 'volume' in alert_reasons else ''}

            {'<div style="height: 15px;"></div>' if 'volume' in alert_reasons and 'premium' in alert_reasons else ''}

            {'<div style="font-weight: bold; color: #7c3aed; margin-bottom: 10px;">💰 净权利金预警</div>' if 'premium' in alert_reasons else ''}
            {'<div class="field-row">' if 'premium' in alert_reasons and premium_paid_usd is not None else ''}
            {'<span class="field-label">支付权利金 (Paid):</span>' if 'premium' in alert_reasons and premium_paid_usd is not None else ''}
            {'<span class="field-value" style="color: #dc2626;">' + f"${premium_paid_usd:,.2f}" + '</span>' if 'premium' in alert_reasons and premium_paid_usd is not None else ''}
            {'</div>' if 'premium' in alert_reasons and premium_paid_usd is not None else ''}
            {'<div class="field-row">' if 'premium' in alert_reasons and premium_received_usd is not None else ''}
            {'<span class="field-label">收到权利金 (Received):</span>' if 'premium' in alert_reasons and premium_received_usd is not None else ''}
            {'<span class="field-value" style="color: #059669;">' + f"${premium_received_usd:,.2f}" + '</span>' if 'premium' in alert_reasons and premium_received_usd is not None else ''}
            {'</div>' if 'premium' in alert_reasons and premium_received_usd is not None else ''}
            {'<div class="field-row">' if 'premium' in alert_reasons and net_premium_usd is not None else ''}
            {'<span class="field-label">净权利金 (Net):</span>' if 'premium' in alert_reasons and net_premium_usd is not None else ''}
            {'<span class="field-value" style="color: ' + ('color: #059669;' if net_premium_usd >= 0 else '#dc2626;') + ' font-weight: bold;">' + f"{'$' if net_premium_usd >= 0 else '-$'}{abs(net_premium_usd):,.2f}" + '</span>' if 'premium' in alert_reasons and net_premium_usd is not None else ''}
            {'</div>' if 'premium' in alert_reasons and net_premium_usd is not None else ''}
            {'<div class="field-row">' if 'premium' in alert_reasons and abs_net_premium_usd is not None else ''}
            {'<span class="field-label">净权利金绝对值:</span>' if 'premium' in alert_reasons and abs_net_premium_usd is not None else ''}
            {'<span class="field-value"><span class="volume-highlight" style="color: #7c3aed;">' + f"${abs_net_premium_usd:,.2f}" + '</span></span>' if 'premium' in alert_reasons and abs_net_premium_usd is not None else ''}
            {'</div>' if 'premium' in alert_reasons and abs_net_premium_usd is not None else ''}
            {'<div class="field-row">' if 'premium' in alert_reasons else ''}
            {'<span class="field-label">权利金阈值:</span>' if 'premium' in alert_reasons else ''}
            {'<span class="field-value">$1,000,000</span>' if 'premium' in alert_reasons else ''}
            {'</div>' if 'premium' in alert_reasons else ''}
            {'<div class="field-row">' if 'premium' in alert_reasons and abs_net_premium_usd is not None and abs_net_premium_usd >= 1000000 else ''}
            {'<span class="field-label">超出幅度:</span>' if 'premium' in alert_reasons and abs_net_premium_usd is not None and abs_net_premium_usd >= 1000000 else ''}
            {'<span class="field-value" style="color: #7c3aed; font-weight: bold;">' + f"{((abs_net_premium_usd / 1000000 - 1) * 100):.1f}%" + '</span>' if 'premium' in alert_reasons and abs_net_premium_usd is not None and abs_net_premium_usd >= 1000000 else ''}
            {'</div>' if 'premium' in alert_reasons and abs_net_premium_usd is not None and abs_net_premium_usd >= 1000000 else ''}
        </div>

        <div class="section">
            <div class="section-title">📈 期权腿信息 (Options Legs)</div>
            {''.join([f'''
            <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; border-radius: 6px; margin: 10px 0;">
                <div style="font-weight: bold; color: #92400e; margin-bottom: 8px;">
                    腿 #{i+1}: {leg.get('contract', 'Unknown')}
                </div>
                <div class="field-row">
                    <span class="field-label">方向/数量:</span>
                    <span class="field-value">{leg.get('side', 'Unknown')} <span class="volume-highlight">{leg.get('volume', 0):.1f}x</span></span>
                </div>
                <div class="field-row">
                    <span class="field-label">价格:</span>
                    <span class="field-value">{f"{leg.get('price_btc', 0):.4f} ₿" if leg.get('price_btc') else "N/A"} {f"(${leg.get('price_usd', 0):,.2f})" if leg.get('price_usd') else ""}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Total:</span>
                    <span class="field-value">{f"{leg.get('total_btc', 0):.4f} ₿" if leg.get('total_btc') else "N/A"} {f"(${leg.get('total_usd', 0):,.0f})" if leg.get('total_usd') else ""}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">IV:</span>
                    <span class="field-value">{f"{leg.get('iv', 0):.2f}%" if leg.get('iv') else "N/A"}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Ref (现货价):</span>
                    <span class="field-value">{f"${leg.get('ref_spot_usd', 0):,.2f}" if leg.get('ref_spot_usd') else "N/A"}</span>
                </div>
                {f"""<div class="field-row">
                    <span class="field-label">Quote:</span>
                    <span class="field-value" style="font-size: 12px;">
                        bid: {leg.get('bid', 'N/A')} {f"(size: {leg.get('bid_size')})" if leg.get('bid_size') else ""} |
                        mark: {leg.get('mark', 'N/A')} |
                        ask: {leg.get('ask', 'N/A')} {f"(size: {leg.get('ask_size')})" if leg.get('ask_size') else ""}
                    </span>
                </div>""" if leg.get('bid') or leg.get('mark') or leg.get('ask') else ''}
            </div>
            ''' for i, leg in enumerate(options_legs)])}
        </div>

        {f'''
        <div class="section">
            <div class="section-title">📉 非期权腿 (Non-Options Legs)</div>
            {''.join([f"""
            <div style="background: #f3f4f6; border-left: 4px solid #9ca3af; padding: 15px; border-radius: 6px; margin: 10px 0;">
                <div style="font-weight: bold; color: #4b5563; margin-bottom: 8px;">
                    腿 #{i+1}: {leg.get('contract', 'Unknown')} ({leg.get('instrument_type', 'Unknown')})
                </div>
                <div class="field-row">
                    <span class="field-label">方向/数量:</span>
                    <span class="field-value">{leg.get('side', 'Unknown')} {leg.get('volume', 0):.1f}x</span>
                </div>
                <div class="field-row">
                    <span class="field-label">价格:</span>
                    <span class="field-value">{f"{leg.get('price_btc', 0):.4f} ₿" if leg.get('price_btc') else "N/A"} {f"(${leg.get('price_usd', 0):,.2f})" if leg.get('price_usd') else ""}</span>
                </div>
            </div>
            """ for i, leg in enumerate(non_options_legs)])}
        </div>
        ''' if non_options_legs else '<div class="section"><div class="section-title">📉 非期权腿 (Non-Options Legs)</div><div class="field-row"><span class="field-value" style="color: #9ca3af;">无</span></div></div>'}

        {f'''
        <div class="section">
            <div class="section-title">⚠️ 风险提示 (Risks)</div>
            <div class="greeks-grid">
                <div class="greek-item">
                    <div class="greek-label">Delta (Δ)</div>
                    <div class="greek-value">{greeks.get('delta', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Gamma (Γ)</div>
                    <div class="greek-value">{greeks.get('gamma', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Vega (ν)</div>
                    <div class="greek-value">{greeks.get('vega', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Theta (Θ)</div>
                    <div class="greek-value">{greeks.get('theta', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Rho (ρ)</div>
                    <div class="greek-value">{greeks.get('rho', 'N/A')}</div>
                </div>
            </div>
        </div>
        ''' if any(greeks.values()) else ''}

        <div class="section">
            <div class="section-title">📝 原始消息 (Raw Text)</div>
            <div class="message-box">{message_data.get('text', '')[:1000]}</div>
        </div>

        <div class="footer">
            <p><strong>预警类型:</strong> 单笔大宗期权交易 (OPTIONS ONLY)</p>
            <p><strong>监控交易所:</strong> {config.MONITORED_EXCHANGE}</p>
            <p><strong>触发阈值:</strong> {asset} 期权数量 > {threshold}x</p>
            <p>生成时间: {generated_time}</p>
        </div>
    </div>
</body>
</html>
"""
    else:
        # 英文模板（修正：使用 options_sum 显示期权腿总和）
        test_prefix = "[TEST] " if test_mode else ""
        subject = f"{test_prefix}🚨 Large {asset} OPTIONS Alert - Total {options_sum:.1f}x ({options_count} legs) - {exchange} (Threshold: {threshold})"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #dc2626 0%, #f59e0b 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .alert-tag {{ display: inline-block; background: #dc2626; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 8px; margin-right: 8px; }}
        .trade-card {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .trade-field {{ margin: 12px 0; }}
        .trade-field strong {{ color: #4b5563; min-width: 140px; display: inline-block; }}
        .trade-value {{ color: #1f2937; font-weight: 600; }}
        .volume-highlight {{ font-size: 20px; color: #dc2626; font-weight: bold; }}
        .greeks-section {{ margin-top: 20px; padding: 15px; background: #f3f4f6; border-radius: 6px; }}
        .greeks-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 10px; }}
        .greek-item {{ text-align: center; padding: 8px; background: white; border-radius: 4px; }}
        .greek-label {{ font-size: 11px; color: #6b7280; margin-bottom: 4px; }}
        .greek-value {{ font-size: 14px; color: #1f2937; font-weight: 600; }}
        .message-box {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 15px; border-radius: 6px; margin: 20px 0; font-size: 13px; color: #374151; white-space: pre-wrap; font-family: monospace; max-height: 400px; overflow-y: auto; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Large Block Trade Alert</h1>
            <span class="alert-tag">REALTIME</span>
            <span class="alert-tag">OPTIONS ONLY</span>
        </div>

        <div class="trade-card">
            <h2 style="margin-top: 0; color: #92400e;">{asset} OPTIONS - Large Volume Detected</h2>

            <div class="trade-field">
                <strong>Asset:</strong>
                <span class="trade-value">{asset}</span>
            </div>

            <div class="trade-field">
                <strong>Exchange:</strong>
                <span class="trade-value">{exchange}</span>
            </div>

            <div class="trade-field">
                <strong>Instrument Type:</strong>
                <span class="trade-value">{instrument_type}</span>
            </div>

            <div class="trade-field">
                <strong>Contract:</strong>
                <span class="trade-value">{contract}</span>
            </div>

            <div class="trade-field">
                <strong>Strategy:</strong>
                <span class="trade-value">{strategy}</span>
            </div>

            <div class="trade-field">
                <strong>Side:</strong>
                <span class="trade-value">{side}</span>
            </div>

            <div class="trade-field">
                <strong>Total Options Volume:</strong>
                <span class="volume-highlight">{options_sum:.1f}x</span>
                <span style="color: #6b7280; font-size: 14px;">(Threshold: {threshold}x, Options Legs: {options_count})</span>
            </div>

            <div class="trade-field">
                <strong>Price:</strong>
                <span class="trade-value">{price}</span>
            </div>

            <div class="trade-field">
                <strong>Amount (USD):</strong>
                <span class="trade-value">${amount_usd:,.2f}</span>
            </div>

            <div class="trade-field">
                <strong>IV:</strong>
                <span class="trade-value">{iv}</span>
            </div>

            <div class="trade-field">
                <strong>Spot Price:</strong>
                <span class="trade-value">{spot_price}</span>
            </div>

            <div class="trade-field">
                <strong>Trade Time:</strong>
                <span class="trade-value">{trade_time}</span>
            </div>

            {f'''
            <div class="greeks-section">
                <h3 style="margin-top: 0; color: #4b5563; font-size: 16px;">Greeks</h3>
                <div class="greeks-grid">
                    <div class="greek-item">
                        <div class="greek-label">Delta (Δ)</div>
                        <div class="greek-value">{greeks.get('delta', 'N/A')}</div>
                    </div>
                    <div class="greek-item">
                        <div class="greek-label">Gamma (Γ)</div>
                        <div class="greek-value">{greeks.get('gamma', 'N/A')}</div>
                    </div>
                    <div class="greek-item">
                        <div class="greek-label">Vega (ν)</div>
                        <div class="greek-value">{greeks.get('vega', 'N/A')}</div>
                    </div>
                    <div class="greek-item">
                        <div class="greek-label">Theta (Θ)</div>
                        <div class="greek-value">{greeks.get('theta', 'N/A')}</div>
                    </div>
                    <div class="greek-item">
                        <div class="greek-label">Rho (ρ)</div>
                        <div class="greek-value">{greeks.get('rho', 'N/A')}</div>
                    </div>
                </div>
            </div>
            ''' if any(greeks.values()) else ''}
        </div>

        {f'''
        <h3 style="color: #4b5563; margin-top: 30px;">Options Legs Details:</h3>
        {''.join([f"""
        <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; border-radius: 6px; margin: 10px 0;">
            <div style="font-weight: bold; color: #92400e; margin-bottom: 8px;">
                Leg #{i+1}: {leg.get('contract', 'Unknown')}
            </div>
            <div class="trade-field">
                <strong>Side / Volume:</strong>
                <span class="trade-value">{leg.get('side', 'Unknown')} <span class="volume-highlight">{leg.get('volume', 0):.1f}x</span></span>
            </div>
            <div class="trade-field">
                <strong>Price:</strong>
                <span class="trade-value">{f"{leg.get('price_btc', 0):.4f} ₿" if leg.get('price_btc') else "N/A"} {f"(${leg.get('price_usd', 0):,.2f})" if leg.get('price_usd') else ""}</span>
            </div>
            <div class="trade-field">
                <strong>Total:</strong>
                <span class="trade-value">{f"{leg.get('total_btc', 0):.4f} ₿" if leg.get('total_btc') else "N/A"} {f"(${leg.get('total_usd', 0):,.0f})" if leg.get('total_usd') else ""}</span>
            </div>
            <div class="trade-field">
                <strong>IV:</strong>
                <span class="trade-value">{f"{leg.get('iv', 0):.2f}%" if leg.get('iv') else "N/A"}</span>
            </div>
            <div class="trade-field">
                <strong>Ref Spot:</strong>
                <span class="trade-value">{f"${leg.get('ref_spot_usd', 0):,.2f}" if leg.get('ref_spot_usd') else "N/A"}</span>
            </div>
        </div>
        """ for i, leg in enumerate(options_legs)])}
        ''' if options_legs else ''}

        <h3 style="color: #4b5563; margin-top: 30px;">Original Message:</h3>
        <div class="message-box">{message_data.get('text', '')[:1000]}</div>

        <div class="footer">
            <p><strong>Alert Type:</strong> Single Block Trade (OPTIONS ONLY)</p>
            <p><strong>Monitored Exchange:</strong> {config.MONITORED_EXCHANGE}</p>
            <p><strong>Threshold:</strong> {asset} volume > {threshold}x</p>
            <p>Generated at: {generated_time}</p>
        </div>
    </div>
</body>
</html>
"""

    # 发送 HTML 邮件（接入路由）
    print(f"  [发送] OPTIONS 预警邮件: {asset} options_sum={options_sum:.1f}x options_legs={options_count} @ {exchange}")
    msg_id_str = str(message_data.get('message_id', 'Unknown'))
    mode = 'test' if test_mode else None  # test_mode 参数决定是否强制 test 模式
    return send_html_email(subject, html_body, recipients=None, email_type='alert', mode=mode, msg_id=msg_id_str, report_date=None)


def send_single_trade_alert(asset: str, volume: float, exchange: str,
                            message_text: str, message_date: str, threshold: int) -> bool:
    """
    发送单笔大宗交易预警邮件（简化版，阈值已在外部检查）

    Args:
        asset: 资产类型（BTC / ETH）
        volume: 交易量
        exchange: 交易所
        message_text: 原始消息文本
        message_date: 消息时间（ISO 格式）
        threshold: 触发的阈值

    Returns:
        True: 发送成功
        False: 发送失败
    """
    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print(f"  [跳过] 邮件发送未启用（EMAIL_ENABLED=false）")
        return False

    if not config.EMAIL_PASSWORD:
        print(f"  [错误] EMAIL_PASSWORD 未设置")
        return False

    # 构造邮件标题
    subject = f"🚨 Large Block Trade Alert: {asset} {volume:.1f}x on {exchange} (Threshold: {threshold})"

    # 构造邮件正文
    try:
        trade_time = datetime.fromisoformat(message_date).strftime('%Y-%m-%d %H:%M:%S')
    except:
        trade_time = message_date

    import pytz
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    generated_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

    body = f"""Single Block Trade Alert - {trade_time}
============================================================

🚨 LARGE BLOCK TRADE DETECTED

ASSET: {asset}
EXCHANGE: {exchange}
VOLUME: {volume:.1f}x
THRESHOLD: {threshold} (Exceeded by {volume - threshold:.1f}x)

============================================================
ORIGINAL MESSAGE:
------------------------------------------------------------
{message_text[:800]}
{'...(truncated)' if len(message_text) > 800 else ''}
------------------------------------------------------------

============================================================
Alert generated at: {generated_time}
Monitored exchange: {config.MONITORED_EXCHANGE}
============================================================
"""

    # 发送邮件
    print(f"  [发送] 单笔预警邮件: {asset} {volume:.1f}x @ {exchange}")
    return send_email(subject, body)


def test_daily_report(date: str):
    """测试日报邮件发送"""
    print("\n" + "=" * 60)
    print("测试 1: 发送日报邮件")
    print("=" * 60)

    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print("\n⚠ 警告: EMAIL_ENABLED = False")
        print("提示: 在 config.py 或环境变量中设置 EMAIL_ENABLED=true")
        response = input("是否继续测试? (y/n): ")
        if response.lower() != 'y':
            print("测试已取消")
            return

    if not config.EMAIL_PASSWORD:
        print("\n✗ 错误: EMAIL_PASSWORD 未设置")
        print("请在 config.py 或环境变量中设置 Gmail 应用专用密码")
        return

    # 发送测试邮件
    success = send_daily_report_email_simple(date)

    if success:
        print("\n" + "=" * 60)
        print("✓ 测试成功！请检查邮箱收件")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ 测试失败，请检查错误信息")
        print("=" * 60)


def test_single_trade_alert():
    """测试单笔大宗交易预警邮件"""
    print("\n" + "=" * 60)
    print("测试: 单笔大宗交易预警邮件")
    print("=" * 60)

    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print("\n⚠ 警告: EMAIL_ENABLED = False")
        print("提示: 在 config.py 或环境变量中设置 EMAIL_ENABLED=true")
        response = input("是否继续测试? (y/n): ")
        if response.lower() != 'y':
            print("测试已取消")
            return

    if not config.EMAIL_PASSWORD:
        print("\n✗ 错误: EMAIL_PASSWORD 未设置")
        print("请在 config.py 或环境变量中设置 Gmail 应用专用密码")
        return

    # 构造测试数据（模拟 Deribit 大单）
    print("\n构造测试数据...")
    test_asset = 'BTC'
    test_volume = 250.0  # 超过默认阈值 200
    test_exchange = 'Deribit'
    test_threshold = config.BTC_VOLUME_THRESHOLD
    test_message = """**LONG BTC CALL (🐂 Spot) (250.0x):**
🟢 Bought 250.0x 🔶 BTC-27DEC24-110000-C 📈 at 0.0234 ₿ ($2,456.78)
Total Bought: 5.8500 ₿ ($614.20K), **IV**: 52.34%, **Ref**: $105234.56

Exchange: Deribit
#block"""
    test_date = datetime.now().isoformat()

    print(f"  资产: {test_asset}")
    print(f"  交易所: {test_exchange}")
    print(f"  Volume: {test_volume}x")
    print(f"  阈值: {test_threshold}")
    print(f"  超出: {test_volume - test_threshold:.1f}x")

    # 发送测试邮件
    print(f"\n发送测试邮件...")
    success = send_single_trade_alert(
        asset=test_asset,
        volume=test_volume,
        exchange=test_exchange,
        message_text=test_message,
        message_date=test_date,
        threshold=test_threshold
    )

    if success:
        print("\n" + "=" * 60)
        print("✓ 测试成功！请检查邮箱收件")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ 测试失败，请检查错误信息")
        print("=" * 60)


def test_volume_alert(date: str, force_trigger: bool = False):
    """测试阈值预警邮件发送"""
    print("\n" + "=" * 60)
    print("测试 2: 发送阈值预警邮件")
    print("=" * 60)

    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print("\n⚠ 警告: EMAIL_ENABLED = False")
        print("提示: 在 config.py 或环境变量中设置 EMAIL_ENABLED=true")
        response = input("是否继续测试? (y/n): ")
        if response.lower() != 'y':
            print("测试已取消")
            return

    if not config.EMAIL_PASSWORD:
        print("\n✗ 错误: EMAIL_PASSWORD 未设置")
        print("请在 config.py 或环境变量中设置 Gmail 应用专用密码")
        return

    # 查询统计数据
    print(f"\n查询 {date} 的统计数据...")
    stats = query_daily_stats(date)

    # 判断是否触发阈值
    triggered_assets = []
    if stats['btc_total_volume'] > config.BTC_VOLUME_THRESHOLD:
        triggered_assets.append('BTC')
    if stats['eth_total_volume'] > config.ETH_VOLUME_THRESHOLD:
        triggered_assets.append('ETH')

    # 如果没有触发但强制测试
    if not triggered_assets and force_trigger:
        print(f"\n⚠ 注意: 实际数据未触发阈值，但使用 --force 强制发送测试邮件")
        print(f"  BTC: {stats['btc_total_volume']:.1f} <= {config.BTC_VOLUME_THRESHOLD}")
        print(f"  ETH: {stats['eth_total_volume']:.1f} <= {config.ETH_VOLUME_THRESHOLD}")
        print(f"\n强制触发 BTC 阈值（仅供测试）...")
        triggered_assets = ['BTC']
    elif not triggered_assets:
        print(f"\n✓ 统计完成，但未触发阈值:")
        print(f"  BTC: {stats['btc_total_volume']:.1f} <= {config.BTC_VOLUME_THRESHOLD}")
        print(f"  ETH: {stats['eth_total_volume']:.1f} <= {config.ETH_VOLUME_THRESHOLD}")
        print(f"\n提示: 使用 --force 参数可以强制发送测试邮件")
        return

    # 发送测试邮件
    success = send_volume_threshold_alert_simple(stats, triggered_assets, date)

    if success:
        print("\n" + "=" * 60)
        print("✓ 测试成功！请检查邮箱收件")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ 测试失败，请检查错误信息")
        print("=" * 60)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='Telegram Trade Alert 邮件发送测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 发送日报测试邮件
  python email_sender.py --test-daily --date 2025-12-11

  # 发送阈值预警测试邮件（日汇总）
  python email_sender.py --test-alert --date 2025-12-11

  # 强制发送阈值预警邮件（即使未触发阈值）
  python email_sender.py --test-alert --date 2025-12-11 --force

  # 测试单笔大宗交易预警邮件
  python email_sender.py --test-single-trade
        """
    )

    parser.add_argument('--test-daily', action='store_true',
                       help='测试日报邮件发送')
    parser.add_argument('--test-alert', action='store_true',
                       help='测试阈值预警邮件发送（日汇总）')
    parser.add_argument('--test-single-trade', action='store_true',
                       help='测试单笔大宗交易预警邮件')
    parser.add_argument('--date', type=str,
                       help='指定日期 (格式: YYYY-MM-DD)，默认为今天')
    parser.add_argument('--force', action='store_true',
                       help='强制发送阈值预警邮件（即使未触发阈值）')

    args = parser.parse_args()

    # 确定日期
    if args.date:
        test_date = args.date
    else:
        tz = pytz.timezone(config.REPORT_TIMEZONE)
        test_date = datetime.now(tz).strftime('%Y-%m-%d')

    # 验证日期格式
    try:
        datetime.strptime(test_date, '%Y-%m-%d')
    except ValueError:
        print(f"✗ 错误: 无效的日期格式 '{test_date}'，请使用 YYYY-MM-DD")
        sys.exit(1)

    # 执行测试
    if args.test_daily:
        test_daily_report(test_date)
    elif args.test_alert:
        test_volume_alert(test_date, force_trigger=args.force)
    elif args.test_single_trade:
        test_single_trade_alert()
    else:
        parser.print_help()
        print("\n✗ 错误: 请指定测试类型 (--test-daily / --test-alert / --test-single-trade)")
        sys.exit(1)


# ============================================
# STEP 3：权利金预警邮件发送函数
# ============================================
def send_premium_alert_html(trade_info: dict, message_data: dict, premium_usd_sum: float, threshold: float, lang: str = 'zh', test_mode: bool = False) -> bool:
    """
    发送权利金预警邮件（Premium USD Alert）

    硬规则：
    - 只针对 OPTIONS 腿的总权利金（USD）超过阈值时发送
    - 邮件标题和内容必须区分于张数预警（Volume Alert）
    - 必须包含逐腿的 premium_usd 信息

    Args:
        trade_info: parse_block_trade_message() 解析后的交易信息
        message_data: 消息数据字典
        premium_usd_sum: 期权腿总权利金（USD）
        threshold: 触发的权利金阈值（USD）
        lang: 语言模式 ('en' 或 'zh')
        test_mode: 测试模式（在邮件标题添加【TEST】标记）

    Returns:
        True: 发送成功
        False: 发送失败
    """
    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print(f"  [跳过] 邮件发送未启用（EMAIL_ENABLED=false）")
        return False

    if not config.EMAIL_PASSWORD:
        print(f"  [错误] EMAIL_PASSWORD 未设置")
        return False

    # 提取关键字段
    asset = trade_info.get('asset', 'Unknown')
    exchange = trade_info.get('exchange', 'Unknown')
    strategy = trade_info.get('strategy', 'Unknown')
    greeks = trade_info.get('greeks', {})

    # 提取 legs 信息
    options_legs = trade_info.get('options_legs', [])
    non_options_legs = trade_info.get('non_options_legs', [])
    options_premium_usd_leg_list = trade_info.get('options_premium_usd_leg_list', [])

    options_sum = trade_info.get('options_sum', 0)
    options_count = trade_info.get('options_count', 0)
    spot_price_derived = trade_info.get('spot_price_derived', 'N/A')
    ref_price_usd = trade_info.get('ref_price_usd', None)

    # 格式化时间
    try:
        trade_time = datetime.fromisoformat(message_data['date']).strftime('%Y-%m-%d %H:%M:%S')
    except:
        trade_time = str(message_data.get('date', 'Unknown'))

    import pytz
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    generated_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

    # 构造邮件标题和正文（中文模板）
    if lang == 'zh':
        test_prefix = "【TEST】" if test_mode else ""
        # 🚨 Premium Alert - BTC - $1,234,567 - Deribit - 2025-12-xx xx:xx
        subject = f"{test_prefix}🚨 权利金预警 - {asset} - ${premium_usd_sum:,.0f} - {exchange} - {trade_time}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .alert-tag {{ display: inline-block; background: #7c3aed; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 8px; margin-right: 8px; }}
        .section {{ margin: 20px 0; }}
        .section-title {{ font-size: 16px; font-weight: bold; color: #1f2937; margin-bottom: 10px; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; }}
        .field-row {{ margin: 8px 0; padding: 8px; background: #f9fafb; border-radius: 4px; }}
        .field-label {{ color: #6b7280; min-width: 100px; display: inline-block; }}
        .field-value {{ color: #1f2937; font-weight: 600; }}
        .premium-highlight {{ font-size: 22px; color: #7c3aed; font-weight: bold; }}
        .greeks-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-top: 10px; }}
        .greek-item {{ text-align: center; padding: 8px; background: #f3f4f6; border-radius: 4px; }}
        .greek-label {{ font-size: 11px; color: #6b7280; margin-bottom: 4px; }}
        .greek-value {{ font-size: 14px; color: #1f2937; font-weight: 600; }}
        .message-box {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 15px; border-radius: 6px; margin: 10px 0; font-size: 13px; color: #374151; white-space: pre-wrap; font-family: "Courier New", monospace; max-height: 400px; overflow-y: auto; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💰 单笔大宗期权权利金预警</h1>
            {'<span class="alert-tag">【测试】</span>' if test_mode else ''}
            <span class="alert-tag">PREMIUM USD ALERT</span>
            <span class="alert-tag">OPTIONS ONLY</span>
        </div>

        <div class="section">
            <div class="section-title">📊 资产 / 交易所 / 时间</div>
            <div class="field-row">
                <span class="field-label">资产:</span>
                <span class="field-value">{asset}</span>
            </div>
            <div class="field-row">
                <span class="field-label">交易所:</span>
                <span class="field-value">{exchange}</span>
            </div>
            <div class="field-row">
                <span class="field-label">时间:</span>
                <span class="field-value">{trade_time}</span>
            </div>
            <div class="field-row">
                <span class="field-label">现货价 (Ref):</span>
                <span class="field-value">{spot_price_derived}</span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">🚨 预警触发信息（权利金预警）</div>
            <div class="field-row">
                <span class="field-label">期权腿总权利金:</span>
                <span class="field-value"><span class="premium-highlight">${premium_usd_sum:,.2f}</span></span>
            </div>
            <div class="field-row">
                <span class="field-label">期权腿数量:</span>
                <span class="field-value">{options_count} 条腿（总张数: {options_sum:.1f}x）</span>
            </div>
            <div class="field-row">
                <span class="field-label">触发阈值:</span>
                <span class="field-value">${threshold:,.0f}</span>
            </div>
            <div class="field-row">
                <span class="field-label">超出幅度:</span>
                <span class="field-value" style="color: #7c3aed; font-weight: bold;">{((premium_usd_sum / threshold - 1) * 100):.1f}%</span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">📈 期权腿信息 (Options Legs)</div>
            {''.join([f'''
            <div style="background: #f3e8ff; border-left: 4px solid #7c3aed; padding: 15px; border-radius: 6px; margin: 10px 0;">
                <div style="font-weight: bold; color: #5b21b6; margin-bottom: 8px;">
                    腿 #{i+1}: {leg.get('contract', 'Unknown')}
                </div>
                <div class="field-row">
                    <span class="field-label">方向/数量:</span>
                    <span class="field-value">{leg.get('side', 'Unknown')} <span style="color: #7c3aed; font-weight: bold;">{leg.get('volume', 0):.1f}x</span></span>
                </div>
                <div class="field-row">
                    <span class="field-label">价格:</span>
                    <span class="field-value">{f"{leg.get('price_btc', 0):.4f} ₿" if leg.get('price_btc') else "N/A"} {f"(${leg.get('price_usd', 0):,.2f})" if leg.get('price_usd') else ""}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Total:</span>
                    <span class="field-value">{f"{leg.get('total_btc', 0):.4f} ₿" if leg.get('total_btc') else "N/A"} {f"(${leg.get('total_usd', 0):,.0f})" if leg.get('total_usd') else ""}</span>
                </div>
                <div class="field-row" style="background: #fef3c7; border-left: 2px solid #f59e0b;">
                    <span class="field-label">💰 Premium (USD):</span>
                    <span class="field-value" style="color: #7c3aed; font-weight: bold;">
                        {f"${next((p['premium_usd'] for p in options_premium_usd_leg_list if p['leg'] == i+1), 0):,.2f}" if options_premium_usd_leg_list else "N/A"}
                    </span>
                </div>
                <div class="field-row">
                    <span class="field-label">IV:</span>
                    <span class="field-value">{f"{leg.get('iv', 0):.2f}%" if leg.get('iv') else "N/A"}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Ref (现货价):</span>
                    <span class="field-value">{f"${leg.get('ref_spot_usd', 0):,.2f}" if leg.get('ref_spot_usd') else "N/A"}</span>
                </div>
                {f"""<div class="field-row">
                    <span class="field-label">Quote:</span>
                    <span class="field-value" style="font-size: 12px;">
                        bid: {leg.get('bid', 'N/A')} {f"(size: {leg.get('bid_size')})" if leg.get('bid_size') else ""} |
                        mark: {leg.get('mark', 'N/A')} |
                        ask: {leg.get('ask', 'N/A')} {f"(size: {leg.get('ask_size')})" if leg.get('ask_size') else ""}
                    </span>
                </div>""" if leg.get('bid') or leg.get('mark') or leg.get('ask') else ''}
            </div>
            ''' for i, leg in enumerate(options_legs)])}
        </div>

        {f'''
        <div class="section">
            <div class="section-title">📉 非期权腿 (Non-Options Legs)</div>
            {''.join([f"""
            <div style="background: #f3f4f6; border-left: 4px solid #9ca3af; padding: 15px; border-radius: 6px; margin: 10px 0;">
                <div style="font-weight: bold; color: #4b5563; margin-bottom: 8px;">
                    腿 #{i+1}: {leg.get('contract', 'Unknown')} ({leg.get('instrument_type', 'Unknown')})
                </div>
                <div class="field-row">
                    <span class="field-label">方向/数量:</span>
                    <span class="field-value">{leg.get('side', 'Unknown')} {leg.get('volume', 0):.1f}x</span>
                </div>
                <div class="field-row">
                    <span class="field-label">价格:</span>
                    <span class="field-value">{f"{leg.get('price_btc', 0):.4f} ₿" if leg.get('price_btc') else "N/A"} {f"(${leg.get('price_usd', 0):,.2f})" if leg.get('price_usd') else ""}</span>
                </div>
            </div>
            """ for i, leg in enumerate(non_options_legs)])}
        </div>
        ''' if non_options_legs else '<div class="section"><div class="section-title">📉 非期权腿 (Non-Options Legs)</div><div class="field-row"><span class="field-value" style="color: #9ca3af;">无</span></div></div>'}

        {f'''
        <div class="section">
            <div class="section-title">⚠️ 风险提示 (Risks)</div>
            <div class="greeks-grid">
                <div class="greek-item">
                    <div class="greek-label">Delta (Δ)</div>
                    <div class="greek-value">{greeks.get('delta', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Gamma (Γ)</div>
                    <div class="greek-value">{greeks.get('gamma', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Vega (ν)</div>
                    <div class="greek-value">{greeks.get('vega', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Theta (Θ)</div>
                    <div class="greek-value">{greeks.get('theta', 'N/A')}</div>
                </div>
                <div class="greek-item">
                    <div class="greek-label">Rho (ρ)</div>
                    <div class="greek-value">{greeks.get('rho', 'N/A')}</div>
                </div>
            </div>
        </div>
        ''' if any(greeks.values()) else ''}

        <div class="section">
            <div class="section-title">📝 原始消息 (Raw Text)</div>
            <div class="message-box">{message_data.get('text', '')[:1000]}</div>
        </div>

        <div class="footer">
            <p><strong>预警类型:</strong> 权利金预警 (Premium USD Alert - OPTIONS ONLY)</p>
            <p><strong>监控交易所:</strong> {config.MONITORED_EXCHANGE}</p>
            <p><strong>触发阈值:</strong> 期权腿总权利金 (USD) > ${threshold:,.0f}</p>
            <p>生成时间: {generated_time}</p>
        </div>
    </div>
</body>
</html>
"""
    else:
        # 英文模板
        test_prefix = "[TEST] " if test_mode else ""
        subject = f"{test_prefix}🚨 Premium Alert - {asset} - ${premium_usd_sum:,.0f} - {exchange} - {trade_time}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .alert-tag {{ display: inline-block; background: #7c3aed; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 8px; margin-right: 8px; }}
        .trade-card {{ background: #f3e8ff; border-left: 4px solid #7c3aed; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .trade-field {{ margin: 12px 0; }}
        .trade-field strong {{ color: #4b5563; min-width: 180px; display: inline-block; }}
        .trade-value {{ color: #1f2937; font-weight: 600; }}
        .premium-highlight {{ font-size: 22px; color: #7c3aed; font-weight: bold; }}
        .message-box {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 15px; border-radius: 6px; margin: 20px 0; font-size: 13px; color: #374151; white-space: pre-wrap; font-family: monospace; max-height: 400px; overflow-y: auto; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💰 Premium USD Alert</h1>
            <span class="alert-tag">REALTIME</span>
            <span class="alert-tag">OPTIONS ONLY</span>
        </div>

        <div class="trade-card">
            <h2 style="margin-top: 0; color: #5b21b6;">{asset} OPTIONS - Large Premium Detected</h2>

            <div class="trade-field">
                <strong>Asset:</strong>
                <span class="trade-value">{asset}</span>
            </div>

            <div class="trade-field">
                <strong>Exchange:</strong>
                <span class="trade-value">{exchange}</span>
            </div>

            <div class="trade-field">
                <strong>Total Options Premium (USD):</strong>
                <span class="premium-highlight">${premium_usd_sum:,.2f}</span>
                <span style="color: #6b7280; font-size: 14px;">(Threshold: ${threshold:,.0f})</span>
            </div>

            <div class="trade-field">
                <strong>Options Legs:</strong>
                <span class="trade-value">{options_count} legs (Total Volume: {options_sum:.1f}x)</span>
            </div>

            <div class="trade-field">
                <strong>Spot Price (Ref):</strong>
                <span class="trade-value">{spot_price_derived}</span>
            </div>

            <div class="trade-field">
                <strong>Trade Time:</strong>
                <span class="trade-value">{trade_time}</span>
            </div>
        </div>

        <h3 style="color: #4b5563; margin-top: 30px;">Options Legs Details:</h3>
        {''.join([f"""
        <div style="background: #f3e8ff; border-left: 4px solid #7c3aed; padding: 15px; border-radius: 6px; margin: 10px 0;">
            <div style="font-weight: bold; color: #5b21b6; margin-bottom: 8px;">
                Leg #{i+1}: {leg.get('contract', 'Unknown')}
            </div>
            <div class="trade-field">
                <strong>Side / Volume:</strong>
                <span class="trade-value">{leg.get('side', 'Unknown')} <span style="color: #7c3aed; font-weight: bold;">{leg.get('volume', 0):.1f}x</span></span>
            </div>
            <div class="trade-field">
                <strong>Price:</strong>
                <span class="trade-value">{f"{leg.get('price_btc', 0):.4f} ₿" if leg.get('price_btc') else "N/A"} {f"(${leg.get('price_usd', 0):,.2f})" if leg.get('price_usd') else ""}</span>
            </div>
            <div class="trade-field">
                <strong>Total:</strong>
                <span class="trade-value">{f"{leg.get('total_btc', 0):.4f} ₿" if leg.get('total_btc') else "N/A"} {f"(${leg.get('total_usd', 0):,.0f})" if leg.get('total_usd') else ""}</span>
            </div>
            <div class="trade-field" style="background: #fef3c7; padding: 8px; border-radius: 4px;">
                <strong>💰 Premium (USD):</strong>
                <span class="trade-value" style="color: #7c3aed; font-weight: bold;">
                    {f"${next((p['premium_usd'] for p in options_premium_usd_leg_list if p['leg'] == i+1), 0):,.2f}" if options_premium_usd_leg_list else "N/A"}
                </span>
            </div>
            <div class="trade-field">
                <strong>IV:</strong>
                <span class="trade-value">{f"{leg.get('iv', 0):.2f}%" if leg.get('iv') else "N/A"}</span>
            </div>
            <div class="trade-field">
                <strong>Ref Spot:</strong>
                <span class="trade-value">{f"${leg.get('ref_spot_usd', 0):,.2f}" if leg.get('ref_spot_usd') else "N/A"}</span>
            </div>
        </div>
        """ for i, leg in enumerate(options_legs)])}

        <h3 style="color: #4b5563; margin-top: 30px;">Original Message:</h3>
        <div class="message-box">{message_data.get('text', '')[:1000]}</div>

        <div class="footer">
            <p><strong>Alert Type:</strong> Premium USD Alert (OPTIONS ONLY)</p>
            <p><strong>Monitored Exchange:</strong> {config.MONITORED_EXCHANGE}</p>
            <p><strong>Threshold:</strong> Total Options Premium (USD) > ${threshold:,.0f}</p>
            <p>Generated at: {generated_time}</p>
        </div>
    </div>
</body>
</html>
"""

    # 发送 HTML 邮件
    print(f"  [发送] 权利金预警邮件: {asset} premium_usd_sum=${premium_usd_sum:,.2f} @ {exchange}")
    return send_html_email(subject, html_body)


if __name__ == '__main__':
    main()
