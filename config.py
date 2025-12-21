"""
配置文件
管理 Telegram API 凭证、目标群组和其他系统参数
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()

# ============================================
# Telegram API 配置
# ============================================
API_ID = os.getenv('API_ID', '38073635')
API_HASH = os.getenv('API_HASH', '2c78d114834d147f1e46e0cbf9898ef6')
PHONE_NUMBER = os.getenv('PHONE_NUMBER', '+85264915979')  # 请替换为你的手机号

# Session 文件路径
# 重要：使用本地磁盘而不是 NFS，避免 SQLite 文件锁定问题
# NFS 不支持 SQLite 所需的文件锁定机制，会导致频繁的 "database disk image is malformed" 错误
SESSION_DIR = os.getenv('SESSION_DIR', '/tmp/telegram-sessions-kunkka')
SESSION_NAME = os.path.join(SESSION_DIR, os.getenv('SESSION_NAME', 'telegram_session'))

# ============================================
# 目标群组配置
# ============================================
TARGET_CHAT_ID = int(os.getenv('TARGET_CHAT_ID', '-1001881744197'))  # SignalPlus Trade Alert
TARGET_CHAT_NAME = 'SignalPlus Trade Alert'

# ============================================
# 数据库配置
# ============================================
# ⚠️ 重要：生产数据库必须在本地磁盘，不能在 NFS 上
# SQLite 在 NFS 上的文件锁机制不稳定，会导致 "readonly database" 错误
DB_PATH_OVERRIDE = os.getenv('DB_PATH_OVERRIDE', '/tmp/dailyreport_kunkka/reports.db')
DB_DIR = os.path.join(os.path.dirname(__file__), 'data')
DB_PATH = DB_PATH_OVERRIDE if DB_PATH_OVERRIDE else os.path.join(DB_DIR, 'reports.db')

# SQLite 配置
DB_JOURNAL_MODE = os.getenv('DB_JOURNAL_MODE', 'WAL')  # WAL 模式（仅在本地磁盘）
DB_BUSY_TIMEOUT = int(os.getenv('DB_BUSY_TIMEOUT', '10000'))  # 10秒超时

# ============================================
# 历史数据导出配置
# ============================================
HISTORY_EXPORT_DIR = os.path.join(os.path.dirname(__file__), 'history')
HISTORY_DAYS = int(os.getenv('HISTORY_DAYS', '30'))  # 导出最近 30 天的历史数据

# ============================================
# 日报配置
# ============================================
# 日报时区（东八区）
REPORT_TIMEZONE = 'Asia/Shanghai'

# 日报触发时间（东八区 16:00）
REPORT_HOUR = int(os.getenv('REPORT_HOUR', '16'))
REPORT_MINUTE = int(os.getenv('REPORT_MINUTE', '0'))

# 日报时间范围（过去24小时）
REPORT_WINDOW_HOURS = int(os.getenv('REPORT_WINDOW_HOURS', '24'))

# ============================================
# 邮件配置
# ============================================
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'

# SMTP 服务器配置（Gmail）
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'

# Gmail 账号配置
EMAIL_SENDER = os.getenv('EMAIL_SENDER', 'kunkka@signalplus.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')  # Gmail 应用专用密码

# 收件人配置
EMAIL_RECIPIENTS = os.getenv('EMAIL_RECIPIENTS', 'kunkka@signalplus.com').split(',')

# 邮件发送时间配置
EMAIL_SEND_TIME = os.getenv('EMAIL_SEND_TIME', '16:05')  # 邮件发送时间（日报生成后5分钟）

# ============================================
# 阈值预警配置（单笔大宗交易）
# ============================================
# 注意：这是「单笔订单」的 volume 阈值，且仅针对 MONITORED_EXCHANGE 交易所
# ✅ OPTIONS ONLY：只对期权（OPTIONS）触发预警，PERPETUAL/FUTURES 一律跳过
VOLUME_ALERT_ENABLED = os.getenv('VOLUME_ALERT_ENABLED', 'true').lower() == 'true'
MONITORED_EXCHANGE = os.getenv('MONITORED_EXCHANGE', 'Deribit')  # 监控的交易所

# 正式环境阈值（OPTIONS ONLY）
BTC_VOLUME_THRESHOLD = int(os.getenv('BTC_VOLUME_THRESHOLD', '200'))   # BTC options volume > 200
ETH_VOLUME_THRESHOLD = int(os.getenv('ETH_VOLUME_THRESHOLD', '5000'))  # ETH options volume > 5000

# 测试模式（用于测试邮件，ETH 阈值临时降低）
ALERT_TEST_MODE = os.getenv('ALERT_TEST_MODE', 'false').lower() == 'true'
ETH_VOLUME_THRESHOLD_TEST = int(os.getenv('ETH_VOLUME_THRESHOLD_TEST', '1000'))  # 测试模式下 ETH 阈值

# ============================================
# 日报模板版本
# ============================================
REPORT_TEMPLATE_VERSION = os.getenv('REPORT_TEMPLATE_VERSION', 'v1')  # v1 或 v2

# ============================================
# 日志配置
# ============================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')

# ============================================
# 标签配置
# ============================================
BLOCK_TRADE_TAG = '#block'  # 大宗交易标签
SPOT_PRICE_TAG = '🏷️ Spot Prices'  # 现货价格标签

# ============================================
# 配置验证
# ============================================
def validate_config():
    """验证配置是否完整"""
    errors = []

    if API_ID == '38073635' and API_HASH == '2c78d114834d147f1e46e0cbf9898ef6':
        print("✓ 使用预设的 API 凭证")
    else:
        print("✓ 使用自定义 API 凭证")

    if PHONE_NUMBER == '+86XXXXXXXXXXX':
        errors.append("请在 config.py 中设置你的手机号 PHONE_NUMBER")

    if TARGET_CHAT_ID == -1001881744197:
        print(f"✓ 监听群组: {TARGET_CHAT_NAME} (ID: {TARGET_CHAT_ID})")

    if errors:
        print("\n⚠ 配置警告:")
        for error in errors:
            print(f"  - {error}")
        return False

    return True


def print_config():
    """打印当前配置（脱敏）"""
    print("=" * 60)
    print("当前配置:")
    print("=" * 60)
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH[:8]}...{API_HASH[-4:] if len(API_HASH) > 12 else ''}")
    print(f"PHONE_NUMBER: {PHONE_NUMBER[:3]}****{PHONE_NUMBER[-4:] if len(PHONE_NUMBER) > 7 else '****'}")
    print(f"TARGET_CHAT_ID: {TARGET_CHAT_ID}")
    print(f"TARGET_CHAT_NAME: {TARGET_CHAT_NAME}")
    print(f"SESSION_NAME: {SESSION_NAME}")
    print(f"DB_PATH: {DB_PATH}")
    print(f"HISTORY_EXPORT_DIR: {HISTORY_EXPORT_DIR}")
    print(f"HISTORY_DAYS: {HISTORY_DAYS}")
    print(f"REPORT_TIMEZONE: {REPORT_TIMEZONE}")
    print(f"REPORT_TIME: {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}")
    print(f"REPORT_WINDOW_HOURS: {REPORT_WINDOW_HOURS}")
    print(f"EMAIL_ENABLED: {EMAIL_ENABLED}")
    print("=" * 60)


if __name__ == '__main__':
    """测试配置"""
    print_config()
    print()
    if validate_config():
        print("\n✓ 配置验证通过！")
    else:
        print("\n✗ 配置验证失败，请修正上述问题")
