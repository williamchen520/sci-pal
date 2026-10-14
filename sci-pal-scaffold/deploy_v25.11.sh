#!/usr/bin/env bash
# =============================================================================
# Sci-Pal V25.11 部署脚本
# 自动将 11 个文件（9改+2新增）复制到用户工程对应位置
#
# 用法:
#   1. 解压 Sci-Pal-V25.11.zip
#   2. 进入解压后的目录
#   3. bash deploy_v25.11.sh
#
# 目标工程路径默认 /home/kokomi/sciPal，可通过参数修改：
#   bash deploy_v25.11.sh /path/to/your/sciPal
# =============================================================================
set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 源目录（脚本所在目录，即解压后的脚手架根目录）
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 目标工程目录（默认 /home/kokomi/sciPal，可通过第一个参数覆盖）
DEST_DIR="${1:-/home/kokomi/sciPal}"

echo "============================================================"
echo "🚀 Sci-Pal V25.11 部署"
echo "============================================================"
echo "源目录: $SRC_DIR"
echo "目标:   $DEST_DIR"
echo ""

# 检查目标目录是否存在
if [ ! -d "$DEST_DIR" ]; then
    echo -e "${RED}✗ 目标目录不存在: $DEST_DIR${NC}"
    echo "请确认路径正确，或通过参数指定: bash deploy_v25.11.sh /path/to/sciPal"
    exit 1
fi

# 检查源文件是否齐全
MISSING=0
check_file() {
    if [ ! -f "$SRC_DIR/$1" ]; then
        echo -e "${RED}✗ 缺少源文件: $1${NC}"
        MISSING=1
    fi
}

check_file "api_server.py"
check_file "frontend/review.html"
check_file "frontend/src/paper_list.js"
check_file "frontend/src/outline_editor.js"
check_file "frontend/src/review.css"
check_file "frontend/vendor/pdf.min.js"
check_file "frontend/vendor/pdf.worker.min.js"
check_file "VERSION"
check_file "WORKLOG.md"
check_file "scripts/self_check.py"
check_file "scripts/run_tests.sh"

if [ $MISSING -eq 1 ]; then
    echo -e "${RED}✗ 源文件不齐全，请确认解压完整${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 源文件齐全（11个）${NC}"
echo ""

# 复制文件
copy_file() {
    local src="$1"
    local dest="$2"
    local desc="$3"
    
    # 确保目标目录存在
    mkdir -p "$(dirname "$DEST_DIR/$dest")"
    
    # 备份原文件（如果存在）
    if [ -f "$DEST_DIR/$dest" ]; then
        cp "$DEST_DIR/$dest" "$DEST_DIR/$dest.bak.v25.10"
    fi
    
    # 复制
    cp "$SRC_DIR/$src" "$DEST_DIR/$dest"
    echo -e "  ${GREEN}✓${NC} $desc → $dest"
}

echo "📋 复制文件中..."
echo ""

copy_file "api_server.py"                    "api_server.py"                    "后端服务"
copy_file "frontend/review.html"             "frontend/review.html"             "前端页面"
copy_file "frontend/src/paper_list.js"       "frontend/src/paper_list.js"       "论文列表模块"
copy_file "frontend/src/outline_editor.js"   "frontend/src/outline_editor.js"   "大纲编辑器主入口"
copy_file "frontend/src/review.css"          "frontend/src/review.css"          "样式表"
copy_file "frontend/vendor/pdf.min.js"       "frontend/vendor/pdf.min.js"       "PDF.js 库（新增）"
copy_file "frontend/vendor/pdf.worker.min.js" "frontend/vendor/pdf.worker.min.js" "PDF.js worker（新增）"
copy_file "VERSION"                           "VERSION"                           "版本号"
copy_file "WORKLOG.md"                        "WORKLOG.md"                        "工作日志"
copy_file "scripts/self_check.py"            "scripts/self_check.py"            "自检脚本"
copy_file "scripts/run_tests.sh"             "scripts/run_tests.sh"             "测试工作流"

echo ""
echo "============================================================"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "============================================================"
echo ""
echo "📝 说明："
echo "  - 原文件已备份为 *.bak.v25.10（如需回退，删掉新文件去掉 .bak 后缀即可）"
echo "  - frontend/vendor/ 目录是新建的，存放本地 PDF.js"
echo ""
echo "🚀 启动服务："
echo "  cd $DEST_DIR"
echo "  source venv_sciPal/bin/activate"
echo "  export SCIPAL_LLM_PROVIDER=openai"
echo "  export SCIPAL_LLM_BASE_URL=https://api.deepseek.com/v1"
echo "  export SCIPAL_LLM_API_KEY=你的DeepSeek_Key"
echo "  export SCIPAL_LLM_MODEL=deepseek-chat"
echo "  export SCIPAL_LLM_LIGHT_MODEL=deepseek-chat"
echo "  python api_server.py"
echo ""
echo "然后浏览器打开 http://localhost:5000，Ctrl+Shift+R 硬刷新。"
