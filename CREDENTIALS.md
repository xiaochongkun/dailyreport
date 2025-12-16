# 🔐 Telegram API 凭证信息

## 应用信息

**App api_id:** `38073635`
**App api_hash:** `2c78d114834d147f1e46e0cbf9898ef6`

## 目标群组信息

**群组名称:** SignalPlus Trade Alert
**Chat ID:** `-1001881744197`

---

## 配置说明

这些凭证已经预设在 `config.py` 中，无需手动修改代码。

### 方式 1：直接使用（推荐）

配置已经内置在 `config.py` 中：

```python
API_ID = '38073635'
API_HASH = '2c78d114834d147f1e46e0cbf9898ef6'
TARGET_CHAT_ID = -1001881744197
TARGET_CHAT_NAME = 'SignalPlus Trade Alert'
```

**唯一需要配置的：** 你的手机号

编辑 `config.py` 第 17 行：
```python
PHONE_NUMBER = '+8613800138000'  # 替换为你的手机号
```

### 方式 2：使用环境变量（可选）

如果需要使用 `.env` 文件覆盖默认配置，创建 `.env` 文件：

```bash
cp .env.example .env
nano .env
```

然后在 `.env` 中设置：

```bash
API_ID=38073635
API_HASH=2c78d114834d147f1e46e0cbf9898ef6
PHONE_NUMBER=+8613800138000
TARGET_CHAT_ID=-1001881744197
```

---

## 验证配置

运行以下命令验证配置是否正确：

```bash
source .venv/bin/activate
python config.py
```

应该看到输出：

```
============================================================
当前配置:
============================================================
API_ID: 38073635
API_HASH: 2c78d114...8ef6
PHONE_NUMBER: +86****0000
TARGET_CHAT_ID: -1001881744197
TARGET_CHAT_NAME: SignalPlus Trade Alert
...
============================================================
✓ 配置验证通过！
```

---

## 安全提示

- ✅ 这些凭证已经内置在代码中，适合团队内部使用
- ⚠️ 不要将 `.env` 文件提交到公共 Git 仓库
- ⚠️ 不要分享 `telegram_session.session` 文件
- ✅ `.gitignore` 已配置，会自动忽略敏感文件

---

## 快速开始

1. **设置手机号**（编辑 config.py）
   ```python
   PHONE_NUMBER = '+8613800138000'
   ```

2. **首次认证**
   ```bash
   python telegram_client.py
   ```

3. **启动系统**
   ```bash
   python main.py
   ```

---

**最后更新:** 2025-12-11
**凭证来源:** 用户提供
