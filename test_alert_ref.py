"""
测试预警邮件中的 Ref 价格显示
验证修复后的 Ref 提取逻辑
"""

from datetime import datetime
import asyncio
from report_generator import parse_block_trade_message
from email_sender import send_single_trade_alert_html

# 测试消息：包含 Ref 价格的真实格式
test_message_text = """**✅OPENED LONG BTC CALL (250.0x):**
🟢 Bought 250.0x 🔶 BTC-19DEC25-91000-C 📈 at 0.0234 ₿ ($2,456.78)
Total Bought: 58.5000 ₿ ($614.20K), **IV**: 52.34%, **Ref**: $87232.15

📖 **Risks**: Δ: -47,933.19, Γ: 1.31, ν: 23,456.78, Θ: -1,234.56, ρ: 567.89

__Deribit__ __#block__
"""

def test_ref_extraction():
    """测试 Ref 提取逻辑"""
    print("\n" + "=" * 60)
    print("测试 Ref 提取逻辑")
    print("=" * 60)

    # 解析消息
    trade_info = parse_block_trade_message(test_message_text)

    # 打印关键字段
    print(f"\n解析结果：")
    print(f"  资产: {trade_info['asset']}")
    print(f"  合约: {trade_info['contract']}")
    print(f"  数量: {trade_info['volume']}x")
    print(f"  交易所: {trade_info['exchange']}")
    print(f"  spot_price (字符串): {trade_info.get('spot_price', 'N/A')}")
    print(f"  ref_price_usd (数值): {trade_info.get('ref_price_usd', None)}")

    # 验证 Ref 提取
    if trade_info.get('ref_price_usd') is not None:
        print(f"\n✅ Ref 提取成功：${trade_info['ref_price_usd']:,.2f}")
    else:
        print(f"\n❌ Ref 提取失败：spot_price = {trade_info.get('spot_price', 'N/A')}")

    return trade_info

def test_alert_email(trade_info):
    """测试预警邮件发送"""
    print("\n" + "=" * 60)
    print("测试预警邮件发送")
    print("=" * 60)

    # 构造消息数据
    message_data = {
        'message_id': 999999,
        'date': datetime.now().isoformat(),
        'text': test_message_text,
        'is_block_trade': True
    }

    # 发送测试邮件（中文模板）
    print(f"\n发送测试邮件...")
    success = send_single_trade_alert_html(
        trade_info=trade_info,
        message_data=message_data,
        threshold=200,
        lang='zh',
        test_mode=True  # 邮件标题添加 【TEST】 标记
    )

    if success:
        print(f"\n✅ 测试邮件发送成功！")
        print(f"  主题: 【TEST】单笔大宗期权预警 - BTC - ...")
        print(f"  现货价应显示: $87,232.15（不是 N/A）")
        print(f"\n请检查邮箱收件！")
    else:
        print(f"\n❌ 测试邮件发送失败")

    return success

if __name__ == '__main__':
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TEST_ALERT] start")

    # 步骤1：测试 Ref 提取
    trade_info = test_ref_extraction()

    # 步骤2：测试邮件发送
    test_alert_email(trade_info)

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TEST_ALERT] end")
    print("=" * 60)
