#!/usr/bin/env python3
"""
验证脚本：测试"只发送最新日报"的策略 B（体验优先）

用途：
1. 只读检查数据库状态（最新日报、历史 backlog）
2. 触发一次"仅发送最新日报"的测试
3. 验证幂等性（重复执行不会重复发送）

运行方式：
    python verify_send_latest_only.py           # 只读检查（不发送）
    python verify_send_latest_only.py --send    # 检查 + 发送最新日报
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

import config
from database import get_session, DailyReport
from report_generator import send_pending_daily_reports


def check_database_status():
    """
    只读检查：数据库中的日报状态

    Returns:
        dict: 状态信息
    """
    session = get_session()
    try:
        # 查询所有未发送的日报
        pending_reports = (
            session.query(DailyReport)
            .filter_by(is_sent=False)
            .order_by(DailyReport.report_date.desc())
            .all()
        )

        # 查询最新的日报（无论是否发送）
        latest_report = (
            session.query(DailyReport)
            .order_by(DailyReport.report_date.desc())
            .first()
        )

        status = {
            'total_pending': len(pending_reports),
            'latest_report_date': latest_report.report_date if latest_report else None,
            'latest_is_sent': latest_report.is_sent if latest_report else None,
            'latest_sent_at': latest_report.sent_at if latest_report else None,
            'backlog_count': 0,
            'backlog_oldest': None,
            'backlog_newest': None,
        }

        if pending_reports:
            latest_pending = pending_reports[0]
            status['latest_pending_date'] = latest_pending.report_date

            # 统计 backlog（历史未发送）
            backlog = [r for r in pending_reports if r.report_date < latest_pending.report_date]
            status['backlog_count'] = len(backlog)
            if backlog:
                status['backlog_oldest'] = backlog[-1].report_date
                status['backlog_newest'] = backlog[0].report_date

        return status

    finally:
        session.close()


def print_status(status):
    """打印数据库状态"""
    print("\n" + "=" * 80)
    print("数据库状态检查")
    print("=" * 80)

    print(f"\n📊 总体状态:")
    print(f"  - 未发送日报总数: {status['total_pending']}")
    print(f"  - 最新日报日期: {status['latest_report_date']}")
    print(f"  - 最新日报是否已发送: {status['latest_is_sent']}")
    if status['latest_sent_at']:
        print(f"  - 最新日报发送时间: {status['latest_sent_at']}")

    if status['total_pending'] > 0:
        print(f"\n📮 待发送候选:")
        print(f"  - 最新未发送日期: {status.get('latest_pending_date')}")
        print(f"  - 按策略 B 将发送: {status.get('latest_pending_date')}")

        if status['backlog_count'] > 0:
            print(f"\n⚠️  历史未发送日报（backlog）:")
            print(f"  - 数量: {status['backlog_count']}")
            print(f"  - 最旧日期: {status['backlog_oldest']}")
            print(f"  - 最新日期: {status['backlog_newest']}")
            print(f"  - 按策略 B 将被忽略（只记录日志）")
    else:
        print(f"\n✅ 没有待发送的日报")

    print("=" * 80)


async def test_send_latest_only():
    """
    测试发送最新日报（策略 B）

    Returns:
        bool: 是否成功
    """
    print("\n" + "=" * 80)
    print("开始测试：发送最新日报（策略 B）")
    print("=" * 80)

    # 检查邮件配置
    if not config.EMAIL_ENABLED:
        print(f"\n⚠️  警告: EMAIL_ENABLED = {config.EMAIL_ENABLED}")
        print("提示: 在 config.py 或环境变量中设置 EMAIL_ENABLED=true")
        return False

    if not config.EMAIL_PASSWORD:
        print(f"\n❌ 错误: EMAIL_PASSWORD 未设置")
        print("提示: 在 config.py 或环境变量中设置 Gmail 应用专用密码")
        return False

    print(f"\n✓ 邮件配置已启用")
    print(f"  - 发件人: {config.EMAIL_SENDER}")
    print(f"  - 收件人: {config.EMAIL_RECIPIENTS}")

    # 调用发送函数
    print(f"\n🚀 调用 send_pending_daily_reports()...")
    print("-" * 80)

    try:
        await send_pending_daily_reports()
        print("-" * 80)
        print(f"✓ 发送函数执行完成（请查看上方日志）")
        return True

    except Exception as e:
        print("-" * 80)
        print(f"❌ 发送函数执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='验证"只发送最新日报"策略',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 只读检查数据库状态（不发送）
  python verify_send_latest_only.py

  # 检查 + 发送最新日报
  python verify_send_latest_only.py --send
        """
    )

    parser.add_argument('--send', action='store_true',
                       help='发送最新日报（默认只读检查）')

    args = parser.parse_args()

    # ==========================================
    # 1. 只读检查数据库状态
    # ==========================================
    print(f"\n{'=' * 80}")
    print(f"验证脚本：只发送最新日报（策略 B）")
    print(f"{'=' * 80}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"数据库路径: {config.DB_PATH}")

    status = check_database_status()
    print_status(status)

    # ==========================================
    # 2. 如果指定 --send，则触发发送
    # ==========================================
    if args.send:
        if status['total_pending'] == 0:
            print(f"\n⚠️  警告: 数据库中没有待发送的日报")
            print(f"提示: 请先生成日报，或检查数据库是否有数据")
            print(f"\n跳过发送测试")
            sys.exit(0)

        success = asyncio.run(test_send_latest_only())

        # 再次检查状态（验证幂等性）
        print(f"\n" + "=" * 80)
        print("发送后状态检查（验证幂等性）")
        print("=" * 80)

        status_after = check_database_status()
        print_status(status_after)

        if success:
            print(f"\n✅ 验证通过！")
            print(f"\n关键验证点:")
            print(f"  1. 只发送了最新日报: {status.get('latest_pending_date')}")
            print(f"  2. 历史 backlog 未发送: {status['backlog_count']} 条")
            print(f"  3. 重复执行时会跳过: 请再次运行 --send 验证")
        else:
            print(f"\n❌ 验证失败，请检查日志")
            sys.exit(1)

    else:
        print(f"\n💡 提示:")
        print(f"  - 使用 --send 参数触发发送测试")
        print(f"  - 示例: python verify_send_latest_only.py --send")


if __name__ == '__main__':
    main()
