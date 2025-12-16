#!/usr/bin/env python3
"""
配置检查工具
验证所有 Telegram API 配置是否正确
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

import config


def check_api_credentials():
    """检查 API 凭证"""
    print("=" * 60)
    print("检查 Telegram API 凭证")
    print("=" * 60)

    errors = []
    warnings = []

    # 检查 API_ID
    if config.API_ID == '38073635':
        print("✓ API_ID: 38073635 (已配置)")
    else:
        print(f"⚠ API_ID: {config.API_ID} (自定义)")
        warnings.append("API_ID 不是预设值，请确认是否正确")

    # 检查 API_HASH
    if config.API_HASH == '2c78d114834d147f1e46e0cbf9898ef6':
        print(f"✓ API_HASH: {config.API_HASH[:8]}...{config.API_HASH[-4:]} (已配置)")
    else:
        print(f"⚠ API_HASH: {config.API_HASH[:8]}...{config.API_HASH[-4:]} (自定义)")
        warnings.append("API_HASH 不是预设值，请确认是否正确")

    # 检查 PHONE_NUMBER
    if config.PHONE_NUMBER == '+86XXXXXXXXXXX':
        print("✗ PHONE_NUMBER: 未设置")
        errors.append("请在 config.py 中设置你的手机号 PHONE_NUMBER")
    else:
        print(f"✓ PHONE_NUMBER: {config.PHONE_NUMBER[:3]}****{config.PHONE_NUMBER[-4:]}")

    return errors, warnings


def check_target_chat():
    """检查目标群组"""
    print("\n" + "=" * 60)
    print("检查目标群组配置")
    print("=" * 60)

    errors = []

    # 检查 TARGET_CHAT_ID
    if config.TARGET_CHAT_ID == -1001881744197:
        print(f"✓ TARGET_CHAT_ID: {config.TARGET_CHAT_ID}")
        print(f"✓ TARGET_CHAT_NAME: {config.TARGET_CHAT_NAME}")
    else:
        print(f"⚠ TARGET_CHAT_ID: {config.TARGET_CHAT_ID} (自定义)")
        print(f"⚠ TARGET_CHAT_NAME: {config.TARGET_CHAT_NAME}")

    return errors


def check_session_file():
    """检查 Session 文件"""
    print("\n" + "=" * 60)
    print("检查 Session 文件")
    print("=" * 60)

    session_file = f"{config.SESSION_NAME}.session"

    if os.path.exists(session_file):
        print(f"✓ Session 文件存在: {session_file}")
        print("  说明: 已经完成 Telegram 认证")
        return True
    else:
        print(f"⚠ Session 文件不存在: {session_file}")
        print("  说明: 需要首次认证")
        print("  运行: python telegram_client.py")
        return False


def check_database():
    """检查数据库"""
    print("\n" + "=" * 60)
    print("检查数据库")
    print("=" * 60)

    if os.path.exists(config.DB_PATH):
        print(f"✓ 数据库文件存在: {config.DB_PATH}")

        # 获取数据库统计
        try:
            from database import get_session, get_database_stats
            session = get_session()
            try:
                stats = get_database_stats(session)
                print(f"  总消息数: {stats['total_messages']}")
                print(f"  大宗交易数: {stats['total_block_trades']}")
                if stats['latest_message_date']:
                    print(f"  最新消息: {stats['latest_message_date'].strftime('%Y-%m-%d %H:%M:%S')}")
            finally:
                session.close()
        except Exception as e:
            print(f"  ⚠ 无法读取数据库统计: {e}")
    else:
        print(f"⚠ 数据库文件不存在: {config.DB_PATH}")
        print("  说明: 数据库将在首次运行时自动创建")


def check_dependencies():
    """检查依赖"""
    print("\n" + "=" * 60)
    print("检查 Python 依赖")
    print("=" * 60)

    required_packages = [
        'telethon',
        'sqlalchemy',
        'apscheduler',
        'pytz',
        'pandas',
        'python-dotenv'
    ]

    missing = []

    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} (未安装)")
            missing.append(package)

    if missing:
        print(f"\n⚠ 缺少依赖，请运行: uv pip install -r requirements.txt")

    return missing


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Telegram Trade Alert 系统 - 配置检查")
    print("=" * 60)
    print()

    all_errors = []
    all_warnings = []

    # 1. 检查依赖
    missing_deps = check_dependencies()
    if missing_deps:
        all_errors.extend([f"缺少依赖: {dep}" for dep in missing_deps])

    # 2. 检查 API 凭证
    errors, warnings = check_api_credentials()
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # 3. 检查目标群组
    errors = check_target_chat()
    all_errors.extend(errors)

    # 4. 检查 Session 文件
    has_session = check_session_file()

    # 5. 检查数据库
    check_database()

    # 总结
    print("\n" + "=" * 60)
    print("检查总结")
    print("=" * 60)

    if all_errors:
        print("\n❌ 发现错误:")
        for i, error in enumerate(all_errors, 1):
            print(f"  {i}. {error}")

    if all_warnings:
        print("\n⚠️  警告:")
        for i, warning in enumerate(all_warnings, 1):
            print(f"  {i}. {warning}")

    if not all_errors and not all_warnings:
        print("\n✅ 所有配置检查通过！")

    # 下一步建议
    print("\n" + "=" * 60)
    print("下一步操作建议")
    print("=" * 60)

    if all_errors:
        print("\n1. 修复上述错误")
        if "PHONE_NUMBER" in str(all_errors):
            print("   编辑 config.py，设置 PHONE_NUMBER = '+8613800138000'")
        if missing_deps:
            print("   运行: uv pip install -r requirements.txt")
    elif not has_session:
        print("\n1. 首次认证:")
        print("   python telegram_client.py")
        print("\n2. 导出历史数据（可选）:")
        print("   python main.py export")
        print("\n3. 启动系统:")
        print("   python main.py")
    else:
        print("\n配置完成，可以直接运行:")
        print("   python main.py")

    print("\n查看完整文档:")
    print("   - README.md (完整文档)")
    print("   - QUICKSTART.md (快速启动)")
    print("   - CREDENTIALS.md (凭证说明)")
    print()


if __name__ == '__main__':
    main()
