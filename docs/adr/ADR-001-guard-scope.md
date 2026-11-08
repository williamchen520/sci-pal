# ADR-001：机器守卫的范围

日期：2026-11-09  
决定：先落 3 条守卫；其余等架构解耦改造时再加。  
到期检查：2026-12-31 复审一次。

---

## 当前启用

```text
1. route-unique-owner
   同一个 (URL, method) 只能由一个蓝图注册

2. deadline-todo
   TODO(decouple, deadline=YYYY-MM-DD) 过期即失败

3. new-file-no-sqlite
   新增 services/**/*.py 不得出现 sqlite3.connect
```

执行器：

```text
scripts/guard.py
ARCH_CONTRACT.json
```

---

## 暂缓

### 守卫 2：service 不直连 DB

```text
现在 services 里仍有大量 psycopg / pg_pool 调用
直接上会首日全红
需要先有 repository 层和冻结清单
```

### 守卫 4：新 service 必须走 repository

```text
repository 接口尚未普遍存在
现在强制只会逼出空 import
```

### 守卫 5：外部调用必须走 adapter

```text
EuropePMC / OpenAlex / LLM 调用仍分散
等 adapters 层稳定后再加
```

### 路由命名规范

```text
先解决归属唯一性
命名规范等 API 边界稳定
```

---

## 为什么不上 freeze

当前 3 条规则没有存量违规：

```text
route duplicate = 0
deadline todo    = 0
new sqlite       = 0
```

等加守卫 2/4 时再实现：

```text
python scripts/guard.py --freeze --expires ...
```

冻结清单必须带 reason + expires。

---

## 复审触发条件

```text
1. 开始架构解耦改造
2. repository 层落地
3. 开始清理 services 直连 DB
4. 2026-12-31 到期
```
