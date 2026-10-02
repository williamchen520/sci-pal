"""
V25.9 - 大纲保存/加载存储（OutlineStore）。

文件级 JSON 存储，用于保存用户自定义的段落级大纲，方便复用。
存储目录：data/outlines/
文件命名：{sanitized_name}.json

每个保存的大纲包含：
- name: 大纲名称（用户指定）
- topic: 综述主题
- review_type: 综述模板类型
- outline: 段落级大纲 JSON（sections → paragraphs → topic/assigned_paper_ids）
- created_at: 创建时间
- updated_at: 更新时间
- paper_count: 涉及的论文数（冗余，方便列表展示）

用法:
    store = OutlineStore(data_dir="data/outlines")
    store.save("my_outline", topic="STAT1", review_type="narrative", outline_data={...})
    outlines = store.list()
    data = store.load("my_outline")
    store.delete("my_outline")
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional


class OutlineStore:
    """文件级大纲存储（JSON）。"""

    def __init__(self, data_dir: str = "data/outlines"):
        """
        Args:
            data_dir: 大纲存储目录路径
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        name: str,
        topic: str,
        outline_data: dict,
        review_type: str = "narrative",
        paper_count: int = 0,
    ) -> dict:
        """
        保存大纲（如果已存在则覆盖，并更新 updated_at）。

        Args:
            name: 大纲名称（会被 sanitize 为安全文件名）
            topic: 综述主题
            outline_data: 段落级大纲 JSON，格式 {"sections": [...]}
            review_type: 综述模板类型
            paper_count: 涉及的论文数

        Returns:
            保存后的完整记录 dict
        """
        safe_name = self._sanitize_name(name)
        if not safe_name:
            raise ValueError("大纲名称不能为空或全为特殊字符")

        filepath = self.data_dir / f"{safe_name}.json"

        # 检查是否已存在（保留 created_at）
        existing = self._load_raw(safe_name)
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        record = {
            "name": safe_name,
            "display_name": name,
            "topic": topic,
            "review_type": review_type,
            "outline": outline_data,
            "paper_count": paper_count,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        return record

    def load(self, name: str) -> Optional[dict]:
        """
        加载指定名称的大纲。

        Args:
            name: 大纲名称

        Returns:
            完整记录 dict，不存在返回 None
        """
        safe_name = self._sanitize_name(name)
        return self._load_raw(safe_name)

    def list(self) -> list[dict]:
        """
        列出所有已保存的大纲（按更新时间倒序）。

        Returns:
            大纲摘要列表 [{name, display_name, topic, review_type, paper_count, created_at, updated_at}, ...]
        """
        outlines = []
        for filepath in self.data_dir.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    record = json.load(f)
                # 只返回摘要，不返回完整 outline（节省传输）
                outlines.append({
                    "name": record.get("name", filepath.stem),
                    "display_name": record.get("display_name", record.get("name", filepath.stem)),
                    "topic": record.get("topic", ""),
                    "review_type": record.get("review_type", "narrative"),
                    "paper_count": record.get("paper_count", 0),
                    "section_count": len(record.get("outline", {}).get("sections", [])),
                    "paragraph_count": sum(
                        len(s.get("paragraphs", []))
                        for s in record.get("outline", {}).get("sections", [])
                    ),
                    "created_at": record.get("created_at", ""),
                    "updated_at": record.get("updated_at", ""),
                })
            except Exception:
                # 跳过损坏的文件
                continue

        # 按更新时间倒序
        outlines.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return outlines

    def delete(self, name: str) -> bool:
        """
        删除指定名称的大纲。

        Args:
            name: 大纲名称

        Returns:
            是否删除成功
        """
        safe_name = self._sanitize_name(name)
        filepath = self.data_dir / f"{safe_name}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def exists(self, name: str) -> bool:
        """检查大纲是否存在。"""
        safe_name = self._sanitize_name(name)
        return (self.data_dir / f"{safe_name}.json").exists()

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    def _load_raw(self, safe_name: str) -> Optional[dict]:
        """加载原始 JSON 记录。"""
        filepath = self.data_dir / f"{safe_name}.json"
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """
        将大纲名称转换为安全的文件名。
        保留中英文、数字、下划线、连字符，其他替换为下划线。
        """
        if not name:
            return ""
        # 替换不安全字符
        cleaned = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name.strip())
        # 合并连续下划线
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        # 限制长度
        return cleaned[:80] if len(cleaned) > 80 else cleaned


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    import os

    print("📦 Outline Store Test (V25.9)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        store = OutlineStore(data_dir=os.path.join(tmpdir, "outlines"))

        # 测试保存
        test_outline = {
            "sections": [
                {
                    "title": "Introduction",
                    "paragraphs": [
                        {"topic": "Background of STAT1", "assigned_paper_ids": ["paper1"]},
                        {"topic": "STAT1 in disease", "assigned_paper_ids": ["paper2"]},
                    ],
                }
            ]
        }
        record = store.save("test_outline", topic="STAT1", outline_data=test_outline, paper_count=2)
        print(f"✓ 保存成功: {record['name']} (created_at={record['created_at']})")

        # 测试列表
        outlines = store.list()
        print(f"✓ 列表: {len(outlines)} 个大纲")
        for o in outlines:
            print(f"  - {o['display_name']}: {o['topic']} ({o['section_count']}章 {o['paragraph_count']}段)")

        # 测试加载
        loaded = store.load("test_outline")
        assert loaded is not None
        assert loaded["topic"] == "STAT1"
        assert len(loaded["outline"]["sections"]) == 1
        print(f"✓ 加载成功: {loaded['name']}, 章节数={len(loaded['outline']['sections'])}")

        # 测试覆盖保存（updated_at 应更新）
        time.sleep(1)
        record2 = store.save("test_outline", topic="STAT1 updated", outline_data=test_outline)
        assert record2["created_at"] == record["created_at"]
        assert record2["updated_at"] != record["created_at"]
        print(f"✓ 覆盖保存: created_at 保留, updated_at 更新")

        # 测试 exists
        assert store.exists("test_outline")
        assert not store.exists("nonexistent")
        print("✓ exists 检查正常")

        # 测试删除
        assert store.delete("test_outline")
        assert not store.exists("test_outline")
        assert not store.delete("test_outline")  # 再次删除返回 False
        print("✓ 删除成功")

        # 测试名称 sanitize
        record3 = store.save("My Outline!@#", topic="test", outline_data={"sections": []})
        assert record3["name"] == "My_Outline"
        print(f"✓ 名称 sanitize: 'My Outline!@#' → '{record3['name']}'")

    print("\n✅ 全部测试通过。")
