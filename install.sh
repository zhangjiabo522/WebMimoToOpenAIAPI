#!/usr/bin/env bash
set -e

REPO="https://github.com/zhangjiabo522/WebMimoToOpenAIAPI"
DIR="WebMimoToOpenAIAPI"

echo "=== WebMimoToOpenAIAPI 一键安装脚本 ==="
echo ""

# 检测 Windows (Git Bash)
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$(uname -o 2>/dev/null)" == "Msys" ]]; then
    echo "检测到 Windows 环境"
    PYTHON="python"
    PIP="pip3"
    if ! command -v python &>/dev/null; then
        echo "请先安装 Python: https://www.python.org/downloads/"
        exit 1
    fi
else
    echo "检测到 Linux 环境"
    PYTHON="python3"
    PIP="pip3"
    if ! command -v python3 &>/dev/null; then
        echo "安装 Python3..."
        apt update -y && apt install -y python3 python3-pip || yum install -y python3 python3-pip
    fi
    if ! command -v git &>/dev/null; then
        echo "安装 Git..."
        apt install -y git || yum install -y git
    fi
fi

# 下载源码
echo ""
echo "下载源码..."
if [ -d "$DIR" ]; then
    cd "$DIR" && git pull
else
    git clone "$REPO"
    cd "$DIR"
fi

# 安装依赖
echo ""
echo "安装 Python 依赖..."
$PIP install -r requirements.txt --break-system-packages 2>/dev/null || $PIP install -r requirements.txt

# 启动
echo ""
echo "=== 安装完成 ==="
echo ""
echo "启动命令:"
echo "  cd $DIR && $PYTHON main.py"
echo ""
echo "管理界面: http://localhost:9999"
echo ""
echo "后台运行:"
echo "  cd $DIR && nohup $PYTHON main.py > nohup.out 2>&1 &"
echo ""
echo "按任意键退出..."
read -n 1 -s -r
