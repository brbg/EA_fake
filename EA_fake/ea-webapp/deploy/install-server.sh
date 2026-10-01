#!/usr/bin/env bash
# ============================================================
# EA Web 服务器端一键安装（Ubuntu 22.04/24.04）
#
#   用法：sudo bash install-server.sh [部署包路径] [端口]
#   例：  sudo bash install-server.sh /tmp/EA_fake-deploy.tar.gz
#         sudo bash install-server.sh /tmp/EA_fake-deploy.tar.gz 8081
#
# 幂等：可以反复执行。已存在的 /opt/ea-webapp 会先备份再替换。
# 干的事：解压 → 建 venv（走国内镜像装依赖）→ 准备 .env → 装 systemd → 自检
# ============================================================
set -euo pipefail

APP_DIR=/opt/ea-webapp
TARBALL="${1:-/tmp/EA_fake-deploy.tar.gz}"
PORT="${2:-${PORT:-8080}}"
PIP_MIRROR="${PIP_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"
SERVICE=ea-webapp

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m[注意]\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m[错误] %s\033[0m\n' "$*"; exit 1; }

# ---------------------------------------------------------------- 0 环境自检
step "0/7 环境自检"
[ -f "$TARBALL" ] || die "找不到部署包：$TARBALL"
[ "$(id -u)" -eq 0 ] || die "需要 root：sudo bash $0 $*"
if ! command -v python3 >/dev/null 2>&1; then
    echo "    没装 python3，正在安装..."
    apt-get update -qq && apt-get install -y -qq python3 python3-venv
fi
command -v python3 >/dev/null || die "python3 装不上，请手动 apt install python3 python3-venv"
python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' \
    || die "Python 版本过低（$(python3 -V)），本项目需要 3.10+"
ok "$(python3 -V)"
if [ -r /etc/os-release ]; then
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian) ok "系统 $PRETTY_NAME" ;;
        *) warn "系统是 ${PRETTY_NAME:-未知}，本脚本按 Ubuntu 写的，出问题请反馈" ;;
    esac
fi

# ---------------------------------------------------------------- 1 解压
step "1/7 解压到 $APP_DIR"
if [ -d "$APP_DIR" ]; then
    BAK="$APP_DIR.bak-$(date +%s)"
    mv "$APP_DIR" "$BAK"
    warn "已存在旧目录，备份到 $BAK"
fi
tar xzf "$TARBALL" -C /opt
[ -f "$APP_DIR/backend/app.py" ] || die "解压后结构不对，确认包里有 backend/app.py"
[ -f "$APP_DIR/dist/index.html" ] || die "包里缺 dist/index.html（前端构建产物），后端没法伺服页面"
ok "$(find "$APP_DIR" -type f | wc -l) 个文件"
ok "dist/ 已就位 → 服务器不需要装 Node"

# ---------------------------------------------------------------- 2 依赖
step "2/7 建 venv 并装依赖（国内镜像）"
echo "    镜像：$PIP_MIRROR"
python3 -m venv "$APP_DIR/backend/venv"
"$APP_DIR/backend/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/backend/venv/bin/pip" install -q -i "$PIP_MIRROR" -r "$APP_DIR/backend/requirements.txt"
ok "依赖安装完成"

# ---------------------------------------------------------------- 3 AI 配置
step "3/7 AI 配置"
# systemd 单元的 EnvironmentFile 指向 .env，文件不存在会导致服务起不来 →
# 无论走哪条 key 路径，都必须保证 .env 存在
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/deploy/.env.example" "$APP_DIR/.env"
    ok "已从 .env.example 生成 .env（systemd 需要这个文件存在）"
fi
if [ -f "$APP_DIR/data/ea.db" ]; then
    ok "带 ea.db → 库里的 AI 配置优先于 .env"
    warn "想改 API Key 请在页面右上角「配置」里改；直接改 .env 不生效"
else
    if grep -q '^OPENAI_API_KEY=sk-' "$APP_DIR/.env" 2>/dev/null; then
        ok ".env 里已有 API Key"
    else
        warn ".env 里还没填 OPENAI_API_KEY —— AI 会走本地模板回退（功能可用，质量降级）"
        warn "填法：nano $APP_DIR/.env  然后 sudo systemctl restart $SERVICE"
    fi
fi

# ---------------------------------------------------------------- 4 端口
step "4/7 端口检查（$PORT）"
if ss -ltn 2>/dev/null | grep -qE "[:.]$PORT[[:space:]]"; then
    warn "端口 $PORT 已被占用，若服务起不来就换一个：sudo bash $0 $TARBALL 8081"
else
    ok "端口 $PORT 空闲"
fi

# ---------------------------------------------------------------- 5 服务单元
step "5/7 安装 systemd 服务"
UNIT_SRC="$APP_DIR/deploy/ea-webapp.service"
UNIT_DST="/etc/systemd/system/$SERVICE.service"
cp "$UNIT_SRC" "$UNIT_DST"
if [ "$PORT" != "8080" ]; then
    # 单元里默认没写 PORT，走 app.py 的 8080；换端口就补一行 Environment
    sed -i "/^EnvironmentFile=/a Environment=PORT=$PORT" "$UNIT_DST"
    ok "已把 PORT=$PORT 写进服务单元"
fi
systemctl daemon-reload
systemctl enable --now "$SERVICE" >/dev/null 2>&1 || true
systemctl restart "$SERVICE"
sleep 3
if systemctl is-active --quiet "$SERVICE"; then
    ok "服务已启动并设为开机自启"
else
    echo
    journalctl -u "$SERVICE" -n 25 --no-pager || true
    die "服务没能启动，上面的日志末尾就是原因"
fi

# ---------------------------------------------------------------- 6 防火墙
step "6/7 服务器防火墙"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$PORT/tcp" >/dev/null && ok "ufw 已放行 $PORT/tcp"
else
    ok "ufw 未启用，跳过（若启用了 firewalld 请自行放行）"
fi
warn "别忘了云控制台的【安全组】也要放行 $PORT —— 这一步漏了会「本地通、外网打不开」"

# ---------------------------------------------------------------- 7 自检
step "7/7 本机自检"
CODE=000
for i in $(seq 1 15); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/" || echo 000)
    [ "$CODE" = "200" ] && break
    sleep 1
done
if [ "$CODE" = "200" ]; then
    ok "首页 HTTP 200"
else
    warn "首页返回 $CODE，服务在跑但页面没出来；看 journalctl -u $SERVICE -n 40"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
printf '\n\033[1;32m==== 装好了 ====\033[0m\n'
echo "  本机访问： http://127.0.0.1:$PORT"
[ -n "${IP:-}" ] && echo "  内网访问： http://$IP:$PORT"
echo "  外网访问： http://<公网IP>:$PORT     ← 先确认安全组已放行 $PORT"
echo
echo "  常用命令："
echo "    sudo systemctl status  $SERVICE"
echo "    sudo systemctl restart $SERVICE"
echo "    sudo journalctl -u $SERVICE -f"
echo
echo "  提醒：会话存在内存，重启服务后所有人都要重新登录。"
