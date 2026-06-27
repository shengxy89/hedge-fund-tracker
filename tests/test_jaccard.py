"""
测试 Jaccard 相似度计算（普通 + 加权）
"""


def _mock_holdings_sets():
    """构造两个基金的持仓数据，用于测试加权 Jaccard"""
    return {
        1: {
            "AAPL": {"weight_pct": 10.0, "value": 1000},
            "MSFT": {"weight_pct": 8.0, "value": 800},
            "GOOGL": {"weight_pct": 5.0, "value": 500},
        },
        2: {
            "AAPL": {"weight_pct": 12.0, "value": 1200},
            "MSFT": {"weight_pct": 0.0, "value": 0},
            "TSLA": {"weight_pct": 7.0, "value": 700},
        },
    }


def test_jaccard_basic():
    """测试普通 Jaccard 计算"""
    set_a = {"AAPL", "MSFT", "GOOGL"}
    set_b = {"AAPL", "MSFT", "TSLA"}
    intersection = set_a & set_b
    union = set_a | set_b
    jaccard = len(intersection) / len(union)
    assert jaccard == 2 / 4  # 0.5
    assert len(intersection) == 2


def test_weighted_jaccard_formula():
    """测试加权 Jaccard 符合 min/max 权重公式"""
    holdings = _mock_holdings_sets()
    weights_a = holdings[1]
    weights_b = holdings[2]
    union = set(weights_a.keys()) | set(weights_b.keys())

    min_sum = 0.0
    max_sum = 0.0
    for ticker in union:
        wa = weights_a.get(ticker, {}).get("weight_pct", 0)
        wb = weights_b.get(ticker, {}).get("weight_pct", 0)
        min_sum += min(wa, wb)
        max_sum += max(wa, wb)

    weighted_jaccard = min_sum / max_sum if max_sum > 0 else 0

    # AAPL: min=10, max=12
    # MSFT: min=0, max=8
    # GOOGL: min=0, max=5
    # TSLA: min=0, max=7
    # min_sum = 10 + 0 + 0 + 0 = 10
    # max_sum = 12 + 8 + 5 + 7 = 32
    assert min_sum == 10.0
    assert max_sum == 32.0
    assert weighted_jaccard == 10.0 / 32.0


def test_overlap_value_pct():
    """测试重合持仓市值占比"""
    holdings = _mock_holdings_sets()
    weights_a = holdings[1]
    weights_b = holdings[2]
    intersection = set(weights_a.keys()) & set(weights_b.keys())

    total_value_a = sum(v.get("value", 0) for v in weights_a.values())
    total_value_b = sum(v.get("value", 0) for v in weights_b.values())

    overlap_value_a = sum(weights_a.get(t, {}).get("value", 0) for t in intersection)
    overlap_value_b = sum(weights_b.get(t, {}).get("value", 0) for t in intersection)

    overlap_value_pct_a = (overlap_value_a / total_value_a * 100) if total_value_a > 0 else 0
    overlap_value_pct_b = (overlap_value_b / total_value_b * 100) if total_value_b > 0 else 0

    # intersection = AAPL, MSFT
    # total_value_a = 1000 + 800 + 500 = 2300
    # total_value_b = 1200 + 0 + 700 = 1900
    # overlap_value_a = 1000 + 800 = 1800
    # overlap_value_b = 1200 + 0 = 1200
    assert overlap_value_pct_a == 1800.0 / 2300.0 * 100
    assert overlap_value_pct_b == 1200.0 / 1900.0 * 100


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
