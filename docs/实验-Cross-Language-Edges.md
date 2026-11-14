# 实验记录：跨语言低置信边

> 日期：2026-11-14  
> 状态：R↔Python 静态字符串调用可标记；不生成确定调用图

---

## 1. R → Python

```text
reticulate::source_python("tools.py")
reticulate::py_run_file("run.py")
reticulate::import("module")
system("python run.py")
```

输出：

```text
relation = cross_language
confidence = low
dst = cross_language:tools.py
```

## 2. Python → R

```text
Rscript plot.R
subprocess.run(["Rscript", "plot.R"])
rpy2 ...
```

输出同上，`source=python`。

## 3. 原则

```text
只认字符串字面量
只标 low
不解析变量路径
不解析动态命令
不合并跨语言 unit
```

## 4. 测试

```text
source_python + system -> 2 edges
Rscript -> 1 edge
```

```text
test_code_rag_r_parser 7 passed
```

## 5. 边界

```text
不把 low 当确定调用
不把 Python 文件自动绑定到 R 函数
不生成跨语言数据流
```

## 6. 下一步

```text
1. cross-language data artifact
2. module purpose
3. scipal-paper 插件
```
