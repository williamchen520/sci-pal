# Base 镜像策略

> 日期：2026-11-02  
> 状态：app 层已从 clean git archive 重建；base 仍是运行时快照。

## 1. 本次结果

```text
scipal-base:py312      f301ba576744
scipal-app:latest      20433c4e6a16
app                    healthy
/api/health            200
```

app 层：

```text
git archive HEAD -> clean context
FROM scipal-base:py312
COPY . .
```

只有代码层变化，没有重新下载 CUDA。

## 2. Base 的来源

```text
scipal-base:py312 = 之前的运行镜像快照
```

它不是从零构建的：

```text
python:3.12-slim + apt + pip install
```

这一步仍受 CUDA 依赖下载影响。

## 3. 目标 Base

`deploy/Dockerfile.base` 定义了目标结构：

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

正式构建命令：

```bash
docker build -f deploy/Dockerfile.base -t scipal-base:py312 .
```

## 4. 当前取舍

```text
app 层可复现：是
base 层可复现：否
生产可用：是
```

在 CI 或网络稳定环境完成一次 base 构建后，后续 app 重建只需几十秒。

## 5. 注意

```text
不要删除 scipal-base:py312
不要删除 scipal-app:pre-clean-rebuild
```

它们是 app 层重建和回滚的基础。
