# PostgreSQL 迁移基线（P0）

> 日期：2026-10-31  
> 目的：在写任何迁移代码前，锁定 SQLite 原库快照、行数与校验值。  
> 原则：原库只读；迁移只使用副本。

---

## 1. 快照

```text
源库：D:\sciPal\data\research.db
快照：D:\sciPal\backups\research_20261031_210616.db
副本：G:\sciPal_deploy\backups\research_20261031_210616.db
```

大小：

```text
源库  1,832,071,168 bytes
快照  1,769,127,936 bytes
```

校验：

```text
PRAGMA integrity_check = ok
sha256 = 37e328a8a40edf5e1f25f1dcd72af80bdfdbbcfa4f7796e13d803aa5762fc607
```

生成方式：

```python
conn.execute("VACUUM INTO ?", (dst,))
```

快照生成后，原始 `data/research.db` 未被写入。

---

## 2. 行数基线

| 表 | 行数 |
|---|---:|
| papers | 3,310 |
| paragraphs | 167,388 |
| sentences | 862,677 |
| sections | 69,128 |
| citations | 182,817 |
| sentence_links | 296,951 |
| paper_links | 164,802 |
| claim_cards | 10 |
| claim_card_evidence | 17 |
| watch_items | 11 |
| users | 1 |
| workspaces | 1 |

---

## 3. 恢复演练

在任何迁移步骤前，先验证快照可用：

```powershell
python -c "import sqlite3; c=sqlite3.connect(r'D:\sciPal\backups\research_20261031_210616.db'); print(c.execute('PRAGMA integrity_check').fetchone()); print(c.execute('select count(*) from papers').fetchone())"
```

预期：

```text
('ok',)
(3310,)
```

---

## 4. 回退边界

```text
1. 迁移脚本只能读快照，不能写 data/research.db
2. 任何阶段失败 -> 停止迁移
3. 回退 = 继续使用原 SQLite 或恢复快照
4. P6 验收前不删除原库
5. 备份至少保留 30 天
```

---

## 5. 下一步

P1 之前必须完成的检查：

```text
[ ] 快照 D 盘存在
[ ] 快照 G 盘存在
[ ] integrity_check = ok
[ ] 行数与本文件一致
[ ] 原库未被覆盖
```

只有全部通过，才进入 P1（schema / DBAdapter）。
