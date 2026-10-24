# 协作约定（WorkBuddy × CodeBuddy）

> 本文件是双 AI 协作的**唯一权威约定**。两条 AI 都按本文件执行，与别处冲突时以本文为准。
> 建立时间：2026-10-24 ｜ 分支：`dev` ｜ 版本基线：V33.17

---

## 一、为什么需要这份约定

两个 AI 共用同一个工作树（`D:\sciPal`）和同一个 git 仓库。官方（腾讯 Agent Suite）对两者的
定位是 **CODING AGENT（CodeBuddy）+ WORK AGENT（WorkBuddy）**，协同方式是**按场景接力**，
并明确不建议多端同时高频并发请求。

**冲突的根源是「两个写者改同一份文件」。** 所以本约定用**路径所有权**切分，而不是按「谁在
干什么」切分 —— 后者在边界模糊时会失效。

## 二、角色分工

| | CodeBuddy（VS Code 插件） | WorkBuddy（桌面端） |
|---|---|---|
| 定位 | CODING AGENT | WORK AGENT |
| 干什么 | **写代码** —— 唯一写码者 | 构建命令、架构设计、流程改造、方案与验收 |
| 不干什么 | 不改架构方向、不自行扩大改动范围 | **不写业务代码** |

边界价值：WorkBuddy 不写业务代码 ⇒ 唯一写码者是 CodeBuddy ⇒ 「同一时间只有一个写者」
自动成立，官方劝退的并发冲突从根上不会发生。

## 三、路径所有权（按路径切，不按职责切）

| 范围 | 主写方 | 说明 |
|---|---|---|
| `docs/**`、架构类 `*.md`、`docs/任务.md`、`docs/变更日志.md`、`docs/工作日志/` | **WorkBuddy** | 架构决策、任务板、工单、验收结论 |
| `*.py` / `*.js` / `*.html` / `config/` / `data/` | **CodeBuddy** | 业务代码与数据 |
| `CODEBUDDY.md`、`AGENTS.md`、`AI_CONTEXT.md`、`VERSION`、`ARCHITECTURE.md` | **需用户点名** | 两边都读，改动会影响对方 |

**越界规则**：确需动对方地盘时，**先写工单，不直接改**。

### 3.1 文档落位（2026-10-24 补）

- **新文档一律只放 `docs/` 下**；根目录只保留
  `AGENTS.md` / `CODEBUDDY.md` / `AI_CONTEXT.md` / `README.md` / `ARCHITECTURE.md` 这几个入口文件。
- 需要给人或 AI 看的总览时，**改根 `README.md`**，不要在 `docs/` 下另起一份正文副本。
- 已在 `docs/` 下的旧副本，若与根版同字节 → 删 `docs/` 那份；
  若根版是超集 → 在 `docs/` 那份文件头加「历史快照，以根版为准」标注，**不直接删**。
- 判定「哪份是活的」看**是否被入口文档引用**（`CODEBUDDY.md` 阅读清单 / `AI_CONTEXT.md` / 根 `README.md`），
  **不看文件大小和新旧**。

## 四、四拍闭环

1. **出方案**（WorkBuddy）—— 目标一句话、要动哪些文件、不许碰什么、完成定义
2. **派工单**（用户）—— 粘贴进 VS Code，或挂进 `docs/任务.md`
3. **实施**（CodeBuddy）—— 按工单执行并提交，**不自行扩大范围**
4. **验收**（WorkBuddy）—— 见第六节

> 缺了第 4 拍，架构就会变成「PPT 架构」：想得很漂亮，代码落不了地，也没人知道落没落。

**架构决策的落点**：写进 `docs/架构.md`，并在 `docs/变更日志.md` 记一笔。
原因：CodeBuddy 按 `CODEBUDDY.md` 的阅读清单开工，**它看不到对话记录** —— 不落在仓库里
的决策，对它等于不存在。

## 五、红线（出方案和执行前都要先过一遍）

- `UnifiedRetriever.retrieve()` / `HybridRetriever.search_papers()` **签名不动**
- `data/research.db` 表结构改动**必须走 migration**
- `data/outlines/` 的 **7 章大纲模板不得删除**
- 综述流程**不加**关系抽取 / 冲突检测 / 多智能体
- Protocols.io **只走 API，不落库**
- 未经用户点名**不 push**

## 六、验收标准（由 WorkBuddy 执行）

- `python self_check.py`：基线 **通过 110 / 失败 1 / 总计 121**。
  **失败项增加即判定为回归**（已知失败项 `abstracts.db: no such table: abstracts`，历史遗留，未修）
- `git diff --stat`：改动范围与工单一致，无越界文件
- 逐条核对第五节红线未被触碰

## 七、开工前必做

- `git status -sb` 确认当前分支是 **`dev`**
  （⚠️ 曾发生过提交落到 `ai/experiment` 的事故 —— 共用工作树时两边都可能切分支）
- `git log --oneline -3` 确认基线
- 有未提交改动先处理，**不要带着脏工作树开工**

## 八、提交与推送

- 提交信息格式：`V33.x: 简要描述`
- 本地 commit 可以；**push 必须用户点名**
- CodeBuddy 改完代码应尽快提交，保持工作树干净 —— 否则可能被对方的下一次 `checkout` 吞掉

---

## 附：如果换成别的编码 CLI

本仓库的入口文件是 `CODEBUDDY.md`（CodeBuddy 读）。若改用 Anthropic 的 Claude Code CLI，
它**只读 `CLAUDE.md`，看不到 `CODEBUDDY.md`** —— 必须先补 `CLAUDE.md`（可以是薄壳，
指向 `CODEBUDDY.md` 与本文件），否则它一条项目规矩都不知道，上来就容易踩第五节红线。
