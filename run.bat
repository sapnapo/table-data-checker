@echo off
title 表格数据检查与简报生成助手
cd /d "%~dp0"

set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py"
)

if not defined PY (
    echo [错误] 未检测到 Python。请先到 python.org 安装 Python 3.9 或更高版本，
    echo        安装时务必勾选 "Add Python to PATH"，装好后再双击本脚本。
    pause
    exit /b 1
)

echo ============================================
echo   表格数据检查与简报生成助手
echo ============================================
echo.
echo [1/2] 安装依赖（首次运行需要几分钟，之后秒开）...
"%PY%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo [2/2] 启动应用...
echo 程序正在启动，约 5 秒后浏览器将自动打开 http://localhost:8501
echo 使用期间请保持本窗口开启；关闭本窗口或按 Ctrl+C 即可停止程序。
echo.
start /b cmd /c "timeout /t 5 /nobreak >nul & start http://localhost:8501"
"%PY%" -m streamlit run app.py --server.headless true
pause
