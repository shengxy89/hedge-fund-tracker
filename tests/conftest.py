"""Shared pytest fixtures — in-memory SQLite E2E setup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root on sys.path so `import db.models` etc work from tests/
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force a per-test in-memory SQLite before settings/engine are imported
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SEC_USER_AGENT", "test-agent@example.com")


@pytest.fixture(scope="session")
def engine_obj():
    """Session-scoped SQLite engine (in-memory, StaticPool keeps single connection)."""
    from db.engine import engine
    from db.models import Base
    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture()
def db_session(engine_obj):
    """Per-test transactional session — rolled back after each test."""
    from db.engine import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def seeded_db(engine_obj):
    """Seed 3 funds, 4 securities, 2 quarters of holdings into a fresh DB."""
    from datetime import date
    from db.engine import SessionLocal
    from db.models import Base, Fund, Security, Filing, Holding

    # Reset tables (in-memory; we recreate for determinism)
    Base.metadata.drop_all(bind=engine_obj)
    Base.metadata.create_all(bind=engine_obj)

    session = SessionLocal()
    try:
        funds = [
            Fund(cik="1", name="Fund A", manager="M1", strategy="Growth", is_active=True),
            Fund(cik="2", name="Fund B", manager="M2", strategy="Value", is_active=True),
            Fund(cik="3", name="Fund C", manager="M3", strategy="Macro", is_active=True),
        ]
        session.add_all(funds)
        session.flush()

        securities = [
            Security(cusip="CUSIP1", ticker="AAPL", name="Apple", sector="Information Technology"),
            Security(cusip="CUSIP2", ticker="MSFT", name="Microsoft", sector="Information Technology"),
            Security(cusip="CUSIP3", ticker="XOM", name="Exxon", sector="Energy"),
            Security(cusip="CUSIP4", ticker="JPM", name="JPMorgan", sector="Financials"),
        ]
        session.add_all(securities)
        session.flush()

        q_prev = date(2024, 9, 30)
        q_curr = date(2024, 12, 31)

        # filings + holdings
        for fund in funds:
            for rd in (q_prev, q_curr):
                session.add(Filing(
                    fund_id=fund.fund_id,
                    accession_number=f"ACC-{fund.cik}-{rd.isoformat()}",
                    filing_date=rd,
                    report_date=rd,
                    form_type="13F-HR",
                    is_amendment=False,
                    total_value=1_000_000,
                    holding_count=2,
                ))
        session.flush()

        # Fund A: AAPL + MSFT both quarters (HOLD), increase AAPL in curr
        # Fund B: AAPL + XOM prev; AAPL + XOM + JPM curr (NEW JPM, ADD AAPL)
        # Fund C: MSFT prev only; MSFT + AAPL curr (NEW AAPL)
        def _hold(fund_id, rd, cusip, ticker, shares, value, weight):
            session.add(Holding(
                fund_id=fund_id, report_date=rd, cusip=cusip, ticker=ticker,
                name=ticker, shares=shares, value=value, weight_pct=weight, put_call=None,
            ))

        # Q prev
        _hold(1, q_prev, "CUSIP1", "AAPL", 100, 500, 50.0)
        _hold(1, q_prev, "CUSIP2", "MSFT", 100, 500, 50.0)
        _hold(2, q_prev, "CUSIP1", "AAPL", 200, 400, 40.0)
        _hold(2, q_prev, "CUSIP3", "XOM", 300, 600, 60.0)
        _hold(3, q_prev, "CUSIP2", "MSFT", 500, 1000, 100.0)
        # Q curr
        _hold(1, q_curr, "CUSIP1", "AAPL", 150, 750, 60.0)  # ADD (shares 100→150, weight 50→60)
        _hold(1, q_curr, "CUSIP2", "MSFT", 100, 500, 40.0)  # HOLD
        _hold(2, q_curr, "CUSIP1", "AAPL", 250, 500, 50.0)  # ADD (shares 200→250, weight 40→50)
        _hold(2, q_curr, "CUSIP3", "XOM", 300, 300, 30.0)   # HOLD (value dropped, but shares unchanged → HOLD)
        _hold(2, q_curr, "CUSIP4", "JPM", 100, 200, 20.0)   # NEW
        _hold(3, q_curr, "CUSIP2", "MSFT", 500, 1000, 50.0) # HOLD
        _hold(3, q_curr, "CUSIP1", "AAPL", 100, 1000, 50.0) # NEW

        session.commit()
    finally:
        session.close()

    return {"q_prev": "2024Q3", "q_curr": "2024Q4"}
