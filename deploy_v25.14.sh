#!/usr/bin/env bash
# =============================================================================
# Sci-Pal V25.14 部署脚本
# 将脚手架目录的文件复制到用户工程目录
# 用法: bash deploy_v25.14.sh <目标工程目录>
# 示例: bash deploy_v25.14.sh /home/kokomi/sciPal
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-/home/kokomi/sciPal}"

echo "============================================"
echo "  Sci-Pal V25.14 部署"
echo "============================================"
echo "源目录: $SCRIPT_DIR"
echo "目标目录: $TARGET"
echo ""

if [ ! -d "$TARGET" ]; then
    echo "❌ 目标目录不存在: $TARGET"
    exit 1
fi

# 需要复制的文件/目录
FILES=(
    "api_server.py"
    "VERSION"
    "WORKLOG.md"
    "README.md"
    "frontend/review.html"
    "frontend/index.html"
    "frontend/src/pdf_viewer.js"
    "frontend/src/outline_editor.js"
    "frontend/src/paper_list.js"
    "frontend/src/outline_core.js"
    "frontend/src/resizer.js"
    "frontend/src/review.js"
    "frontend/src/review.css"
    "scripts/self_check.py"
    "scripts/run_tests.sh"
    "services/"
    "core/"
    "config/"
    "routes/"
    "build_db/"
    "utils/"
    "validators/"
    "tests/"
)

echo "开始复制文件..."
for item in "${FILES[@]}"; do
    if [ -e "$SCRIPT_DIR/$item" ]; then
        if [ -d "$SCRIPT_DIR/$item" ]; then
            mkdir -p "$TARGET/$item"
            cp -r "$SCRIPT_DIR/$item/"* "$TARGET/$item/" 2>/dev/null || true
            echo "  📁 $item/"
        else
            mkdir -p "$(dirname "$TARGET/$item")"
            cp "$SCRIPT_DIR/$item" "$TARGET/$item"
            echo "  📄 $item"
        fi
    fi
done

echo ""
echo "✅ V25.14 部署完成!"
echo ""
echo "启动命令（在目标目录执行）:"
echo "  cd $TARGET"
echo "  source venv_sciPal/bin/activate"
echo "  export SCIPAL_LLM_PROVIDER=openai"
echo "  export SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1"
echo "  export SCIPAL_LLM_MODEL=deepseek-chat"
echo "  export TRANSFORMERS_OFFLINE=1"
echo "  export HF_HUB_OFFLINE=1"
echo "  python api_server.py"
