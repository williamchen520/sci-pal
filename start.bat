@echo off
chcp 65001 >nul
title Sci-Pal 科研文献助手
echo ============================================================
echo   Sci-Pal 科研文献助手 V26.2
echo ============================================================
echo.

REM ── LLM 配置（改成你自己的）──────────────────────────────────
set SCIPAL_LLM_PROVIDER=openai
set SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
set SCIPAL_LLM_API_KEY=在这里填你的DeepSeek_API_Key
set SCIPAL_LLM_MODEL=deepseek-chat

REM ── 模型离线模式（不联网下载模型）────────────────────────────
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1

REM ── 检查虚拟环境 ────────────────────────────────────────────
if not exist "venv_sciPal\Scripts\activate.bat" (
    echo [提示] 虚拟环境不存在，先运行 install.bat 安装环境
    pause
    exit /b 1
)

REM 激活虚拟环境
call venv_sciPal\Scripts\activate.bat

REM 检查数据目录
if not exist "data" mkdir data
if not exist "documents" mkdir documents

echo [启动] 正在启动 Sci-Pal 服务...
echo [提示] 浏览器将自动打开 http://127.0.0.1:5000
echo [提示] 按 Ctrl+C 停止服务
echo.

REM 延迟2秒后打开浏览器
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

REM 启动服务（单线程，避免 PyTorch 死锁）
python api_server.py

pause
