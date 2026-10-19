@echo off
chcp 65001 >nul
title Sci-Pal 科研文献助手 - 环境安装
echo ============================================================
echo   Sci-Pal 科研文献助手 V33.13 - Windows 环境一键安装
echo ============================================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.11 或 3.12
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python 版本: %PYVER%

REM 创建虚拟环境
if not exist "venv_sciPal\Scripts\activate.bat" (
    echo [1/3] 创建虚拟环境 venv_sciPal...
    python -m venv venv_sciPal
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境创建成功
) else (
    echo [OK] 虚拟环境已存在，跳过创建
)

REM 激活虚拟环境
echo [2/3] 激活虚拟环境...
call venv_sciPal\Scripts\activate.bat

REM 升级 pip
echo [3/3] 升级 pip 并安装依赖（首次约 5-15 分钟）...
python -m pip install --upgrade pip -q
REM 网络慢可加清华镜像：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo 下一步:
echo   1. 有旧机备份时，把 data\ 和 documents\ 放到项目目录
echo   2. 配置 LLM：默认本地 Ollama（见 start.bat 注释），或改 openai 走云端
echo   3. 双击 start.bat 启动服务，浏览器打开 http://127.0.0.1:5000
echo.
echo LLM 详细配置见 .env.example 与 README-WINDOWS.md
echo.
pause
