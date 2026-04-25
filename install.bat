@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set REPO=https://github.com/zhangjiabo522/WebMimoToOpenAIAPI
set DIR=WebMimoToOpenAIAPI

echo === WebMimoToOpenAIAPI 一键安装脚本 (Windows) ===
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo 错误: 未找到 Python，请先安装: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 下载源码...
if exist "%DIR%" (
    cd /d "%DIR%"
    git pull 2>nul || echo Git 未安装，请手动下载:%REPO%
) else (
    git clone "%REPO%" 2>nul || (
        echo Git 未安装，请手动下载源码:
        echo %REPO%
        pause
        exit /b 1
    )
    cd /d "%DIR%"
)

echo.
echo 安装 Python 依赖...
python -m pip install -r requirements.txt

echo.
echo === 安装完成 ===
echo.
echo 启动命令:
echo   cd /d "%CD%" && python main.py
echo.
echo 管理界面: http://localhost:9999
echo.
pause
