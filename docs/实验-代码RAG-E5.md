# 实验记录：code-rag E5 真实 DSH 会话 pilot

> 日期：2026-11-13  
> 状态：**6 题 pilot；B1/C1 都 6/6，未分出差异**  
> 数据：`eval/code_rag_stack/results/e5_dsh_pilot.json`

---

## 1. 设计

6 题：

```text
scanpy    3
rnaseq    3
```

两条臂：

```text
B1  DSH 原生 grep/glob/read/pwsh
    禁止 mcp__scipal-code__*
    禁止查询 scipal_code

C1  mcp__scipal-code__code_search
    code_trace（如需）
    read 实际文件
```

约束：

```text
同一仓库/commit
最多 5 次工具调用
不告诉 expected
返回 path + symbol + confidence
```

## 2. 结果

| 臂 | File 正确 | Symbol 正确 |
|---|---:|---:|
| B1 | 6/6 | 6/6 |
| C1 | 6/6 | 6/6 |

```text
B1 file_accuracy   1.000
B1 symbol_accuracy 1.000
C1 file_accuracy   1.000
C1 symbol_accuracy 1.000
```

## 3. 这说明什么

```text
不能说明 code RAG 更好
只能说明这 6 题太容易
```

题目特点：

```text
query 和 symbol 高度同名
目标文件唯一
没有版本歧义
没有跨文件数据流
没有 config/错误
```

B1 用 3–5 次 grep/read 就能找到；  
C1 用一次 code_search 也能找到。

## 4. 观察

```text
C1 在 STAR_ALIGN 上 code_trace 返回 0 边
但文件读取仍能确认答案
```

说明：

```text
trace 不是万能
最终仍要 read 文件
```

B1 的优势：

```text
不用索引
直接读最新文件
```

C1 的优势：

```text
精确符号候选更快
少几次 grep
```

## 5. 结论

```text
pilot 通过协议
但没有区分度
不能据此下结论
```

不能写：

```text
code RAG 优于 DSH
```

## 6. 下一步

扩到 30 题，必须加难：

```text
跨文件调用链
config override
版本/API 迁移
报错/测试定位
同名 symbol 多文件
```

否则会继续得到 6/6 vs 6/6。

当前：
```text
E5 pilot 完成
E5 full 未完成
```
