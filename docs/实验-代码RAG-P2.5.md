# 实验记录：code-rag P2.5 Python 符号绑定

> 日期：2026-11-12  
> 状态：**局部符号绑定可用；未接 LSP**  
> 代码：`code_rag/resolve.py`

---

## 1. 目标

P2 的 calls 边是：

```text
unresolved:view_to_actual
```

P2.5 把它解析成：

```text
unit_8754d86a79028d6c
src/scanpy/_utils/__init__.py
```

让 `code_trace` 能跨文件落到真实函数。

## 2. 方法

```text
1. 从 file unit 读源码
2. 解析 import / from import / relative import
3. 建立 module -> path
4. 建立 path -> symbol -> unit_id
5. 对 calls 边：
   - 同文件函数
   - import alias 指向的目标文件
   - module.attr
6. 只更新能高置信解析的边
```

不做：

```text
LSP/类型推断
self.method 绑定
外部库源码绑定
```

## 3. 结果

scanpy 1.12.5：

```text
calls candidates 9,127
resolved            1,425
unresolved          7,701
resolved rate        15.6%
```

解释：

```text
多数 calls 是 numpy/scipy/logging/dict 等外部调用
15.6% 是“本地可解析比例”，不是总体正确率
```

## 4. trace 前后

### 前

```text
nodes 1
edges 9（全部 unresolved:）
```

### 后

```text
nodes 6
edges 18
```

新增节点：

```text
info / debug
  src/scanpy/logging.py

view_to_actual
  src/scanpy/_utils/__init__.py

_normalize_total_helper
  src/scanpy/preprocessing/_normalization.py

warn
  src/scanpy/_compat.py
```

这才说明 `code_trace` 有跨文件价值。

## 5. 验证

```text
tests.test_code_rag_resolve 3 passed
tests.test_code_rag_trace 2 passed
```

DSH 实际调用：

```text
code_trace(normalize_total, out, 1)
-> 4 nodes / 18 edges
```

## 6. 已知缺口

```text
self.method 未绑定
sc.pl.umap 这类模块属性链未绑定
外部库不索引
测试/benchmark 同名函数仍会干扰搜索
没有 LSP
```

## 7. 结论

```text
局部 import 绑定可用
跨文件 trace 已从“文本边”变成“真实 unit”
解析率不高，但阈值可控
```

下一步：

```text
P5 UI「我的代码库」
或先补 self.method / 模块属性链
```
