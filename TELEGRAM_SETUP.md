# Telegram 数据采集环境配置指南

## 📋 前置条件

✓ Python 3.12.3 已安装
✓ uv (包管理器) 已安装

## 🚀 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
# 进入项目目录
cd /home/kunkka/projects/dailyreport

# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv pip install -r requirements.txt
```

### 2. 获取 Telegram API 凭证

1. 访问 https://my.telegram.org/apps
2. 使用你的 Telegram 账号登录
3. 创建一个新的应用（如果还没有）
4. 获取以下信息：
   - **API_ID** (数字)
   - **API_HASH** (32位十六进制字符串)

### 3. 配置脚本

编辑 `telegram_client.py`，替换以下占位符：

```python
API_ID = 'YOUR_API_ID'        # 替换为你的 API ID
API_HASH = 'YOUR_API_HASH'    # 替换为你的 API Hash
PHONE_NUMBER = '+86XXXXXXXXXXX'  # 替换为你的手机号（国际格式）
```

### 4. 首次运行

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 运行脚本
python telegram_client.py
```

**首次运行时会提示：**
1. 输入手机号验证码（Telegram 会发送到你的手机）
2. 如果启用了两步验证，需要输入密码
3. 认证信息会保存在 `telegram_session.session` 文件中

### 5. 验证输出

成功运行后，你会看到：
- ✓ 登录成功信息（用户名、ID、手机号）
- 前 5 个对话框的列表（包括群组/频道/用户）
- 每个对话框的 ID 和类型信息

## 📁 生成的文件

运行后会生成以下文件：

```
telegram_session.session         # 认证会话文件（包含登录状态）
telegram_session.session-journal # 会话日志文件
```

**⚠️ 重要：** 这些文件包含你的登录凭证，请勿分享或提交到 Git！

## 🔍 获取目标群组 ID

运行脚本后，查看输出中的对话框列表：

```
[1] 我的群组
    类型: 群组
    ID: -1001234567890    ← 这就是群组 ID
    Username: @mygroup
    成员数: 1234
```

将这个 ID 用于后续的消息采集功能。

## 🛠️ 常见问题

### Q: 提示 "API ID or Hash invalid"
- 确认你的 API_ID 和 API_HASH 是从 https://my.telegram.org/apps 获取的
- API_ID 应该是纯数字，API_HASH 是 32 位字符串

### Q: 无法收到验证码
- 确认手机号格式正确（必须包含国家代码，如 +86）
- 检查 Telegram 应用是否正常接收消息
- 可能会发送到 "Telegram" 官方账号而不是短信

### Q: Session 文件被删除后需要重新登录
- 这是正常的，Session 文件丢失后需要重新验证
- 建议备份 `telegram_session.session` 文件

## 📚 下一步

成功运行后，你可以：
1. 记录目标群组的 ID
2. 开发消息采集功能
3. 实现数据存储和分析

## 🔐 安全提示

- 不要将 Session 文件提交到 Git
- 不要分享你的 API_ID 和 API_HASH
- 使用 Userbot 请遵守 Telegram 服务条款
- 避免过于频繁的 API 调用，防止被限流

## 📞 技术支持

如遇到问题，请检查：
- Telethon 官方文档: https://docs.telethon.dev/
- Telegram API 文档: https://core.telegram.org/api
