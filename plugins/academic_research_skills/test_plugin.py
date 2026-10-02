"""
Academic Research Skills Plugin 测试脚本
========================================
"""

from core import AcademicResearchSkills


def test_plugin():
    """测试插件"""
    print("Testing Academic Research Skills Plugin...")

    # 初始化插件
    plugin = AcademicResearchSkills()

    # 测试写摘要
    print("\n1. Testing write_abstract...")
    abstract = plugin.write_abstract(
        title="STAT1 in interferon signaling",
        content="STAT1 is a key transcription factor in interferon signaling.",
        language="english"
    )
    print(f"Abstract: {abstract[:200]}...")

    # 测试检查引用
    print("\n2. Testing check_citations...")
    result = plugin.check_citations(
        text="STAT1 is a key transcription factor [1]. It regulates interferon signaling [2]."
    )
    print(f"Result: {result[:200]}...")

    print("\n✅ Plugin test completed!")


if __name__ == "__main__":
    test_plugin()
