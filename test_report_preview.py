"""
基于测试数据生成报告预览
不依赖数据库，直接使用 tests/raw_messages/messages_last_30_days.json
"""

import json
import os
from datetime import datetime, timedelta
import pytz
from report_generator import (
    extract_spot_prices,
    calculate_trade_statistics,
    extract_top_trades,
    parse_block_trade_message
)
from image_report_generator import generate_image_report


# 模拟 Message 对象
class MockMessage:
    def __init__(self, data):
        self.message_id = data['message_id']
        self.date = datetime.strptime(data['date'], '%Y-%m-%d %H:%M:%S')
        self.date = pytz.timezone('Asia/Shanghai').localize(self.date)
        self.text = data['text']
        self.is_block_trade = '#block' in data['text'].lower()


def generate_test_report():
    """
    基于测试数据生成报告预览
    """
    print("=" * 60)
    print("基于测试数据生成报告预览...")
    print("=" * 60)

    # 1. 读取测试数据
    test_data_path = 'tests/raw_messages/messages_last_30_days.json'
    with open(test_data_path, 'r', encoding='utf-8') as f:
        messages_data = json.load(f)

    print(f"✓ 读取到 {len(messages_data)} 条测试消息")

    # 2. 转换为 MockMessage 对象
    all_messages = [MockMessage(msg) for msg in messages_data]

    # 3. 筛选最近24小时的消息（取最后一天的数据）
    tz = pytz.timezone('Asia/Shanghai')
    end_date = all_messages[-1].date if all_messages else datetime.now(tz)
    start_date = end_date - timedelta(hours=24)

    filtered_messages = [
        msg for msg in all_messages
        if start_date <= msg.date <= end_date
    ]

    print(f"✓ 筛选出最近24小时的消息: {len(filtered_messages)} 条")
    print(f"  时间范围: {start_date} 到 {end_date}")

    # 4. 提取现货价格
    spot_prices = extract_spot_prices(filtered_messages)
    print(f"✓ 提取现货价格: BTC=${spot_prices['btc']}, ETH=${spot_prices['eth']}")

    # 5. 获取大宗交易
    block_trades = [msg for msg in filtered_messages if msg.is_block_trade]
    print(f"✓ 大宗交易数: {len(block_trades)} 条")

    # 6. 统计大宗交易
    trade_stats = calculate_trade_statistics(block_trades)
    print(f"✓ 统计: 总={trade_stats['total']}, BTC={trade_stats['btc_count']}, ETH={trade_stats['eth_count']}")

    # 7. 提取 Top 3 交易
    top_trades = extract_top_trades(block_trades, limit=3)
    print(f"✓ 提取 Top 3:")
    print(f"  BTC 按金额: {len(top_trades['btc_by_amount'])} 条")
    print(f"  BTC 按数量: {len(top_trades['btc_by_volume'])} 条")
    print(f"  ETH 按金额: {len(top_trades['eth_by_amount'])} 条")
    print(f"  ETH 按数量: {len(top_trades['eth_by_volume'])} 条")

    # 8. 生成报告数据
    report_data = {
        'generated_at': datetime.now(tz).isoformat(),
        'time_range': {
            'start': start_date.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'end': end_date.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'timezone': 'Asia/Shanghai'
        },
        'spot_prices': spot_prices,
        'trade_statistics': trade_stats,
        'top_trades': top_trades,
        'total_messages': len(filtered_messages),
        'total_block_trades': len(block_trades)
    }

    # 9. 生成图片报告
    output_file = generate_image_report(report_data, output_dir='tests/reports_preview')

    print(f"\n✓ 报告图片已保存到: {output_file}")
    print(f"  文件大小: {os.path.getsize(output_file) / 1024:.2f} KB")

    # 11. 显示一些样本数据
    print("\n" + "=" * 60)
    print("样本数据预览")
    print("=" * 60)

    if top_trades['btc_by_amount']:
        sample = top_trades['btc_by_amount'][0]
        print(f"\nBTC Top 1 (按金额):")
        print(f"  策略: {sample['strategy']}")
        print(f"  金额: ${sample['amount_usd']:,.2f}")
        print(f"  数量: {sample['volume']}x")
        print(f"  合约: {sample['contract']}")
        print(f"  IV: {sample['iv']}")
        print(f"  Delta: {sample['greeks']['delta']}")

    print("\n" + "=" * 60)
    print("✓ 测试完成！图片报告已生成")
    print("=" * 60)


if __name__ == '__main__':
    generate_test_report()
