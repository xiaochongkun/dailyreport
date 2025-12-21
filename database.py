"""
数据库模型和初始化 - 优化版
使用 SQLAlchemy 管理 SQLite 数据库

优化内容：
1. 添加索引优化查询性能
2. 启用 WAL 模式提高并发稳定性
3. 数据库健康检测和自动修复
4. 测试数据库隔离支持
5. 历史数据归档机制
6. 会话文件路径分离
"""

from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Index, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
import os
import json
import shutil
import sqlite3

# 创建基类
Base = declarative_base()


class Message(Base):
    """
    Telegram 消息存储表

    字段说明：
    - id: 主键，自增
    - message_id: Telegram 消息ID（唯一）
    - date: 消息时间戳（有索引）
    - text: 消息内容
    - is_block_trade: 是否为大宗交易（有索引）
    - created_at: 记录创建时间
    """
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, unique=True, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)  # 单列索引
    text = Column(Text, nullable=True)
    is_block_trade = Column(Boolean, default=False, index=True)  # 单列索引
    created_at = Column(DateTime, default=datetime.utcnow)

    # 定义联合索引（用于日报查询优化）
    __table_args__ = (
        Index('idx_messages_date_block', 'date', 'is_block_trade'),
        Index('idx_messages_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<Message(id={self.id}, message_id={self.message_id}, date={self.date}, is_block={self.is_block_trade})>"

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'message_id': self.message_id,
            'date': self.date.isoformat() if self.date else None,
            'text': self.text,
            'is_block_trade': self.is_block_trade,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DailyReport(Base):
    """
    每日报告存储表

    字段说明：
    - id: 主键，自增
    - report_date: 报告日期（格式：YYYY-MM-DD）
    - start_time: 统计开始时间
    - end_time: 统计结束时间
    - total_messages: 总消息数
    - total_block_trades: 总大宗交易数
    - btc_trade_count: BTC 交易笔数
    - btc_total_volume: BTC 总交易量
    - eth_trade_count: ETH 交易笔数
    - eth_total_volume: ETH 总交易量
    - btc_spot_price: BTC 现货价格
    - eth_spot_price: ETH 现货价格
    - report_data: 完整报告数据（JSON 格式）
    - html_content: HTML 邮件内容
    - is_sent: 是否已发送邮件
    - sent_at: 邮件发送时间
    - created_at: 报告生成时间
    """
    __tablename__ = 'daily_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False)
    total_messages = Column(Integer, default=0)
    total_block_trades = Column(Integer, default=0)
    btc_trade_count = Column(Integer, default=0)
    btc_total_volume = Column(Integer, default=0)
    eth_trade_count = Column(Integer, default=0)
    eth_total_volume = Column(Integer, default=0)
    btc_spot_price = Column(String(20), nullable=True)
    eth_spot_price = Column(String(20), nullable=True)
    report_data = Column(Text, nullable=True)  # JSON string
    html_content = Column(Text, nullable=True)
    is_sent = Column(Boolean, default=False, index=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DailyReport(id={self.id}, date={self.report_date}, sent={self.is_sent})>"

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'report_date': self.report_date,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_messages': self.total_messages,
            'total_block_trades': self.total_block_trades,
            'btc_trade_count': self.btc_trade_count,
            'btc_total_volume': self.btc_total_volume,
            'eth_trade_count': self.eth_trade_count,
            'eth_total_volume': self.eth_total_volume,
            'btc_spot_price': self.btc_spot_price,
            'eth_spot_price': self.eth_spot_price,
            'is_sent': self.is_sent,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# 全局引擎和会话工厂
engines = {}  # 存储不同数据库的引擎
session_factories = {}  # 存储不同数据库的会话工厂


def get_db_path(test=False):
    """
    获取数据库文件路径

    ⚠️ 修正：优先使用 config.DB_PATH（支持本地磁盘路径）

    Args:
        test: 是否使用测试数据库

    Returns:
        数据库文件路径
    """
    import config

    if test:
        db_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, 'reports_test.db')
    else:
        # 使用 config.DB_PATH（已配置为本地磁盘路径）
        db_path = config.DB_PATH

        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        return db_path


def ensure_database_health(db_path):
    """
    数据库健康检测（只读模式 - 不自动修复）

    ⚠️ 修正：严格遵守「只告警+备份+退出」约束
    - 若 integrity_check 非 ok：只告警+备份副本+抛异常（不自动删除/重建）
    - 管理员必须手动确认后续操作

    Args:
        db_path: 数据库文件路径

    Returns:
        True: 数据库健康
        False: 数据库损坏（需手动处理）

    Raises:
        RuntimeError: 数据库损坏且需要人工介入
    """
    from datetime import datetime
    import shutil

    if not os.path.exists(db_path):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] new_db path={db_path}")
        return True

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()

        # 执行完整性检查
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()

        if result and result[0] == 'ok':
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] integrity_check status=ok")
            conn.close()
            return True
        else:
            # 数据库损坏 - 只告警和备份，不自动重建
            integrity_msg = result[0] if result else 'FAILED'
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] corrupt_detected integrity={integrity_msg}")

            conn.close()

            # 备份损坏文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{db_path}.corrupt.{timestamp}"
            shutil.copy2(db_path, backup_path)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] backup_created path={backup_path}")

            # ⚠️ 修正：不自动删除/重建，抛出异常要求人工介入
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] halt reason=database_corrupt action_required=manual_recovery")
            raise RuntimeError(f"Database corrupt (integrity={integrity_msg}), manual recovery required. Backup: {backup_path}")

    except sqlite3.OperationalError as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] access_error error={e}")
        return False

    except Exception as e:
        if isinstance(e, RuntimeError) and 'manual recovery required' in str(e):
            raise  # 重新抛出 RuntimeError
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] health_check_error error={e}")
        import traceback
        traceback.print_exc()
        return False


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """
    在每次连接时设置 SQLite PRAGMA
    启用 WAL 模式和优化性能参数

    ⚠️ 修正：
    - 本地磁盘：使用 WAL 模式（高并发）
    - busy_timeout 使用 config.DB_BUSY_TIMEOUT（默认 10秒）
    """
    import config
    cursor = dbapi_conn.cursor()

    # 使用 WAL 模式（仅在本地磁盘，不在 NFS）
    # WAL 模式支持更高的并发性
    cursor.execute(f"PRAGMA journal_mode = {config.DB_JOURNAL_MODE}")

    # 设置同步模式为 NORMAL（在 WAL 模式下足够安全）
    cursor.execute("PRAGMA synchronous = NORMAL")

    # 设置缓存大小（负数表示 KB，这里设置为 10MB）
    cursor.execute("PRAGMA cache_size = -10000")

    # 设置临时存储为内存
    cursor.execute("PRAGMA temp_store = MEMORY")

    # 启用外键约束
    cursor.execute("PRAGMA foreign_keys = ON")

    # 设置 busy_timeout（从 config 读取，默认 10秒）
    cursor.execute(f"PRAGMA busy_timeout = {config.DB_BUSY_TIMEOUT}")

    cursor.close()


def init_database(test=False):
    """
    初始化数据库 + journal_mode 硬化

    Args:
        test: 是否使用测试数据库

    Returns:
        数据库引擎
    """
    from datetime import datetime
    import config

    # 获取数据库路径
    db_path = get_db_path(test=test)

    # 健康检查（如果数据库损坏会自动修复）
    if not ensure_database_health(db_path):
        raise RuntimeError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] init_failed path={db_path}")

    # 创建数据库引擎
    db_key = 'test' if test else 'prod'

    engine = create_engine(
        f'sqlite:///{db_path}',
        echo=False,
        connect_args={'check_same_thread': False}
    )

    # 创建所有表（包括索引）
    Base.metadata.create_all(engine)

    # 设置 journal_mode（默认 DELETE，可通过 config 覆盖）
    target_mode = getattr(config, 'DB_JOURNAL_MODE', 'DELETE').upper()

    conn = engine.raw_connection()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA journal_mode={target_mode}")
    actual_mode = cursor.fetchone()[0]
    conn.close()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] journal_mode target={target_mode} actual={actual_mode}")

    # 创建会话工厂
    session_factory = sessionmaker(bind=engine)

    # 保存到全局字典
    engines[db_key] = engine
    session_factories[db_key] = session_factory

    db_type = "测试数据库" if test else "生产数据库"
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DB] init_ok type={db_type} path={db_path}")

    return engine


def get_session(test=False):
    """
    获取数据库会话

    Args:
        test: 是否使用测试数据库

    Returns:
        数据库会话对象

    使用示例：
        # 使用生产数据库
        session = get_session()

        # 使用测试数据库
        session = get_session(test=True)

        try:
            # 数据库操作
            pass
        finally:
            session.close()
    """
    db_key = 'test' if test else 'prod'

    if db_key not in session_factories:
        init_database(test=test)

    return session_factories[db_key]()


def save_message(session, message_id, date, text, is_block_trade=False):
    """
    保存消息到数据库

    Args:
        session: 数据库会话
        message_id: Telegram 消息ID
        date: 消息时间
        text: 消息内容
        is_block_trade: 是否为大宗交易

    Returns:
        Message 对象，如果消息已存在则返回 None
    """
    try:
        # 检查消息是否已存在
        existing = session.query(Message).filter_by(message_id=message_id).first()
        if existing:
            print(f"⚠ 消息 {message_id} 已存在，跳过")
            return None

        # 创建新消息记录
        message = Message(
            message_id=message_id,
            date=date,
            text=text,
            is_block_trade=is_block_trade
        )

        session.add(message)
        session.commit()

        print(f"✓ 消息已保存: ID={message_id}, Block={is_block_trade}")
        return message

    except Exception as e:
        session.rollback()
        print(f"✗ 保存消息失败: {e}")
        raise


def get_messages_by_date_range(session, start_date, end_date):
    """
    查询指定时间范围内的消息

    Args:
        session: 数据库会话
        start_date: 开始时间
        end_date: 结束时间

    Returns:
        消息列表
    """
    return session.query(Message).filter(
        Message.date >= start_date,
        Message.date <= end_date
    ).order_by(Message.date.desc()).all()


def get_block_trades_by_date_range(session, start_date, end_date):
    """
    查询指定时间范围内的大宗交易
    利用联合索引 (date, is_block_trade) 优化查询

    Args:
        session: 数据库会话
        start_date: 开始时间
        end_date: 结束时间

    Returns:
        大宗交易消息列表
    """
    return session.query(Message).filter(
        Message.date >= start_date,
        Message.date <= end_date,
        Message.is_block_trade == True
    ).order_by(Message.date.desc()).all()


def get_database_stats(session):
    """
    获取数据库统计信息

    Args:
        session: 数据库会话

    Returns:
        统计信息字典
    """
    total_messages = session.query(Message).count()
    total_blocks = session.query(Message).filter_by(is_block_trade=True).count()

    latest_message = session.query(Message).order_by(Message.date.desc()).first()
    oldest_message = session.query(Message).order_by(Message.date.asc()).first()

    # 获取数据库文件大小
    db_path = get_db_path(test=False)
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    return {
        'total_messages': total_messages,
        'total_block_trades': total_blocks,
        'latest_message_date': latest_message.date if latest_message else None,
        'oldest_message_date': oldest_message.date if oldest_message else None,
        'database_size_mb': round(db_size / (1024 * 1024), 2)
    }


def archive_old_messages(days=90, output_dir=None):
    """
    归档并清理旧消息

    功能：
    1. 查询 date < today - days 的消息
    2. 导出为 JSON 文件
    3. 从数据库中删除

    Args:
        days: 保留最近多少天的数据（默认90天）
        output_dir: 归档文件输出目录（默认为 archives/）

    Returns:
        归档信息字典 {
            'archived_count': int,
            'archive_file': str,
            'success': bool
        }
    """
    # 设置归档目录
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), 'archives')

    os.makedirs(output_dir, exist_ok=True)

    # 计算截止日期
    cutoff_date = datetime.now() - timedelta(days=days)

    print("\n" + "=" * 60)
    print(f"开始归档旧消息...")
    print(f"  保留天数: {days} 天")
    print(f"  截止日期: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    session = get_session()

    try:
        # 查询需要归档的消息
        old_messages = session.query(Message).filter(
            Message.date < cutoff_date
        ).order_by(Message.date.asc()).all()

        if not old_messages:
            print("✓ 没有需要归档的消息")
            return {
                'archived_count': 0,
                'archive_file': None,
                'success': True
            }

        print(f"✓ 找到 {len(old_messages)} 条待归档消息")

        # 转换为字典列表
        messages_data = [msg.to_dict() for msg in old_messages]

        # 生成归档文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_file = os.path.join(output_dir, f'messages_archive_{timestamp}.json')

        # 导出为 JSON
        with open(archive_file, 'w', encoding='utf-8') as f:
            json.dump({
                'archived_at': datetime.now().isoformat(),
                'cutoff_date': cutoff_date.isoformat(),
                'message_count': len(messages_data),
                'messages': messages_data
            }, f, ensure_ascii=False, indent=2)

        print(f"✓ 已导出到: {archive_file}")

        # 删除已归档的消息（事务保护）
        for msg in old_messages:
            session.delete(msg)

        session.commit()

        print(f"✓ 已从数据库删除 {len(old_messages)} 条旧消息")

        print("\n" + "=" * 60)
        print("✓ 归档完成！")
        print(f"  归档数量: {len(old_messages)} 条")
        print(f"  归档文件: {archive_file}")
        print("=" * 60)

        return {
            'archived_count': len(old_messages),
            'archive_file': archive_file,
            'success': True
        }

    except Exception as e:
        session.rollback()
        print(f"✗ 归档失败: {e}")
        return {
            'archived_count': 0,
            'archive_file': None,
            'success': False,
            'error': str(e)
        }

    finally:
        session.close()


def vacuum_database(test=False):
    """
    压缩数据库文件（回收空间）
    在归档后调用可以减小数据库文件大小

    Args:
        test: 是否操作测试数据库
    """
    db_path = get_db_path(test=test)

    try:
        conn = sqlite3.connect(db_path)
        print(f"\n开始压缩数据库: {db_path}")

        # 获取压缩前大小
        before_size = os.path.getsize(db_path) / (1024 * 1024)

        conn.execute("VACUUM")
        conn.close()

        # 获取压缩后大小
        after_size = os.path.getsize(db_path) / (1024 * 1024)
        saved = before_size - after_size

        print(f"✓ 数据库压缩完成")
        print(f"  压缩前: {before_size:.2f} MB")
        print(f"  压缩后: {after_size:.2f} MB")
        print(f"  节省: {saved:.2f} MB ({saved/before_size*100:.1f}%)")

    except Exception as e:
        print(f"✗ 数据库压缩失败: {e}")


if __name__ == '__main__':
    """测试数据库模块"""
    print("=" * 60)
    print("数据库模块测试")
    print("=" * 60)

    # 测试 1: 初始化生产数据库
    print("\n[测试 1] 初始化生产数据库")
    init_database(test=False)

    # 测试 2: 初始化测试数据库
    print("\n[测试 2] 初始化测试数据库")
    init_database(test=True)

    # 测试 3: 获取生产数据库统计
    print("\n[测试 3] 生产数据库统计")
    session = get_session(test=False)
    try:
        stats = get_database_stats(session)
        print(f"  总消息数: {stats['total_messages']}")
        print(f"  大宗交易数: {stats['total_block_trades']}")
        print(f"  最新消息: {stats['latest_message_date']}")
        print(f"  最早消息: {stats['oldest_message_date']}")
        print(f"  数据库大小: {stats['database_size_mb']} MB")
    finally:
        session.close()

    # 测试 4: 测试健康检查
    print("\n[测试 4] 健康检查测试")
    db_path = get_db_path(test=False)
    ensure_database_health(db_path)

    print("\n" + "=" * 60)
    print("✓ 所有测试完成！")
    print("=" * 60)
