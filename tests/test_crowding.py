"""
测试拥挤度计算
"""
import pandas as pd


def test_crowding_basic():
    """测试基本拥挤度公式"""
    holder_count = 25
    total_funds = 50
    crowding = holder_count / total_funds
    assert crowding == 0.5


def test_crowding_sorting():
    """测试排序逻辑"""
    data = [
        {"ticker": "A", "holder_count": 30},
        {"ticker": "B", "holder_count": 10},
        {"ticker": "C", "holder_count": 45},
    ]
    df = pd.DataFrame(data).sort_values("holder_count", ascending=False)
    assert df.iloc[0]["ticker"] == "C"
    assert df.iloc[2]["ticker"] == "B"
