# SciPal 部署（Linux + Docker Compose）

> 目标：实验室 Linux 服务器，单节点起步；数据留在本机/外挂盘，不把私有数据发到公网。

## 1. 准备

- Linux 服务器，Docker + Compose；
- 数据目录：
  - `data/`：SQLite、Chroma、索引；
  - `documents/`、`documents_xml/`：论文与 XML；
  - `logs/`；
- GPU 可选；本地模型/解析服务单独部署。

## 2. 配置

```bash
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env
```

至少设置：

```text
SCIPAL_SECRET_KEY=<长随机字符串>
SCIPAL_LLM_*=<公网或本地/超算端点>
SCIPAL_AUTH_REQUIRED=1
```

不要把 `deploy/.env` 提交到 Git。

## 3. 启动

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

访问：

```text
http://<服务器IP>/
```

首次创建管理员：

```bash
docker compose -f deploy/docker-compose.yml exec app \
  python scripts/create_admin.py admin
```

登录：

```text
http://<服务器IP>/login.html
```

## 3.1 文献监控定时任务

compose 会启动独立的 `watch-cron` 服务，每 5 分钟检查一次到期 profile：

```text
python scripts/run_watch_due.py --loop --interval 300
```

手动运行一次：

```bash
docker compose -f deploy/docker-compose.yml exec app \
  python scripts/run_watch_due.py --once
```

查看日志：

```bash
docker compose -f deploy/docker-compose.yml logs -f watch-cron
```

## 4. 数据与备份

数据通过 volume 挂载：

```yaml
./data:/app/data
./documents:/app/documents
./documents_xml:/app/documents_xml
./logs:/app/logs
```

备份：

```bash
bash deploy/backup.sh
# 或
powershell -File deploy/backup.ps1
```

生成：

```text
backups/scipal-<UTC时间>.tar.gz
```

建议：

- 每日备份；
- 备份到另一块盘/NAS；
- 定期恢复演练；
- 备份含私有数据，注意访问权限。

## 5. 网络与安全

- 只开 LAN；远程用 VPN；
- 不要直接把 5000 暴露到公网；
- Caddy 负责反向代理；
- `SCIPAL_AUTH_REQUIRED=1`；
- workspace 隔离由应用层保证；
- 私有数据只允许本地/超算模型端点。

## 6. 当前限制

- 单节点 SQLite，适合 20–30 活跃用户；
- 1000 账号/100 并发需 PostgreSQL + Redis + 多 worker；
- 模型/解析服务需要单独部署；
- 本 compose 不含 GPU 调度。

## 7. 离线 bundle

在联网机器生成：

```bash
python deploy/build_offline_bundle.py --out backups
```

如需带镜像：

```bash
python deploy/build_offline_bundle.py --out backups \
  --images scipal-app:latest,caddy:2
```

产物：

```text
backups/scipal-offline-<UTC>.tar.gz
├─ app/            # 源码 + deploy
├─ images/         # 可选 docker save
├─ install.sh
└─ manifest.json   # 文件 hash 清单
```

目标机器：

```bash
tar xzf scipal-offline-*.tar.gz
bash install.sh
```

说明：

- 不包含 `data/`、`documents/`、模型、`.env`；
- 安装后需编辑 `app/deploy/.env`；
- 镜像方式可减少目标机器构建时间。

## 8. 后续

- PostgreSQL/Redis 版本；
- systemd/NSSM 备选方案；
- 监控与日志轮转；
- 部署机实际 build 验收。
