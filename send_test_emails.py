#!/usr/bin/env python3
"""
测试邮件发送脚本（OPTIONS ONLY 调试专用）
生成并发送 3 封测试邮件：
1. [TEST] Daily Report
2. [TEST] BTC Alert
3. [TEST] ETH Alert
"""

import sys
from datetime import datetime
import pytz

import config
from database import get_session, Message
from report_generator import (
    build_daily_report_data,
    build_daily_report_html,
    build_trade_card_html,
    normalize_block_trades,
    parse_block_trade_message
)
from email_sender import send_html_email


# 测试窗口（东八区）
TZ = pytz.timezone(config.REPORT_TIMEZONE)
START_TIME = TZ.localize(datetime(2025, 12, 11, 16, 0, 0))
END_TIME = TZ.localize(datetime(2025, 12, 12, 16, 0, 0))

# 测试阈值（临时降低以匹配测试数据）
TEST_THRESHOLD_BTC = 200   # BTC OPTIONS volume > 200
TEST_THRESHOLD_ETH = 1000  # ETH OPTIONS volume >= 1000


def send_test_daily_report():
    """发送测试日报邮件（OPTIONS ONLY）"""
    print("\n" + "=" * 70)
    print("测试邮件 #1: [TEST] Daily Report (OPTIONS ONLY)")
    print("=" * 70)

    # 1. 读取测试窗口数据
    session = get_session()
    try:
        messages = session.query(Message).filter(
            Message.date >= START_TIME,
            Message.date < END_TIME
        ).order_by(Message.date).all()

        block_trades = [msg for msg in messages if msg.is_block_trade]

        print(f"✓ 数据加载: {len(messages)} 条消息, {len(block_trades)} 笔大宗交易")

        # 2. 生成日报数据（使用 OPTIONS ONLY 过滤）
        report_data = build_daily_report_data(
            messages=messages,
            block_trades=block_trades,
            start_date=START_TIME,
            end_date=END_TIME,
            top_limit=3
        )

        # 3. 验证 OPTIONS ONLY 过滤
        btc_opts = report_data['volume_stats']['btc_volume']
        eth_opts = report_data['volume_stats']['eth_volume']
        print(f"✓ OPTIONS 统计: BTC={btc_opts:.1f}x, ETH={eth_opts:.1f}x")

        # 4. 生成 HTML（需要转换为 v1 兼容格式）
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
        html_body = build_daily_report_html(legacy_data)

        # 5. 发送邮件
        subject = f"[TEST] Daily Report - 2025-12-11 16:00 to 2025-12-12 16:00 (OPTIONS ONLY)"

        print(f"✓ 发送邮件...")
        success = send_html_email(subject, html_body)

        if success:
            print(f"✅ 成功: {subject}")
            return True
        else:
            print(f"❌ 失败: {subject}")
            return False

    finally:
        session.close()


def send_test_btc_alert():
    """发送测试 BTC 预警邮件（OPTIONS ONLY，volume > 200）"""
    print("\n" + "=" * 70)
    print(f"测试邮件 #2: [TEST] BTC Alert (OPTIONS, volume > {TEST_THRESHOLD_BTC})")
    print("=" * 70)

    # 1. 读取测试窗口数据
    session = get_session()
    try:
        messages = session.query(Message).filter(
            Message.date >= START_TIME,
            Message.date < END_TIME
        ).order_by(Message.date).all()

        block_trades = [msg for msg in messages if msg.is_block_trade]

        # 2. 归一化并过滤 OPTIONS
        normalized = normalize_block_trades(block_trades, filter_non_options=True)

        # 3. 筛选符合条件的 BTC OPTIONS 交易
        btc_opts = [
            t for t in normalized
            if t['asset'] == 'BTC'
            and t['instrument_type'] == 'OPTIONS'
            and t['volume'] > TEST_THRESHOLD_BTC
        ]

        if not btc_opts:
            print(f"⚠️  警告: 没有找到 BTC OPTIONS 交易 volume > {TEST_THRESHOLD_BTC}")
            print(f"    测试数据不足，请检查 reports.db 中的数据")
            return False

        # 4. 选择最大 volume 的交易
        selected_trade = max(btc_opts, key=lambda t: t['volume'])

        print(f"✓ 选中交易:")
        print(f"  - Asset: {selected_trade['asset']}")
        print(f"  - Contract: {selected_trade['contract']}")
        print(f"  - Volume: {selected_trade['volume']:.1f}x")
        print(f"  - Amount USD: ${selected_trade['amount_usd']:,.2f}")
        print(f"  - IV: {selected_trade['iv']}")
        print(f"  - Msg ID: {selected_trade['msg_id']}")

        # 5. 生成 HTML（使用 alert card 模板）
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .alert-tag {{ display: inline-block; background: #f59e0b; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 8px; }}
        .trade-card {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .trade-field {{ margin: 12px 0; }}
        .trade-field strong {{ color: #4b5563; min-width: 120px; display: inline-block; }}
        .trade-value {{ color: #1f2937; font-weight: 600; }}
        .message-box {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 15px; border-radius: 6px; margin: 20px 0; font-size: 13px; color: #374151; white-space: pre-wrap; font-family: monospace; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Large Block Trade Alert</h1>
            <span class="alert-tag">TEST MODE</span>
            <span class="alert-tag">OPTIONS ONLY</span>
        </div>

        <div class="trade-card">
            <h2 style="margin-top: 0; color: #92400e;">BTC OPTIONS - Large Volume Detected</h2>

            <div class="trade-field">
                <strong>Asset:</strong>
                <span class="trade-value">{selected_trade['asset']}</span>
            </div>

            <div class="trade-field">
                <strong>Exchange:</strong>
                <span class="trade-value">{selected_trade['exchange']}</span>
            </div>

            <div class="trade-field">
                <strong>Instrument Type:</strong>
                <span class="trade-value">{selected_trade['instrument_type']}</span>
            </div>

            <div class="trade-field">
                <strong>Contract:</strong>
                <span class="trade-value">{selected_trade['contract']}</span>
            </div>

            <div class="trade-field">
                <strong>Strategy:</strong>
                <span class="trade-value">{selected_trade['strategy']}</span>
            </div>

            <div class="trade-field">
                <strong>Volume:</strong>
                <span class="trade-value" style="font-size: 18px; color: #dc2626;">{selected_trade['volume']:.1f}x</span>
                <span style="color: #6b7280; font-size: 14px;">(Threshold: {TEST_THRESHOLD_BTC}x)</span>
            </div>

            <div class="trade-field">
                <strong>Price:</strong>
                <span class="trade-value">{selected_trade['price']}</span>
            </div>

            <div class="trade-field">
                <strong>Amount (USD):</strong>
                <span class="trade-value">${selected_trade['amount_usd']:,.2f}</span>
            </div>

            <div class="trade-field">
                <strong>IV:</strong>
                <span class="trade-value">{selected_trade['iv']}</span>
            </div>

            <div class="trade-field">
                <strong>Side:</strong>
                <span class="trade-value">{selected_trade['side']}</span>
            </div>

            <div class="trade-field">
                <strong>Spot Price:</strong>
                <span class="trade-value">${selected_trade.get('spot_price', 'N/A')}</span>
            </div>

            {f'''
            <div class="trade-field">
                <strong>Greeks:</strong>
                <span class="trade-value">
                    Δ: {selected_trade['greeks'].get('delta', 'N/A')},
                    Γ: {selected_trade['greeks'].get('gamma', 'N/A')},
                    ν: {selected_trade['greeks'].get('vega', 'N/A')},
                    Θ: {selected_trade['greeks'].get('theta', 'N/A')},
                    ρ: {selected_trade['greeks'].get('rho', 'N/A')}
                </span>
            </div>
            ''' if selected_trade['greeks'] else ''}

            <div class="trade-field">
                <strong>Message ID:</strong>
                <span class="trade-value">{selected_trade['msg_id']}</span>
            </div>

            <div class="trade-field">
                <strong>Date:</strong>
                <span class="trade-value">{selected_trade['date']}</span>
            </div>
        </div>

        <h3 style="color: #4b5563; margin-top: 30px;">Original Message:</h3>
        <div class="message-box">{selected_trade['raw_text'][:800]}</div>

        <div class="footer">
            <p><strong>Test Window:</strong> 2025-12-11 16:00 to 2025-12-12 16:00 (Asia/Shanghai)</p>
            <p><strong>Filter:</strong> OPTIONS ONLY (FUTURES/PERPETUAL excluded)</p>
            <p><strong>Test Threshold:</strong> BTC volume > {TEST_THRESHOLD_BTC}x</p>
            <p>Generated at: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}</p>
        </div>
    </div>
</body>
</html>
"""

        # 6. 发送邮件
        subject = f"[TEST] BTC Alert - {selected_trade['contract']} - Volume {selected_trade['volume']:.1f}x"

        print(f"✓ 发送邮件...")
        success = send_html_email(subject, html_body)

        if success:
            print(f"✅ 成功: {subject}")
            return True
        else:
            print(f"❌ 失败: {subject}")
            return False

    finally:
        session.close()


def send_test_eth_alert():
    """发送测试 ETH 预警邮件（OPTIONS ONLY，volume >= 1000）"""
    print("\n" + "=" * 70)
    print(f"测试邮件 #3: [TEST] ETH Alert (OPTIONS, volume >= {TEST_THRESHOLD_ETH})")
    print("=" * 70)

    # 1. 读取测试窗口数据
    session = get_session()
    try:
        messages = session.query(Message).filter(
            Message.date >= START_TIME,
            Message.date < END_TIME
        ).order_by(Message.date).all()

        block_trades = [msg for msg in messages if msg.is_block_trade]

        # 2. 归一化并过滤 OPTIONS
        normalized = normalize_block_trades(block_trades, filter_non_options=True)

        # 3. 筛选符合条件的 ETH OPTIONS 交易（注意：使用 >= 因为最大值恰好是 1000.0）
        eth_opts = [
            t for t in normalized
            if t['asset'] == 'ETH'
            and t['instrument_type'] == 'OPTIONS'
            and t['volume'] >= TEST_THRESHOLD_ETH
        ]

        if not eth_opts:
            # 找到最大 volume 的 ETH OPTIONS 交易作为证据
            all_eth_opts = [
                t for t in normalized
                if t['asset'] == 'ETH'
                and t['instrument_type'] == 'OPTIONS'
            ]

            if all_eth_opts:
                max_trade = max(all_eth_opts, key=lambda t: t['volume'])
                print(f"⚠️  警告: 没有找到 ETH OPTIONS 交易 volume >= {TEST_THRESHOLD_ETH}")
                print(f"    测试数据不足")
                print(f"    最大 ETH OPTIONS volume: {max_trade['volume']:.1f}x")
                print(f"    Contract: {max_trade['contract']}")
                print(f"    Msg ID: {max_trade['msg_id']}")
            else:
                print(f"⚠️  警告: 测试窗口内没有任何 ETH OPTIONS 交易")

            return False

        # 4. 选择最大 volume 的交易
        selected_trade = max(eth_opts, key=lambda t: t['volume'])

        print(f"✓ 选中交易:")
        print(f"  - Asset: {selected_trade['asset']}")
        print(f"  - Contract: {selected_trade['contract']}")
        print(f"  - Volume: {selected_trade['volume']:.1f}x")
        print(f"  - Amount USD: ${selected_trade['amount_usd']:,.2f}")
        print(f"  - IV: {selected_trade['iv']}")
        print(f"  - Msg ID: {selected_trade['msg_id']}")

        # 5. 生成 HTML
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .alert-tag {{ display: inline-block; background: #f59e0b; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 8px; }}
        .trade-card {{ background: #dbeafe; border-left: 4px solid #3b82f6; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .trade-field {{ margin: 12px 0; }}
        .trade-field strong {{ color: #4b5563; min-width: 120px; display: inline-block; }}
        .trade-value {{ color: #1f2937; font-weight: 600; }}
        .message-box {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 15px; border-radius: 6px; margin: 20px 0; font-size: 13px; color: #374151; white-space: pre-wrap; font-family: monospace; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Large Block Trade Alert</h1>
            <span class="alert-tag">TEST MODE</span>
            <span class="alert-tag">OPTIONS ONLY</span>
        </div>

        <div class="trade-card">
            <h2 style="margin-top: 0; color: #1e40af;">ETH OPTIONS - Large Volume Detected</h2>

            <div class="trade-field">
                <strong>Asset:</strong>
                <span class="trade-value">{selected_trade['asset']}</span>
            </div>

            <div class="trade-field">
                <strong>Exchange:</strong>
                <span class="trade-value">{selected_trade['exchange']}</span>
            </div>

            <div class="trade-field">
                <strong>Instrument Type:</strong>
                <span class="trade-value">{selected_trade['instrument_type']}</span>
            </div>

            <div class="trade-field">
                <strong>Contract:</strong>
                <span class="trade-value">{selected_trade['contract']}</span>
            </div>

            <div class="trade-field">
                <strong>Strategy:</strong>
                <span class="trade-value">{selected_trade['strategy']}</span>
            </div>

            <div class="trade-field">
                <strong>Volume:</strong>
                <span class="trade-value" style="font-size: 18px; color: #dc2626;">{selected_trade['volume']:.1f}x</span>
                <span style="color: #6b7280; font-size: 14px;">(Threshold: {TEST_THRESHOLD_ETH}x)</span>
            </div>

            <div class="trade-field">
                <strong>Price:</strong>
                <span class="trade-value">{selected_trade['price']}</span>
            </div>

            <div class="trade-field">
                <strong>Amount (USD):</strong>
                <span class="trade-value">${selected_trade['amount_usd']:,.2f}</span>
            </div>

            <div class="trade-field">
                <strong>IV:</strong>
                <span class="trade-value">{selected_trade['iv']}</span>
            </div>

            <div class="trade-field">
                <strong>Side:</strong>
                <span class="trade-value">{selected_trade['side']}</span>
            </div>

            <div class="trade-field">
                <strong>Spot Price:</strong>
                <span class="trade-value">${selected_trade.get('spot_price', 'N/A')}</span>
            </div>

            {f'''
            <div class="trade-field">
                <strong>Greeks:</strong>
                <span class="trade-value">
                    Δ: {selected_trade['greeks'].get('delta', 'N/A')},
                    Γ: {selected_trade['greeks'].get('gamma', 'N/A')},
                    ν: {selected_trade['greeks'].get('vega', 'N/A')},
                    Θ: {selected_trade['greeks'].get('theta', 'N/A')},
                    ρ: {selected_trade['greeks'].get('rho', 'N/A')}
                </span>
            </div>
            ''' if selected_trade['greeks'] else ''}

            <div class="trade-field">
                <strong>Message ID:</strong>
                <span class="trade-value">{selected_trade['msg_id']}</span>
            </div>

            <div class="trade-field">
                <strong>Date:</strong>
                <span class="trade-value">{selected_trade['date']}</span>
            </div>
        </div>

        <h3 style="color: #4b5563; margin-top: 30px;">Original Message:</h3>
        <div class="message-box">{selected_trade['raw_text'][:800]}</div>

        <div class="footer">
            <p><strong>Test Window:</strong> 2025-12-11 16:00 to 2025-12-12 16:00 (Asia/Shanghai)</p>
            <p><strong>Filter:</strong> OPTIONS ONLY (FUTURES/PERPETUAL excluded)</p>
            <p><strong>Test Threshold:</strong> ETH volume >= {TEST_THRESHOLD_ETH}x</p>
            <p>Generated at: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}</p>
        </div>
    </div>
</body>
</html>
"""

        # 6. 发送邮件
        subject = f"[TEST] ETH Alert - {selected_trade['contract']} - Volume {selected_trade['volume']:.1f}x"

        print(f"✓ 发送邮件...")
        success = send_html_email(subject, html_body)

        if success:
            print(f"✅ 成功: {subject}")
            return True
        else:
            print(f"❌ 失败: {subject}")
            return False

    finally:
        session.close()


def main():
    """主函数：依次发送 3 封测试邮件"""
    print("\n" + "=" * 70)
    print("测试邮件发送脚本 (OPTIONS ONLY)")
    print("=" * 70)
    print(f"测试窗口: 2025-12-11 16:00 → 2025-12-12 16:00 (Asia/Shanghai)")
    print(f"测试阈值: BTC > {TEST_THRESHOLD_BTC}, ETH >= {TEST_THRESHOLD_ETH}")
    print(f"过滤规则: OPTIONS ONLY (排除 FUTURES/PERPETUAL)")
    print("=" * 70)

    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print("\n⚠️  警告: EMAIL_ENABLED = False")
        print("   请在 .env 或 config.py 中设置 EMAIL_ENABLED=true")
        response = input("\n是否继续测试? (y/n): ")
        if response.lower() != 'y':
            print("测试已取消")
            sys.exit(0)

    if not config.EMAIL_PASSWORD:
        print("\n❌ 错误: EMAIL_PASSWORD 未设置")
        print("   请在 .env 中设置 Gmail 应用专用密码")
        sys.exit(1)

    # 依次发送 3 封测试邮件
    results = []

    # 邮件 #1: Daily Report
    try:
        success = send_test_daily_report()
        results.append(("Daily Report", success))
    except Exception as e:
        print(f"❌ 邮件 #1 异常: {e}")
        results.append(("Daily Report", False))

    # 邮件 #2: BTC Alert
    try:
        success = send_test_btc_alert()
        results.append(("BTC Alert", success))
    except Exception as e:
        print(f"❌ 邮件 #2 异常: {e}")
        results.append(("BTC Alert", False))

    # 邮件 #3: ETH Alert
    try:
        success = send_test_eth_alert()
        results.append(("ETH Alert", success))
    except Exception as e:
        print(f"❌ 邮件 #3 异常: {e}")
        results.append(("ETH Alert", False))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    for email_type, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"{status}: {email_type}")

    success_count = sum(1 for _, success in results if success)
    print(f"\n总计: {success_count}/3 封邮件发送成功")

    if success_count == 3:
        print("\n🎉 所有测试邮件发送完成！请检查邮箱收件。")
        sys.exit(0)
    else:
        print("\n⚠️  部分测试邮件发送失败，请检查错误信息。")
        sys.exit(1)


if __name__ == '__main__':
    main()
