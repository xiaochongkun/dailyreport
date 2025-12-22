#!/usr/bin/env python3
"""
验收脚本：净权利金预警（Net Premium Alert）真实历史数据测试

功能：
1. 扫描给定时间窗口内的历史 block trade 消息（从 reports.db）
2. 计算每笔订单的 net_premium_usd = premium_received_usd - premium_paid_usd
3. 筛选满足阈值的候选订单：abs(net_premium_usd) >= 1,000,000
4. 输出 Top N 候选订单（按 abs_net_premium_usd 降序）
5. 可选：发送 1-2 封 🧪 [TEST] 邮件到订阅邮箱

CRITICAL: 必须使用真实历史数据，禁止模拟数据
"""

import sys
import os
from datetime import datetime, timedelta
import config
from database import get_session, Message
from report_generator import parse_block_trade_message
from email_sender import send_single_trade_alert_html


def scan_net_premium_candidates(start_date, end_date, min_abs_net_premium=None):
    """
    扫描历史数据，查找满足净权利金阈值的候选订单

    Args:
        start_date: 开始时间（datetime）
        end_date: 结束时间（datetime）
        min_abs_net_premium: 最小净权利金绝对值（可选，用于筛选）

    Returns:
        List[dict]: 订单列表（按 abs_net_premium_usd 降序）
    """
    print(f"=" * 80)
    print(f"净权利金预警候选订单扫描（Net Premium Alert）")
    print(f"=" * 80)
    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M')} ~ {end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"最小净权利金绝对值: ${min_abs_net_premium:,.0f}" if min_abs_net_premium else "最小净权利金绝对值: 无限制")
    print(f"阈值参考: ${config.PREMIUM_USD_THRESHOLD:,.0f}" if hasattr(config, 'PREMIUM_USD_THRESHOLD') else "阈值参考: $1,000,000")
    print(f"=" * 80)
    print()

    session = get_session()
    try:
        # 查询时间范围内的 block trade 消息
        messages = session.query(Message).filter(
            Message.is_block_trade == True,
            Message.date >= start_date,
            Message.date < end_date
        ).order_by(Message.date.desc()).all()

        print(f"[SCAN] 找到 {len(messages)} 条 block trade 消息")

        candidates = []
        processed = 0
        skipped = 0
        skipped_reasons = {
            'no_options': 0,
            'no_premium_data': 0,
            'below_threshold': 0
        }

        for msg in messages:
            processed += 1

            # 解析交易信息
            trade_info = parse_block_trade_message(msg.text)

            # 提取关键字段
            asset = trade_info.get('asset', 'Unknown')
            exchange = trade_info.get('exchange', 'Unknown')
            options_count = trade_info.get('options_count', 0)
            options_sum = trade_info.get('options_sum', 0)

            # 净权利金相关字段
            premium_paid_usd = trade_info.get('premium_paid_usd', None)
            premium_received_usd = trade_info.get('premium_received_usd', None)
            net_premium_usd = trade_info.get('net_premium_usd', None)
            abs_net_premium_usd = trade_info.get('abs_net_premium_usd', None)
            ref_price_usd = trade_info.get('ref_price_usd', None)

            # 跳过非期权订单
            if options_count == 0:
                skipped += 1
                skipped_reasons['no_options'] += 1
                continue

            # 跳过无法计算净权利金的订单
            if abs_net_premium_usd is None:
                skipped += 1
                skipped_reasons['no_premium_data'] += 1
                print(f"[SKIP] msg_id={msg.message_id} asset={asset} reason=no_premium_data options_count={options_count}")
                continue

            # 可选：筛选最小净权利金绝对值
            if min_abs_net_premium and abs_net_premium_usd < min_abs_net_premium:
                skipped += 1
                skipped_reasons['below_threshold'] += 1
                continue

            # 添加到候选列表
            candidates.append({
                'message_id': msg.message_id,
                'date': msg.date,
                'asset': asset,
                'exchange': exchange,
                'options_count': options_count,
                'options_sum': options_sum,
                'premium_paid_usd': premium_paid_usd,
                'premium_received_usd': premium_received_usd,
                'net_premium_usd': net_premium_usd,
                'abs_net_premium_usd': abs_net_premium_usd,
                'ref_price_usd': ref_price_usd,
                'trade_info': trade_info,
                'message_data': msg.to_dict(),
                'raw_text_snippet': msg.text[:200] + '...' if len(msg.text) > 200 else msg.text
            })

        print(f"[SCAN] 处理完成: processed={processed} candidates={len(candidates)} skipped={skipped}")
        print(f"[SKIP_REASONS] no_options={skipped_reasons['no_options']} no_premium_data={skipped_reasons['no_premium_data']} below_threshold={skipped_reasons['below_threshold']}")
        print()

        # 按 abs_net_premium_usd 降序排序
        candidates.sort(key=lambda x: x['abs_net_premium_usd'], reverse=True)

        return candidates

    finally:
        session.close()


def print_top_candidates(candidates, top_n=5):
    """打印 Top N 候选订单"""
    threshold = config.PREMIUM_USD_THRESHOLD if hasattr(config, 'PREMIUM_USD_THRESHOLD') else 1_000_000

    print(f"=" * 80)
    print(f"Top {top_n} 净权利金绝对值最大的订单")
    print(f"=" * 80)

    if not candidates:
        print("⚠️ 未找到满足条件的订单")
        return

    for i, cand in enumerate(candidates[:top_n], 1):
        abs_net_premium = cand['abs_net_premium_usd']
        net_premium = cand['net_premium_usd']
        premium_paid = cand['premium_paid_usd']
        premium_received = cand['premium_received_usd']
        trigger = "✅ 触发" if abs_net_premium >= threshold else "❌ 未触发"

        # 判断净敞口方向
        direction = "🟢 NET SHORT (收到 > 支付)" if net_premium > 0 else "🔴 NET LONG (支付 > 收到)"

        print(f"\n#{i}. {trigger}")
        print(f"  Message ID: {cand['message_id']}")
        print(f"  时间: {cand['date'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  资产: {cand['asset']} @ {cand['exchange']}")
        print(f"  期权腿数: {cand['options_count']} ({cand['options_sum']:.1f}x)")
        print(f"  {direction}")
        print(f"    - 支付权利金 (Paid):     ${premium_paid:>12,.2f}")
        print(f"    - 收到权利金 (Received): ${premium_received:>12,.2f}")
        print(f"    - 净权利金 (Net):        ${net_premium:>12,.2f}")
        print(f"    - 净权利金绝对值 (Abs):  ${abs_net_premium:>12,.2f}")
        print(f"  币价 (Ref): ${cand['ref_price_usd']:,.2f}" if cand['ref_price_usd'] else "  币价 (Ref): N/A")
        print(f"  阈值: ${threshold:,.0f}")
        print(f"  超出幅度: {((abs_net_premium / threshold - 1) * 100):.1f}%" if abs_net_premium >= threshold else "  未达阈值")
        print(f"  原始消息片段: {cand['raw_text_snippet'][:100]}...")

    print(f"\n" + "=" * 80)


def send_test_alert(candidate, dry_run=False):
    """
    发送测试 Net Premium Alert 邮件（带 🧪 [TEST] 前缀）

    Args:
        candidate: 候选订单字典
        dry_run: 是否为试运行（不实际发送）

    Returns:
        bool: 是否发送成功
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}准备发送测试邮件...")
    print(f"  Message ID: {candidate['message_id']}")
    print(f"  资产: {candidate['asset']}")
    print(f"  净权利金 (Net): ${candidate['net_premium_usd']:,.2f}")
    print(f"  净权利金绝对值 (Abs): ${candidate['abs_net_premium_usd']:,.2f}")
    print(f"  支付权利金 (Paid): ${candidate['premium_paid_usd']:,.2f}")
    print(f"  收到权利金 (Received): ${candidate['premium_received_usd']:,.2f}")

    if dry_run:
        print(f"  [DRY RUN] 跳过实际发送")
        return True

    # 判断预警原因（可能同时触发张数和权利金预警）
    threshold = config.PREMIUM_USD_THRESHOLD if hasattr(config, 'PREMIUM_USD_THRESHOLD') else 1_000_000
    options_sum = candidate['options_sum']
    asset = candidate['asset']

    # 判断张数阈值
    if asset == 'BTC':
        volume_threshold = config.BTC_VOLUME_THRESHOLD  # 200
    elif asset == 'ETH':
        volume_threshold = config.ETH_VOLUME_THRESHOLD  # 5000
    else:
        volume_threshold = 9999999  # 其他资产不触发张数预警

    # 判断两种预警
    volume_trigger = options_sum > volume_threshold
    premium_trigger = candidate['abs_net_premium_usd'] >= threshold

    # 构造 alert_reasons 列表
    reasons = []
    if volume_trigger:
        reasons.append('volume')
    if premium_trigger:
        reasons.append('premium')

    print(f"  预警原因: {', '.join(reasons) if reasons else 'None'}")
    print(f"    - 张数预警: {'✅ 触发' if volume_trigger else '❌ 未触发'} (options_sum={options_sum}, threshold={volume_threshold})")
    print(f"    - 权利金预警: {'✅ 触发' if premium_trigger else '❌ 未触发'} (abs_net_premium={candidate['abs_net_premium_usd']:,.0f}, threshold={threshold})")

    # 发送邮件（合并预警）
    success = send_single_trade_alert_html(
        trade_info=candidate['trade_info'],
        message_data=candidate['message_data'],
        threshold=volume_threshold,
        alert_reasons=reasons,
        lang='zh',
        test_mode=True  # 标记为测试模式（邮件标题带 🧪 [TEST]）
    )

    if success:
        print(f"  ✅ 邮件发送成功")
    else:
        print(f"  ❌ 邮件发送失败")

    return success


def main():
    import argparse
    import pytz

    parser = argparse.ArgumentParser(
        description='验收脚本：净权利金预警（Net Premium Alert）真实历史数据测试',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:

  # 扫描昨天的数据，显示 Top 5
  python verify_net_premium_alert.py --days 1

  # 扫描最近 7 天的数据
  python verify_net_premium_alert.py --days 7

  # 扫描昨天的数据，并发送测试邮件（第1条）
  python verify_net_premium_alert.py --days 1 --send-test

  # 试运行（不实际发送邮件）
  python verify_net_premium_alert.py --days 1 --send-test --dry-run

  # 只显示超过阈值的订单
  python verify_net_premium_alert.py --days 7 --min-premium 1000000

  # 发送多封测试邮件（Top 2）
  python verify_net_premium_alert.py --days 7 --send-test --send-count 2
        """
    )

    parser.add_argument('--days', type=int, default=1,
                       help='扫描最近 N 天的数据（默认: 1）')
    parser.add_argument('--min-premium', type=float, default=None,
                       help='最小净权利金绝对值筛选（默认: 无限制）')
    parser.add_argument('--top', type=int, default=5,
                       help='显示 Top N 订单（默认: 5）')
    parser.add_argument('--send-test', action='store_true',
                       help='发送测试邮件')
    parser.add_argument('--send-count', type=int, default=1,
                       help='发送测试邮件数量（默认: 1，最多 3）')
    parser.add_argument('--dry-run', action='store_true',
                       help='试运行模式（不实际发送邮件）')

    args = parser.parse_args()

    # 计算时间范围
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    end_date = datetime.now(tz)
    start_date = end_date - timedelta(days=args.days)

    # 扫描候选订单
    candidates = scan_net_premium_candidates(
        start_date=start_date,
        end_date=end_date,
        min_abs_net_premium=args.min_premium
    )

    # 打印 Top N
    print_top_candidates(candidates, top_n=args.top)

    # 发送测试邮件（可选）
    if args.send_test:
        if not candidates:
            print("\n⚠️ 未找到候选订单，无法发送测试邮件")
            sys.exit(1)

        # 限制发送数量（最多 3 封）
        send_count = min(args.send_count, 3, len(candidates))

        print(f"\n{'=' * 80}")
        print(f"发送测试邮件（共 {send_count} 封）")
        print(f"{'=' * 80}")

        success_count = 0
        for i in range(send_count):
            print(f"\n--- 测试邮件 #{i+1}/{send_count} ---")
            success = send_test_alert(candidates[i], dry_run=args.dry_run)
            if success:
                success_count += 1

        print(f"\n{'=' * 80}")
        if success_count == send_count:
            print(f"✅ 验收完成：成功发送 {success_count}/{send_count} 封测试邮件")
            sys.exit(0)
        else:
            print(f"⚠️ 部分失败：成功发送 {success_count}/{send_count} 封测试邮件")
            sys.exit(1)
    else:
        print(f"\n💡 提示: 使用 --send-test 参数可以发送测试邮件")
        sys.exit(0)


if __name__ == '__main__':
    main()
