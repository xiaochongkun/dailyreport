#!/usr/bin/env python3
"""
SQLite 健康检查脚本
"""
import sqlite3
import os
from datetime import datetime

def check_sqlite_health(file_path):
    """检查单个 SQLite 文件的健康状态"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"[{timestamp}] [CHECK] file={file_path} integrity=NOT_EXIST journal_mode=N/A err=File does not exist")
        return

    # 检查文件是否可读
    if not os.access(file_path, os.R_OK):
        print(f"[{timestamp}] [CHECK] file={file_path} integrity=NO_ACCESS journal_mode=N/A err=File not accessible")
        return

    try:
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()

        # 运行 integrity_check
        try:
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            integrity = "OK" if integrity_result == "ok" else integrity_result
        except Exception as e:
            integrity = "ERROR"
            integrity_err = str(e)

        # 获取 journal_mode
        try:
            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
        except Exception as e:
            journal_mode = "ERROR"
            journal_err = str(e)

        conn.close()

        # 输出结果
        if integrity == "OK":
            print(f"[{timestamp}] [CHECK] file={file_path} integrity={integrity} journal_mode={journal_mode} err=None")
        else:
            err_msg = integrity_err if integrity == "ERROR" else integrity
            print(f"[{timestamp}] [CHECK] file={file_path} integrity={integrity} journal_mode={journal_mode} err={err_msg}")

    except Exception as e:
        print(f"[{timestamp}] [CHECK] file={file_path} integrity=ERROR journal_mode=N/A err={str(e)}")

if __name__ == '__main__':
    print("=== SQLITE HEALTH CHECK ===\n")

    # 检查 reports.db
    reports_db = "/home/kunkka/projects/dailyreport/data/reports.db"
    check_sqlite_health(reports_db)

    # 检查 Telethon session
    session_db = "/tmp/telegram-sessions-kunkka/telegram_session.session"
    check_sqlite_health(session_db)

    print("\n=== HEALTH CHECK COMPLETE ===")
