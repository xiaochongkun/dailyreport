#!/usr/bin/env python3
"""
验收脚本：扫描历史数据，查找满足权利金阈值的候选订单

STEP 4：验收（必须用真实历史数据，不允许模拟）

功能：
1. 扫描给定时间窗口内的历史 block trade 消息
2. 计算每笔订单的 options_premium_usd_sum
3. 输出 Top 5 premium_usd_sum 最大的订单
4. 可选：对其中 1 条订单发送测试 Premium Alert 邮件
"""

import sys
import os
from datetime import datetime, timedelta
import config
from database import get_session, Message
from report_generator import parse_block_trade_message
from email_sender import send_premium_alert_html


def scan_premium_candidates(start_date, end_date, min_premium=None):
    """
    扫描历史数据，查找高权利金订单

    Args:
        start_date: 开始时间（datetime）
        end_date: 结束时间（datetime）
        min_premium: 最小权利金（可选，用于筛选）

    Returns:
        List[dict]: 订单列表（按 premium_usd_sum 降序）
    """
    print(f"=" * 80)
    print(f"权利金预警候选订单扫描")
    print(f"=" * 80)
    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M')} ~ {end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"最小权利金: ${min_premium:,.0f}" if min_premium else "最小权利金: 无限制")
    print(f"阈值参考: ${config.PREMIUM_USD_THRESHOLD:,.0f}")
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

        for msg in messages:
            processed += 1

            # 解析交易信息
            trade_info = parse_block_trade_message(msg.text)

            # 提取关键字段
            asset = trade_info.get('asset', 'Unknown')
            exchange = trade_info.get('exchange', 'Unknown')
            options_count = trade_info.get('options_count', 0)
            options_sum = trade_info.get('options_sum', 0)
            options_premium_usd_sum = trade_info.get('options_premium_usd_sum', None)
            ref_price_usd = trade_info.get('ref_price_usd', None)

            # 跳过非期权订单
            if options_count == 0:
                skipped += 1
                continue

            # 跳过无法计算权利金的订单
            if options_premium_usd_sum is None:
                skipped += 1
                print(f"[SKIP] msg_id={msg.message_id} asset={asset} reason=no_premium_data options_count={options_count}")
                continue

            # 可选：筛选最小权利金
            if min_premium and options_premium_usd_sum < min_premium:
                skipped += 1
                continue

            # 添加到候选列表
            candidates.append({
                'message_id': msg.message_id,
                'date': msg.date,
                'asset': asset,
                'exchange': exchange,
                'options_count': options_count,
                'options_sum': options_sum,
                'options_premium_usd_sum': options_premium_usd_sum,
                'ref_price_usd': ref_price_usd,
                'trade_info': trade_info,
                'message_data': msg.to_dict()
            })

        print(f"[SCAN] 处理完成: processed={processed} candidates={len(candidates)} skipped={skipped}")
        print()

        # 按 premium_usd_sum 降序排序
        candidates.sort(key=lambda x: x['options_premium_usd_sum'], reverse=True)

        return candidates

    finally:
        session.close()


def print_top_candidates(candidates, top_n=5):
    """打印 Top N 候选订单"""
    print(f"=" * 80)
    print(f"Top {top_n} 权利金最大的订单")
    print(f"=" * 80)

    if not candidates:
        print("⚠️ 未找到满足条件的订单")
        return

    for i, cand in enumerate(candidates[:top_n], 1):
        premium_usd = cand['options_premium_usd_sum']
        threshold = config.PREMIUM_USD_THRESHOLD
        trigger = "✅ 触发" if premium_usd > threshold else "❌ 未触发"

        print(f"\n#{i}. {trigger}")
        print(f"  Message ID: {cand['message_id']}")
        print(f"  时间: {cand['date'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  资产: {cand['asset']} @ {cand['exchange']}")
        print(f"  期权腿数: {cand['options_count']} ({cand['options_sum']:.1f}x)")
        print(f"  总权利金: ${premium_usd:,.2f}")
        print(f"  币价 (Ref): ${cand['ref_price_usd']:,.2f}" if cand['ref_price_usd'] else "  币价 (Ref): N/A")
        print(f"  阈值: ${threshold:,.0f}")
        print(f"  超出幅度: {((premium_usd / threshold - 1) * 100):.1f}%" if premium_usd > threshold else "  未达阈值")

    print(f"\n" + "=" * 80)


def send_test_alert(candidate, dry_run=False):
    """
    发送测试 Premium Alert 邮件

    Args:
        candidate: 候选订单字典
        dry_run: 是否为试运行（不实际发送）
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}准备发送测试邮件...")
    print(f"  Message ID: {candidate['message_id']}")
    print(f"  资产: {candidate['asset']}")
    print(f"  总权利金: ${candidate['options_premium_usd_sum']:,.2f}")

    if dry_run:
        print(f"  [DRY RUN] 跳过实际发送")
        return True

    # 发送邮件
    success = send_premium_alert_html(
        trade_info=candidate['trade_info'],
        message_data=candidate['message_data'],
        premium_usd_sum=candidate['options_premium_usd_sum'],
        threshold=config.PREMIUM_USD_THRESHOLD,
        lang='zh',
        test_mode=True  # 标记为测试模式
    )

    if success:
        print(f"  ✅ 邮件发送成功")
    else:
        print(f"  ❌ 邮件发送失败")

    return success


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='验收脚本：扫描历史数据，查找满足权利金阈值的候选订单',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:

  # 扫描昨天的数据，显示 Top 5
  python verify_premium_alert_candidate.py --days 1

  # 扫描最近 7 天的数据
  python verify_premium_alert_candidate.py --days 7

  # 扫描昨天的数据，并发送测试邮件（第1条）
  python verify_premium_alert_candidate.py --days 1 --send-test

  # 试运行（不实际发送邮件）
  python verify_premium_alert_candidate.py --days 1 --send-test --dry-run

  # 只显示超过阈值的订单
  python verify_premium_alert_candidate.py --days 7 --min-premium 1000000
        """
    )

    parser.add_argument('--days', type=int, default=1,
                       help='扫描最近 N 天的数据（默认: 1）')
    parser.add_argument('--min-premium', type=float, default=None,
                       help='最小权利金筛选（默认: 无限制）')
    parser.add_argument('--top', type=int, default=5,
                       help='显示 Top N 订单（默认: 5）')
    parser.add_argument('--send-test', action='store_true',
                       help='发送测试邮件（使用第1条订单）')
    parser.add_argument('--dry-run', action='store_true',
                       help='试运行模式（不实际发送邮件）')

    args = parser.parse_args()

    # 计算时间范围
    import pytz
    tz = pytz.timezone(config.REPORT_TIMEZONE)
    end_date = datetime.now(tz)
    start_date = end_date - timedelta(days=args.days)

    # 扫描候选订单
    candidates = scan_premium_candidates(
        start_date=start_date,
        end_date=end_date,
        min_premium=args.min_premium
    )

    # 打印 Top N
    print_top_candidates(candidates, top_n=args.top)

    # 发送测试邮件（可选）
    if args.send_test:
        if not candidates:
            print("\n⚠️ 未找到候选订单，无法发送测试邮件")
            sys.exit(1)

        # 使用第1条订单（权利金最大）
        top_candidate = candidates[0]

        print(f"\n{'=' * 80}")
        print(f"发送测试邮件")
        print(f"{'=' * 80}")

        success = send_test_alert(top_candidate, dry_run=args.dry_run)

        if success:
            print(f"\n✅ 验收完成")
            sys.exit(0)
        else:
            print(f"\n❌ 验收失败")
            sys.exit(1)
    else:
        print(f"\n💡 提示: 使用 --send-test 参数可以发送测试邮件")
        sys.exit(0)


if __name__ == '__main__':
    main()
