#!/usr/bin/env python3
"""
错误处理和重试机制
添加指数退避，防止 PM2 重启风暴
"""

import time
from datetime import datetime
from functools import wraps
import sqlite3
from sqlalchemy.exc import OperationalError, DatabaseError


class ExponentialBackoff:
    """指数退避管理器"""

    def __init__(self, initial_delay=1.0, max_delay=30.0, multiplier=2.0):
        """
        初始化指数退避

        Args:
            initial_delay: 初始延迟（秒）
            max_delay: 最大延迟（秒）
            multiplier: 延迟倍数
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.current_delay = initial_delay
        self.failure_count = 0

    def wait(self):
        """执行等待"""
        if self.failure_count > 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKOFF] waiting delay_s={self.current_delay:.1f} failures={self.failure_count}")
            time.sleep(self.current_delay)

            # 增加延迟
            self.current_delay = min(self.current_delay * self.multiplier, self.max_delay)

    def record_failure(self):
        """记录失败"""
        self.failure_count += 1

    def reset(self):
        """重置（成功后）"""
        if self.failure_count > 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [BACKOFF] reset after_failures={self.failure_count}")
        self.current_delay = self.initial_delay
        self.failure_count = 0


# 全局退避管理器
db_write_backoff = ExponentialBackoff(initial_delay=1.0, max_delay=30.0)


def is_db_write_error(error):
    """
    判断是否为数据库写入错误

    Args:
        error: 异常对象

    Returns:
        bool: 是否为数据库写入错误
    """
    error_str = str(error).lower()

    # SQLite 写入错误关键词
    db_write_keywords = [
        'readonly database',
        'database is locked',
        'database disk image is malformed',
        'unable to open database',
        'attempt to write a readonly database'
    ]

    return any(keyword in error_str for keyword in db_write_keywords)


def handle_db_write_error(func):
    """
    装饰器：处理数据库写入错误，应用指数退避

    Usage:
        @handle_db_write_error
        def my_db_write_function():
            # 数据库写入操作
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            db_write_backoff.reset()  # 成功后重置
            return result
        except (OperationalError, DatabaseError, sqlite3.OperationalError) as e:
            if is_db_write_error(e):
                db_write_backoff.record_failure()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DBWRITE_FAIL] error={e} backoff_s={db_write_backoff.current_delay:.1f}")
                db_write_backoff.wait()
                raise  # 重新抛出异常，让上层决定是否重试
            else:
                raise  # 非写入错误，直接抛出

    return wrapper


async def handle_db_write_error_async(func):
    """
    装饰器：处理数据库写入错误（异步版本）

    Usage:
        @handle_db_write_error_async
        async def my_async_db_write_function():
            # 数据库写入操作
            pass
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            db_write_backoff.reset()  # 成功后重置
            return result
        except (OperationalError, DatabaseError, sqlite3.OperationalError) as e:
            if is_db_write_error(e):
                db_write_backoff.record_failure()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DBWRITE_FAIL] error={e} backoff_s={db_write_backoff.current_delay:.1f}")
                import asyncio
                await asyncio.sleep(db_write_backoff.current_delay)
                raise  # 重新抛出异常，让上层决定是否重试
            else:
                raise  # 非写入错误，直接抛出

    return wrapper


def log_exception(error, context=""):
    """
    记录异常日志（结构化格式）

    Args:
        error: 异常对象
        context: 上下文描述
    """
    error_type = type(error).__name__
    error_msg = str(error)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] context={context} type={error_type} msg={error_msg}")

    # 如果是数据库错误，额外标记
    if is_db_write_error(error):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] category=db_write_error")


if __name__ == '__main__':
    """测试指数退避"""
    print("测试指数退避机制...")

    backoff = ExponentialBackoff(initial_delay=0.5, max_delay=5.0)

    for i in range(10):
        print(f"\n尝试 {i+1}:")
        backoff.record_failure()
        backoff.wait()

    print("\n✓ 测试完成")
