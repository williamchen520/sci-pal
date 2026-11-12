# SciPal 文档索引

> 更新：2026-11-12 · 共 440 篇 Markdown  
> 分类是索引视图，不移动原文件；原路径与既有链接保持不变。

## 五大分类

| 分类 | 数量 | 索引 |
|---|---:|---|
| 架构规范 | 133 | [architecture/README.md](architecture/README.md) |
| 阶段计划 | 141 | [plans/README.md](plans/README.md) |
| 安全复盘 | 32 | [security/README.md](security/README.md) |
| 测试报告 | 52 | [testing/README.md](testing/README.md) |
| 废弃历史 | 82 | [legacy/README.md](legacy/README.md) |

完整清单：[_index/all.md](_index/all.md)

## 常用入口

- [架构与路由全景图](架构与路由全景图.md)
- [开发-模块手册](开发-模块手册.md)
- [开发流程规范](开发流程规范.md)
- [数据层隔离审计](数据层隔离审计.md)
- [恢复演练-20261112](恢复演练-20261112.md)
- [代码审查-20261112](代码审查-20261112.md)
- [工程治理门禁规范](工程治理门禁规范.md)
- [公共测试集选型](公共测试集选型.md)
- [计划-生信代码RAG](计划-生信代码RAG.md)
- [补充-生信代码RAG-DSH原生检索](补充-生信代码RAG-DSH原生检索.md)
- [Changelog](Changelog.md)

## 为什么不立即 git mv

```text
438 篇文档，348 篇在 docs/ 根目录
现有 43 个本地链接已经断开
全量移动会新增断链，并让 RAG 语料出现重复/重定向
```

所以先建立分类索引、时间轴和稳定入口；物理迁移等链接检查器就绪后再做。
