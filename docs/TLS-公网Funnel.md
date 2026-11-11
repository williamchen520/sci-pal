# 无域名公网 HTTPS：Tailscale Funnel

> 日期：2026-11-11  
> 域名：Tailscale 提供的 `*.ts.net`，无需自购域名

---

## 1. 当前入口

```text
https://desktop-e417o44.tailf0cce8.ts.net/
```

本地 Caddy：

```text
:80                    HTTP（127.0.0.1 / MCP 使用）
https://localhost      内部 CA
```

Funnel：

```text
Tailscale 443 -> 127.0.0.1:80
```

## 2. 验证

```text
GET /api/health   -> 200
GET /api/papers   -> 401（未登录）
```

证书由 Tailscale 自动签发，公网客户端可信。

## 3. 命令

```powershell
tailscale funnel --bg 80
tailscale funnel status
```

关闭：

```powershell
tailscale funnel reset
```

## 4. 安全边界

```text
公网入口只有 Funnel 的 HTTPS
API 仍要求 session / token
登录有限速
MCP 内部 token 不暴露
```

注意：

```text
Funnel URL 公开可达
任何拿到 URL 的人都能看到登录页
必须保留全局鉴权和限速
```

## 5. 与正式域名 A 的区别

```text
A：自有域名 + Let's Encrypt/企业证书
当前：Tailscale 域名 + Tailscale 证书
```

功能上都是公网可信 HTTPS；品牌/可控性不同。

## 6. 依赖

```text
Tailscale 客户端已安装
节点已登录 tailnet
Funnel 已在 tailnet 管理页启用
```
