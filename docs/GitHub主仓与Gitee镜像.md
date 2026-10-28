# GitHub 主仓 + Gitee 镜像

> 目标：GitHub 作为主线（分支保护完整），Gitee 作为国内镜像。
> 当前本地 remote：`origin` = Gitee，`github` = GitHub。

## 0. 已执行（2026-10-28）

- GitHub 仓库：https://github.com/williamchen520/sci-pal （public）
- 默认分支：`dev`
- `dev` / `master` 已开启保护：
  - Require PR（单账号 approvals=0，多人时改为 1）
  - Do not allow bypassing（enforce_admins=true）
  - Allow force pushes = false
  - Allow deletions = false
- 已推送分支：`dev` / `master` / `DSH-dev`

## 1. 在 GitHub 创建空仓库

用 GitHub Desktop：

```
File → Add Local Repository…
→ 选择 D:\sciPal
→ Publish repository
   Name: sci-pal
   Description: 本地优先的科研文献 RAG 系统
   取消勾选 Keep this code private（公开）
→ Publish
```

> 也可以网页 New repository：名字 `sci-pal`，**不要**勾 README/gitignore/license（本地已有）。

## 2. 推送所有分支

```powershell
git push github dev master DSH-dev
```

如果 GitHub 上默认分支不是 dev：

```
GitHub → Settings → Branches → Default branch → 选择 dev
```

## 3. GitHub 分支保护（dev）

```
Settings → Branches → Add branch protection rule
```

配置：

| 项 | 值 |
|---|---|
| Branch name pattern | `dev` |
| Require a pull request before merging | 开 |
| Required approvals | 0（单账号）；多人时 1 |
| Dismiss stale approvals | 开（可选） |
| Require status checks | 有 CI 就开 |
| Require conversation resolution | 开（可选） |
| **Do not allow bypassing the above settings** | **开** |
| Allow force pushes | 关 |
| Allow deletions | 关 |

`master` 可同样加一条；`DSH-dev` 不保护。

> 这一项是 Gitee 个人版做不到的：开启后管理员也不能绕过 PR/force push 限制。

## 4. 日常工作流

```
DSH-dev → GitHub PR → dev
```

合并后镜像到 Gitee：

```powershell
git push origin dev master
```

（`origin` 仍是 Gitee；如果以后把 origin 改成 GitHub，则用 `git push gitee dev master`。）

## 5. 镜像脚本

```powershell
powershell -ExecutionPolicy Bypass -File scripts/push_all.ps1
```

脚本行为：

1. 推 `DSH-dev` 到 GitHub；
2. 推 `dev` / `master` 到 GitHub；
3. 推 `dev` / `master` / `DSH-dev` 到 Gitee。

## 6. 注意

- 两个平台的 PR/Issue 不互通，选 GitHub 为主后，PR 在 GitHub 开；
- Gitee 侧仍保留 AGPL、默认分支 dev；
- 本地 `.githooks/pre-push` 仍拦截 Gitee `dev/master` 的强推与删除；
- GitHub 的 “Do not allow bypassing” 是服务端强约束，钩子只是补充。

## 7. 可选：GitHub Actions 自动镜像到 Gitee

需要：

1. Gitee 生成私人令牌（projects 权限）；
2. GitHub 仓库 Secrets 添加 `GITEE_TOKEN`；
3. Workflow 在 push 到 dev 时执行：

```yaml
git push https://oauth2:${{ secrets.GITEE_TOKEN }}@gitee.com/williamsucas/sci-pal.git dev master
```

> 令牌只放 GitHub Secrets，不要写进仓库。
