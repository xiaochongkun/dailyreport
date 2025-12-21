"""
日报生成模块
从数据库提取过去 24 小时的数据并生成结构化的 HTML 邮件
"""

from datetime import datetime, timedelta
import pytz
import json
import sqlite3
import time
import config
from database import get_session, get_messages_by_date_range, get_block_trades_by_date_range, DailyReport
from filelock import FileLock, Timeout


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

            # ⚠️ 修正：对于多腿策略，重新计算 volume 和 amount_usd（从 options_legs 推导）
            options_legs = parsed.get('options_legs', [])

            if len(options_legs) >= 1:
                # 有期权腿：使用 options_sum 作为 volume（所有期权腿张数总和）
                volume_display = parsed.get('options_sum', 0)

                # 计算 amount_usd：所有期权腿的 total_usd 总和
                amount_usd_display = sum(
                    leg.get('total_usd', 0) for leg in options_legs if leg.get('total_usd')
                )

                # 如果 amount_usd 为0，回退到全局解析值
                if amount_usd_display == 0:
                    amount_usd_display = parsed.get('amount_usd', 0.0)
            else:
                # 无期权腿：使用全局解析值
                volume_display = parsed.get('volume', 0.0)
                amount_usd_display = parsed.get('amount_usd', 0.0)

            normalized.append({
                'asset': parsed.get('asset', 'Unknown'),
                'volume': volume_display,  # ⚠️ 修正：多腿时为 options_sum
                'exchange': parsed.get('exchange', 'Unknown'),
                'amount_usd': amount_usd_display,  # ⚠️ 修正：多腿时为各腿总和
                'ts': ts,
                'date': date_str,  # 兼容 legacy template
                'raw_text': trade.text or '',
                'strategy': parsed.get('strategy', 'Unknown'),
                'strategy_title': parsed.get('strategy_title', 'Unknown'),  # ⚠️ 新增
                'contract': parsed.get('contract', 'Unknown'),
                'price': parsed.get('price', 'Unknown'),
                'iv': parsed.get('iv', 'Unknown'),
                'ask': parsed.get('ask', 'Unknown'),
                'mark': parsed.get('mark', 'Unknown'),
                'premium': parsed.get('premium', 'Unknown'),
                'instrument_type': parsed.get('instrument_type', 'Unknown'),
                'greeks': parsed.get('greeks', {}),
                'options_legs': options_legs,  # ⚠️ 新增
                'non_options_legs': parsed.get('non_options_legs', []),  # ⚠️ 新增
                'msg_id': getattr(trade, 'message_id', 'Unknown'),  # 添加 message_id
                'side': parsed.get('side', 'Unknown'),  # 添加 side
                'spot_price': parsed.get('spot_price', 'N/A'),  # 添加 spot_price
                # ⚠️ 新增：添加推导字段用于调试和验证
                'options_sum': parsed.get('options_sum', 0),  # 期权腿总张数（推导字段）
                'options_count': len(options_legs),  # 期权腿数量
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
    # 提取现货价格（传递时间范围）
    spot_prices = extract_spot_prices(messages, start_date, end_date)

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

    # ⚠️ 按数量排序：只要 volume > 0 即可（期权张数）
    btc_by_volume = sorted(btc_trades, key=lambda x: x['volume'], reverse=True)[:top_limit]
    eth_by_volume = sorted(eth_trades, key=lambda x: x['volume'], reverse=True)[:top_limit]

    # ⚠️ 按金额排序：必须基于 amount_usd != null 且 > 0 的集合（期权腿总权利金）
    btc_trades_with_amount = [t for t in btc_trades if t.get('amount_usd', 0) > 0]
    eth_trades_with_amount = [t for t in eth_trades if t.get('amount_usd', 0) > 0]

    btc_by_amount = sorted(btc_trades_with_amount, key=lambda x: x['amount_usd'], reverse=True)[:top_limit]
    eth_by_amount = sorted(eth_trades_with_amount, key=lambda x: x['amount_usd'], reverse=True)[:top_limit]

    # 添加 rank（从1开始递增）
    for i, t in enumerate(btc_by_volume, 1):
        t['rank'] = i
    for i, t in enumerate(eth_by_volume, 1):
        t['rank'] = i
    for i, t in enumerate(btc_by_amount, 1):
        t['rank'] = i
    for i, t in enumerate(eth_by_amount, 1):
        t['rank'] = i

    # ⚠️ 打印 Top3 统计日志（用于验证）
    for t in btc_by_volume[:3]:
        legs_opts = len(t.get('options_legs', []))
        legs_non_opts = len(t.get('non_options_legs', []))
        print(f"[TOP] rank={t['rank']} asset=BTC sort=volume legs_options={legs_opts} legs_non_options={legs_non_opts} volume={t['volume']} amount_usd={t.get('amount_usd', 0):.2f}")

    for t in btc_by_amount[:3]:
        legs_opts = len(t.get('options_legs', []))
        legs_non_opts = len(t.get('non_options_legs', []))
        print(f"[TOP] rank={t['rank']} asset=BTC sort=amount legs_options={legs_opts} legs_non_options={legs_non_opts} volume={t['volume']} amount_usd={t.get('amount_usd', 0):.2f}")

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

        # 6. 保存报告到数据库（加锁防止并发写入）
        report_date = start_date.strftime('%Y-%m-%d')
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [GENERATE_REPORT] start report_date={report_date}")

        # 使用文件锁确保串行写入
        lock_path = '/tmp/dailyreport.lock'
        lock = FileLock(lock_path, timeout=10)

        try:
            with lock:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] lock_acquired path={lock_path}")

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
                    # 处理 None 值：转换为字符串
                    existing_report.btc_spot_price = str(report_data['spot_prices']['btc']) if report_data['spot_prices']['btc'] is not None else None
                    existing_report.eth_spot_price = str(report_data['spot_prices']['eth']) if report_data['spot_prices']['eth'] is not None else None
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
                        # 处理 None 值：转换为字符串
                        btc_spot_price=str(report_data['spot_prices']['btc']) if report_data['spot_prices']['btc'] is not None else None,
                        eth_spot_price=str(report_data['spot_prices']['eth']) if report_data['spot_prices']['eth'] is not None else None,
                        report_data=json.dumps(report_data, ensure_ascii=False),
                        html_content=html_content,
                        is_sent=False
                    )
                    session.add(new_report)
                    print(f"✓ 创建新报告: {report_date}")

                # 提交事务，带重试机制
                max_retries = 3
                retry_delay = 1.0

                for retry in range(max_retries):
                    try:
                        session.flush()  # 先检测问题
                        session.commit()
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] commit_success report_date={report_date}")
                        break  # 成功则退出重试循环
                    except sqlite3.OperationalError as op_err:
                        if 'database is locked' in str(op_err):
                            if retry < max_retries - 1:
                                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] commit_retry attempt={retry+1}/{max_retries} delay={retry_delay}s err='{op_err}'")
                                session.rollback()
                                time.sleep(retry_delay)
                                retry_delay *= 2  # 指数退避
                            else:
                                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] commit_failed max_retries_exceeded err='{op_err}'")
                                session.rollback()
                                raise
                        else:
                            print(f"✗ 保存报告失败（非锁错误）: {op_err}")
                            session.rollback()
                            raise
                    except Exception as commit_err:
                        print(f"✗ 保存报告失败: {commit_err}")
                        session.rollback()
                        raise  # generate 失败要抛出

                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] lock_released path={lock_path}")

        except Timeout:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] lock_timeout err='Failed to acquire lock within 10s'")
            raise

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


def extract_spot_prices(messages, start_date, end_date):
    """
    从消息列表中提取最新的 BTC 和 ETH 现货价格

    ⚠️ 修正：优先级顺序
    1) 在统计窗口 start_date~end_date 内查找最后一条"🏷️ Spot Prices"播报
    2) 若窗口内没有：回退到窗口开始前最近一条"🏷️ Spot Prices"播报
    3) 若仍没有：从交易消息的 **Ref**: $xxxxx 推断（取窗口内最新）
    4) 若都没有：返回 None

    Args:
        messages: 消息列表 (Message ORM 对象)
        start_date: 统计窗口开始时间
        end_date: 统计窗口结束时间

    Returns:
        {
            'btc': float or None,
            'eth': float or None,
            'spot_source': 'spot_prices_tag' | 'spot_prices_fallback' | 'ref_fallback' | 'missing',
            'spot_ts': datetime or None,
            'source_msg_id': int or None
        }
    """
    import re
    import pytz

    def parse_spot_message(text):
        """解析单条 Spot Prices 消息"""
        btc_price = None
        eth_price = None

        # 提取 BTC 价格
        btc_match = re.search(r'BTC[^\d$]*\$?\s*([0-9,]+\.?[0-9]*)', text, re.IGNORECASE)
        if btc_match:
            try:
                price_val = float(btc_match.group(1).replace(',', ''))
                # 合理性检查：现货价格应该在 1000-200000 范围
                if 1000 < price_val < 200000:
                    btc_price = price_val
            except:
                pass

        # 提取 ETH 价格
        eth_match = re.search(r'ETH[^\d$]*\$?\s*([0-9,]+\.?[0-9]*)', text, re.IGNORECASE)
        if eth_match:
            try:
                price_val = float(eth_match.group(1).replace(',', ''))
                # 合理性检查：现货价格应该在 100-10000 范围
                if 100 < price_val < 10000:
                    eth_price = price_val
            except:
                pass

        return btc_price, eth_price

    def ensure_aware(dt, target_tz):
        """确保 datetime 有时区信息"""
        if dt.tzinfo is None:
            return pytz.utc.localize(dt).astimezone(target_tz)
        else:
            return dt.astimezone(target_tz)

    # 获取目标时区
    target_tz = start_date.tzinfo if start_date.tzinfo else pytz.timezone(config.REPORT_TIMEZONE)

    # 筛选所有 Spot Prices 消息
    spot_messages = [msg for msg in messages
                     if ('🏷️ Spot Prices' in (msg.text or '') or '🏷️Spot Prices' in (msg.text or ''))]

    # 步骤1：在窗口内查找最后一条 Spot Prices
    in_window_msgs = []
    for msg in spot_messages:
        msg_date_aware = ensure_aware(msg.date, target_tz)
        if start_date <= msg_date_aware <= end_date:
            in_window_msgs.append(msg)

    if in_window_msgs:
        latest_msg = sorted(in_window_msgs, key=lambda x: x.date, reverse=True)[0]
        btc_price, eth_price = parse_spot_message(latest_msg.text or '')

        print(f"[SPOT] source=spot_prices_tag msg_id={latest_msg.message_id} btc={btc_price} eth={eth_price} spot_ts={latest_msg.date.isoformat()}")
        return {
            'btc': btc_price,
            'eth': eth_price,
            'spot_source': 'spot_prices_tag',
            'spot_ts': latest_msg.date.isoformat() if latest_msg.date else None,  # ⚠️ 修正：转为ISO字符串
            'source_msg_id': latest_msg.message_id
        }

    # 步骤2：回退到窗口开始前最近一条 Spot Prices
    before_window_msgs = []
    for msg in spot_messages:
        msg_date_aware = ensure_aware(msg.date, target_tz)
        if msg_date_aware < start_date:
            before_window_msgs.append(msg)

    if before_window_msgs:
        latest_msg = sorted(before_window_msgs, key=lambda x: x.date, reverse=True)[0]
        btc_price, eth_price = parse_spot_message(latest_msg.text or '')

        print(f"[SPOT] source=spot_prices_fallback msg_id={latest_msg.message_id} btc={btc_price} eth={eth_price} spot_ts={latest_msg.date.isoformat()}")
        return {
            'btc': btc_price,
            'eth': eth_price,
            'spot_source': 'spot_prices_fallback',
            'spot_ts': latest_msg.date.isoformat() if latest_msg.date else None,  # ⚠️ 修正：转为ISO字符串
            'source_msg_id': latest_msg.message_id
        }

    # 步骤3：从交易消息的 Ref 推断（窗口内最新）
    ref_messages = []
    for msg in messages:
        text = msg.text or ''
        # 提取 Ref 价格和资产类型
        ref_match = re.search(r'(?:Ref|REF)[\*:\s：]{1,5}\$([0-9,.]+)', text, re.IGNORECASE)
        if ref_match:
            try:
                ref_val = float(ref_match.group(1).replace(',', ''))
                # 判断资产类型
                asset = None
                if 'BTC' in text.upper():
                    asset = 'BTC'
                elif 'ETH' in text.upper():
                    asset = 'ETH'

                if asset:
                    msg_date_aware = ensure_aware(msg.date, target_tz)
                    if start_date <= msg_date_aware <= end_date:
                        ref_messages.append({
                            'msg': msg,
                            'asset': asset,
                            'ref_price': ref_val,
                            'date': msg.date
                        })
            except:
                pass

    if ref_messages:
        # 按时间倒序排序
        ref_messages_sorted = sorted(ref_messages, key=lambda x: x['date'], reverse=True)

        # 提取最新的 BTC 和 ETH Ref
        btc_price = None
        eth_price = None
        latest_btc_msg = None
        latest_eth_msg = None

        for ref_msg in ref_messages_sorted:
            if ref_msg['asset'] == 'BTC' and btc_price is None:
                btc_price = ref_msg['ref_price']
                latest_btc_msg = ref_msg['msg']
            elif ref_msg['asset'] == 'ETH' and eth_price is None:
                eth_price = ref_msg['ref_price']
                latest_eth_msg = ref_msg['msg']

            # 如果两者都找到了，退出
            if btc_price is not None and eth_price is not None:
                break

        # 使用最新的一条作为代表（取BTC优先，ETH次之）
        latest_msg = latest_btc_msg if latest_btc_msg else latest_eth_msg

        if latest_msg:
            print(f"[SPOT] source=ref_fallback msg_id={latest_msg.message_id} btc={btc_price} eth={eth_price} spot_ts={latest_msg.date.isoformat()}")
            return {
                'btc': btc_price,
                'eth': eth_price,
                'spot_source': 'ref_fallback',
                'spot_ts': latest_msg.date.isoformat() if latest_msg.date else None,  # ⚠️ 修正：转为ISO字符串
                'source_msg_id': latest_msg.message_id
            }

    # 步骤4：都没有
    print(f"[SPOT] source=missing reason=no_spot_message_and_no_ref btc=None eth=None spot_ts=None")
    return {
        'btc': None,
        'eth': None,
        'spot_source': 'missing',
        'spot_ts': None,
        'source_msg_id': None
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
        'strategy_title': 'Unknown',  # ⚠️ 新增：完整策略标题（从消息标题行提取）
        'volume': 0.0,           # 合约数量（总和，用于排序）
        'amount_usd': 0.0,       # 美元金额（期权腿总权利金）
        'exchange': 'Unknown',
        'contract': 'Unknown',   # 单腿时显示合约名，多腿时显示"合约（多腿）"
        'price': 'Unknown',      # 单腿每张价格（币本位+USD）
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
        },
        # ⚠️ 新增：多腿结构
        'options_legs': [],       # 期权腿列表：[{side, volume, contract, price_native, price_usd, iv, ...}, ...]
        'non_options_legs': []    # 非期权腿（PERPETUAL/FUTURES/SPOT）：[{side, volume, contract, price, ...}, ...]
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

    # 8. 提取价格信息（支持 BTC ₿ 和 ETH Ξ）
    price_native = None
    price_usd = None
    price_inferred = False

    # 尝试从 "at X ₿ ($Y)" 格式提取 BTC 价格
    btc_price_match = re.search(r'at\s+([\d,.]+)\s*₿\s*\(\$([0-9,.]+[KMB]?)\)', text)
    if btc_price_match:
        price_native_val = btc_price_match.group(1).replace(',', '')
        price_usd_val = btc_price_match.group(2).replace(',', '')
        price_native = f"{price_native_val} ₿"
        price_usd = f"${price_usd_val}"

    # 尝试从 "at X Ξ ($Y)" 格式提取 ETH 价格
    eth_price_match = re.search(r'at\s+([\d,.]+)\s*Ξ\s*\(\$([0-9,.]+[KMB]?)\)', text)
    if eth_price_match:
        price_native_val = eth_price_match.group(1).replace(',', '')
        price_usd_val = eth_price_match.group(2).replace(',', '')
        price_native = f"{price_native_val} Ξ"
        price_usd = f"${price_usd_val}"

    # 如果找到了价格，保存到 result
    if price_native and price_usd:
        result['price_native'] = price_native
        result['price_usd'] = price_usd
        result['price'] = f"{price_native} ({price_usd})"
        result['price_inferred'] = price_inferred
    else:
        # 尝试反推：如果有 Total 和 volume
        # 辅助函数：解析金额（支持 K/M/B 后缀）
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

        # 从 Total Bought/Sold: X ₿ ($Y) 提取
        total_btc_match = re.search(r'Total (?:Bought|Sold):\s*([\d,.]+)\s*₿\s*\(\$([0-9,.]+[KMB]?)\)', text)
        total_eth_match = re.search(r'Total (?:Bought|Sold):\s*([\d,.]+)\s*Ξ\s*\(\$([0-9,.]+[KMB]?)\)', text)

        if total_btc_match and result['volume'] > 0:
            total_native = float(total_btc_match.group(1).replace(',', ''))
            price_native = f"{total_native / result['volume']:.4f} ₿"
            total_usd = parse_amount(total_btc_match.group(2))
            price_usd = f"${total_usd / result['volume']:,.2f}"
            result['price_native'] = price_native
            result['price_usd'] = price_usd
            result['price'] = f"{price_native} ({price_usd})"
            result['price_inferred'] = True
        elif total_eth_match and result['volume'] > 0:
            total_native = float(total_eth_match.group(1).replace(',', ''))
            price_native = f"{total_native / result['volume']:.4f} Ξ"
            total_usd = parse_amount(total_eth_match.group(2))
            price_usd = f"${total_usd / result['volume']:,.2f}"
            result['price_native'] = price_native
            result['price_usd'] = price_usd
            result['price'] = f"{price_native} ({price_usd})"
            result['price_inferred'] = True

    # 9. 提取现货参考价格 (Ref: $105234.56)
    # 支持多种格式：Ref: $123 / **Ref**: $123 / Ref**: $123 / Ref：$123（中文冒号）
    spot_match = re.search(r'(?:Ref|REF)[\*:\s：]{1,5}\$([0-9,.]+)', text, re.IGNORECASE)
    if spot_match:
        try:
            spot_val = float(spot_match.group(1).replace(',', ''))
            result['spot_price'] = f"${spot_val:,.2f}"
            result['ref_price_usd'] = spot_val  # 新增：数值字段（用于日志和进一步处理）
        except:
            pass

    # 10. 提取 strategy_title（完整策略标题）
    # 从消息第一行提取，通常格式为 **✅OPENED ...** 或 **CUSTOM ... STRATEGY:**
    title_match = re.search(r'\*\*(.*?)\*\*', text)
    if title_match:
        result['strategy_title'] = title_match.group(1).strip()

    # 11. 提取 legs 结构（多腿交易）- 详细版本（用于单笔预警）
    # ⚠️ 修正：逐行解析每条腿，提取完整信息
    # 格式：🟢 Bought 225.0x 🔶 BTC-27FEB26-80000-P 📉 at 0.0427 ₿ ($3,716.30) Total Bought: 9.6075 ₿ ($836.17K), IV: 46.71%, Ref: $87032.71
    #       bid: 0.042 (size: 78.0), mark: 0.0425, ask: 0.043 (size: 20.0)

    def parse_amount_with_suffix(amt_str):
        """解析金额（支持K/M/B后缀）"""
        amt_str = amt_str.replace(',', '').replace('$', '').strip()
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
            return None

    # 分行处理
    lines = text.split('\n')
    current_leg = None

    for line in lines:
        # 检查是否是新的腿（Bought/Sold 开头）
        leg_match = re.search(r'(Bought|Sold)\s+([\d.]+)x\s+.*?((BTC|ETH)-[\dA-Z-]+)', line, re.IGNORECASE)

        if leg_match:
            # 如果有未完成的腿，先保存
            if current_leg:
                # 根据合约名判断instrument_type
                contract_name = current_leg['contract']
                if 'PERPETUAL' in contract_name.upper() or 'PERP' in contract_name.upper():
                    current_leg['instrument_type'] = 'PERPETUAL'
                    result['non_options_legs'].append(current_leg)
                elif 'FUTURES' in contract_name.upper() or 'FUT' in contract_name.upper():
                    current_leg['instrument_type'] = 'FUTURES'
                    result['non_options_legs'].append(current_leg)
                elif re.search(r'-\d+-[PC]$', contract_name):  # 以 -数字-P/C 结尾
                    current_leg['instrument_type'] = 'OPTIONS'
                    result['options_legs'].append(current_leg)
                else:
                    # 未分类的合约（如 BTC-27MAR26，可能是 FUTURES 或 SPOT）
                    current_leg['instrument_type'] = 'FUTURES'
                    result['non_options_legs'].append(current_leg)

            # 开始新的腿
            side_str = leg_match.group(1)  # Bought / Sold
            volume_val = float(leg_match.group(2))
            contract_name = leg_match.group(3)

            current_leg = {
                'contract': contract_name,
                'side': 'LONG' if side_str.upper() == 'BOUGHT' else 'SHORT',
                'volume': volume_val,
                'price_btc': None,
                'price_usd': None,
                'total_btc': None,
                'total_usd': None,
                'iv': None,
                'ref_spot_usd': None,
                'bid': None,
                'bid_size': None,
                'mark': None,
                'ask': None,
                'ask_size': None
            }

            # 提取价格：at 0.0427 ₿ ($3,716.30)
            price_match = re.search(r'at\s+([\d.]+)\s*₿\s*\(\$([0-9,.]+)\)', line)
            if price_match:
                current_leg['price_btc'] = float(price_match.group(1))
                current_leg['price_usd'] = parse_amount_with_suffix(price_match.group(2))

            # 提取Total：Total Bought: 9.6075 ₿ ($836.17K)
            total_match = re.search(r'Total\s+(?:Bought|Sold):\s+([\d.]+)\s*₿\s*\(\$([0-9,.KMB]+)\)', line)
            if total_match:
                current_leg['total_btc'] = float(total_match.group(1))
                current_leg['total_usd'] = parse_amount_with_suffix(total_match.group(2))

            # 提取IV：IV: 46.71% 或 **IV**: 46.71%
            iv_match = re.search(r'\*\*IV\*\*:\s*([\d.]+)%|IV:\s*([\d.]+)%', line)
            if iv_match:
                current_leg['iv'] = float(iv_match.group(1) or iv_match.group(2))

            # 提取Ref：Ref: $87032.71 或 **Ref**: $87032.71
            ref_match = re.search(r'\*\*Ref\*\*:\s*\$([0-9,.]+)|Ref:\s*\$([0-9,.]+)', line)
            if ref_match:
                current_leg['ref_spot_usd'] = float((ref_match.group(1) or ref_match.group(2)).replace(',', ''))

        # 检查是否是quote行（bid/mark/ask）
        elif current_leg and re.search(r'bid.*mark.*ask', line, re.IGNORECASE):
            # bid: 0.042 (size: 78.0), mark: 0.0425, ask: 0.043 (size: 20.0)
            bid_match = re.search(r'bid:\s*([\d.]+)(?:\s*\(size:\s*([\d.]+)\))?', line, re.IGNORECASE)
            if bid_match:
                current_leg['bid'] = float(bid_match.group(1))
                if bid_match.group(2):
                    current_leg['bid_size'] = float(bid_match.group(2))

            mark_match = re.search(r'mark:\s*([\d.]+)', line, re.IGNORECASE)
            if mark_match:
                current_leg['mark'] = float(mark_match.group(1))

            ask_match = re.search(r'ask:\s*([\d.]+)(?:\s*\(size:\s*([\d.]+)\))?', line, re.IGNORECASE)
            if ask_match:
                current_leg['ask'] = float(ask_match.group(1))
                if ask_match.group(2):
                    current_leg['ask_size'] = float(ask_match.group(2))

    # 保存最后一条腿
    if current_leg:
        contract_name = current_leg['contract']
        if 'PERPETUAL' in contract_name.upper() or 'PERP' in contract_name.upper():
            current_leg['instrument_type'] = 'PERPETUAL'
            result['non_options_legs'].append(current_leg)
        elif 'FUTURES' in contract_name.upper() or 'FUT' in contract_name.upper():
            current_leg['instrument_type'] = 'FUTURES'
            result['non_options_legs'].append(current_leg)
        elif re.search(r'-\d+-[PC]$', contract_name):
            current_leg['instrument_type'] = 'OPTIONS'
            result['options_legs'].append(current_leg)
        else:
            # 未分类的合约（如 BTC-27MAR26，可能是 FUTURES 或 SPOT）
            current_leg['instrument_type'] = 'FUTURES'
            result['non_options_legs'].append(current_leg)

    # 如果有多个期权腿，更新 contract 显示
    if len(result['options_legs']) > 1:
        result['contract'] = f"合约（{len(result['options_legs'])}腿）"

    # ⚠️ 修正：添加预警专用推导字段（消除全局正则串线）
    # 这些字段专门用于预警判断，从 options_legs 推导而来
    result['options_sum'] = sum(leg.get('volume', 0) for leg in result['options_legs'])
    result['options_max'] = max([leg.get('volume', 0) for leg in result['options_legs']], default=0)
    result['options_count'] = len(result['options_legs'])

    # 修正 instrument_type：基于 options_legs 是否存在（而非全局正则）
    if result['options_legs']:
        result['instrument_type_derived'] = 'OPTIONS'
    elif result['non_options_legs']:
        # 从第一条非期权腿推导
        first_non_option = result['non_options_legs'][0]
        result['instrument_type_derived'] = first_non_option.get('instrument_type', 'Unknown')
    else:
        result['instrument_type_derived'] = result['instrument_type']  # fallback 到全局判断

    # 修正 spot_price：从 legs 中的 ref 推导（优先级：最后一条腿 > 出现最多的值）
    ref_values = []
    for leg in result['options_legs'] + result['non_options_legs']:
        if leg.get('ref_spot_usd'):
            ref_values.append(leg['ref_spot_usd'])

    if ref_values:
        # 取最后一个 ref 值（通常最新）
        result['spot_price_derived'] = f"${ref_values[-1]:,.2f}"
        result['ref_price_usd'] = ref_values[-1]
    else:
        # fallback 到全局解析的 spot_price
        result['spot_price_derived'] = result.get('spot_price', 'N/A')

    # 修正 contract_list：所有期权合约列表（用于预警显示）
    result['options_contracts'] = [leg.get('contract', 'Unknown') for leg in result['options_legs']]

    return result


def build_trade_card_html(trades, title, sort_type):
    """
    构建交易卡片 HTML

    ⚠️ 修正：
    - Greeks改为紧凑横排显示（单行）
    - 支持多腿交易展示
    - 使用strategy_title（如果有）

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

    # ✅ 修正：使用enumerate直接获取正确的排名（1, 2, 3），不依赖trade['rank']
    for rank, trade in enumerate(trades, 1):
        # ⚠️ 修正：Greeks改为紧凑横排显示（单行，类似标签）
        def format_greek(value):
            """格式化希腊值（处理大数和None）"""
            if value is None:
                return 'N/A'
            if abs(value) >= 1000:
                return f"{value:,.0f}"  # 大数不显示小数
            else:
                return f"{value:.2f}"

        greeks = trade.get('greeks', {})
        greeks_html = f"""
        <div class="greeks-inline">
            <span class="greek-tag">Δ: {format_greek(greeks.get('delta'))}</span>
            <span class="greek-tag">Γ: {format_greek(greeks.get('gamma'))}</span>
            <span class="greek-tag">ν: {format_greek(greeks.get('vega'))}</span>
            <span class="greek-tag">Θ: {format_greek(greeks.get('theta'))}</span>
            <span class="greek-tag">ρ: {format_greek(greeks.get('rho'))}</span>
        </div>
        """

        # 排序指标高亮显示（注释：字段语义已明确）
        if sort_type == 'amount':
            # amount_usd = 期权腿总权利金（USD）
            sort_value_html = f'<tr><td><strong>💰 交易金额:</strong></td><td><span style="color: #e74c3c; font-size: 18px; font-weight: bold;">${trade["amount_usd"]:,.2f}</span></td></tr>'
        else:  # volume
            # volume = 期权张数（总和）
            sort_value_html = f'<tr><td><strong>📦 合约数量:</strong></td><td><span style="color: #e74c3c; font-size: 18px; font-weight: bold;">{trade["volume"]}x</span></td></tr>'

        # ⚠️ 修正：使用strategy_title（如果有），否则fallback到strategy
        strategy_display = trade.get('strategy_title', trade.get('strategy', 'Unknown'))

        # ⚠️ 修正：支持多腿显示（显示完整信息）
        options_legs = trade.get('options_legs', [])
        non_options_legs = trade.get('non_options_legs', [])

        # 合约字段：单腿显示合约名，多腿显示"合约（X腿）"并列出每条腿的详细信息
        if len(options_legs) > 1:
            contract_html = f'<tr><td><strong>合约:</strong></td><td>{trade["contract"]}</td></tr>'
            contract_html += '<tr><td colspan="2">'
            contract_html += '<div style="background: #fef3c7; border-left: 3px solid #f59e0b; padding: 8px; margin: 5px 0; border-radius: 4px;">'
            contract_html += '<strong>期权腿详情:</strong><ul style="margin: 5px 0 0 0; padding-left: 20px; list-style: none;">'
            for i, leg in enumerate(options_legs, 1):
                side_icon = '🟢' if leg.get('side') == 'LONG' else '🔴'
                leg_volume = leg.get('volume', 0)
                leg_contract = leg.get('contract', 'Unknown')
                leg_price_btc = leg.get('price_btc', 0)
                leg_total_usd = leg.get('total_usd', 0)
                leg_iv = leg.get('iv', 0)

                leg_html = f'<li style="margin: 4px 0; font-size: 12px; line-height: 1.6;">'
                leg_html += f'{side_icon} <strong>腿{i}:</strong> {leg.get("side", "?")} {leg_volume:.0f}x {leg_contract}'

                # 添加价格和总金额信息
                if leg_price_btc:
                    leg_html += f' @ {leg_price_btc:.4f} ₿'
                if leg_total_usd:
                    leg_html += f' (${leg_total_usd:,.0f})'

                # 添加IV信息
                if leg_iv:
                    leg_html += f', IV: {leg_iv:.2f}%'

                leg_html += '</li>'
                contract_html += leg_html

            contract_html += '</ul></div></td></tr>'
        else:
            contract_html = f'<tr><td><strong>合约:</strong></td><td>{trade["contract"]}</td></tr>'

        # price字段：单腿每张价格
        price_display = trade.get('price', 'Unknown')

        # ⚠️ 新增：ALSO_IN 标签显示
        also_in_tag = trade.get('also_in')
        also_in_html = ''
        if also_in_tag:
            also_in_html = f'<span style="display: inline-block; background: #3498db; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 10px;">{also_in_tag}</span>'

        html += f"""
        <div class="trade-card">
            <div class="trade-header">#{rank} - {trade['date']}{also_in_html}</div>
            <table>
                <tr><td><strong>交易策略:</strong></td><td>{strategy_display}</td></tr>
                {sort_value_html}
                {contract_html}
                <tr><td><strong>价格:</strong></td><td>{price_display}</td></tr>
                <tr><td><strong>IV:</strong></td><td>{trade['iv']}</td></tr>
            </table>
            <div style="margin-top: 10px;">
                <strong>希腊字母:</strong>
                {greeks_html}
            </div>
        </div>
        """

    return html


def build_daily_report_html(report_data):
    """
    构建每日报告 HTML 内容

    ⚠️ 修正：添加 ALSO_IN 交叉引用标签

    Args:
        report_data: 报告数据字典

    Returns:
        HTML 字符串
    """
    time_range = report_data['time_range']
    spot_prices = report_data['spot_prices']
    stats = report_data['trade_statistics']
    top_trades = report_data['top_trades']

    # ⚠️ 新增：为交易添加 ALSO_IN 标签（检测同时出现在两个榜单的交易）
    def add_also_in_tags(trades_by_amount, trades_by_volume):
        """
        为同时出现在两个榜单的交易添加 ALSO_IN 标签

        Args:
            trades_by_amount: 按金额排名的交易列表
            trades_by_volume: 按数量排名的交易列表
        """
        # 构建 msg_id -> rank 映射
        amount_map = {t['msg_id']: i+1 for i, t in enumerate(trades_by_amount)}
        volume_map = {t['msg_id']: i+1 for i, t in enumerate(trades_by_volume)}

        # 为 amount 榜单添加标签
        for trade in trades_by_amount:
            msg_id = trade['msg_id']
            if msg_id in volume_map:
                volume_rank = volume_map[msg_id]
                trade['also_in'] = f"[ALSO_IN: VOLUME #{volume_rank}]"
            else:
                trade['also_in'] = None

        # 为 volume 榜单添加标签
        for trade in trades_by_volume:
            msg_id = trade['msg_id']
            if msg_id in amount_map:
                amount_rank = amount_map[msg_id]
                trade['also_in'] = f"[ALSO_IN: AMOUNT #{amount_rank}]"
            else:
                trade['also_in'] = None

    # 处理 BTC 和 ETH 的交叉引用
    add_also_in_tags(
        top_trades.get('btc_by_amount', []),
        top_trades.get('btc_by_volume', [])
    )
    add_also_in_tags(
        top_trades.get('eth_by_amount', []),
        top_trades.get('eth_by_volume', [])
    )

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
            }}
            /* ⚠️ 新增：Greeks横排紧凑显示 */
            .greeks-inline {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 5px;
            }}
            .greek-tag {{
                display: inline-block;
                padding: 4px 10px;
                background: #ecf0f1;
                border-radius: 3px;
                font-size: 13px;
                white-space: nowrap;
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
                    <div class="stat-number">{'${:,.2f}'.format(spot_prices['btc']) if spot_prices['btc'] is not None else 'N/A'}</div>
                    <div class="stat-label">BTC 现货价格</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{'${:,.2f}'.format(spot_prices['eth']) if spot_prices['eth'] is not None else 'N/A'}</div>
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


def send_existing_report_fast(report_date: str):
    """
    秒级测试发送：从 DB 读取已有日报并快速发送（用于模板调试）

    优先级：
    1. DailyReport 表有 html_content：直接发送（最快）
    2. DailyReport 表有 report_data：渲染后发送
    3. 不存在：生成一次后发送（兜底）

    Args:
        report_date: 报告日期 (格式: YYYY-MM-DD)

    Returns:
        True: 发送成功
        False: 发送失败
    """
    from email_sender import send_html_email
    import json

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] start date={report_date}")

    session = get_session()
    try:
        # 步骤1：查询 DailyReport 表
        report = session.query(DailyReport).filter_by(report_date=report_date).first()

        if report:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] db_report_found=true has_html={report.html_content is not None and len(report.html_content or '') > 0}")

            # 情况1：已有 html_content（最快路径）
            if report.html_content and len(report.html_content) > 0:
                html_content = report.html_content
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] mode=existing_html")

            # 情况2：有 report_data，需要渲染
            elif report.report_data:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] mode=render_from_report_data")
                report_data = json.loads(report.report_data)
                html_content = render_report_html(report_data)

            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] error='report exists but no html_content or report_data'")
                return False

        else:
            # 情况3：不存在，需要生成（兜底，只执行一次）
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] db_report_found=false mode=generated_then_send")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] generating_report date={report_date}")

            # 异步生成日报
            import asyncio
            report_data = asyncio.run(generate_daily_report(target_date=report_date))

            # 重新查询获取生成的报告（注意：report_date 可能是 start_date 的日期）
            # 先尝试原日期，再尝试前一天（因为窗口是 D-1 16:00 - D 16:00）
            report = session.query(DailyReport).filter_by(report_date=report_date).first()
            if not report:
                # 尝试前一天
                from datetime import date, timedelta
                prev_date = (datetime.strptime(report_date, '%Y-%m-%d').date() - timedelta(days=1)).strftime('%Y-%m-%d')
                report = session.query(DailyReport).filter_by(report_date=prev_date).first()
                if report:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] using_prev_date actual_report_date={prev_date}")

            if not report or not report.html_content:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] error='report generation failed or html_content empty'")
                return False

            html_content = report.html_content
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] generation_complete")

        # 步骤2：发送邮件
        subject = f"🧪 TEST Daily Report - {report_date} (From DB)"
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] sending_email subject='{subject}'")

        success = send_html_email(subject, html_content)

        if success:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] email_sent=true")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] email_sent=false")

        return success

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FAST_TEST] error={e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        session.close()


async def send_pending_daily_reports(limit: int = None):
    """
    发送待发送的每日报告邮件（16:05 定时任务）- 策略 B（体验优先）

    ⚠️ 策略变更（2025-12-21）：
    - 每天最多发送 1 封日报（只发最新 report_date）
    - 历史未发送日报不自动补发（只记录告警日志）
    - 幂等性保障：发送前后原子更新状态

    Args:
        limit: 保留参数（兼容性），实际已改为"最多发送1封最新日报"
    """
    import time
    from sqlalchemy import desc
    session = get_session()

    try:
        # ==========================================
        # A) 查询最新 report_date 的未发送日报（候选）
        # ==========================================
        latest_pending_report = (
            session.query(DailyReport)
            .filter_by(is_sent=False)
            .order_by(desc(DailyReport.report_date))
            .first()
        )

        if not latest_pending_report:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] mode=latest_only action=skip reason=no_pending")
            return

        latest_date = latest_pending_report.report_date
        candidate_sent = latest_pending_report.is_sent

        # ==========================================
        # B) 统计历史未发送日报（backlog）
        # ==========================================
        backlog_reports = (
            session.query(DailyReport)
            .filter(DailyReport.is_sent == False)
            .filter(DailyReport.report_date < latest_date)
            .order_by(DailyReport.report_date)
            .all()
        )

        backlog_count = len(backlog_reports)
        oldest_backlog = backlog_reports[0].report_date if backlog_reports else None
        newest_backlog = backlog_reports[-1].report_date if backlog_reports else None

        # 结构化日志：候选日报信息
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] mode=latest_only report_date={latest_date} candidate_sent={candidate_sent} pending_old={backlog_count}")

        # 告警：历史未发送日报
        if backlog_count > 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_BACKLOG] count={backlog_count} oldest={oldest_backlog} newest={newest_backlog} action=ignored reason=policy_latest_only")

        # ==========================================
        # C) 检查候选日报是否已发送（幂等）
        # ==========================================
        if candidate_sent:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=skip report_date={latest_date} reason=already_sent")
            return

        # ==========================================
        # D) 检查邮件配置
        # ==========================================
        if not config.EMAIL_ENABLED:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=skip report_date={latest_date} reason=email_disabled")
            return

        # ==========================================
        # E) 发送最新日报（带幂等保障）
        # ==========================================
        from email_sender import send_html_email, send_email

        try:
            subject = f"📊 Daily Trade Report - {latest_pending_report.report_date}"

            # 发送前日志（标记开始发送）
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=sending report_date={latest_date} subject='{subject[:50]}' recipients={config.EMAIL_RECIPIENTS}")

            # 发送邮件
            if latest_pending_report.html_content:
                success = send_html_email(subject, latest_pending_report.html_content)
            else:
                fallback_body = f"""Daily Trade Report - {latest_pending_report.report_date}

BTC: {latest_pending_report.btc_trade_count} 笔, {latest_pending_report.btc_total_volume}x
ETH: {latest_pending_report.eth_trade_count} 笔, {latest_pending_report.eth_total_volume}x
Total: {latest_pending_report.total_messages} 条消息, {latest_pending_report.total_block_trades} 笔交易
"""
                success = send_email(subject, fallback_body)

            # ==========================================
            # F) 原子更新发送状态（幂等保障）
            # ==========================================
            if success:
                try:
                    # 原子更新：is_sent + sent_at
                    latest_pending_report.is_sent = True
                    latest_pending_report.sent_at = datetime.utcnow()
                    session.flush()
                    session.commit()

                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=sent report_date={latest_date} sent_at={latest_pending_report.sent_at.strftime('%Y-%m-%d %H:%M:%S')}")

                except Exception as commit_err:
                    session.rollback()
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=commit_failed report_date={latest_date} error={type(commit_err).__name__}: {commit_err}")
                    # ⚠️ 发送成功但状态更新失败：下次会重复发送（幂等风险）
                    raise

            else:
                # 发送失败：保持 is_sent=False，记录错误日志
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=send_failed report_date={latest_date} reason=email_send_failed")

        except Exception as send_err:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=exception report_date={latest_date} error={type(send_err).__name__}: {send_err}")
            raise

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [REPORT_SEND] action=error error={type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

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
    parser.add_argument('--send-existing-report', type=str, metavar='DATE',
                       help='秒级测试发送：从 DB 读取已有日报快速发送（格式: YYYY-MM-DD）')
    parser.add_argument('--date', type=str,
                       help='指定日期 (格式: YYYY-MM-DD)，默认为今天')

    args = parser.parse_args()

    # 优先处理：秒级测试发送（快速路径）
    if args.send_existing_report:
        report_date = args.send_existing_report
        print(f"\n" + "=" * 60)
        print(f"秒级测试发送日报：{report_date}")
        print("=" * 60)

        success = send_existing_report_fast(report_date)

        print("\n" + "=" * 60)
        if success:
            print("✓ 测试邮件发送成功！")
            print(f"  主题: 🧪 TEST Daily Report - {report_date} (From DB)")
            print("  请检查邮箱收件")
        else:
            print("✗ 测试邮件发送失败")
        print("=" * 60)
        sys.exit(0)

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
