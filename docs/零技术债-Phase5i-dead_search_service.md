# 零技术债 Phase 5i：删除死代码 SearchService / AIService

> 日期：2026-11-09  
> 状态：**整对死代码删除**

---

## 1. 判断

全仓 `git grep`：

```text
SearchService -> 只被 AIService 引用
AIService     -> 无任何调用方
```

两者互相引用，但没有任何路由、服务、脚本入口。

---

## 2. 改动

```text
删除 services/query/search_service.py
删除 services/ai/ai_service.py
```

---

## 3. 验证

```text
api_server py_compile OK
allowlist 18 -> 17
```

---

## 4. 下一步

```text
services/search/context_expander.py
services/search/graph_traverser.py
```

继续 PG-only；检索引擎主体仍保留。
