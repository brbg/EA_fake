# 部署指南（演示，2核2G 服务器够用）

后端 Flask + WebSocket + SQLite，前端由后端直接伺服（`dist/`），**单进程**运行（会话/在线用户存在内存）。端口 `8080`。

## 方案 A：本地构建 dist，服务器不装 Node（推荐）

服务器只需 Python，最省资源。

### 1. 本地构建前端（Windows/Mac 上）

```bash
cd EA_fake/ea-webapp
npm install
npm run build        # 生成 dist/
```

### 2. 上传代码到服务器

把整个 `EA_fake/ea-webapp/` 传到 `/opt/ea-webapp`（含 `dist/`、`backend/`、`run.sh`、`deploy/`）。可用 scp 或 FileZilla，或：

```bash
cd /opt
git clone https://github.com/brbg/EA_fake.git   # 若源码已在 GitHub
cp -r EA_fake/ea-webapp /opt/ea-webapp
```

### 3. 服务器装 Python + 配置 .env

```bash
# Ubuntu 22.04/24.04
sudo apt update && sudo apt install -y python3 python3-venv

cd /opt/ea-webapp
cp deploy/.env.example .env
nano .env             # 填入 OPENAI_API_KEY（DeepSeek 的 sk-xxx）
```

### 4. 启动

```bash
bash run.sh           # 首次自动建 venv + 装依赖 + 启动（Ctrl+C 停止）
```

或作为后台服务（开机自启 + 崩溃重启）：

```bash
sudo cp deploy/ea-webapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ea-webapp
sudo systemctl status ea-webapp
```

### 5. 开放端口

- 阿里云/腾讯云：安全组放行 `8080`
- 服务器防火墙：`sudo ufw allow 8080/tcp`

访问 `http://<服务器IP>:8080`。

## 方案 B：服务器上装 Node，脚本自动构建

```bash
sudo apt install -y curl
# Node 18+（Ubuntu 22.04 自带 node12 太老，用 NodeSource 装新版）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs python3 python3-venv

cd /opt/ea-webapp
cp deploy/.env.example .env && nano .env
bash run.sh --rebuild   # 首次构建前端并启动
```

## 验证

- 打开首页 → 注册/登录
- 右上角头像显示 6 位账户 ID
- 新建项目 → 另一账号「协作 → 输入对方 ID → 加入」→ 双方进入协作模式实时同步
- AI 功能：先在 `.env` 填好 `OPENAI_API_KEY`，否则走本地模板回退

## 常见问题

| 现象 | 处理 |
|---|---|
| 打不开页面 | 确认安全组/防火墙放行 8080；`curl -I http://localhost:8080` 看后端是否在跑 |
| AI 没反应/回退 | `.env` 的 `OPENAI_API_KEY` 没填或填错；改完 `sudo systemctl restart ea-webapp` |
| 改了前端不生效 | 重新 `npm run build`，dist 需重新上传（或服务器上 `bash run.sh --rebuild`） |
| 重启后数据还在吗 | 在，数据在 `data/ea.db`（SQLite）+ `uploads/`，备份这两个目录即可 |
| 想多人同时在线 | 单进程 threading 模式几十并发没问题；要更高并发改 gunicorn+eventlet（见 requirements.txt 注释） |
