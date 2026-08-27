#!/usr/bin/env bash
# ============================================================
# AI 原生 Enterprise Architect — 演示/生产启动脚本
# 2核2G 服务器足够。用法：
#   bash run.sh           # 首次自动构建前端 + 装依赖 + 启动
#   bash run.sh --rebuild # 前端源码有更新时强制重新构建
# 可选：在脚本同目录放 .env 提供 OPENAI_API_KEY 等（见 DEPLOY.md）
# ============================================================
set -e
cd "$(dirname "$0")"

# ---------- AI（DeepSeek）配置，优先级：环境变量 > .env > 默认 ----------
set -a
[ -f .env ] && . ./.env
set +a
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.deepseek.com/v1}"
export OPENAI_MODEL="${OPENAI_MODEL:-deepseek-chat}"
export OPENAI_REASONING_MODEL="${OPENAI_REASONING_MODEL:-deepseek-reasoner}"
export SECRET_KEY="${SECRET_KEY:-$(date +%s%N | md5sum | head -c 32)}"

if [ -z "$OPENAI_API_KEY" ]; then
  echo "[警告] 未设置 OPENAI_API_KEY，AI 功能会回退到本地模板/模拟；要启用真 AI 请在 .env 里填 key。" >&2
fi

# ---------- 前端构建（首次或 --rebuild） ----------
if [ ! -f dist/index.html ] || [ "$1" = "--rebuild" ]; then
  echo "==> 构建前端 (npm run build)"
  [ -d node_modules ] || npm install
  npm run build
fi

# ---------- 后端 Python 环境 ----------
# 优先 python3.11（阿里云 Linux 3 / RHEL 系自带 3.6，必须用 3.11）；Ubuntu 用 python3 即可
PY=python3
command -v python3.11 >/dev/null 2>&1 && PY=python3.11
if [ ! -d backend/venv ]; then
  echo "==> 创建 Python 虚拟环境并安装依赖"
  "$PY" -m venv backend/venv
  backend/venv/bin/pip install -r backend/requirements.txt
fi

# ---------- 单进程启动（必须单进程：会话/在线用户存在内存，多 worker 会互相丢） ----------
echo "==> 启动 http://0.0.0.0:8080  （Ctrl+C 停止）"
exec backend/venv/bin/python backend/app.py
