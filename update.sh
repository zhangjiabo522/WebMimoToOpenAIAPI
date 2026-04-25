#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== WebMimoToOpenAIAPI 一键更新 ==="
echo ""

# git pull
echo "拉取最新代码..."
git pull
echo ""

# 安装依赖
echo "更新依赖..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt
echo ""

# 重启
echo "重启服务..."
pkill -f "python.*main.py" 2>/dev/null || true
sleep 1
nohup python3 main.py > nohup.out 2>&1 &
sleep 2

echo "更新完成！"
echo "管理界面: http://localhost:9999"
echo "日志: tail -f nohup.out"
