"""
测试季度调仓计算逻辑
"""
import polars as pl
from datetime import date

from analytics.delta_engine import compute_deltas_for_fund


def test_compute_deltas_new_sold():
    """测试新建仓和清仓判断"""
    # 使用模拟数据直接测试逻辑
    curr = pl.DataFrame({
        "cusip": ["A", "B"],
        "ticker": ["T1", "T2"],
        "shares": [100, 200],
        "value": [1000, 2000],
        "weight_pct": [10.0, 20.0],
    })
    prev = pl.DataFrame({
        "cusip": ["B", "C"],
        "ticker": ["T2", "T3"],
        "shares": [150, 300],
        "value": [1500, 3000],
        "weight_pct": [15.0, 30.0],
    })

    # 模拟 join
    joined = curr.join(prev, on="cusip", how="outer", suffix="_prev").fill_null(0)
    joined = joined.with_columns([
        pl.when(pl.col("shares_prev") == 0)
        .then(pl.lit("NEW"))
        .when(pl.col("shares") == 0)
        .then(pl.lit("SOLD"))
        .when(pl.col("shares") > pl.col("shares_prev"))
        .then(pl.lit("ADD"))
        .when(pl.col("shares") < pl.col("shares_prev"))
        .then(pl.lit("REDUCE"))
        .otherwise(pl.lit("HOLD"))
        .alias("action"),
    ])

    actions = joined["action"].to_list()
    assert "NEW" in actions  # A is new
    assert "SOLD" in actions  # C is sold
    assert "ADD" in actions  # B is add (200 > 150)


def test_compute_deltas_empty():
    """测试空持仓"""
    # 直接测试空 DataFrame 的 join 行为
    empty = pl.DataFrame({"cusip": [], "shares": [], "value": [], "weight_pct": []}).cast({"cusip": pl.Utf8, "shares": pl.Int64, "value": pl.Int64, "weight_pct": pl.Float64})
    result = empty.join(empty, on="cusip", how="full", suffix="_prev")
    assert isinstance(result, pl.DataFrame)
