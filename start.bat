@echo off
chcp 65001 >nul
title Sci-Pal 科研文献助手
echo ============================================================
echo   Sci-Pal 科研文献助手 V33.13
echo ============================================================
echo.

REM ── LLM 配置（二选一，默认本地 Ollama）──────────────────────
REM 路线 A：本地 Ollama（推荐，需先安装 Ollama 并拉取模型）
set SCIPAL_LLM_PROVIDER=ollama
set SCIPAL_LLM_HOST=http://localhost:11434
set SCIPAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M
set SCIPAL_LLM_LIGHT_MODEL=qwen2.5:3b

REM 路线 B：OpenAI 兼容云端（DeepSeek / DashScope / OpenAI）
REM 切到本路线时，把上面 SCIPAL_LLM_PROVIDER 改为 openai，并取消下面注释
REM set SCIPAL_LLM_PROVIDER=openai
REM set SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1
REM set SCIPAL_LLM_API_KEY=在这里填你的API_Key
REM set SCIPAL_LLM_MODEL=deepseek-chat

REM ── 模型离线模式（可选）─────────────────────────────────────
REM 已有本地模型缓存、不想联网检查更新时再打开；首装请保持注释
REM set TRANSFORMERS_OFFLINE=1
REM set HF_HUB_OFFLINE=1

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
