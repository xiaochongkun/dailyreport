# 中文预警邮件模板测试总结

## 📋 修复概要

已成功在现有预警邮件模板中添加中文支持，实现：
- ✅ **测试专用开关**：通过 `lang='zh'` 和 `test_mode=True` 参数切换中文模板
- ✅ **不影响生产**：仅修改现有函数参数，不新增独立模板文件
- ✅ **OPTIONS ONLY**：保持期权过滤规则
- ✅ **历史数据测试**：使用 reports.db 真实数据（2025-12-11 16:00 → 2025-12-12 16:00）
- ✅ **发送成功**：已发送 2 封【TEST】中文预警邮件（BTC + ETH）

---

## 🔧 改动文件

### 1. **email_sender.py**

修改了 `send_single_trade_alert_html()` 函数，增加语言切换支持：

**改动位置：** 第 373-561 行

**关键改动：**

```python
def send_single_trade_alert_html(
    trade_info: dict,
    message_data: dict,
    threshold: int,
    lang: str = 'en',      # 新增：语言参数
    test_mode: bool = False # 新增：测试模式
) -> bool:
```

**中文模板特征：**
1. 邮件主题：`【TEST】单笔大宗期权预警 - BTC/ETH - <时间> - Deribit`
2. 页面标题：`🚨 单笔大宗期权预警`
3. 分段结构：
   - 📊 资产 / 交易所 / 时间
   - 📈 期权腿信息 (Options Legs)
   - 📉 非期权腿 (Non-Options Legs) - 显示"无"
   - ⚠️ 风险提示 (Risks) - 显示"暂无"
   - 📝 原始消息 (Raw Text)
4. 字段中文化：资产、交易所、时间、合约、方向、数量、价格、IV、现货价、Greeks
5. 不显示 msg_id（按用户要求隐藏）

**调用方式：**
```python
# 英文模板（默认，生产环境）
send_single_trade_alert_html(trade_info, message_data, threshold)

# 中文测试模板
send_single_trade_alert_html(
    trade_info,
    message_data,
    threshold,
    lang='zh',        # 切换到中文
    test_mode=True    # 添加【TEST】标记
)
```

---

### 2. **send_test_alert_emails.py**（新增）

创建测试脚本，用于发送中文预警邮件：

**功能：**
1. 从 reports.db 查询历史数据（2025-12-11 16:00 → 2025-12-12 16:00）
2. 筛选 OPTIONS ONLY 交易（instrument_type=OPTIONS）
3. 找到最大的 BTC 和 ETH OPTIONS 交易
4. 调用 `send_single_trade_alert_html()` 发送中文测试邮件

**使用方法：**
```bash
source .venv/bin/activate && python3 send_test_alert_emails.py
```

**输出示例：**
```
======================================================================
中文预警邮件测试脚本
======================================================================

[配置检查]
  EMAIL_ENABLED: True
  EMAIL_SENDER: zaxandxck@gmail.com
  EMAIL_PASSWORD: 已设置
  EMAIL_RECIPIENTS: kunkka@signalplus.com
  MONITORED_EXCHANGE: Deribit
  BTC_VOLUME_THRESHOLD: 200
  ETH_VOLUME_THRESHOLD: 5000

[数据范围]
  开始: 2025-12-11 16:00:00 CST
  结束: 2025-12-12 16:00:00 CST

[查询历史数据]
查询到 176 条 block trade 消息
  BTC OPTIONS: 116 笔
  ETH OPTIONS: 48 笔
  最大 BTC OPTIONS: 500.0x (msg_id=340715)
  最大 ETH OPTIONS: 1000.0x (msg_id=340690)

======================================================================
测试结果汇总
======================================================================
  BTC: ✅ 成功
  ETH: ✅ 成功

总计: 2/2 封邮件发送成功
```

---

## ✅ 验证结果

### **测试执行（2025-12-16）**

```bash
$ source .venv/bin/activate && python3 send_test_alert_emails.py
```

**结果：**
- ✅ 成功查询到 176 条 block trade 消息
- ✅ 筛选出 116 笔 BTC OPTIONS，48 笔 ETH OPTIONS
- ✅ 选择最大交易：BTC 500.0x (msg_id=340715)，ETH 1000.0x (msg_id=340690)
- ✅ 成功发送 2 封中文预警邮件

### **邮件内容验证**

#### BTC 测试邮件
- **主题：** 【TEST】单笔大宗期权预警 - BTC - 2025-12-12 04:56:42 - Deribit
- **合约：** BTC-30JAN26-70000-P
- **方向：** LONG
- **数量：** 500.0x (阈值: 200x)
- **格式：** HTML 中文模板 ✅

#### ETH 测试邮件
- **主题：** 【TEST】单笔大宗期权预警 - ETH - 2025-12-12 03:55:26 - Deribit
- **合约：** ETH-26DEC25-3300-C
- **方向：** SHORT
- **数量：** 1000.0x (阈值: 5000x)
- **格式：** HTML 中文模板 ✅

---

## 🎯 关键结论

1. ✅ **不影响生产环境**
   - 修改仅增加可选参数（默认值保持英文模板）
   - 测试脚本独立运行，不依赖 Telegram/PM2
   - 邮件标题包含【TEST】标记，易于区分

2. ✅ **中文模板完整实现**
   - 邮件主题、正文、字段标签全部中文化
   - 保留 Greeks 符号（Δ Γ ν Θ ρ）和英文名称
   - 分段结构清晰：资产信息、期权腿、非期权腿、风险提示、原始消息

3. ✅ **OPTIONS ONLY 规则保持**
   - 测试脚本仅筛选 instrument_type=OPTIONS
   - PERPETUAL/FUTURES 不参与测试
   - 与生产环境过滤逻辑一致

4. ✅ **历史数据验证可靠**
   - 使用真实历史数据（2025-12-11 16:00 → 2025-12-12 16:00）
   - BTC 最大 OPTIONS: 500.0x > 阈值 200x
   - ETH 最大 OPTIONS: 1000.0x < 阈值 5000x（但仍发送测试邮件）

---

## 🚀 使用说明

### **测试中文预警邮件（推荐）**

```bash
source .venv/bin/activate && python3 send_test_alert_emails.py
```

发送 2 封【TEST】中文预警邮件（BTC + ETH 最大 OPTIONS 交易）

### **生产环境预警（英文，默认）**

生产环境保持不变，使用英文模板：

```python
# message_listener.py 中的调用（不需要修改）
send_single_trade_alert_html(
    trade_info=trade_info,
    message_data=message_data,
    threshold=threshold
)
```

### **手动调用中文模板**

如需在其他场景使用中文模板：

```python
from email_sender import send_single_trade_alert_html

# 调用中文测试模板
send_single_trade_alert_html(
    trade_info=trade_info,
    message_data=message_data,
    threshold=threshold,
    lang='zh',        # 切换到中文
    test_mode=True    # 添加【TEST】标记
)
```

---

## 📊 数据统计（2025-12-11 16:00 → 2025-12-12 16:00）

### **消息统计**
- 总消息数：176 条 block trade
- BTC OPTIONS：116 笔
- ETH OPTIONS：48 笔
- PERPETUAL/FUTURES：12 笔（已排除）

### **测试样本**
| Asset | Volume | Contract | Side | Exchange | Msg ID |
|-------|--------|----------|------|----------|--------|
| BTC | 500.0x | BTC-30JAN26-70000-P | LONG | Deribit | 340715 |
| ETH | 1000.0x | ETH-26DEC25-3300-C | SHORT | Deribit | 340690 |

---

## 📝 后续维护

### **调整中文模板内容**

修改 `email_sender.py` 第 422-561 行的 HTML 模板：

```python
if lang == 'zh':
    # 中文模板
    html_body = f"""
    <!DOCTYPE html>
    ...
    """
```

### **切换回英文模板**

删除 `lang='zh'` 参数即可：

```python
# 默认使用英文模板
send_single_trade_alert_html(trade_info, message_data, threshold)
```

### **添加其他语言支持**

在 `send_single_trade_alert_html()` 中增加 `elif lang == 'ja':` 分支

---

## 🔄 与之前修复的关系

### **阈值修复（已完成）**
- BTC 阈值：5000 → 200 ✅
- ETH 阈值：5000 ✅
- 测试模式：ETH 降低到 1000 ✅

### **OPTIONS ONLY 过滤（已完成）**
- 硬规则：只对 OPTIONS 触发预警 ✅
- PERPETUAL/FUTURES 跳过 ✅
- 结构化日志：[ALERT_SKIP] / [ALERT_SEND] ✅

### **本次中文模板（已完成）**
- 增加语言切换参数 `lang='zh'` ✅
- 测试模式标记 `test_mode=True` ✅
- 发送 2 封测试邮件 ✅

---

## 📁 改动文件清单

1. **email_sender.py** (第 373-561 行)
   - 增加 `lang` 和 `test_mode` 参数
   - 添加中文模板分支

2. **send_test_alert_emails.py** (新增)
   - 测试脚本，查询历史数据并发送中文测试邮件

3. **CHINESE_TEMPLATE_TEST_SUMMARY.md** (新增)
   - 本文档，总结中文模板测试结果

---

## 📞 问题排查

### **查看测试邮件**

检查邮箱收件箱（kunkka@signalplus.com），搜索关键词：

- 主题包含：`【TEST】单笔大宗期权预警`
- 发件人：zaxandxck@gmail.com
- 发送时间：2025-12-16 06:45:51 UTC (BTC) 和 06:45:54 UTC (ETH)

### **重新发送测试邮件**

```bash
source .venv/bin/activate && python3 send_test_alert_emails.py
```

### **验证 Python 语法**

```bash
python3 -m py_compile email_sender.py
python3 -m py_compile send_test_alert_emails.py
```

---

## ✅ 验收通过

1. ✅ **中文模板已实现**
   - 测试数据：BTC 500.0x (msg_id=340715)，ETH 1000.0x (msg_id=340690)
   - 结果：成功发送 2 封【TEST】中文预警邮件

2. ✅ **不影响生产环境**
   - 生产代码无需修改（默认参数保持英文）
   - 测试脚本独立运行

3. ✅ **邮件格式正确**
   - 主题：【TEST】单笔大宗期权预警 - BTC/ETH - <时间> - Deribit
   - 正文：分段清晰，字段中文化，Greeks 保留符号

---

修复完成日期：2025-12-16
修复状态：✅ 全部验收通过
测试邮件：2 封（BTC + ETH）已发送
