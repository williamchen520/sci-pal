# 实验记录：code-rag E3 L2 上下文闭合

> 日期：2026-11-13  
> 状态：**20 题上下文包已构建；import/closure 是构造结果，不是可运行证明**  
> 数据：`eval/code_rag_stack/results/e3_context.json`

---

## 1. 做了什么

对 20 个检索 top1：

```text
目标 unit
+ 目标文件的 import 行
+ 已解析的直接调用目标
+ snapshot/ref
```

组成 evidence package。

## 2. 结果

| 指标 | 值 |
|---|---:|
| cases | 20 |
| import_recall | 1.000 |
| symbol_closure_expanded | 1.000 |
| symbol_closure_no_expand | 0.450 |
| version_match | 1.000 |
| 有 resolved calls 的题 | 11 |
| 有 unresolved calls 的题 | 15 |

## 3. 怎么读

### import_recall = 1.0

因为 builder **把目标文件的所有 import 行都装进包**。  
这是构造结果，不是“模型自动找齐依赖”。

没有包时：

```text
函数 snippet 本身不带 import
```

所以 L2 的价值是：

```text
把 import 从“模型自己猜”
变成“包内固定携带”
```

### symbol_closure

```text
expanded 1.0     包内包含已解析调用目标
no_expand 0.45   只给 top1 时，11 题有 resolved calls，全部没覆盖
```

也就是说：

```text
不做上下文扩展
一半以上的调用链是断的
```

### version_match = 1.0

20 题都在固定 snapshot：

```text
scanpy 1.12.5
rnaseq 3.28.0
```

所以这一项是“版本过滤生效”，不是“版本推理正确”。

## 4. 不能声称

```text
不能声称 import 齐全就能跑
不能声称 symbol_closure=1 就语义正确
不能声称这 20 题代表真实用户
```

`unresolved` 仍有：

```text
np / pd / 外部库 / 实例方法
```

## 5. Gate

```text
G3 import_recall ≥0.90   PASS（构造口径）
G3 symbol_closure        未设硬门槛
```

必须标注：

```text
G3 是 package-level，不是 execution-level
```

## 6. 下一步

E4：

```text
compile_pass
test_pass@1
```

只选可执行子集，不能拿 20 题全部跑。

建议先做：

```text
Python 纯函数/小模块
Nextflow -stub
```

不碰需要 reference genome/容器的完整 pipeline。
