"""
测试季度调仓计算逻辑
"""
from datetime import date

import polars as pl

from analytics.delta_engine import compute_deltas_from_frames


def test_compute_deltas_new_sold_add_reduce():
    """测试 NEW、SOLD、ADD、REDUCE 判断及各项指标"""
    curr = pl.DataFrame({
        "cusip": ["A", "B", "C"],
        "ticker": ["T1", "T2", "T3"],
        "name": ["N1", "N2", "N3"],
        "shares": [100, 200, 50],
        "value": [1000, 2000, 500],
        "weight_pct": [10.0, 20.0, 5.0],
        "put_call": [None, None, None],
        "sector": ["Tech", "Tech", "Health"],
    })
    prev = pl.DataFrame({
        "cusip": ["B", "C", "D"],
        "ticker": ["T2", "T3", "T4"],
        "name": ["N2", "N3", "N4"],
        "shares": [150, 0, 300],
        "value": [1500, 0, 3000],
        "weight_pct": [15.0, 0.0, 30.0],
        "put_call": [None, None, None],
        "sector": ["Tech", "Health", "Finance"],
    })

    result = compute_deltas_from_frames(curr, prev, fund_id=1, curr_date=date(2024, 6, 30), prev_date=date(2024, 3, 31))

    assert not result.is_empty()
    # 应该有 4 条记录：A(NEW), B(ADD), C(REDUCE), D(SOLD)
    assert len(result) == 4

    # 检查 action 分类
    actions = {row["cusip"]: row["action"] for row in result.to_dicts()}
    assert actions["A"] == "NEW"
    assert actions["B"] == "ADD"   # 200 > 150
    assert actions["C"] == "NEW"  # curr=50, prev=0 -> NEW
    assert actions["D"] == "SOLD"  # curr=0, prev=300 -> SOLD

    # 检查 shares_change
    row_b = result.filter(pl.col("cusip") == "B").to_dicts()[0]
    assert row_b["shares_change"] == 50   # 200 - 150
    assert row_b["shares_change_pct"] == 50.0 / 150.0 * 100
    assert row_b["value_change"] == 500   # 2000 - 1500
    assert row_b["weight_change_pct"] == 5.0  # 20.0 - 15.0
    assert row_b["value_change_pct"] == 500.0 / 1500.0 * 100

    # 检查 NEW 的值
    row_a = result.filter(pl.col("cusip") == "A").to_dicts()[0]
    assert row_a["shares_change_pct"] == 100.0
    assert row_a["value_change_pct"] == 100.0

    # 检查 SOLD 的值
    row_d = result.filter(pl.col("cusip") == "D").to_dicts()[0]
    assert row_d["shares_change_pct"] == -100.0
    assert row_d["value_change_pct"] == -100.0


def test_compute_deltas_empty():
    """测试空 DataFrame"""
    empty = pl.DataFrame({
        "cusip": [],
        "ticker": [],
        "name": [],
        "shares": [],
        "value": [],
        "weight_pct": [],
        "put_call": [],
        "sector": [],
    }).cast({
        "cusip": pl.Utf8,
        "ticker": pl.Utf8,
        "name": pl.Utf8,
        "shares": pl.Int64,
        "value": pl.Int64,
        "weight_pct": pl.Float64,
        "put_call": pl.Utf8,
        "sector": pl.Utf8,
    })
    result = compute_deltas_from_frames(
        empty, empty, fund_id=1,
        curr_date=date(2024, 6, 30), prev_date=date(2024, 3, 31),
    )
    assert isinstance(result, pl.DataFrame)
    assert result.is_empty()
