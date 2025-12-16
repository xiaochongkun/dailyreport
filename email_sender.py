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


def create_smtp_connection():
    """
    创建并返回已登录的 SMTP 连接

    Returns:
        SMTP 连接对象或 None（失败时）
    """
    try:
        smtp = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=10)
        if config.SMTP_USE_TLS:
            smtp.starttls()
        smtp.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] smtp_connected")
        return smtp
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] smtp_failed error={e}")
        return None


def send_email(subject: str, body: str, recipients: list = None) -> bool:
    """
    通用邮件发送函数（retry 1次）

    Args:
        subject: 邮件标题
        body: 邮件正文（纯文本）
        recipients: 收件人列表（默认使用 config.EMAIL_RECIPIENTS）

    Returns:
        True: 发送成功
        False: 发送失败
    """
    import time
    if recipients is None:
        recipients = config.EMAIL_RECIPIENTS

    for attempt in range(2):
        try:
            msg = MIMEMultipart()
            msg['From'] = config.EMAIL_SENDER
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            smtp = create_smtp_connection()
            if smtp is None:
                raise Exception("SMTP connection failed")
            smtp.send_message(msg)
            smtp.quit()

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] sent subject='{subject[:50]}'")
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] failed attempt={attempt+1} error={e}")
            if attempt == 0:
                time.sleep(2)
    return False


def send_html_email(subject: str, html_body: str, recipients: list = None) -> bool:
    """
    发送 HTML 格式邮件（带纯文本 fallback，retry 1次）

    Args:
        subject: 邮件标题
        html_body: HTML 正文
        recipients: 收件人列表（默认使用 config.EMAIL_RECIPIENTS）

    Returns:
        True: 发送成功
        False: 发送失败
    """
    import time, re
    if recipients is None:
        recipients = config.EMAIL_RECIPIENTS

    for attempt in range(2):
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = config.EMAIL_SENDER
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject

            text_body = re.sub(r'<[^>]+>', '', html_body)
            text_body = re.sub(r'\s+', ' ', text_body).strip()

            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            smtp = create_smtp_connection()
            if smtp is None:
                raise Exception("SMTP connection failed")
            smtp.send_message(msg)
            smtp.quit()

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] html_sent subject='{subject[:50]}'")
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] html_failed attempt={attempt+1} error={e}")
            if attempt == 0:
                time.sleep(2)
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

    # 发送邮件
    print(f"\n发送日报邮件...")
    return send_email(subject, body)


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


def send_single_trade_alert_html(trade_info: dict, message_data: dict, threshold: int, lang: str = 'en', test_mode: bool = False) -> bool:
    """
    发送单笔 OPTIONS 交易预警邮件（HTML 格式，OPTIONS ONLY）

    Args:
        trade_info: parse_block_trade_message() 解析后的交易信息
        message_data: 消息数据字典
        threshold: 触发的阈值
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
    volume = trade_info.get('volume', 0.0)
    exchange = trade_info.get('exchange', 'Unknown')
    contract = trade_info.get('contract', 'Unknown')
    strategy = trade_info.get('strategy', 'Unknown')
    instrument_type = trade_info.get('instrument_type', 'Unknown')
    side = trade_info.get('side', 'Unknown')
    price = trade_info.get('price', 'Unknown')
    iv = trade_info.get('iv', 'Unknown')
    amount_usd = trade_info.get('amount_usd', 0.0)
    spot_price = trade_info.get('spot_price', 'N/A')
    greeks = trade_info.get('greeks', {})

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
            {'<span class="alert-tag">【测试】</span>' if test_mode else ''}
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
        </div>

        <div class="section">
            <div class="section-title">📈 期权腿信息 (Options Legs)</div>
            <div class="field-row">
                <span class="field-label">合约:</span>
                <span class="field-value">{contract}</span>
            </div>
            <div class="field-row">
                <span class="field-label">方向:</span>
                <span class="field-value">{side}</span>
            </div>
            <div class="field-row">
                <span class="field-label">数量:</span>
                <span class="volume-highlight">{volume:.1f}x</span>
                <span style="color: #6b7280; font-size: 14px;"> (阈值: {threshold}x)</span>
            </div>
            <div class="field-row">
                <span class="field-label">价格:</span>
                <span class="field-value">{price}</span>
            </div>
            <div class="field-row">
                <span class="field-label">IV:</span>
                <span class="field-value">{iv}</span>
            </div>
            <div class="field-row">
                <span class="field-label">现货价:</span>
                <span class="field-value">{spot_price}</span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">📉 非期权腿 (Non-Options Legs)</div>
            <div class="field-row">
                <span class="field-value" style="color: #9ca3af;">无</span>
            </div>
        </div>

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
        # 英文模板（原有逻辑）
        test_prefix = "[TEST] " if test_mode else ""
        subject = f"{test_prefix}🚨 Large {asset} OPTIONS Alert - {contract} - Volume {volume:.1f}x (Threshold: {threshold})"

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
                <strong>Volume:</strong>
                <span class="volume-highlight">{volume:.1f}x</span>
                <span style="color: #6b7280; font-size: 14px;">(Threshold: {threshold}x)</span>
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

    # 发送 HTML 邮件
    print(f"  [发送] OPTIONS 预警邮件: {asset} {volume:.1f}x @ {exchange}")
    return send_html_email(subject, html_body)


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


if __name__ == '__main__':
    main()
