# 测试环境使用说明

## 📁 目录结构

```
tests/
├── README_TEST.md           # 本文件
├── raw_messages/            # 存放最近30天的原始消息（JSON格式）
├── reports_preview/         # 存放日报预览HTML
└── alerts_preview/          # 存放预警模板预览HTML
```

## 🚀 快速开始

### 1. 导出测试数据（最近30天消息）

在项目根目录执行：

```bash
cd /home/kunkka/projects/dailyreport

# 激活虚拟环境（如果未激活）
source .venv/bin/activate

# 导出最近30天的消息
python export_test_data.py

# 或者自定义天数（例如最近7天）
python export_test_data.py 7
```

### 2. 执行过程

脚本会自动：
1. ✅ 创建测试目录结构（如果不存在）
2. ✅ 连接 Telegram 客户端（使用现有 session）
3. ✅ 从 SignalPlus Trade Alert 群组拉取消息
4. ✅ 使用 Asia/Shanghai 时区
5. ✅ 过滤掉空消息
6. ✅ 保存为 JSON 格式：`tests/raw_messages/messages_last_30_days.json`

### 3. 输出示例

```
==============================================================
开始导出测试数据...
==============================================================
时间范围: 2025-11-11 11:46:00 CST
        到 2025-12-11 11:46:00 CST
目标群组: SignalPlus Trade Alert (ID: -1001881744197)
保存路径: /home/kunkka/projects/dailyreport/tests/raw_messages/messages_last_30_days.json

✓ 已登录: 张三 (@username)

✓ 成功连接到群组: SignalPlus Trade Alert

正在拉取消息...
  已拉取 100 条消息...
  已拉取 200 条消息...
  ...

✓ 共拉取 456 条有效消息（已过滤空消息）

✓ 数据已保存到: /home/kunkka/projects/dailyreport/tests/raw_messages/messages_last_30_days.json
  文件大小: 234.56 KB

==============================================================
数据统计
==============================================================
总消息数: 456
时间跨度: 2025-11-11 12:00:00 到 2025-12-11 11:45:00
包含 #block 标签: 23 条

==============================================================
示例消息（前3条）
==============================================================

[1] ID: 123456 | 时间: 2025-11-11 12:00:00
    内容: 🏷️ Spot Prices
BTC: $45,123.45
ETH: $2,345.67...

[2] ID: 123457 | 时间: 2025-11-11 12:30:00
    内容: #block BTC Call Option
Strategy: Long Call
Notional: $5.2M...

[3] ID: 123458 | 时间: 2025-11-11 13:00:00
    内容: ETH Put Option
Strategy: Protective Put...

✓ 客户端已断开连接

==============================================================
✓ 测试数据导出完成！
==============================================================

接下来可以：
  1. 查看导出的 JSON 文件
  2. 开始设计日报模板
  3. 开始设计预警模板
```

## 📊 JSON 数据格式

```json
[
  {
    "message_id": 123456,
    "date": "2025-12-10 12:30:00",
    "text": "🏷️ Spot Prices\nBTC: $45,123.45\nETH: $2,345.67"
  },
  {
    "message_id": 123457,
    "date": "2025-12-10 13:00:00",
    "text": "#block BTC Call Option\nStrategy: Long Call\nNotional: $5.2M\n..."
  }
]
```

### 字段说明

- `message_id`: Telegram 消息唯一 ID
- `date`: 消息时间（东八区，格式：YYYY-MM-DD HH:MM:SS）
- `text`: 消息原文（已去除首尾空白）

## 📝 注意事项

1. **网络连接**
   - 确保能够访问 Telegram API
   - 如果连接失败，检查网络代理配置

2. **认证会话**
   - 使用现有的 `telegram_session.session` 文件
   - 如果 session 过期，脚本会提示重新认证

3. **数据量**
   - 30天通常会有几百到几千条消息
   - 导出时间约 10-30 秒（取决于消息数量）

4. **时区处理**
   - 所有时间均转换为 Asia/Shanghai (CST/东八区)
   - 确保系统已安装 pytz 库

5. **空消息过滤**
   - 自动跳过图片、视频、文件等纯媒体消息
   - 只保存包含文本内容的消息

## 🔍 查看导出数据

```bash
# 查看 JSON 文件（使用 jq 美化输出）
cat tests/raw_messages/messages_last_30_days.json | jq '.[0:3]'

# 统计消息数量
cat tests/raw_messages/messages_last_30_days.json | jq 'length'

# 查找包含 #block 的消息
cat tests/raw_messages/messages_last_30_days.json | jq '.[] | select(.text | contains("#block"))'
```

## 🛠️ 常见问题

### Q: 提示 "Session file not found"
**A:** 先运行 `python telegram_client.py` 完成首次认证

### Q: 导出的消息数量为 0
**A:** 检查：
  1. 时间范围是否合理（默认30天）
  2. 群组 ID 是否正确
  3. 账号是否有权限查看该群组

### Q: 如何重新导出数据？
**A:** 直接重新运行脚本即可，会覆盖旧文件

### Q: 可以导出其他群组的消息吗？
**A:** 暂不支持，当前仅用于测试 SignalPlus Trade Alert 群组

## 🎯 下一步

完成数据导出后，可以继续进行：

1. **日报模板设计**
   - 创建 HTML 模板
   - 设计数据展示格式
   - 测试报告预览

2. **预警模板设计**
   - 设计实时预警格式
   - 提取大宗交易信息
   - 测试预警预览

---

**最后更新**: 2025-12-11
