"""
主程序
整合所有组件：Telegram 客户端、消息监听、定时任务
"""

import asyncio
import signal
import sys
import os
import shutil
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
import config
from database import init_database, get_database_stats, get_session
from message_listener import MessageListener
from scheduler import TaskScheduler


def check_telegram_session_health(session_path):
    """
    检查 Telegram session 文件健康状态

    Args:
        session_path: session 文件路径（不含 .session 后缀）

    Returns:
        True: session 健康
        False: session 损坏（需要重新登录）
    """
    session_file = f"{session_path}.session"
    journal_file = f"{session_file}-journal"
    wal_file = f"{session_file}-wal"
    shm_file = f"{session_file}-shm"

    # 如果 session 文件不存在，说明是首次运行
    if not os.path.exists(session_file):
        print(f"ℹ️ Telegram session 文件不存在，将进行首次登录")
        print(f"   Session 路径: {session_file}")
        # 清理残留文件
        for cleanup_file in [journal_file, wal_file, shm_file]:
            if os.path.exists(cleanup_file):
                try:
                    os.remove(cleanup_file)
                    print(f"✓ 已清理残留文件: {os.path.basename(cleanup_file)}")
                except Exception as e:
                    print(f"⚠️ 清理失败: {e}")
        return True

    # 检查是否存在残留的 DELETE mode journal 文件（说明需要转换为 WAL）
    journal_warning = False
    if os.path.exists(journal_file):
        journal_size = os.path.getsize(journal_file)
        if journal_size > 0:
            print(f"⚠️ 检测到 DELETE mode journal 文件: {journal_file} ({journal_size} bytes)")
            journal_warning = True

    try:
        # 尝试打开 session 的 SQLite 数据库
        conn = sqlite3.connect(session_file, timeout=5)
        cursor = conn.cursor()

        # 执行完整性检查
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()

        # 检查 journal mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]

        conn.close()

        if result and result[0] == 'ok':
            # 如果检测到 DELETE mode journal，转换为 WAL mode
            if journal_warning or journal_mode == 'delete':
                print(f"⚙️ 将 session 转换为 WAL mode 以提高稳定性...")
                try:
                    # 转换为 WAL mode
                    conn = sqlite3.connect(session_file)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL")
                    new_mode = cursor.fetchone()[0]
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA wal_autocheckpoint=100")
                    conn.commit()
                    conn.close()

                    print(f"✓ Journal mode 已转换: {journal_mode} → {new_mode}")

                    # 清理旧的 journal 文件
                    if os.path.exists(journal_file):
                        os.remove(journal_file)
                        print(f"✓ 已清理旧 journal 文件")
                except Exception as e:
                    print(f"⚠️ WAL 转换失败: {e}")
                    print(f"   Session 可能不稳定")
            elif journal_mode == 'wal':
                print(f"✓ Session 已使用 WAL mode")

            print(f"✓ Telegram session 健康检查通过: {session_file}")
            return True
        else:
            # Session 数据库损坏
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] session_health_check_failed integrity='{result[0] if result else 'FAILED'}'")
            print(f"\n{'='*70}")
            print(f"❌ Telegram Session 文件损坏")
            print(f"{'='*70}")
            print(f"Session 文件: {session_file}")
            print(f"完整性检查结果: {result[0] if result else 'FAILED'}")

            # 备份损坏的 session 文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{session_file}.corrupt.{timestamp}"

            try:
                shutil.move(session_file, backup_path)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] session_isolated backup_path={backup_path}")
                print(f"\n✓ 已将损坏的 session 文件备份到:")
                print(f"   {backup_path}")

                # 同时备份 journal 文件（如果存在）
                journal_file = f"{session_file}-journal"
                if os.path.exists(journal_file):
                    shutil.move(journal_file, f"{backup_path}-journal")
                    print(f"✓ 已备份 session journal 文件")

            except Exception as backup_error:
                print(f"\n⚠️ 备份 session 文件失败: {backup_error}")

            # 打印恢复步骤
            print(f"\n📋 下一步操作：")
            print(f"{'='*70}")
            print(f"Session 文件已损坏并被移除，需要重新登录 Telegram。")
            print(f"\n请按以下步骤操作：")
            print(f"  1. 停止服务:")
            print(f"     pm2 stop telegram-report")
            print(f"\n  2. 重新认证 Telegram:")
            print(f"     cd /home/kunkka/projects/dailyreport")
            print(f"     python auto_auth.py")
            print(f"     (按提示输入手机号和验证码)")
            print(f"\n  3. 重启服务:")
            print(f"     pm2 restart telegram-report")
            print(f"{'='*70}\n")
            return False

    except sqlite3.DatabaseError as e:
        # Session 数据库错误
        print(f"\n{'='*70}")
        print(f"❌ Telegram Session 数据库错误")
        print(f"{'='*70}")
        print(f"Session 文件: {session_file}")
        print(f"错误: {e}")

        # 备份并移除
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{session_file}.corrupt.{timestamp}"

        try:
            if os.path.exists(session_file):
                shutil.move(session_file, backup_path)
                print(f"\n✓ 已备份损坏文件到: {backup_path}")
        except Exception as backup_error:
            print(f"\n⚠️ 备份失败: {backup_error}")

        print(f"\n📋 请按阶段1诊断报告中的步骤重新认证")
        print(f"{'='*70}\n")
        return False

    except Exception as e:
        print(f"\n⚠️ Telegram session 检查失败: {e}")
        return False


class TelegramReportBot:
    """Telegram 报告机器人"""

    def __init__(self):
        """初始化机器人"""
        self.client = None
        self.listener = None
        self.scheduler = None
        self.running = False

    async def setup(self):
        """设置机器人组件"""
        print("\n" + "=" * 60)
        print("Telegram Trade Alert 报告系统")
        print("=" * 60)

        # 0. 健康检查（Session 和数据库）
        print("\n[0/5] 启动前健康检查...")

        # 检查 Telegram session
        if not check_telegram_session_health(config.SESSION_NAME):
            print("\n❌ Telegram session 健康检查失败")
            print("⚠️ 进程将退出，请按提示重新认证后再启动")
            sys.exit(1)  # 明确失败退出

        # 1. 验证配置
        print("\n[1/5] 验证配置...")
        if not config.validate_config():
            raise Exception("配置验证失败，请检查 config.py")
        print("✓ 配置验证通过")

        # 打印邮件路由配置（启动时必须打印）
        config.print_email_config()

        # 2. 初始化数据库（内部会调用 ensure_database_health）
        print("\n[2/5] 初始化数据库...")
        try:
            init_database()
        except RuntimeError as e:
            # 数据库健康检查失败
            print(f"\n❌ 数据库初始化失败: {e}")
            print("⚠️ 进程将退出，请检查数据库状态")
            sys.exit(1)  # 明确失败退出

        # 显示数据库统计
        session = get_session()
        try:
            stats = get_database_stats(session)
            print(f"  数据库统计:")
            print(f"    总消息数: {stats['total_messages']}")
            print(f"    大宗交易数: {stats['total_block_trades']}")
            if stats['latest_message_date']:
                print(f"    最新消息: {stats['latest_message_date'].strftime('%Y-%m-%d %H:%M:%S')}")
            if stats['oldest_message_date']:
                print(f"    最早消息: {stats['oldest_message_date'].strftime('%Y-%m-%d %H:%M:%S')}")
        finally:
            session.close()

        # 3. 创建 Telegram 客户端
        print("\n[3/5] 连接 Telegram...")
        self.client = TelegramClient(
            config.SESSION_NAME,
            config.API_ID,
            config.API_HASH
        )

        await self.client.start(phone=config.PHONE_NUMBER)

        # 获取当前用户信息
        me = await self.client.get_me()
        print(f"✓ 已登录: {me.first_name} (@{me.username})")

        # 结构化连接日志
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] connected user={me.username or me.first_name} user_id={me.id} chat_id={config.TARGET_CHAT_ID}")

        # 注册断线事件处理器
        @self.client.on(events.Raw)
        async def handle_disconnect(event):
            """处理 Telegram 断线事件"""
            if hasattr(event, '_disconnected') and event._disconnected:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] disconnected reason='connection lost'")

        # 4. 设置消息监听器
        print("\n[4/5] 设置消息监听器...")
        self.listener = MessageListener(self.client)
        self.listener.setup()

        # 5. 设置定时任务
        print("\n[5/5] 设置定时任务...")
        self.scheduler = TaskScheduler()
        self.scheduler.setup()
        self.scheduler.start()

        print("\n" + "=" * 60)
        print("✓ 系统初始化完成！")
        print("=" * 60)

    async def run(self):
        """运行机器人（带错误恢复）"""
        self.running = True

        print("\n系统正在运行...")
        print("按 Ctrl+C 停止")
        print("-" * 60)

        try:
            # 保持运行
            await self.client.run_until_disconnected()

        except KeyboardInterrupt:
            print("\n收到停止信号...")

        except sqlite3.DatabaseError as e:
            # 捕获 SQLite 错误（通常来自 session）
            error_msg = str(e)
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] sqlite_error={error_msg}")

            if 'malformed' in error_msg.lower() or 'corrupt' in error_msg.lower():
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] session_corrupt detected reason='database malformed'")
                print("⚠️ 检测到 session 数据库损坏，尝试自动修复...")

                # 备份损坏的 session
                session_file = f"{config.SESSION_NAME}.session"
                if os.path.exists(session_file):
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = f"{session_file}.corrupt.{timestamp}"
                    try:
                        shutil.move(session_file, backup_path)
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] session_isolated backup_path={backup_path}")
                        print(f"✓ 已备份损坏的 session: {backup_path}")

                        # 同时备份 journal
                        journal_file = f"{session_file}-journal"
                        if os.path.exists(journal_file):
                            shutil.move(journal_file, f"{backup_path}-journal")
                            print(f"✓ 已备份 journal 文件")

                    except Exception as backup_error:
                        print(f"⚠️ 备份失败: {backup_error}")

                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] graceful_exit reason='session_corrupt'")
                print("\n📋 Session 已损坏，进程将退出")
                print("请运行: python auto_auth.py 重新认证后再启动")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] unknown_sqlite_error reason='{error_msg}'")
                print(f"⚠️ 未知的 SQLite 错误，进程将退出")

        except Exception as e:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] unexpected_error={e}")
            import traceback
            traceback.print_exc()

        finally:
            await self.shutdown()

    async def shutdown(self):
        """关闭机器人（永不崩溃）"""
        from datetime import datetime
        try:
            if self.scheduler:
                self.scheduler.stop()

            if self.listener:
                self.listener.close()

            if self.client:
                await self.client.disconnect()

            self.running = False
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SYSTEM] shutdown_ok")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SYSTEM] shutdown_error error={e}")

    def print_status(self):
        """打印系统状态"""
        print("\n" + "=" * 60)
        print("系统状态")
        print("=" * 60)

        if self.listener:
            stats = self.listener.get_stats()
            print(f"消息监听:")
            print(f"  总消息: {stats['total_messages']}")
            print(f"  大宗交易: {stats['block_trades']}")
            print(f"  警报发送: {stats['alerts_sent']}")

        if self.scheduler:
            print(f"\n定时任务:")
            self.scheduler.list_jobs()

        print("=" * 60)


async def main():
    """主函数（带指数退避重启机制）"""
    import time

    # 退避配置
    retry_count = 0
    max_retries = 5
    base_delay = 1  # 基础延迟（秒）
    max_delay = 30  # 最大延迟（秒）

    # 创建机器人实例
    bot = TelegramReportBot()

    # 设置信号处理
    def signal_handler(sig, frame):
        """处理 Ctrl+C 信号"""
        print("\n收到停止信号，正在关闭...")
        asyncio.create_task(bot.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while retry_count < max_retries:
        try:
            # 如果是重试，先等待（指数退避）
            if retry_count > 0:
                delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [RETRY] attempt={retry_count}/{max_retries} delay={delay}s")
                await asyncio.sleep(delay)

            # 设置系统
            await bot.setup()

            # 运行系统（成功运行说明重置重试计数）
            retry_count = 0
            await bot.run()

            # 正常退出
            break

        except SystemExit as e:
            # 明确的退出（如 session 损坏），不重试
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EXIT] code={e.code}")
            await bot.shutdown()
            sys.exit(e.code)

        except KeyboardInterrupt:
            # 用户中断，不重试
            print("\n收到用户中断信号...")
            await bot.shutdown()
            break

        except Exception as e:
            retry_count += 1
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] retry={retry_count}/{max_retries}")
            print(f"✗ 系统错误: {e}")

            # 计算下次重试的退避时间
            if retry_count < max_retries:
                next_delay = min(base_delay * (2 ** retry_count), max_delay)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TG] reconnecting reason='{error_type}: {error_msg[:100]}' backoff_s={next_delay}")

            import traceback
            traceback.print_exc()

            await bot.shutdown()

            if retry_count >= max_retries:
                print(f"\n❌ 达到最大重试次数 ({max_retries})，进程退出")
                sys.exit(1)


def run_history_export():
    """运行历史数据导出（独立工具）"""
    from history_export import main as export_main
    print("=" * 60)
    print("历史数据导出工具")
    print("=" * 60)
    asyncio.run(export_main())


def run_test_report():
    """运行测试报告生成（独立工具）"""
    from report_generator import generate_daily_report
    print("=" * 60)
    print("测试报告生成")
    print("=" * 60)
    asyncio.run(generate_daily_report())


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'export':
            # 运行历史数据导出
            run_history_export()

        elif command == 'report':
            # 运行测试报告
            run_test_report()

        elif command == 'status':
            # 显示系统状态
            print("系统状态查询功能（需要系统运行中）")
            print("请使用主程序运行系统")

        else:
            print("未知命令:", command)
            print("\n可用命令:")
            print("  python main.py          - 运行主程序（实时监听 + 定时报告）")
            print("  python main.py export   - 导出历史数据（30天）")
            print("  python main.py report   - 生成测试报告")

    else:
        # 运行主程序
        asyncio.run(main())
