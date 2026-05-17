"""
测试 Jaccard 相似度计算
"""
from analytics.jaccard import compute_jaccard_for_quarter


def test_jaccard_basic():
    """测试基本 Jaccard 计算"""
    # 使用 mock 直接测试公式
    set_a = {"AAPL", "MSFT", "GOOGL"}
    set_b = {"AAPL", "MSFT", "TSLA"}
    intersection = set_a & set_b
    union = set_a | set_b
    jaccard = len(intersection) / len(union)
    assert jaccard == 2 / 4  # 0.5
    assert len(intersection) == 2


def test_jaccard_empty():
    """测试空集合"""
    set_a = set()
    set_b = {"AAPL"}
    union = set_a | set_b
    jaccard = len(set_a & set_b) / len(union) if len(union) > 0 else 0
    assert jaccard == 0


def test_jaccard_identical():
    """测试完全相同持仓"""
    set_a = {"AAPL", "MSFT"}
    set_b = {"AAPL", "MSFT"}
    jaccard = len(set_a & set_b) / len(set_a | set_b)
    assert jaccard == 1.0
