# 工单 C · 第二个 Flask 入口 `app.py` 的处置

> 派单方：WorkBuddy（架构/验收）　执行方：CodeBuddy（代码）
> 创建：2026-10-24　独立工单，与 `docs/工单-bundle收尾.md` 无依赖，可并行。
> 来源：阶段四-B 验收时发现的漏项（原挂在 `docs/工单-下一步.md` 第六节，现迁出独立成文）。

---

## 零、已核实的事实（**直接采信，不用重复查**）

### `app.py` 本体（51 行）

| 行 | 内容 |
|---|---|
| 7 | `from config.settings import HOST, PORT, DEBUG, UPLOAD_FOLDER, BASE_DIR` |
| 10 | `Flask(__name__, static_folder='frontend', static_url_path='')` |
| 21-22 | `from database.init_db import init_database` → `init_database()` |
| 25-31 | 注册 **3 个** blueprint：`paper_bp` `/api/papers`、`search_bp` `/api/search`、`ai_bp` `/api/ai` |
| 34-36 | `/` → `frontend/index.html` |
| **38-44** | `/api/health` → 返回 **`"version": "v0.6.0"`** |
| 48-50 | `__main__` → `app.run(host=HOST, port=PORT, debug=DEBUG)` |

### 判定「它已落后/废弃」的三条硬证据

1. **🔴 端口冲突**：`config/settings.py:19-21` 是 `HOST="0.0.0.0"`、`PORT=5000`、`DEBUG=False`。
   `api_server.py` 也用 5000 → **两者不可能同时运行**。谁先起谁占用。
2. **🔴 路由缺失**：`app.py` 只挂 3 个 blueprint，而 `api_server.py` 上存在的
   `/api/review/*`、`/api/tasks/*`、`/api/abstracts/*`、`/api/graph/*`、`/api/qa/*`、
   `/api/papers/<id>/graph` 等**在 `app.py` 里一个都没有** → 若拿它当入口，前端会大面积 404。
3. **🔴 孤儿 blueprint**：`routes/` 下有 4 个文件（`ai_routes` / `paper_routes` / `search_routes` /
   **`writing_routes`**），全仓库 grep 显示 `writing_bp` **只被自身文件引用，没有任何入口注册它**
   （`api_server.py` 也没挂）。→ 说明 `routes/` 这套 blueprint 体系整体已被 `api_server.py` 取代。

### 但仍有一条「活的」消费路径（本工单优先级最高的原因）

- **`build_db/seed_test_data.py:211`** 打印：`print("  1. Start the server: python app.py")`
  → 这是**全仓库唯一还在引导人去跑 `app.py` 的地方**，跑起来会占 5000 端口且功能残缺。

### 文档里的定性（三处说法还不一致，可作为佐证）

- `README.md:66` → `app.py  # 旧版入口（保留兼容）`
- `ARCHITECTURE.md:34,176,1038` → `备用入口（可能已废弃）`
- `docs/ARCHITECTURE.md:34,176,1025` → 同上

---

## 一、C-0 · 修误导文案（**最高优先级，5 分钟**）

`build_db/seed_test_data.py:211`：

```python
print("  1. Start the server: python app.py")
```

改为：

```python
print("  1. Start the server: python api_server.py")
```

**为什么排第一**：改版本号只是显示问题，这条文案会让**活人真的去跑一个残缺入口**并占掉 5000 端口。
顺手在同文件里扫一遍还有没有别的 `app.py` 字样。

判据：改动后 `grep -rn "python app.py" --include=*.py .`（排除 venv）应**无结果**。

---

## 二、C-1 · 判定 `app.py` 的存废（**给结论，不要擅自删**）

基于上面三条硬证据，我的判断是 **已废弃**。但按协作约定，**删文件必须用户点头**，所以：

### 你要做的

1. **独立复核**我的三条证据（尤其是「`writing_bp` 无人注册」和「端口冲突」），
   另外再查两个我可能漏的角度：
   - 有没有任何 `.ps1` / `.bat` / 安装脚本 / 打包配置（`build/`）把 `app.py` 当入口？
   - `frontend/` 里有没有硬编码只走 `app.py` 特有路由的调用？
2. **在交付报告里给出明确结论**（二选一，不要含糊）：
   - **结论 A · 确认废弃** → 输出「建议删除清单」，**不执行删除**，等用户点头。
     同时可以先做无损动作：在 `app.py` 文件头加一段废弃说明注释（指向 `api_server.py`），
     并同步三处文档的说法（见下）。
   - **结论 B · 仍在使用** → 说明到底是谁在用、怎么用，然后修 `app.py:43` 的版本号
     （`v0.6.0` → 与 `VERSION` 对齐），并说明它和 `api_server.py` 如何避免端口冲突。

3. **无论 A 还是 B，都要统一文档说法**：`README.md:66`、`ARCHITECTURE.md:34,176,1038`、
   `docs/ARCHITECTURE.md:34,176,1025` 这几处现在写着「旧版入口/备用入口/可能已废弃」三种说法，
   改成一致的定性。

### 不要做

- ❌ 不要删 `app.py`（等用户点头）
- ❌ 不要删 `routes/` 下任何文件（`writing_routes.py` 虽是孤儿，但删除同样是用户决定）
- ❌ 不要为了「让它能跑」而给 `app.py` 补路由 —— 那是复活一个已死的入口，方向反了

---

## 三、C-2 · 加版本指针守卫（防复发）

**背景**：这个项目版本号散在多处且**无守卫**，全靠手改，已经出现过三处不一致
（`/api/health` `V25.14` / banner `V25.17` / `VERSION` `V33.17`），现在又冒出 `app.py` 的 `v0.6.0`。

**要求**：在 `self_check.py` 里加一项检查，至少覆盖这几个真值来源：

| 来源 | 取值方式 |
|---|---|
| `VERSION` 文件 | 直接读（**作为唯一真值基准**） |
| `api_server.py` `/api/health` 返回的版本字段 | 从源码里提取那个字面量 |
| `api_server.py` 启动 banner | 同上 |
| （若 C-1 结论 B）`app.py:43` | 同上 |

**判据要判语义，不要只判形状**（这个项目栽过：恒等式判据在两边同时漏算时仍成立）。
所以：
- 必须报出**实际取到的值**和**分母**（共检查了几处、哪几处），不能只报「通过」。
- 任一处与 `VERSION` 不一致 → **FAIL**，并在输出里打出「哪一文件哪一行、当前值、期望值」。

**注意**：不要把 `# V25.xx` 这类**历史功能注释**当版本指针抓（`api_server.py` 的
957 / 1406 / 1618 / 1753 / 1979 行有）。守卫只认真正的版本返回值/banner。

---

## 四、交接

- 完成后提交，**不要 `git add -A`**（仓库里有别人的未跟踪文件 `_test_v3317b.py`），显式列路径。
- 提交信息：`V33.17: 工单C —— xxx`
- **不要自行 push**，由用户点名。
- 交付报告里请写明：C-1 的**结论是 A 还是 B**、复核时查了哪几个角度、有没有发现我漏的消费路径。
