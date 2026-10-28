# Git 分支保护与本地钩子

> 目标：`dev` / `master` 不被误强推、误删；开发只走 `DSH-dev → PR → dev`。

## 1. Gitee 保护分支（个人版能做到的部分）

入口：

```
仓库 → 管理 → 保护分支设置
```

对 `dev` 建议：

| 项 | 建议 |
|---|---|
| 允许直接推送 | 关闭 |
| 允许合并角色 | 管理员 / 维护者 |
| 合并前审查 | 开启（至少 1 人） |
| 合并前测试 | 有 CI 就开 |
| 删除分支 | 禁止 |

`master` 同样加一条；`DSH-dev` 不保护。

> 个人版通常**不能**禁止仓库所有者强制推送；“禁止 force push”多是企业版能力。
> 所以再加一层本地钩子防手滑。

## 2. 本地 pre-push 钩子

仓库自带：

```
.githooks/pre-push
scripts/install_git_hooks.ps1
```

安装：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_git_hooks.ps1
```

等价于：

```powershell
git config core.hooksPath .githooks
git update-index --chmod=+x .githooks/pre-push
```

## 3. 钩子行为

对 `refs/heads/dev` 和 `refs/heads/master`：

- 正常 fast-forward：放行；
- 非 fast-forward（force push）：拒绝；
- 删除分支：拒绝。

其他分支（如 `DSH-dev`）不受影响。

## 4. 验证

```powershell
git push origin DSH-dev          # 应正常
git push --force origin dev      # 应被 pre-push 拒绝
```

被拒绝时输出：

```
pre-push: 禁止强制推送（non-fast-forward）到 refs/heads/dev
pre-push: 请走 DSH-dev -> PR -> dev
```

## 5. 绕过与边界

- `git push --no-verify` 可绕过钩子；
- 钩子只防本机误操作，不是安全边界；
- 真正的服务端强制需要 Gitee 企业版或 GitHub/GitLab 的 “do not allow bypassing” 规则；
- 若确实需要强推（例如清理历史），临时执行：

```powershell
git push --no-verify --force-with-lease origin dev
```

并先确认备份与团队通知。

## 6. 日常约定

1. 只推 `DSH-dev`；
2. `dev` 只通过 PR 合并；
3. 合并前跑：

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

4. 合并方式保持 Merge commit，不 Squash、不删源分支；
5. 定期检查 `git reflog` 与 Gitee 动态。
