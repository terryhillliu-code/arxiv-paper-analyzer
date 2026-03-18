#!/bin/bash
# ArXiv Paper Analyzer 功能验证脚本

set -e

# 默认配置
BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:5173"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 颜色定义
GREEN='\033[92m'
RED='\033[91m'
YELLOW='\033[93m'
BLUE='\033[94m'
RESET='\033[0m'

echo -e "${BLUE}======================================${RESET}"
echo -e "${BLUE}ArXiv Paper Analyzer 功能验证${RESET}"
echo -e "${BLUE}======================================${RESET}"
echo

# 检查 Python 环境
if [ ! -d "$SCRIPT_DIR/../backend/venv" ]; then
    echo -e "${YELLOW}警告: 未找到虚拟环境，使用系统 Python${RESET}"
    PYTHON="python3"
else
    echo -e "${GREEN}使用虚拟环境${RESET}"
    PYTHON="$SCRIPT_DIR/../backend/venv/bin/python"
fi

# 检查依赖
echo -e "\n${BLUE}检查依赖...${RESET}"
if ! $PYTHON -c "import httpx" 2>/dev/null; then
    echo -e "${YELLOW}安装 httpx...${RESET}"
    pip install httpx
fi

# 运行验证
echo -e "\n${BLUE}运行验证脚本...${RESET}\n"
$PYTHON "$SCRIPT_DIR/verify_all.py" \
    --backend-url "$BACKEND_URL" \
    --frontend-url "$FRONTEND_URL" \
    "$@"

echo -e "\n${GREEN}验证完成！${RESET}"