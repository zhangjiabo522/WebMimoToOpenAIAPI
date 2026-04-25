@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo === WebMimoToOpenAIAPI 一键更新 ===
echo.

echo 拉取最新代码...
git pull
if %ERRORLEVEL% neq 0 (
    echo Git pull 失败，请检查网络
    pause
    exit /b 1
)
echo.

echo 更新依赖...
python -m pip install -r requirements.txt
echo.

echo 停止旧服务...
taskkill /f /im python.exe 2>nul
timeout /t 2 >nul

echo 启动服务...
start python main.py
timeout /t 3 >nul

echo.
echo 更新完成！
echo 管理界面: http://localhost:9999
echo.
pause
