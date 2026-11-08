# 架构守卫使用说明

## 两个文件

```text
ARCHITECTURE.json   描述：路由表 / 蓝图 / 数据层
ARCH_CONTRACT.json  规则：边界 / 期限 / 禁止模式
```

两个脚本职责分开：

```text
scripts/validate_arch.py   文档与 Flask url_map 是否一致
scripts/guard.py           代码是否违反契约
```

不要合并。

---

## 运行

```bash
python scripts/guard.py
python scripts/guard.py --json
python scripts/guard.py --rule new-file-no-sqlite --staged
python scripts/guard.py --json --base-ref origin/dev
```

输出：

```json
{"ok": true, "violations": []}
```

---

## 规则类型

```text
route_unique_blueprint   同一 (URL, method) 多蓝图
deadline_scan            TODO deadline 过期
forbid_pattern           禁止模式；only_new 只查 git 新增文件
```

---

## 豁免

`ARCH_CONTRACT.json` 的 `exceptions`：

```json
{
  "rule": "new-file-no-sqlite",
  "target": "services/foo/bar.py",
  "reason": "迁移期例外",
  "expires": "2026-12-31"
}
```

没有 `expires` 或已过期，`guard.py` 直接失败。

---

## 当前接线

```text
pre-commit   新 service 的 sqlite3.connect 检查
CI           route / deadline / new file 全量
```

---

## 暂缓

见：

```text
docs/adr/ADR-001-guard-scope.md
```

守卫 2/4/5 等架构解耦改造时再加。
