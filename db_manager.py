#!/usr/bin/env python3
"""
数据库管理工具 CLI
提供归档、压缩、统计等数据库维护功能
"""

import argparse
import sys
from database import (
    get_session,
    get_database_stats,
    archive_old_messages,
    vacuum_database,
    ensure_database_health,
    get_db_path
)


def cmd_stats(args):
    """显示数据库统计信息"""
    print("\n" + "=" * 60)
    print("数据库统计信息")
    print("=" * 60)

    session = get_session(test=args.test)
    try:
        stats = get_database_stats(session)

        print(f"\n数据库文件: {get_db_path(test=args.test)}")
        print(f"  总消息数: {stats['total_messages']:,}")
        print(f"  大宗交易数: {stats['total_block_trades']:,}")
        print(f"  大宗交易占比: {stats['total_block_trades']/stats['total_messages']*100:.1f}%" if stats['total_messages'] > 0 else "  大宗交易占比: N/A")
        print(f"  数据库大小: {stats['database_size_mb']} MB")

        if stats['oldest_message_date']:
            print(f"  最早消息: {stats['oldest_message_date'].strftime('%Y-%m-%d %H:%M:%S')}")
        if stats['latest_message_date']:
            print(f"  最新消息: {stats['latest_message_date'].strftime('%Y-%m-%d %H:%M:%S')}")

            # 计算时间跨度
            if stats['oldest_message_date']:
                delta = stats['latest_message_date'] - stats['oldest_message_date']
                print(f"  时间跨度: {delta.days} 天")

        print("\n" + "=" * 60)
    finally:
        session.close()


def cmd_archive(args):
    """归档旧消息"""
    print(f"\n即将归档超过 {args.days} 天的消息...")

    if not args.yes:
        response = input("确认继续？(y/N): ")
        if response.lower() != 'y':
            print("已取消")
            return

    result = archive_old_messages(days=args.days, output_dir=args.output)

    if result['success']:
        print("\n归档成功！")

        # 如果指定了压缩选项，执行压缩
        if args.vacuum:
            print("\n执行数据库压缩...")
            vacuum_database(test=args.test)


def cmd_vacuum(args):
    """压缩数据库文件"""
    vacuum_database(test=args.test)


def cmd_health(args):
    """检查数据库健康状态"""
    print("\n" + "=" * 60)
    print("数据库健康检查")
    print("=" * 60)

    db_path = get_db_path(test=args.test)
    print(f"\n检查数据库: {db_path}\n")

    result = ensure_database_health(db_path)

    if result:
        print("\n✓ 数据库健康")
    else:
        print("\n✗ 数据库存在问题")
        sys.exit(1)

    print("=" * 60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='数据库管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查看统计信息
  python db_manager.py stats

  # 归档超过90天的消息
  python db_manager.py archive --days 90

  # 归档并压缩
  python db_manager.py archive --days 90 --vacuum

  # 压缩数据库
  python db_manager.py vacuum

  # 健康检查
  python db_manager.py health

  # 使用测试数据库
  python db_manager.py stats --test
        """
    )

    # 全局选项
    parser.add_argument('--test', action='store_true',
                       help='使用测试数据库')

    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # stats 命令
    parser_stats = subparsers.add_parser('stats', help='显示数据库统计信息')
    parser_stats.set_defaults(func=cmd_stats)

    # archive 命令
    parser_archive = subparsers.add_parser('archive', help='归档旧消息')
    parser_archive.add_argument('--days', type=int, default=90,
                               help='保留最近多少天的数据 (默认: 90)')
    parser_archive.add_argument('--output', type=str, default=None,
                               help='归档文件输出目录 (默认: archives/)')
    parser_archive.add_argument('--vacuum', action='store_true',
                               help='归档后压缩数据库')
    parser_archive.add_argument('-y', '--yes', action='store_true',
                               help='自动确认，不提示')
    parser_archive.set_defaults(func=cmd_archive)

    # vacuum 命令
    parser_vacuum = subparsers.add_parser('vacuum', help='压缩数据库文件')
    parser_vacuum.set_defaults(func=cmd_vacuum)

    # health 命令
    parser_health = subparsers.add_parser('health', help='检查数据库健康状态')
    parser_health.set_defaults(func=cmd_health)

    # 解析参数
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 执行命令
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n\n已中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
