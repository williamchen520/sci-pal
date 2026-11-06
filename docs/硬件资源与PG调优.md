# 硬件资源与 PG 调优

> 日期：2026-11-07

## 1. 实测硬件

```text
CPU      Intel Xeon E5-2673 v3
物理核   12
逻辑线程 24
内存     64 GB
GPU      RTX 4060 8 GB
```

说明：

```text
不是 48 核
系统报告为 12C / 24T
```

## 2. Docker / WSL

调整前：

```text
24 线程
31 GB
```

调整后：

```text
24 线程
59 GB
```

配置：

```ini
[wsl2]
memory=56GB
processors=24
swap=8GB
```

## 3. PostgreSQL

```text
shared_buffers                    12GB
effective_cache_size              32GB
maintenance_work_mem               1GB
work_mem                          64MB
max_parallel_workers              16
max_parallel_maintenance_workers   4
random_page_cost                   1.1
effective_io_concurrency           200
wal_buffers                       16MB
max_wal_size                      16GB
checkpoint_timeout                15min
default_statistics_target          200
```

## 4. Embedding

```text
device   cuda
batch    128
```

RTX 4060 8GB 足够 bge-base 128 批。

## 5. 10k 导入

```text
单线程
batch 200
pause 5s
不与 embeddings 并行
```

## 6. 当前下载

```text
2,896 / 10,000
```

按当前速率约 1.5 小时。
