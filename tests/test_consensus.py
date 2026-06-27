"""
测试多基金调仓共识评分逻辑
包含：纯公式测试 + 真实函数端到端测试
"""
import subprocess
import sys
from pathlib import Path

import polars as pl


def test_consensus_scoring_weight_and_value():
    """测试共识评分同时受 weight_change_pct 和 value_change 影响"""
    df = pl.DataFrame({
        "cusip": ["A", "A", "A", "B", "B", "B"],
        "put_call": ["NONE"] * 6,
        "issuer": ["A Inc", "A Inc", "A Inc", "B Inc", "B Inc", "B Inc"],
        "sector": ["Tech"] * 6,
        "industry": ["Software"] * 6,
        "fund_count": [3, 3, 3, 3, 3, 3],
        "avg_weight_change_pct": [5.0, 5.0, 5.0, 2.0, 2.0, 2.0],
        "total_weight_change_pct": [15.0, 15.0, 15.0, 6.0, 6.0, 6.0],
        "total_value_change": [300, 300, 300, 15000, 15000, 15000],
        "avg_value_change": [100.0, 100.0, 100.0, 5000.0, 5000.0, 5000.0],
        "total_abs_value_change": [300, 300, 300, 15000, 15000, 15000],
        "avg_value_change_pct": [100.0, 100.0, 100.0, 50.0, 50.0, 50.0],
        "avg_weight_curr": [5.0, 5.0, 5.0, 10.0, 10.0, 10.0],
        "total_weight_curr": [15.0, 15.0, 15.0, 30.0, 30.0, 30.0],
        "fund_ids": [[1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3]],
        "holder_count": [10, 10, 10, 10, 10, 10],
        "consensus_action": ["ADD", "ADD", "ADD", "ADD", "ADD", "ADD"],
    })

    df = df.with_columns(
        (
            pl.col("fund_count") * pl.col("avg_weight_change_pct").abs()
            + (1 + pl.col("total_value_change").abs()).log10() * 2
            + pl.col("holder_count").fill_null(0) * 0.5
        ).alias("signal_score")
    )

    scores = df.select(["cusip", "signal_score"]).unique().sort("cusip").to_dicts()
    score_a = next(s["signal_score"] for s in scores if s["cusip"] == "A")
    score_b = next(s["signal_score"] for s in scores if s["cusip"] == "B")

    assert score_b > 10, f"B's signal_score {score_b} should reflect large value_change"
    assert score_a > 10, f"A's signal_score {score_a} should reflect high weight_change"
    assert "total_value_change" in df.columns
    assert df.filter(pl.col("cusip") == "B")["total_value_change"][0] == 15000


def test_consensus_new_sold_min_funds():
    """测试 NEW/SOLD 共识的最少基金数过滤"""
    df = pl.DataFrame({
        "cusip": ["X", "X", "Y"],
        "put_call": ["NONE", "NONE", "NONE"],
        "issuer": ["X Inc", "X Inc", "Y Inc"],
        "sector": ["Tech", "Tech", "Health"],
        "industry": ["Software", "Software", "Bio"],
        "action": ["NEW", "NEW", "NEW"],
        "weight_change_pct": [3.0, 4.0, 5.0],
        "value_change": [100, 200, 300],
        "value_curr": [100, 200, 300],
        "value_prev": [0, 0, 0],
        "value_change_pct": [100.0, 100.0, 100.0],
        "weight_curr": [3.0, 4.0, 5.0],
        "weight_prev": [0.0, 0.0, 0.0],
        "fund_id": [1, 2, 3],
        "quarter": ["2024Q2", "2024Q2", "2024Q2"],
    })

    new_consensus = (
        df.filter(pl.col("action") == "NEW")
        .group_by(["cusip", "put_call", "issuer", "sector", "industry"])
        .agg([
            pl.len().alias("fund_count"),
            pl.mean("weight_change_pct").alias("avg_weight_change_pct"),
            pl.sum("weight_change_pct").alias("total_weight_change_pct"),
            pl.sum("value_change").alias("total_value_change"),
            pl.mean("value_change").alias("avg_value_change"),
            pl.col("value_change").abs().sum().alias("total_abs_value_change"),
            pl.mean("value_change_pct").alias("avg_value_change_pct"),
            pl.mean("weight_curr").alias("avg_weight_curr"),
            pl.sum("weight_curr").alias("total_weight_curr"),
            pl.col("fund_id").alias("fund_ids"),
        ])
        .filter(pl.col("fund_count") >= 2)
    )

    assert len(new_consensus) == 1
    assert new_consensus["cusip"][0] == "X"
    assert new_consensus["fund_count"][0] == 2


def test_compute_consensus_and_write_to_db_real_functions(tmp_path: Path):
    """
    真实函数测试：直接调用 compute_consensus 和 write_consensus_to_db，
    确保 quarter=None 时能正确解析并写入数据库。
    """
    db_file = tmp_path / "consensus_real.db"
    script = tmp_path / "consensus_real.py"
    project_root = Path(__file__).parent.parent

    script_code = f'''
import sys
sys.path.insert(0, r"{project_root}")
import os
os.environ["DATABASE_URL"] = "sqlite:///{db_file.as_posix()}"

from datetime import date
from sqlalchemy.orm import Session

from db.models import Base, Fund, Security, Holding
from db.engine import engine
from analytics.delta_engine import run_delta_engine
from analytics.consensus import compute_consensus, write_consensus_to_db

Base.metadata.create_all(bind=engine)

with Session(engine) as session:
    funds = [
        Fund(cik="C0001", name="Fund X", is_active=True),
        Fund(cik="C0002", name="Fund Y", is_active=True),
        Fund(cik="C0003", name="Fund Z", is_active=True),
    ]
    for f in funds:
        session.add(f)
    session.commit()
    fund_ids = [f.fund_id for f in funds]

    secs = [
        Security(cusip="C111", ticker="AAA", name="Alpha", sector="Tech"),
        Security(cusip="C222", ticker="BBB", name="Beta", sector="Health"),
    ]
    for s in secs:
        session.add(s)
    session.commit()

    prev = date(2024, 3, 31)
    curr = date(2024, 6, 30)

    # 所有基金都 NEW 同一股票
    for fid in fund_ids:
        session.add(Holding(fund_id=fid, report_date=prev, cusip="C111",
                            ticker="AAA", shares=100, value=100, weight_pct=50.0))
        session.add(Holding(fund_id=fid, report_date=prev, cusip="C222",
                            ticker="BBB", shares=100, value=100, weight_pct=50.0))
        # curr: 全部 ADD C111, SOLD C222
        session.add(Holding(fund_id=fid, report_date=curr, cusip="C111",
                            ticker="AAA", shares=200, value=200, weight_pct=100.0))
    session.commit()

# run delta
run_delta_engine()

# 测试 compute_consensus(quarter=None)
df = compute_consensus(quarter=None)
assert not df.is_empty(), "compute_consensus(quarter=None) should return data"
assert "quarter" in df.columns, "consensus DataFrame must contain quarter column"
assert df["quarter"][0] == "2024Q2", f"expected 2024Q2, got {{df['quarter'][0]}}"

# 测试 write_consensus_to_db(quarter=None)
count = write_consensus_to_db(quarter=None)
assert count > 0, f"write_consensus_to_db(quarter=None) must write > 0, got {{count}}"

from sqlalchemy import text
with engine.connect() as conn:
    norm_count = conn.execute(text("SELECT COUNT(*) FROM holding_delta_norms")).scalar()
    assert norm_count > 0, "holding_delta_norms must not be empty"

print("REAL_CONSENSUS_PASSED")
'''

    script.write_text(script_code, encoding="utf-8")
    project_root = Path(__file__).parent.parent
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert proc.returncode == 0, (
        f"Real consensus test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "REAL_CONSENSUS_PASSED" in proc.stdout
