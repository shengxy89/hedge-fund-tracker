"""
端到端测试：使用临时 SQLite 数据库验证完整 analytics 链路
核心目标：确保 write_consensus_to_db(quarter=None) 在真实数据下能正确写入。
"""
import subprocess
import sys
from pathlib import Path


def test_analytics_e2e_consensus_with_none_quarter(tmp_path: Path):
    """
    在独立子进程中运行完整 ETL + Analytics 链路，验证：
    1. run_delta_engine() 产生 holding_deltas
    2. write_consensus_to_db(quarter=None) 产生 holding_delta_norms
    3. run_analytics() 返回 consensus > 0
    """
    db_file = tmp_path / "e2e.db"
    script = tmp_path / "e2e_run.py"
    project_root = Path(__file__).parent.parent

    script_code = f'''
import sys
sys.path.insert(0, r"{project_root}")
import os
os.environ["DATABASE_URL"] = "sqlite:///{db_file.as_posix()}"

from datetime import date
from sqlalchemy.orm import Session

from db.models import Base, Fund, Security, Holding, Filing
from db.engine import engine
from analytics.delta_engine import run_delta_engine
from analytics.consensus import write_consensus_to_db
from analytics.runner import run_analytics

# 建表
Base.metadata.create_all(bind=engine)

# 插入 3 个基金
with Session(engine) as session:
    funds = [
        Fund(cik="000001", name="Fund A", is_active=True),
        Fund(cik="000002", name="Fund B", is_active=True),
        Fund(cik="000003", name="Fund C", is_active=True),
    ]
    for f in funds:
        session.add(f)
    session.commit()
    fund_ids = [f.fund_id for f in funds]

# 插入 securities
with Session(engine) as session:
    securities = [
        Security(cusip="CUSIP001", ticker="AAPL", name="Apple Inc", sector="Tech"),
        Security(cusip="CUSIP002", ticker="MSFT", name="Microsoft", sector="Tech"),
        Security(cusip="CUSIP003", ticker="TSLA", name="Tesla", sector="Auto"),
    ]
    for s in securities:
        session.add(s)
    session.commit()

prev_date = date(2024, 3, 31)
curr_date = date(2024, 6, 30)

# 插入两期 holdings（prev + curr），让 3 个基金对同一 CUSIP 都有 ADD/NEW
with Session(engine) as session:
    # Prev quarter holdings
    prev_holdings = [
        # Fund A
        Holding(fund_id=fund_ids[0], report_date=prev_date, cusip="CUSIP001",
                ticker="AAPL", shares=1000, value=1000, weight_pct=50.0),
        Holding(fund_id=fund_ids[0], report_date=prev_date, cusip="CUSIP002",
                ticker="MSFT", shares=1000, value=1000, weight_pct=50.0),
        # Fund B
        Holding(fund_id=fund_ids[1], report_date=prev_date, cusip="CUSIP001",
                ticker="AAPL", shares=1000, value=1000, weight_pct=50.0),
        Holding(fund_id=fund_ids[1], report_date=prev_date, cusip="CUSIP002",
                ticker="MSFT", shares=1000, value=1000, weight_pct=50.0),
        # Fund C
        Holding(fund_id=fund_ids[2], report_date=prev_date, cusip="CUSIP001",
                ticker="AAPL", shares=1000, value=1000, weight_pct=50.0),
    ]
    for h in prev_holdings:
        session.add(h)

    # Curr quarter holdings: 全部 ADD CUSIP003，且 AAPL/MSFT 也有变化形成 ADD
    curr_holdings = [
        # Fund A: AAPL ADD, MSFT ADD, TSLA NEW
        Holding(fund_id=fund_ids[0], report_date=curr_date, cusip="CUSIP001",
                ticker="AAPL", shares=2000, value=2000, weight_pct=33.33),
        Holding(fund_id=fund_ids[0], report_date=curr_date, cusip="CUSIP002",
                ticker="MSFT", shares=2000, value=2000, weight_pct=33.33),
        Holding(fund_id=fund_ids[0], report_date=curr_date, cusip="CUSIP003",
                ticker="TSLA", shares=2000, value=2000, weight_pct=33.33),
        # Fund B: AAPL ADD, MSFT ADD, TSLA NEW
        Holding(fund_id=fund_ids[1], report_date=curr_date, cusip="CUSIP001",
                ticker="AAPL", shares=2000, value=2000, weight_pct=33.33),
        Holding(fund_id=fund_ids[1], report_date=curr_date, cusip="CUSIP002",
                ticker="MSFT", shares=2000, value=2000, weight_pct=33.33),
        Holding(fund_id=fund_ids[1], report_date=curr_date, cusip="CUSIP003",
                ticker="TSLA", shares=2000, value=2000, weight_pct=33.33),
        # Fund C: AAPL ADD, TSLA NEW (没有 MSFT)
        Holding(fund_id=fund_ids[2], report_date=curr_date, cusip="CUSIP001",
                ticker="AAPL", shares=2000, value=2000, weight_pct=50.0),
        Holding(fund_id=fund_ids[2], report_date=curr_date, cusip="CUSIP003",
                ticker="TSLA", shares=2000, value=2000, weight_pct=50.0),
    ]
    for h in curr_holdings:
        session.add(h)

    # Insert filings so that quarter resolution works
    for fid in fund_ids:
        session.add(Filing(
            fund_id=fid,
            accession_number=f"ACC-{{fid}}-PREV",
            filing_date=prev_date,
            report_date=prev_date,
            form_type="13F-HR",
            is_amendment=False,
        ))
        session.add(Filing(
            fund_id=fid,
            accession_number=f"ACC-{{fid}}-CURR",
            filing_date=curr_date,
            report_date=curr_date,
            form_type="13F-HR",
            is_amendment=False,
        ))
    session.commit()

# 运行 delta
print("Running delta engine...")
delta_count = run_delta_engine()
print(f"Delta count: {{delta_count}}")
assert delta_count > 0, "Expected deltas > 0"

# 显式测试 quarter=None 能写入
print("Running write_consensus_to_db with quarter=None...")
consensus_count = write_consensus_to_db(quarter=None)
print(f"Consensus count: {{consensus_count}}")
assert consensus_count > 0, "write_consensus_to_db(quarter=None) must write > 0 records"

# 运行完整 runner
print("Running full run_analytics...")
result = run_analytics()
print(f"Result: {{result}}")
assert result["deltas"] > 0
assert result["consensus"] > 0, f"run_analytics consensus must be > 0, got {{result}}"
assert result["overlaps"] >= 0
assert result["sector_weights"] >= 0

# 验证 holding_delta_norms 字段完整性
from sqlalchemy import text
with engine.connect() as conn:
    row = conn.execute(text("""
        SELECT quarter, total_value_change, avg_weight_change_pct, signal_score
        FROM holding_delta_norms LIMIT 1
    """)).fetchone()
    assert row is not None, "holding_delta_norms should not be empty"
    assert row[0] == "2024Q2", f"Expected quarter 2024Q2, got {{row[0]}}"
    assert row[1] is not None, "total_value_change should not be null"
    assert row[2] is not None, "avg_weight_change_pct should not be null"
    assert row[3] is not None, "signal_score should not be null"

print("E2E PASSED")
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
        f"E2E subprocess failed with rc={proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "E2E PASSED" in proc.stdout
