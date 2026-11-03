# 部署记录：Preflight 入库审计（2026-11-03）

## 1. 结论

```text
生产已部署 preflight 预入库审计
app healthy
health-cron status ok
outbox pending 0
```

## 2. 版本

```text
commit          e26ed56
image           scipal-app:latest  cf81e86c97c3
base image      scipal-base:py312
build context   git archive HEAD
Dockerfile      deploy/Dockerfile.app
```

回滚镜像：

```text
scipal-app:pre-preflight  20433c4e6a16
```

## 3. 构建

```powershell
git archive --format=zip -o G:\runs\scipal_src13.zip HEAD
Expand-Archive G:\runs\scipal_src13.zip -DestinationPath G:\runs\scipal_ctx13
docker tag scipal-app:latest scipal-app:pre-preflight
docker build -f G:\runs\scipal_ctx13\deploy\Dockerfile.app `
  -t scipal-app:latest G:\runs\scipal_ctx13
```

构建耗时约 8 秒，没有重新下载 CUDA/模型。

## 4. 部署

```powershell
cd G:\sciPal_deploy
docker compose -f deploy/docker-compose.yml up -d `
  --force-recreate --no-deps app
docker compose -f deploy/docker-compose.yml up -d `
  --force-recreate --no-deps watch-cron health-cron
```

容器：

```text
deploy-app-1         scipal-app:latest  healthy
deploy-watch-cron-1  scipal-app:latest  Up
deploy-health-cron-1 scipal-app:latest  Up
```

## 5. 验证

```text
GET /api/health     200
health-cron         status ok
outbox pending      0
drift               false
```

容器内 preflight：

```text
preflight enabled   True
module              /app/services/papers/preflight.py
```

写入路径已挂载：

```text
build_db/db_writer.py
build_db/import_jats.py
services/search/ingest.py
```

真实 XML 冒烟：

```text
PMC12771288.xml
ok=True
errors=[]
repairs=78
paragraphs=32
```

## 6. 生效范围

```text
PDF / JATS / PMC ingest
-> preflight 审计
-> 修复 ID / 空段 / 悬挂章节
-> 硬错误阻断
-> PostgreSQL + SQLite
```

默认：

```text
SCIPAL_INGEST_PREFLIGHT=1
```

## 7. 边界

已覆盖：

```text
paper_id
段落/章节/图表/引用 ID
空段落
section parent
metadata 基本结构
```

未覆盖：

```text
入库后的向量覆盖率
SQLite / PG 跨库 ID 一致性
```

这些仍由入库后审计：

```text
scripts/audit_id_vector_contract.py
```

## 8. 回滚

```powershell
docker tag scipal-app:pre-preflight scipal-app:latest
cd G:\sciPal_deploy
docker compose -f deploy/docker-compose.yml up -d `
  --force-recreate --no-deps app
```

## 9. 测试

```text
800 tests OK
```
