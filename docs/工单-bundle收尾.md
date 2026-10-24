# 工单 · 阶段五-A 收尾：让 bundle 能被正式安装

> 派单方：WorkBuddy（架构/验收）　执行方：CodeBuddy（代码）
> 创建：2026-10-24　对应路线图：`docs/DSH插件化-路线图.md` §2.1 / §2.3

---

## 零、背景（这些事实已由我现查核实，**不要再重复查，直接采信**）

| 事实 | 出处 / 证据 |
|---|---|
| bundle 包已存在，5 个文件 | `packages/dsh-scipal/{package.json, cordis.patch.yml, locale/en.json, icon.svg, README.md}` |
| 官方安装方式 = **DSH 会话内**调用 `plugin_manager` `action: install_bundle`，`target` 传绝对目录 | `docs/DSH官方参考/dsh-agent-preset/skills/cordis-plugin-development/SKILL.md:8` |
| 官方**禁止**手写 profile 的 `package.json` / `cordis.patch.yml`，也禁止在 `$DSH_HOME` 下建包 | 同上 `:10`；`references/host-plugin.md:68`「do not reproduce those steps with shell commands」 |
| `install_bundle` 会自己完成「包安装 + bundle 选中」两步 | `references/host-plugin.md:68` |
| bundle 清单要求：唯一 name、version、`dsh.bundle.patch`；配置型 bundle **不需要** Host/Client entry | `references/mcp-bundle.md:3` |
| 展示元数据：`meta.title` / `meta.description` 从 locale JSON 读；图标走 `./icon` 导出，≤256KiB | `references/host-plugin.md:31-51` |
| 图标可以是 SVG/PNG/JPEG/WebP，必须在包内 | `references/host-plugin.md:51` |
| `@deepseek-ai/dsh-mcp-client` **在官方可安装清单里**，且 `config: yes` | `docs/DSH官方参考/cordis-composition-reference/references/packages.md:318` |
| 本地目录安装是「链接 checkout」，不是拷贝；改包内文件即生效（换 JS 模块代需要重启） | `references/host-plugin.md:35,70` |
| **⚠️ 本机现状**：`~/.dsh/profiles/desktop/cordis.patch.yml`（4209 字节）第 68 / 81 行仍手写着 `serverName: scipalhello` 和 `scipal` | 现查 grep |
| serverName 重名 → 加载时报错（官方明示） | 见 `docs/DSH契约要点.md` |

**结论**：bundle 本体已合规；真正卡住的是 ① 手写条目没清（会重名冲突）② 安装动作必须在 DSH 会话里做，agent 在 VS Code 里做不了。

---

## 一、E-1 · 补中文 locale（小，5 分钟）

新建 `packages/dsh-scipal/locale/zh.json`，结构与现有 `locale/en.json` 一致：

```json
{
  "meta": {
    "title": "SciPal 文献工具",
    "description": "接入 SciPal 本地 MCP 服务器，让智能体可检索本地论文库、读取论文详情与摘要、并通过本地 SciPal API 轮询长任务。内含零依赖哨兵服务器用于故障隔离。"
  }
}
```

> 官方要求：除 `en` 外应为「用户的语言」补上同样字段（`host-plugin.md:33`）。用户是中文用户。

---

## 二、E-2 · 新建 `scripts/precheck_dsh_bundle.py`（本工单主体）

**定位：只读诊断 + 备份工具。它绝不写 `~/.dsh` 下任何文件，绝不改 profile 的 `package.json`。**
（原因见背景表第 3 行：官方明令禁止。）

### 必须做到的 5 件事

1. **检测 DSH 是否在运行**
   查进程名 `DeepSeek Harness`（Electron 主进程名），存活则打印：
   `DSH 正在运行 —— 安装请在 DSH 会话内进行（见 packages/dsh-scipal/INSTALL.md）；本脚本不做任何写入。`
   未运行则提示可以备份/清理。

2. **备份 profile patch 文件到仓库内**
   源：`C:\Users\chenwei\.dsh\profiles\desktop\cordis.patch.yml`
   目标：`tests/backups/cordis.patch.yml.<YYYYmmdd-HHMMSS>.bak`
   🔴 **必须落在仓库内** —— 该文件在 git 之外，删坏了 git 救不回来。路径不要硬编码到别处。

3. **冲突扫描**（本脚本最有价值的部分）
   解析源 patch，抽出所有 `serverName` 的值；再解析 `packages/dsh-scipal/cordis.patch.yml` 抽同样字段。
   两边求交集 → 输出冲突清单，并**给出需要删除的行区间**（用真实行号，别给模糊描述）。
   本机预期输出：`scipalhello`（第 68 行所在条目）、`scipal`（第 81 行所在条目）。

4. **bundle 自身静态校验**（逐条给出 PASS/FAIL，**不允许静默跳过**）
   - `package.json` 必填：`name`（唯一）、`version`、`private: true`、`type: module`、
     `exports` 含 `./locale/*.json` 与 `./icon`、`files` 含 `cordis.patch.yml` / `locale/*.json` / `icon.svg`、
     `dsh.bundle.patch` 指向存在的文件
   - `cordis.patch.yml` 可解析（若 PyYAML 不可用，**报 FAIL 并说明缺依赖**，不许报 PASS）
   - 每个条目：必须在 `insert:` 块内（顶层 `- id:` 无 insert = 静默跳过，这是踩过的坑，见 `docs/DSH契约要点.md`）
   - 每个条目：`name` 必须在官方可安装清单内（至少允许 `@deepseek-ai/dsh-mcp-client`）
   - 每个条目：`serverName` 必须匹配 `^[A-Za-z0-9_-]{1,32}$`
   - 图标：`icon.svg` 存在、≤256KiB、以 `<svg` 开头

5. **退出码约定**
   `0` = 无冲突、bundle 合法 → 可安装
   `1` = 存在 serverName 冲突 → 需先按输出的行区间清理
   `2` = bundle 自身不合法 → 不许装

### 硬性约束

- 纯标准库优先；需要 YAML 时先看 `venv_sciPal_py312` 里有没有 `PyYAML`，**没有就报 FAIL 不要自己 pip 装**。
- 不要 `try/except: pass` 吞异常 —— 这个项目已经栽过一次（`run_db_migrations` 缺 `import sqlite3` 被吞成「迁移跳过」）。
- 脚本路径从 `__file__` 推导，不要硬编码 `D:\sciPal`。
- 中文输出（Windows 控制台），注意重定向时可能抛 `UnicodeEncodeError`。

---

## 三、E-3 · 新建 `packages/dsh-scipal/INSTALL.md`

写**给用户在 DSH 会话里逐字粘贴**的操作原文，四步：

```
步骤 0（一次性，需人在 DSH 关闭时做）
  完全退出 DSH → 备份并删除 ~/.dsh/profiles/desktop/cordis.patch.yml 中
  手写的 mcp-scipalhello / mcp-scipal 两条 insert（不删会因 serverName 重名加载失败）
  → 用 python scripts/precheck_dsh_bundle.py 确认退出码为 0

步骤 1（在 DSH 会话里对模型说）
  用 plugin_manager 执行 action: list_plugins 和 list_bundles，报告当前 MCP 相关条目

步骤 2
  用 plugin_manager 执行 action: install_bundle，target 为 D:/sciPal/packages/dsh-scipal

步骤 3
  完全退出 DSH 再重启（新装的包要重启才加载新模块代）

步骤 4（验证）
  问模型："你现在有哪些 mcp__ 开头的工具？"
  期望看到 6 个：
    mcp__scipalhello__ping
    mcp__scipal__health / search_papers / get_paper / get_abstract / task_status
```

⚠️ 文档里必须写明：如果 `install_bundle` 报 pending build scripts，**不要**自动批准，先报告给用户。

---

## 四、E-4 · README 补「卸载」

在 `packages/dsh-scipal/README.md` 补一节：卸载用 `plugin_manager` `action: remove_bundle`（`host-plugin.md:70`），
并说明**卸载后若要回退**，`tests/backups/` 里有 patch 备份。
现有 README 已有重名冲突警告，**保留不要删**。

---

## 五、明确不要做的事

- ❌ 不要写 `~/.dsh/**` 任何文件（官方禁止；且该文件 git 救不回来）
- ❌ 不要改 `~/.dsh/profiles/desktop/package.json`
- ❌ 不要把 bundle 拷进 `$DSH_HOME`
- ❌ 不要尝试用 `dsh` CLI 装（本机 `desktop` profile 被 Electron 独占，CLI 会拒绝）
- ❌ 不要为了让「测试通过」而放宽校验条件

---

## 六、交接

- 完成后提交，**不要 `git add -A`**（仓库里有别人的未跟踪文件 `_test_v3317b.py`），显式列路径。
- 提交信息：`V33.17: 阶段五A 收尾 —— xxx`
- **不要自行 push**，由用户点名。
- 交付报告里请写明：`precheck_dsh_bundle.py` 在本机的实际输出（退出码 + 冲突清单），我要拿它验收。

---

## 附：仍未关闭的上一张工单

`docs/工单-下一步.md` 第六节「补充工单 C」还没做：
- **C-1**：`app.py` 是第二个 Flask 入口（依赖 `routes/`、`database/init_db.py`、`config/settings.py` 都在，是活代码），
  它的 `/api/health` 仍返回 `v0.6.0` —— 先判断在不在用，再决定统一版本还是标废弃（**删文件要用户点头**）。
- **C-2**：给 `self_check.py` 加版本指针守卫。

本工单（bundle 收尾）与 C 完全独立，可任选顺序。
