"""
日报生成模块
从数据库提取过去 24 小时的数据并生成结构化的 HTML 邮件
"""

from datetime import datetime, timedelta
import pytz
import json
import config
from database import get_session, get_messages_by_date_range, get_block_trades_by_date_range, DailyReport


def normalize_block_trades(block_trades, filter_non_options=False):
    """
    标准化交易：统一解析口径

    ⚠️ 修正：支持过滤 FUTURES/PERPETUAL（只保留 OPTIONS）

    Args:
        block_trades: DB 模型列表
        filter_non_options: 是否过滤掉 FUTURES/PERPETUAL，只保留 OPTIONS

    Returns:
        list[dict]: normalized trades
    """
    normalized = []
    for trade in block_trades:
        try:
            parsed = parse_block_trade_message(trade.text or '')

            # ✅ 过滤逻辑：如果 filter_non_options=True，跳过 FUTURES/PERPETUAL
            if filter_non_options:
                instrument_type = parsed.get('instrument_type', 'Unknown')
                if instrument_type in ['FUTURES', 'PERPETUAL']:
                    continue

            # 安全获取 date
            ts = None
            date_str = 'Unknown'
            try:
                if hasattr(trade, 'date') and trade.date:
                    ts = trade.date.isoformat()
                    date_str = trade.date.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

            normalized.append({
                'asset': parsed.get('asset', 'Unknown'),
                'volume': parsed.get('volume', 0.0),
                'exchange': parsed.get('exchange', 'Unknown'),
                'amount_usd': parsed.get('amount_usd', 0.0),
                'ts': ts,
                'date': date_str,  # 兼容 legacy template
                'raw_text': trade.text or '',
                'strategy': parsed.get('strategy', 'Unknown'),
                'contract': parsed.get('contract', 'Unknown'),
                'price': parsed.get('price', 'Unknown'),
                'iv': parsed.get('iv', 'Unknown'),
                'ask': parsed.get('ask', 'Unknown'),
                'mark': parsed.get('mark', 'Unknown'),
                'premium': parsed.get('premium', 'Unknown'),
                'instrument_type': parsed.get('instrument_type', 'Unknown'),
                'greeks': parsed.get('greeks', {}),
                'msg_id': getattr(trade, 'message_id', 'Unknown'),  # 添加 message_id
                'side': parsed.get('side', 'Unknown'),  # 添加 side
                'spot_price': parsed.get('spot_price', 'N/A')  # 添加 spot_price
            })
        except Exception as e:
            # 解析失败，添加默认值
            normalized.append({
                'asset': 'Unknown',
                'volume': 0.0,
                'exchange': 'Unknown',
                'amount_usd': 0.0,
                'ts': None,
                'date': 'Unknown',  # 兼容 legacy template
                'raw_text': getattr(trade, 'text', ''),
                'strategy': 'Unknown',
                'contract': 'Unknown',
                'price': 'Unknown',
                'iv': 'Unknown',
                'ask': 'Unknown',
                'mark': 'Unknown',
                'premium': 'Unknown',
                'instrument_type': 'Unknown',
                'greeks': {},
                'msg_id': getattr(trade, 'message_id', 'Unknown'),
                'side': 'Unknown',
                'spot_price': 'N/A'
            })
    return normalized


def build_daily_report_data(messages, block_trades, start_date, end_date, top_limit=3):
    """
    纯函数：聚合统计数据（不访问DB、不发邮件）

    ⚠️ 修正：
    - volume 统计只基于期权（过滤 FUTURES/PERPETUAL）
    - BTC/ETH TopN 独立生成（不会出现 ETH 为空）

    Args:
        messages: 消息列表
        block_trades: 大宗交易列表
        start_date: 开始时间
        end_date: 结束时间
        top_limit: TopN 数量

    Returns:
        report_data: dict
    """
    # 提取现货价格
    spot_prices = extract_spot_prices(messages)

    # 标准化交易（全量，用于展示所有交易）
    normalized_all = normalize_block_trades(block_trades, filter_non_options=False)

    # ✅ 修正：用于 volume 统计和 TopN 排名的只包含 OPTIONS
    normalized_options = normalize_block_trades(block_trades, filter_non_options=True)

    # ✅ 计算统计指标（只基于期权）
    btc_count = sum(1 for t in normalized_options if t['asset'] == 'BTC')
    eth_count = sum(1 for t in normalized_options if t['asset'] == 'ETH')
    other_count = len(normalized_options) - btc_count - eth_count

    btc_volume = sum(t['volume'] for t in normalized_options if t['asset'] == 'BTC')
    eth_volume = sum(t['volume'] for t in normalized_options if t['asset'] == 'ETH')
    total_volume = btc_volume + eth_volume

    all_volumes = [t['volume'] for t in normalized_options if t['volume'] > 0]
    avg_volume = total_volume / len(normalized_options) if normalized_options else 0
    max_volume = max(all_volumes) if all_volumes else 0

    # breakdown by exchange (只基于期权)
    breakdown_exchange = {}
    for t in normalized_options:
        ex = t['exchange']
        if ex not in breakdown_exchange:
            breakdown_exchange[ex] = {'count': 0, 'total_volume': 0.0}
        breakdown_exchange[ex]['count'] += 1
        breakdown_exchange[ex]['total_volume'] += t['volume']

    # breakdown by asset (只基于期权)
    breakdown_asset = {
        'BTC': {'count': btc_count, 'total_volume': btc_volume},
        'ETH': {'count': eth_count, 'total_volume': eth_volume},
        'Other': {'count': other_count, 'total_volume': 0.0}
    }

    # ✅ 修正：BTC/ETH 独立生成 TopN（各自按 volume 排序）
    btc_trades = [t for t in normalized_options if t['asset'] == 'BTC']
    eth_trades = [t for t in normalized_options if t['asset'] == 'ETH']

    btc_by_volume = sorted(btc_trades, key=lambda x: x['volume'], reverse=True)[:top_limit]
    eth_by_volume = sorted(eth_trades, key=lambda x: x['volume'], reverse=True)[:top_limit]

    btc_by_amount = sorted(btc_trades, key=lambda x: x['amount_usd'], reverse=True)[:top_limit]
    eth_by_amount = sorted(eth_trades, key=lambda x: x['amount_usd'], reverse=True)[:top_limit]

    # 添加 rank
    for i, t in enumerate(btc_by_volume, 1):
        t['rank'] = i
    for i, t in enumerate(eth_by_volume, 1):
        t['rank'] = i
    for i, t in enumerate(btc_by_amount, 1):
        t['rank'] = i
    for i, t in enumerate(eth_by_amount, 1):
        t['rank'] = i

    top_trades = {
        'btc_by_amount': btc_by_amount,
        'btc_by_volume': btc_by_volume,
        'eth_by_amount': eth_by_amount,
        'eth_by_volume': eth_by_volume
    }

    # 全局 TopN（用于兼容旧模板，也只基于期权）
    top_trades_list = sorted(normalized_options, key=lambda x: x['volume'], reverse=True)[:top_limit * 2]
    for i, t in enumerate(top_trades_list, 1):
        t['rank'] = i

    return {
        'meta': {
            'report_date': start_date.strftime('%Y-%m-%d'),
            'start_ts': start_date.isoformat(),
            'end_ts': end_date.isoformat(),
            'generated_at': datetime.now(pytz.timezone(config.REPORT_TIMEZONE)).isoformat(),
            'filter_note': 'Volume 统计只包含期权交易（OPTIONS），已过滤 FUTURES/PERPETUAL'
        },
        'counts': {
            'total_messages': len(messages),
            'block_trades': len(normalized_options),  # 只统计期权
            'btc_count': btc_count,
            'eth_count': eth_count,
            'other_count': other_count,
            'total_trades_all': len(normalized_all)  # 全部交易数（包含期货）
        },
        'volume_stats': {
            'total_volume': total_volume,
            'avg_volume': avg_volume,
            'max_volume': max_volume,
            'btc_volume': btc_volume,
            'eth_volume': eth_volume
        },
        'breakdown_by_exchange': breakdown_exchange,
        'breakdown_by_asset': breakdown_asset,
        'spot_prices': spot_prices,
        'top_trades': top_trades,
        'top_trades_list': top_trades_list,
        'trade_statistics': {
            'total': len(normalized_options),  # 只统计期权
            'btc_count': btc_count,
            'eth_count': eth_count,
            'other_count': other_count
        }
    }


def render_report_text(report_data):
    """纯文本渲染"""
    meta = report_data['meta']
    counts = report_data['counts']
    vol = report_data['volume_stats']

    return f"""Daily Trade Report - {meta['report_date']}

BTC: {counts['btc_count']} trades, {vol['btc_volume']:.1f}x
ETH: {counts['eth_count']} trades, {vol['eth_volume']:.1f}x
Total: {counts['total_messages']} messages, {counts['block_trades']} trades
Volume: total={vol['total_volume']:.1f} avg={vol['avg_volume']:.1f} max={vol['max_volume']:.1f}
"""


def render_report_html(report_data):
    """HTML 渲染（支持 v1/v2）"""
    version = getattr(config, 'REPORT_TEMPLATE_VERSION', 'v1')

    if version == 'v2':
        return render_report_html_v2(report_data)
    else:
        # v1: 兼容旧格式
        legacy_data = {
            'generated_at': report_data['meta']['generated_at'],
            'time_range': {
                'start': report_data['meta']['start_ts'],
                'end': report_data['meta']['end_ts'],
                'timezone': config.REPORT_TIMEZONE
            },
            'spot_prices': report_data['spot_prices'],
            'trade_statistics': report_data['trade_statistics'],
            'top_trades': report_data['top_trades'],
            'total_messages': report_data['counts']['total_messages'],
            'total_block_trades': report_data['counts']['block_trades']
        }
        return build_daily_report_html(legacy_data)


def render_report_html_v2(report_data):
    """v2 简化模板：时间范围 + counts + volume_stats + Top3 表格"""
    meta = report_data['meta']
    counts = report_data['counts']
    vol = report_data['volume_stats']
    top_list = report_data.get('top_trades_list', [])[:3]

    top_rows = ""
    for i, t in enumerate(top_list, 1):
        top_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{t['asset']}</td>
            <td>{t['exchange']}</td>
            <td>{t['volume']:.1f}</td>
            <td>{t['strategy']}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial; max-width: 800px; margin: 20px auto; }}
        h1 {{ color: #2c3e50; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
    </style>
</head>
<body>
    <h1>Daily Trade Report - {meta['report_date']}</h1>

    <h2>Time Range</h2>
    <p>{meta['start_ts']} to {meta['end_ts']}</p>

    <h2>Counts</h2>
    <p>Messages: {counts['total_messages']}, Block Trades: {counts['block_trades']}</p>
    <p>BTC: {counts['btc_count']}, ETH: {counts['eth_count']}, Other: {counts['other_count']}</p>

    <h2>Volume Stats</h2>
    <p>Total: {vol['total_volume']:.1f}, Avg: {vol['avg_volume']:.1f}, Max: {vol['max_volume']:.1f}</p>

    <h2>Top 3 Trades</h2>
    <table>
        <tr>
            <th>#</th>
            <th>Asset</th>
            <th>Exchange</th>
            <th>Volume</th>
            <th>Strategy</th>
        </tr>
        {top_rows}
    </table>

    <p style="text-align: center; color: #999; font-size: 12px;">
        Generated at {meta['generated_at']}
    </p>
</body>
</html>"""


async def generate_daily_report(target_date=None):
    """
    生成每日报告（东八区 16:00 - 16:00）

    Args:
        target_date: 目标日期 (datetime.date 或 None)，None 表示使用默认逻辑

    报告内容包括：
    1. 统计时间范围
    2. 当日关键市场指标（BTC 和 ETH 现货价格）
    3. 大宗交易数量统计（总笔数、BTC 笔数、ETH 笔数）
    4. Top 3 影响力交易详情

    Returns:
        报告数据字典
    """
    # 计算时间范围（东八区 16:00 - 16:00）
    tz = pytz.timezone(config.REPORT_TIMEZONE)

    if target_date:
        # 使用指定日期
        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        base_dt = tz.localize(datetime.combine(target_date, datetime.min.time()))
        end_date = base_dt.replace(hour=config.REPORT_HOUR, minute=config.REPORT_MINUTE, second=0, microsecond=0)
        start_date = end_date - timedelta(hours=config.REPORT_WINDOW_HOURS)
    else:
        # 默认逻辑
        now = datetime.now(tz)
        today_16 = now.replace(hour=config.REPORT_HOUR, minute=config.REPORT_MINUTE, second=0, microsecond=0)

        if now.hour < config.REPORT_HOUR:
            end_date = today_16
            start_date = end_date - timedelta(hours=config.REPORT_WINDOW_HOURS)
        else:
            end_date = today_16
            start_date = end_date - timedelta(hours=config.REPORT_WINDOW_HOURS)

    report_date = None

    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"时区: {config.REPORT_TIMEZONE}")
    print()

    # 获取数据库会话
    session = get_session()

    try:
        # 1. 统计时间范围
        time_range = {
            'start': start_date.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'end': end_date.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'timezone': config.REPORT_TIMEZONE
        }

        # 2. 获取所有消息
        all_messages = get_messages_by_date_range(session, start_date, end_date)
        print(f"✓ 获取到 {len(all_messages)} 条消息")

        # 3. 获取大宗交易
        block_trades = get_block_trades_by_date_range(session, start_date, end_date)
        print(f"✓ 获取到 {len(block_trades)} 条大宗交易")

        # 4. 聚合数据（纯函数）
        report_data = build_daily_report_data(all_messages, block_trades, start_date, end_date)
        print(f"✓ 统计完成: blocks={report_data['counts']['block_trades']} vol={report_data['volume_stats']['total_volume']:.1f}")

        # 5. 渲染 HTML
        html_content = render_report_html(report_data)

        # 6. 保存报告到数据库
        report_date = start_date.strftime('%Y-%m-%d')
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [GENERATE_REPORT] start report_date={report_date}")

        # 检查是否已存在该日期的报告
        existing_report = session.query(DailyReport).filter_by(report_date=report_date).first()

        if existing_report:
            # 更新现有报告
            existing_report.start_time = start_date
            existing_report.end_time = end_date
            existing_report.total_messages = report_data['counts']['total_messages']
            existing_report.total_block_trades = report_data['counts']['block_trades']
            existing_report.btc_trade_count = report_data['counts']['btc_count']
            existing_report.btc_total_volume = int(report_data['volume_stats']['btc_volume'])
            existing_report.eth_trade_count = report_data['counts']['eth_count']
            existing_report.eth_total_volume = int(report_data['volume_stats']['eth_volume'])
            existing_report.btc_spot_price = report_data['spot_prices']['btc']
            existing_report.eth_spot_price = report_data['spot_prices']['eth']
            existing_report.report_data = json.dumps(report_data, ensure_ascii=False)
            existing_report.html_content = html_content
            existing_report.is_sent = False
            existing_report.sent_at = None
            existing_report.created_at = datetime.utcnow()
            print(f"✓ 更新已存在的报告: {report_date}")
        else:
            # 创建新报告
            new_report = DailyReport(
                report_date=report_date,
                start_time=start_date,
                end_time=end_date,
                total_messages=report_data['counts']['total_messages'],
                total_block_trades=report_data['counts']['block_trades'],
                btc_trade_count=report_data['counts']['btc_count'],
                btc_total_volume=int(report_data['volume_stats']['btc_volume']),
                eth_trade_count=report_data['counts']['eth_count'],
                eth_total_volume=int(report_data['volume_stats']['eth_volume']),
                btc_spot_price=report_data['spot_prices']['btc'],
                eth_spot_price=report_data['spot_prices']['eth'],
                report_data=json.dumps(report_data, ensure_ascii=False),
                html_content=html_content,
                is_sent=False
            )
            session.add(new_report)
            print(f"✓ 创建新报告: {report_date}")

        try:
            session.flush()  # 先检测问题
            session.commit()
        except Exception as commit_err:
            print(f"✗ 保存报告失败: {commit_err}")
            session.rollback()
            raise  # generate 失败要抛出

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [GENERATE_REPORT] end report_date={report_date} total_messages={report_data['counts']['total_messages']} total_block_trades={report_data['counts']['block_trades']}")

        print("\n" + "=" * 60)
        print("✓ 每日报告已生成并保存到数据库！")
        print(f"  报告日期: {report_date}")
        print(f"  待发送邮件: 将在 {config.EMAIL_SEND_TIME} 自动发送")
        print("=" * 60)

        session.close()
        return report_data

    except Exception as e:
        rd = report_date if report_date else "unknown"
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [GENERATE_REPORT] error report_date={rd} error={str(e)}")
        session.close()
        raise


def extract_spot_prices(messages):
    """
    从消息列表中提取最新的 BTC 和 ETH 现货价格

    ⚠️ 修正：只从带"🏷️ Spot Prices"标签的专门播报消息提取
    不再从策略标题中的"(🐮 Spot 🐻 Vol)"误匹配数量

    Args:
        messages: 消息列表 (Message ORM 对象)

    Returns:
        {'btc': float, 'eth': float}
    """
    import re

    btc_price = None
    eth_price = None

    # 按时间倒序遍历，优先获取最新价格
    for message in reversed(messages):
        text = message.text or ''

        # ✅ 严格过滤：只处理包含 "🏷️ Spot Prices" 的播报消息
        if '🏷️ Spot Prices' not in text and '🏷️Spot Prices' not in text:
            continue

        # 提取 BTC 价格 - 支持多种格式
        if btc_price is None:
            # 支持：BTC $102,992.00 / BTC 102992 / BTC price: $102992
            btc_match = re.search(r'BTC[^\d$]*\$?\s*([0-9,]+\.?[0-9]*)', text, re.IGNORECASE)
            if btc_match:
                try:
                    price_val = float(btc_match.group(1).replace(',', ''))
                    # 合理性检查：现货价格应该在 1000-200000 范围
                    if 1000 < price_val < 200000:
                        btc_price = price_val
                except:
                    pass

        # 提取 ETH 价格 - 支持多种格式
        if eth_price is None:
            # 支持：ETH $3,423.82 / ETH 3423 / ETH price: $3423
            eth_match = re.search(r'ETH[^\d$]*\$?\s*([0-9,]+\.?[0-9]*)', text, re.IGNORECASE)
            if eth_match:
                try:
                    price_val = float(eth_match.group(1).replace(',', ''))
                    # 合理性检查：现货价格应该在 100-10000 范围
                    if 100 < price_val < 10000:
                        eth_price = price_val
                except:
                    pass

        # 两个价格都找到后退出
        if btc_price and eth_price:
            break

    return {
        'btc': btc_price or 0.0,
        'eth': eth_price or 0.0
    }


def calculate_trade_statistics(block_trades):
    """
    统计大宗交易数量

    Args:
        block_trades: 大宗交易消息列表

    Returns:
        {
            'total': int,       # 总笔数
            'btc_count': int,   # BTC 笔数
            'eth_count': int,   # ETH 笔数
            'other_count': int  # 其他笔数
        }
    """
    total = len(block_trades)
    btc_count = 0
    eth_count = 0

    for trade in block_trades:
        text = (trade.text or '').upper()
        if 'BTC' in text:
            btc_count += 1
        elif 'ETH' in text:
            eth_count += 1

    return {
        'total': total,
        'btc_count': btc_count,
        'eth_count': eth_count,
        'other_count': total - btc_count - eth_count
    }


def extract_top_trades(block_trades, limit=3):
    """
    提取 Top 3 交易（按金额和数量分类，按币种分类）

    Args:
        block_trades: 大宗交易消息列表
        limit: 每个分类返回的交易数量（默认3）

    Returns:
        分类后的 Top 交易字典:
        {
            'btc_by_amount': [...]  # BTC 按金额 Top 3
            'btc_by_volume': [...]  # BTC 按数量 Top 3
            'eth_by_amount': [...]  # ETH 按金额 Top 3
            'eth_by_volume': [...]  # ETH 按数量 Top 3
        }
    """
    # 1. 解析所有交易
    parsed_trades = []

    for trade in block_trades:
        trade_info = parse_block_trade_message(trade.text or '')
        trade_info.update({
            'message_id': trade.message_id,
            'date': trade.date.strftime('%Y-%m-%d %H:%M:%S'),
            'raw_text': trade.text
        })
        parsed_trades.append(trade_info)

    # 2. 按币种分类
    btc_trades = [t for t in parsed_trades if t['asset'] == 'BTC']
    eth_trades = [t for t in parsed_trades if t['asset'] == 'ETH']

    # 3. 按金额排序
    btc_by_amount = sorted(btc_trades, key=lambda x: x.get('amount_usd', 0), reverse=True)[:limit]
    eth_by_amount = sorted(eth_trades, key=lambda x: x.get('amount_usd', 0), reverse=True)[:limit]

    # 4. 按数量排序
    btc_by_volume = sorted(btc_trades, key=lambda x: x.get('volume', 0), reverse=True)[:limit]
    eth_by_volume = sorted(eth_trades, key=lambda x: x.get('volume', 0), reverse=True)[:limit]

    # 5. 添加排名
    for i, trade in enumerate(btc_by_amount, 1):
        trade['rank'] = i

    for i, trade in enumerate(btc_by_volume, 1):
        trade['rank'] = i

    for i, trade in enumerate(eth_by_amount, 1):
        trade['rank'] = i

    for i, trade in enumerate(eth_by_volume, 1):
        trade['rank'] = i

    return {
        'btc_by_amount': btc_by_amount,
        'btc_by_volume': btc_by_volume,
        'eth_by_amount': eth_by_amount,
        'eth_by_volume': eth_by_volume
    }


def parse_block_trade_message(text):
    """
    解析大宗交易消息内容

    ⚠️ 修正：增强 Deribit 官方消息解析
    - 支持 Greeks 符号（Δ Γ ν Θ ρ）解析
    - 支持不以 LONG/SHORT 开头的格式（如 FUTURES SPREAD）
    - 提取更多字段（ask/mark/premium/instrument_type）

    Args:
        text: 消息文本

    Returns:
        交易信息字典
    """
    import re

    result = {
        'asset': 'Unknown',      # BTC or ETH
        'strategy': 'Unknown',
        'volume': 0.0,           # 合约数量
        'amount_usd': 0.0,       # 美元金额
        'exchange': 'Unknown',
        'contract': 'Unknown',
        'price': 'Unknown',
        'iv': 'Unknown',
        'ask': 'Unknown',
        'mark': 'Unknown',
        'premium': 'Unknown',
        'instrument_type': 'Unknown',  # OPTIONS / FUTURES / PERPETUAL
        'side': 'Unknown',        # LONG or SHORT (买入或卖出方向)
        'spot_price': 'N/A',      # 现货价格
        'greeks': {
            'delta': None,
            'gamma': None,
            'vega': None,
            'theta': None,
            'rho': None
        }
    }

    if not text:
        return result

    # 1. 提取资产类型 (BTC or ETH)
    if 'BTC' in text.upper():
        result['asset'] = 'BTC'
    elif 'ETH' in text.upper():
        result['asset'] = 'ETH'

    # 2. 识别交易工具类型（OPTIONS / FUTURES / PERPETUAL）
    if 'PERPETUAL' in text.upper() or 'PERP' in text.upper():
        result['instrument_type'] = 'PERPETUAL'
    elif 'FUTURES' in text.upper() or '-FUT' in text.upper():
        result['instrument_type'] = 'FUTURES'
    elif re.search(r'(PUT|CALL)', text, re.IGNORECASE):
        result['instrument_type'] = 'OPTIONS'
    elif re.search(r'(BTC|ETH)-\d{1,2}[A-Z]{3}\d{2,4}-\d+-[PC]', text):
        result['instrument_type'] = 'OPTIONS'

    # 3. 提取策略类型和方向 (支持多种格式)
    # 格式1: **LONG BTC PUT (...)**
    strategy_match = re.search(r'\*\*(LONG|SHORT)\s+(BTC|ETH)\s+([\w\s]+?)\s*\(', text, re.IGNORECASE)
    if not strategy_match:
        # 格式2: **LONG BTC PUT**
        strategy_match = re.search(r'\*\*(LONG|SHORT)\s+(BTC|ETH)\s+(PUT|CALL|[\w\s]+)\*\*', text, re.IGNORECASE)
    if not strategy_match:
        # 格式3: **BTC FUTURES SPREAD:** (不以 LONG/SHORT 开头)
        strategy_match = re.search(r'\*\*(BTC|ETH)\s+(FUTURES|OPTIONS)?\s*(SPREAD|[\w\s]+?)[:：]\*\*', text, re.IGNORECASE)

    if strategy_match:
        try:
            # 优先使用已匹配的格式3
            if result['strategy'] != 'Unknown':
                pass  # 已经在格式3中设置
            elif strategy_match.lastindex and strategy_match.lastindex >= 3:
                result['strategy'] = f"{strategy_match.group(1)} {strategy_match.group(2)} {strategy_match.group(3)}".strip()
                # 提取方向 (LONG/SHORT)
                if strategy_match.group(1).upper() in ['LONG', 'SHORT']:
                    result['side'] = strategy_match.group(1).upper()
            elif strategy_match.lastindex and strategy_match.lastindex >= 2:
                result['strategy'] = f"{strategy_match.group(1)} {strategy_match.group(2)}".strip()
                # 提取方向
                if strategy_match.group(1).upper() in ['LONG', 'SHORT']:
                    result['side'] = strategy_match.group(1).upper()
            else:
                result['strategy'] = strategy_match.group(0).strip('*').strip(':：')
        except:
            result['strategy'] = strategy_match.group(0).strip('*').strip(':：')

    # 如果 side 还是 Unknown，尝试从 Bought/Sold 提取
    if result['side'] == 'Unknown':
        if re.search(r'\bBought\b', text, re.IGNORECASE):
            result['side'] = 'LONG'
        elif re.search(r'\bSold\b', text, re.IGNORECASE):
            result['side'] = 'SHORT'

    # 4. 提取合约数量 (50.0x)
    volume_match = re.search(r'(\d+\.?\d*)\s*x', text)
    if volume_match:
        result['volume'] = float(volume_match.group(1))

    # 5. 提取交易所 (Deribit / OKX / Binance / Bybit)
    exchanges = ['Deribit', 'OKX', 'Binance', 'Bybit']
    for exchange in exchanges:
        if exchange.lower() in text.lower():
            result['exchange'] = exchange
            break

    # 4. 提取美元金额 (从 Total Bought/Sold 中提取)
    # 格式: Total Bought: 1.7300 ₿ ($181.24K)
    total_amount_matches = re.findall(r'Total (?:Bought|Sold):[^$]*\$([0-9,.]+[KMB]?)', text)
    if total_amount_matches:
        # 转换为数值
        def parse_amount(amt_str):
            amt_str = amt_str.replace(',', '')
            multiplier = 1
            if amt_str.endswith('K'):
                multiplier = 1000
                amt_str = amt_str[:-1]
            elif amt_str.endswith('M'):
                multiplier = 1000000
                amt_str = amt_str[:-1]
            elif amt_str.endswith('B'):
                multiplier = 1000000000
                amt_str = amt_str[:-1]
            try:
                return float(amt_str) * multiplier
            except:
                return 0.0

        amounts = [parse_amount(amt) for amt in total_amount_matches]
        result['amount_usd'] = max(amounts) if amounts else 0.0

    # 5. 提取合约信息 (BTC-28NOV25-105000-P)
    contract_match = re.search(r'(BTC|ETH)-(\d{1,2}[A-Z]{3}\d{2,4})-(\d+)-([PC])', text)
    if contract_match:
        result['contract'] = contract_match.group(0)

    # 6. 提取 IV (隐含波动率)
    iv_match = re.search(r'\*\*IV\*\*:\s*([\d.]+)%', text)
    if iv_match:
        result['iv'] = f"{iv_match.group(1)}%"

    # 7. 提取 Ask / Mark / Premium（权利金）
    # Ask
    ask_match = re.search(r'(?:Ask|ASK)[:\s]+([0-9,.]+)\s*₿', text, re.IGNORECASE)
    if ask_match:
        result['ask'] = ask_match.group(1) + ' ₿'

    # Mark
    mark_match = re.search(r'(?:Mark|MARK)[:\s]+([0-9,.]+)\s*₿', text, re.IGNORECASE)
    if mark_match:
        result['mark'] = mark_match.group(1) + ' ₿'

    # Premium (权利金，币本位/金本位)
    premium_match = re.search(r'(?:Premium|PREMIUM)[:\s]+([0-9,.]+)\s*(?:₿|\$|BTC|USD)', text, re.IGNORECASE)
    if premium_match:
        result['premium'] = premium_match.group(0)

    # 8. 提取希腊字母（支持符号版本 Δ Γ ν Θ ρ 和英文版本）
    # ⚠️ 修正：支持从 "📖 Risks: Δ: ..., Γ: ..., ν: ..., Θ: ..., ρ: ..." 解析

    # Delta (Δ / Delta)
    delta_match = re.search(r'(?:Δ|Delta|DELTA)[:\s,]+([-+]?[\d,.]+[KMB]?)', text, re.IGNORECASE)
    if delta_match:
        try:
            val_str = delta_match.group(1).replace(',', '')
            multiplier = 1
            if val_str.endswith('K'):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_str.endswith('M'):
                multiplier = 1000000
                val_str = val_str[:-1]
            elif val_str.endswith('B'):
                multiplier = 1000000000
                val_str = val_str[:-1]
            result['greeks']['delta'] = float(val_str) * multiplier
        except:
            pass

    # Gamma (Γ / Gamma)
    gamma_match = re.search(r'(?:Γ|Gamma|GAMMA)[:\s,]+([-+]?[\d,.]+[KMB]?)', text, re.IGNORECASE)
    if gamma_match:
        try:
            val_str = gamma_match.group(1).replace(',', '')
            multiplier = 1
            if val_str.endswith('K'):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_str.endswith('M'):
                multiplier = 1000000
                val_str = val_str[:-1]
            result['greeks']['gamma'] = float(val_str) * multiplier
        except:
            pass

    # Vega (ν / Vega)
    vega_match = re.search(r'(?:ν|Vega|VEGA)[:\s,]+([-+]?[\d,.]+[KMB]?)', text, re.IGNORECASE)
    if vega_match:
        try:
            val_str = vega_match.group(1).replace(',', '')
            multiplier = 1
            if val_str.endswith('K'):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_str.endswith('M'):
                multiplier = 1000000
                val_str = val_str[:-1]
            result['greeks']['vega'] = float(val_str) * multiplier
        except:
            pass

    # Theta (Θ / Theta)
    theta_match = re.search(r'(?:Θ|Theta|THETA)[:\s,]+([-+]?[\d,.]+[KMB]?)', text, re.IGNORECASE)
    if theta_match:
        try:
            val_str = theta_match.group(1).replace(',', '')
            multiplier = 1
            if val_str.endswith('K'):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_str.endswith('M'):
                multiplier = 1000000
                val_str = val_str[:-1]
            result['greeks']['theta'] = float(val_str) * multiplier
        except:
            pass

    # Rho (ρ / Rho)
    rho_match = re.search(r'(?:ρ|Rho|RHO)[:\s,]+([-+]?[\d,.]+[KMB]?)', text, re.IGNORECASE)
    if rho_match:
        try:
            val_str = rho_match.group(1).replace(',', '')
            multiplier = 1
            if val_str.endswith('K'):
                multiplier = 1000
                val_str = val_str[:-1]
            elif val_str.endswith('M'):
                multiplier = 1000000
                val_str = val_str[:-1]
            result['greeks']['rho'] = float(val_str) * multiplier
        except:
            pass

    # 8. 提取价格信息 (简化版)
    price_match = re.search(r'at\s+([\d.]+)\s*₿\s*\(\$([^)]+)\)', text)
    if price_match:
        result['price'] = f"{price_match.group(1)} ₿ (${price_match.group(2)})"

    # 9. 提取现货参考价格 (Ref: $105234.56)
    spot_match = re.search(r'(?:Ref|REF)[:\s]+\$([0-9,.]+)', text, re.IGNORECASE)
    if spot_match:
        try:
            spot_val = float(spot_match.group(1).replace(',', ''))
            result['spot_price'] = f"${spot_val:,.2f}"
        except:
            pass

    return result


def build_trade_card_html(trades, title, sort_type):
    """
    构建交易卡片 HTML

    Args:
        trades: 交易列表
        title: 标题（如 "BTC Top 3 按金额"）
        sort_type: 排序类型（"amount" 或 "volume"）

    Returns:
        HTML 字符串
    """
    if not trades:
        return f"<h3>{title}</h3><p>暂无数据</p>"

    html = f"<h3>{title}</h3>"

    for trade in trades:
        # 格式化希腊字母（处理 None 值）
        greeks_html = f"""
        <div class="greeks">
            <div class="greek-item">
                <strong>Delta</strong><br>
                {trade['greeks']['delta'] if trade['greeks']['delta'] is not None else 'N/A'}
            </div>
            <div class="greek-item">
                <strong>Gamma</strong><br>
                {trade['greeks']['gamma'] if trade['greeks']['gamma'] is not None else 'N/A'}
            </div>
            <div class="greek-item">
                <strong>Vega</strong><br>
                {trade['greeks']['vega'] if trade['greeks']['vega'] is not None else 'N/A'}
            </div>
            <div class="greek-item">
                <strong>Theta</strong><br>
                {trade['greeks']['theta'] if trade['greeks']['theta'] is not None else 'N/A'}
            </div>
            <div class="greek-item">
                <strong>Rho</strong><br>
                {trade['greeks']['rho'] if trade['greeks']['rho'] is not None else 'N/A'}
            </div>
        </div>
        """

        # 排序指标高亮显示
        if sort_type == 'amount':
            sort_value_html = f'<tr><td><strong>💰 交易金额:</strong></td><td><span style="color: #e74c3c; font-size: 18px; font-weight: bold;">${trade["amount_usd"]:,.2f}</span></td></tr>'
        else:  # volume
            sort_value_html = f'<tr><td><strong>📦 合约数量:</strong></td><td><span style="color: #e74c3c; font-size: 18px; font-weight: bold;">{trade["volume"]}x</span></td></tr>'

        html += f"""
        <div class="trade-card">
            <div class="trade-header">#{trade['rank']} - {trade['date']}</div>
            <table>
                <tr><td><strong>交易策略:</strong></td><td>{trade['strategy']}</td></tr>
                {sort_value_html}
                <tr><td><strong>合约:</strong></td><td>{trade['contract']}</td></tr>
                <tr><td><strong>价格:</strong></td><td>{trade['price']}</td></tr>
                <tr><td><strong>IV:</strong></td><td>{trade['iv']}</td></tr>
            </table>
            <h4>希腊字母:</h4>
            {greeks_html}
        </div>
        """

    return html


def build_daily_report_html(report_data):
    """
    构建每日报告 HTML 内容

    Args:
        report_data: 报告数据字典

    Returns:
        HTML 字符串
    """
    time_range = report_data['time_range']
    spot_prices = report_data['spot_prices']
    stats = report_data['trade_statistics']
    top_trades = report_data['top_trades']

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #34495e;
                margin-top: 30px;
            }}
            .section {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                margin: 15px 0;
            }}
            .stats {{
                display: flex;
                justify-content: space-around;
                margin: 20px 0;
            }}
            .stat-box {{
                text-align: center;
                padding: 15px;
                background: white;
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .stat-number {{
                font-size: 32px;
                font-weight: bold;
                color: #3498db;
            }}
            .stat-label {{
                font-size: 14px;
                color: #7f8c8d;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            th, td {{
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }}
            th {{
                background-color: #3498db;
                color: white;
            }}
            .trade-card {{
                background: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #e74c3c;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .trade-header {{
                font-size: 18px;
                font-weight: bold;
                color: #e74c3c;
                margin-bottom: 10px;
            }}
            .greeks {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 10px;
                margin-top: 10px;
            }}
            .greek-item {{
                text-align: center;
                padding: 8px;
                background: #ecf0f1;
                border-radius: 3px;
            }}
        </style>
    </head>
    <body>
        <h1>📊 SignalPlus Trade Alert 每日报告</h1>

        <div class="section">
            <h2>📅 1. 统计时间范围</h2>
            <p><strong>开始时间:</strong> {time_range['start']}</p>
            <p><strong>结束时间:</strong> {time_range['end']}</p>
            <p><strong>时区:</strong> {time_range['timezone']}</p>
        </div>

        <div class="section">
            <h2>💰 2. 当日关键市场指标</h2>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number">${spot_prices['btc']:,.2f}</div>
                    <div class="stat-label">BTC 现货价格</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">${spot_prices['eth']:,.2f}</div>
                    <div class="stat-label">ETH 现货价格</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📈 3. 大宗交易统计</h2>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number">{stats['total']}</div>
                    <div class="stat-label">总笔数</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{stats['btc_count']}</div>
                    <div class="stat-label">BTC 笔数</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{stats['eth_count']}</div>
                    <div class="stat-label">ETH 笔数</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>🏆 4. Top 3 交易排名</h2>

            <!-- BTC 部分 -->
            <div style="margin: 30px 0;">
                <h2 style="color: #f39c12;">🔶 BTC 交易</h2>

                <div style="margin: 20px 0;">
                    """ + build_trade_card_html(top_trades.get('btc_by_amount', []), "💰 按金额排名 Top 3", "amount") + """
                </div>

                <div style="margin: 20px 0;">
                    """ + build_trade_card_html(top_trades.get('btc_by_volume', []), "📦 按数量排名 Top 3", "volume") + """
                </div>
            </div>

            <!-- ETH 部分 -->
            <div style="margin: 30px 0;">
                <h2 style="color: #627eea;">🔷 ETH 交易</h2>

                <div style="margin: 20px 0;">
                    """ + build_trade_card_html(top_trades.get('eth_by_amount', []), "💰 按金额排名 Top 3", "amount") + """
                </div>

                <div style="margin: 20px 0;">
                    """ + build_trade_card_html(top_trades.get('eth_by_volume', []), "📦 按数量排名 Top 3", "volume") + """
                </div>
            </div>
    """

    html += """
        </div>

        <hr>
        <p style="text-align: center; color: #7f8c8d; font-size: 12px;">
            此报告由 Telegram 数据采集系统自动生成<br>
            生成时间: """ + report_data['generated_at'] + """
        </p>
    </body>
    </html>
    """

    return html


async def send_daily_report_email(html_content, report_data):
    """
    发送每日报告邮件（占位符函数）

    Args:
        html_content: HTML 邮件内容
        report_data: 报告数据字典
    """
    print(f"\n  [占位符] 发送每日报告邮件")
    print(f"  时间范围: {report_data['time_range']['start']} - {report_data['time_range']['end']}")
    print(f"  总消息数: {report_data['total_messages']}")
    print(f"  大宗交易数: {report_data['total_block_trades']}")

    if config.EMAIL_ENABLED:
        # TODO: 实现邮件发送逻辑
        print(f"  [TODO] 邮件发送功能将在 Phase III 实现")
    else:
        print(f"  [跳过] 邮件发送未启用（EMAIL_ENABLED=false）")

        # 保存 HTML 到本地文件（用于测试）
        import os
        output_dir = os.path.join(os.path.dirname(__file__), 'reports')
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(output_dir, f'daily_report_{timestamp}.html')

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"  ✓ 报告已保存到: {output_file}")


async def send_pending_daily_reports(limit: int = None):
    """
    发送待发送的每日报告邮件（16:05 定时任务）

    从数据库读取尚未发送的报告并发送邮件

    Args:
        limit: 最多处理多少条报告（None表示全部）
    """
    import time
    session = get_session()

    try:
        pending_reports = session.query(DailyReport).filter_by(is_sent=False).all()

        if not pending_reports:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] no_pending")
            return

        if not config.EMAIL_ENABLED:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] skip_email_disabled pending_count={len(pending_reports)}")
            return

        if limit is not None:
            pending_reports = pending_reports[:limit]

        start_time = time.time()

        from email_sender import send_html_email, send_email

        for report in pending_reports:
            if limit is not None and (time.time() - start_time) > 5:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] timeout limit={limit}")
                break

            try:
                subject = f"📊 Daily Trade Report - {report.report_date}"

                if report.html_content:
                    success = send_html_email(subject, report.html_content)
                else:
                    fallback_body = f"""Daily Trade Report - {report.report_date}

BTC: {report.btc_trade_count} 笔, {report.btc_total_volume}x
ETH: {report.eth_trade_count} 笔, {report.eth_total_volume}x
Total: {report.total_messages} 条消息, {report.total_block_trades} 笔交易
"""
                    success = send_email(subject, fallback_body)

                if success:
                    try:
                        report.is_sent = True
                        report.sent_at = datetime.utcnow()
                        session.flush()
                        session.commit()
                    except Exception as commit_err:
                        session.rollback()
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] commit_failed report_date={report.report_date} error={commit_err}")

                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] sent report_date={report.report_date}")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] failed report_date={report.report_date} reason=email_send_failed")

            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] failed report_date={report.report_date} reason={e}")
                # 继续下一个，不中断

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SEND_DAILY_REPORT] error={e}")

    finally:
        session.close()


if __name__ == '__main__':
    """测试报告生成和发送"""
    import asyncio
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='日报生成和发送测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成今天的日报（不发送）
  python report_generator.py

  # 生成并发送指定日期的日报
  python report_generator.py --test-send-daily --date 2025-12-13

  # 生成并发送今天的日报
  python report_generator.py --test-send-daily
        """
    )

    parser.add_argument('--test-send-daily', action='store_true',
                       help='测试完整链路：生成日报 + 发送邮件')
    parser.add_argument('--smoke', action='store_true',
                       help='Smoke测试：生成 + 发送，全程捕获异常不崩溃')
    parser.add_argument('--fast-smoke', action='store_true',
                       help='快速Smoke：仅DB连接+发送1条（<10s）')
    parser.add_argument('--fast-smoke-full', action='store_true',
                       help='完整闭环Smoke：生成昨天日报+发送1条（<30s）')
    parser.add_argument('--backfill-start', type=str,
                       help='历史回放起始日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--backfill-end', type=str,
                       help='历史回放结束日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--backfill-max-days', type=int, default=7,
                       help='历史回放最大天数（默认7）')
    parser.add_argument('--backfill-timeout-seconds', type=int, default=60,
                       help='历史回放总超时秒数（默认60）')
    parser.add_argument('--no-send', action='store_true',
                       help='只生成不发送（配合 backfill 使用）')
    parser.add_argument('--verify', action='store_true',
                       help='快速验收：DB health + generate昨天 + send 1条（<15s）')
    parser.add_argument('--verify-db', action='store_true',
                       help='只读验收：DB health + integrity_check + journal_mode（<5s）')
    parser.add_argument('--date', type=str,
                       help='指定日期 (格式: YYYY-MM-DD)，默认为今天')

    args = parser.parse_args()

    if args.verify_db:
        # 只读验收：DB health + integrity + journal_mode
        import sqlite3
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY_DB] start")

        try:
            db_path = config.DB_PATH
            conn = sqlite3.connect(db_path, timeout=5)
            cursor = conn.cursor()

            # integrity_check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            integrity = result[0] if result else 'FAILED'
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY_DB] integrity_check result={integrity}")

            # journal_mode
            cursor.execute("PRAGMA journal_mode")
            result = cursor.fetchone()
            journal = result[0] if result else 'UNKNOWN'
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY_DB] journal_mode actual={journal}")

            conn.close()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY_DB] status=success")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY_DB] status=failed error={e}")

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY_DB] end")
        sys.exit(0)

    if args.verify:
        # 快速验收链路
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] start")

        # 步骤1: DB health
        try:
            session = get_session()
            session.query(DailyReport).limit(1).all()
            session.close()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] db_health status=success")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] db_health status=failed error={e}")

        # 步骤2: 生成昨天日报
        try:
            import pytz
            tz = pytz.timezone(config.REPORT_TIMEZONE)
            yesterday = datetime.now(tz).date() - timedelta(days=1)
            asyncio.run(generate_daily_report(target_date=yesterday.strftime('%Y-%m-%d')))
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] generate status=success")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] generate status=failed error={e}")

        # 步骤3: 发送1条
        try:
            asyncio.run(send_pending_daily_reports(limit=1))
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] send status=success")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] send status=failed error={e}")

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [VERIFY] end")
        sys.exit(0)

    if args.fast_smoke_full:
        # 完整闭环smoke：生成+发送
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FULL] start")

        # 确定日期：优先使用 --date，否则使用昨天
        if args.date:
            target = args.date
        else:
            import pytz
            tz = pytz.timezone(config.REPORT_TIMEZONE)
            yesterday = datetime.now(tz).date() - timedelta(days=1)
            target = yesterday.strftime('%Y-%m-%d')

        # 步骤1：生成日报
        try:
            asyncio.run(generate_daily_report(target_date=target))
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FULL] generate status=success")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FULL] generate status=failed error={e}")

        # 步骤2：发送日报
        try:
            asyncio.run(send_pending_daily_reports(limit=1))
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FULL] send status=success")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FULL] send status=failed error={e}")

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FULL] end")
        sys.exit(0)

    if args.backfill_start and args.backfill_end:
        # 历史回放（带限制）
        import time
        from datetime import date
        start = datetime.strptime(args.backfill_start, '%Y-%m-%d').date()
        end = datetime.strptime(args.backfill_end, '%Y-%m-%d').date()

        total = 0
        ok = 0
        failed = 0
        start_time = time.time()

        current = start
        while current <= end:
            # 检查 max-days 限制
            if total >= args.backfill_max_days:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKFILL] stopped reason=max_days_reached limit={args.backfill_max_days}")
                break

            # 检查 timeout 限制
            if (time.time() - start_time) > args.backfill_timeout_seconds:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKFILL] stopped reason=timeout_exceeded limit={args.backfill_timeout_seconds}s")
                break

            total += 1
            date_str = current.strftime('%Y-%m-%d')
            day_start = time.time()

            try:
                report_data = asyncio.run(generate_daily_report(target_date=date_str))
                cost_ms = int((time.time() - day_start) * 1000)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKFILL] date={date_str} status=success cost_ms={cost_ms}")

                # 打印 summary
                vol = report_data['volume_stats']
                counts = report_data['counts']
                top_list = report_data.get('top_trades_list', [])
                top_asset = top_list[0]['asset'] if top_list else 'N/A'
                top_exchange = top_list[0]['exchange'] if top_list else 'N/A'
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SUMMARY] date={date_str} total={counts['total_messages']} blocks={counts['block_trades']} top_volume={vol['max_volume']:.1f} top_asset={top_asset} top_exchange={top_exchange}")

                ok += 1
            except Exception as e:
                cost_ms = int((time.time() - day_start) * 1000)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKFILL] date={date_str} status=failed cost_ms={cost_ms} error={e}")
                failed += 1

            current += timedelta(days=1)

        elapsed_s = int(time.time() - start_time)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKFILL] done total={total} ok={ok} failed={failed} elapsed_s={elapsed_s}")

        # 发送（如果没有 --no-send）
        if not args.no_send:
            try:
                asyncio.run(send_pending_daily_reports())
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKFILL] send_failed error={e}")

        sys.exit(0)

    if args.fast_smoke:
        # 快速smoke：DB连接+发送1条
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FAST] start")
        try:
            session = get_session()
            session.query(DailyReport).limit(1).all()
            session.close()
            asyncio.run(send_pending_daily_reports(limit=1))
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FAST] error={e}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SMOKE_FAST] end")
        sys.exit(0)

    if args.smoke:
        # Smoke测试：保证不崩溃
        import pytz
        tz = pytz.timezone(config.REPORT_TIMEZONE)
        test_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

        print("\n" + "=" * 60)
        print("🧪 SMOKE TEST: 生成 + 发送")
        print("=" * 60)
        print(f"测试时间: {test_time}")
        if args.date:
            print(f"指定日期: {args.date}")
        print("=" * 60)

        # 步骤1：生成日报
        try:
            print("\n[SMOKE] step=generate status=running")
            asyncio.run(generate_daily_report())
            print("[SMOKE] step=generate status=success")
        except Exception as e:
            print(f"[SMOKE] step=generate status=failed error={e}")

        # 步骤2：发送日报
        try:
            print("\n[SMOKE] step=send status=running")
            asyncio.run(send_pending_daily_reports())
            print("[SMOKE] step=send status=success")
        except Exception as e:
            print(f"[SMOKE] step=send status=failed error={e}")

        print("\n[SMOKE] end")
        sys.exit(0)

    if args.test_send_daily:
        # 测试完整链路
        import pytz
        tz = pytz.timezone(config.REPORT_TIMEZONE)
        test_time = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')

        print("\n" + "=" * 60)
        print("📊 测试日报完整链路：生成 + 发送")
        print("=" * 60)
        print(f"测试时间: {test_time}")
        if args.date:
            print(f"指定日期: {args.date}")
        print("=" * 60)

        # 步骤1：生成日报
        print("\n[步骤 1/2] 生成日报...")
        print("-" * 60)
        asyncio.run(generate_daily_report())

        # 步骤2：发送日报
        print("\n[步骤 2/2] 发送日报邮件...")
        print("-" * 60)
        asyncio.run(send_pending_daily_reports())

        print("\n" + "=" * 60)
        print("✓ 测试完成！")
        print("=" * 60)
        print("\n📧 请检查邮箱收件（如 EMAIL_ENABLED=true）")
        print("💡 提示: 如需查看数据库状态，运行: python db_manager.py stats")
    else:
        # 默认：仅生成日报
        print("\n仅生成日报（不发送邮件）...")
        asyncio.run(generate_daily_report())
