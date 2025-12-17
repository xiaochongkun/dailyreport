#!/bin/bash

# Telegram Trade Alert 报告系统 - 安装脚本
# 自动完成环境配置和依赖安装

set -e  # 遇到错误立即退出

echo "========================================================"
echo "Telegram Trade Alert 报告系统 - 自动安装"
echo "========================================================"
echo ""

# 检查当前目录
if [ ! -f "main.py" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 1. 检查 Python
echo "[1/4] 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo "错误: Python 3 未安装"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✓ $PYTHON_VERSION"

# 2. 检查 uv
echo ""
echo "[2/4] 检查 uv 包管理器..."
if ! command -v uv &> /dev/null; then
    echo "错误: uv 未安装"
    echo "请运行: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
UV_VERSION=$(uv --version)
echo "✓ $UV_VERSION"

# 3. 创建虚拟环境
echo ""
echo "[3/4] 创建虚拟环境..."
if [ -d ".venv" ]; then
    echo "⚠ 虚拟环境已存在，跳过创建"
else
    uv venv
    echo "✓ 虚拟环境已创建: .venv"
fi

# 4. 安装依赖
echo ""
echo "[4/4] 安装依赖..."
source .venv/bin/activate
uv pip install -r requirements.txt
echo "✓ 依赖安装完成"

# 显示下一步
echo ""
echo "========================================================"
echo "✓ 安装完成！"
echo "========================================================"
echo ""
echo "下一步操作："
echo ""
echo "1. 激活虚拟环境："
echo "   source .venv/bin/activate"
echo ""
echo "2. 配置手机号（编辑 config.py）："
echo "   nano config.py"
echo "   # 设置 PHONE_NUMBER = '+8613800138000'"
echo ""
echo "3. 首次认证："
echo "   python telegram_client.py"
echo ""
echo "4. 导出历史数据（可选）："
echo "   python main.py export"
echo ""
echo "5. 运行主程序："
echo "   python main.py"
echo ""
echo "更多信息请查看："
echo "  - README.md          (完整文档)"
echo "  - QUICKSTART.md      (快速启动指南)"
echo "  - PROJECT_OVERVIEW.md (项目概览)"
echo ""
echo "========================================================"
