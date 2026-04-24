#!/bin/bash

echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    MiMo2API                              ║"
echo "║          小米 MiMo 模型 OpenAI 兼容 API                   ║"
echo "╚══════════════════════════════════════════════════════════╝"

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python 3"
    exit 1
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt -q

# 启动服务
PORT=${PORT:-9999}
echo "启动服务在端口 $PORT..."
nohup python3 main.py > nohup.out 2>&1 &
echo $! > mimo2api.pid

sleep 2

if ps -p $(cat mimo2api.pid) > /dev/null 2>&1; then
    echo "服务已启动: http://localhost:$PORT"
    echo "管理界面: http://localhost:$PORT"
    echo "API端点: http://localhost:$PORT/v1/chat/completions"
    echo "日志: tail -f nohup.out"
else
    echo "启动失败，请查看 nohup.out"
fi
