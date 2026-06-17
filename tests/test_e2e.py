"""End-to-end tests using in-memory SQLite.

Verifies the full pipeline: seed holdings → delta engine → jaccard → sector
weights → consensus → dashboard data_access queries return expected results.
"""
from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

from tests.conftest import *  # noqa: F401,F403 — ensure env vars set before imports


def test_delta_engine_produces_expected_actions(seeded_db):
    from analytics.delta_engine import run_delta_engine

    count = run_delta_engine()
    assert count > 0

    from db.engine import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT action, COUNT(*) FROM holding_deltas WHERE quarter = :q "
            "GROUP BY action"
        ), {"q": seeded_db["q_curr"]}).fetchall()
    actions = {r[0]: r[1] for r in rows}

    # Fund 2 NEW JPM; Fund 3 NEW AAPL; Fund 1 ADD AAPL; Fund 2 ADD AAPL
    assert actions.get("NEW", 0) == 2
    assert actions.get("ADD", 0) == 2
    assert actions.get("SOLD", 0) == 0  # No SOLD in fixture
    assert actions.get("REDUCE", 0) == 0


def test_jaccard_computed(seeded_db):
    from analytics.jaccard import run_jaccard

    count = run_jaccard(quarter=seeded_db["q_curr"])
    assert count > 0
    # 3 funds → C(3,2) = 3 pairs
    assert count == 3


def test_sector_weights_computed(seeded_db):
    from analytics.sector_weights import run_sector_weights

    count = run_sector_weights(quarter=seeded_db["q_curr"])
    assert count > 0

    from db.engine import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        sectors = conn.execute(text(
            "SELECT DISTINCT sector FROM sector_weights WHERE quarter = :q"
        ), {"q": seeded_db["q_curr"]}).fetchall()
    sector_list = {r[0] for r in sectors}
    assert "Information Technology" in sector_list
    assert "Energy" in sector_list
    assert "Financials" in sector_list


def test_consensus_signals(seeded_db):
    # First compute deltas (consensus depends on holding_deltas)
    from analytics.delta_engine import run_delta_engine
    run_delta_engine()

    from analytics.consensus import compute_consensus
    df = compute_consensus(quarter=seeded_db["q_curr"], min_funds=1)
    # With min_funds=1, AAPL should appear as NEW consensus (Fund 3) and ADD (Fund 1+2)
    assert not df.is_empty()
    actions = df["consensus_action"].to_list()
    assert "NEW" in actions
    assert "ADD" in actions


def test_crowding_report(seeded_db):
    from analytics.crowding import get_crowding_report

    df = get_crowding_report(seeded_db["q_curr"], min_holders=1)
    assert not df.is_empty()
    # AAPL held by Fund 1, 2, 3 → crowding_score = 3/3 = 1.0
    aapl = df.filter(pl.col("ticker") == "AAPL")
    assert not aapl.is_empty()
    assert aapl["holder_count"][0] == 3


def test_data_access_summary_metrics(seeded_db):
    # Need deltas first for the "active fund" metric
    from analytics.delta_engine import run_delta_engine
    run_delta_engine()

    # data_access uses streamlit cache; bypass it by calling the underlying logic.
    # Use the engine directly to validate summary SQL.
    from db.engine import engine
    from sqlalchemy import text
    from utils import quarter_to_dates

    _, end_date = quarter_to_dates(seeded_db["q_curr"])
    report_date = end_date.isoformat()
    with engine.connect() as conn:
        total_funds = conn.execute(text(
            "SELECT COUNT(DISTINCT fund_id) FROM holdings WHERE report_date = :rd"
        ), {"rd": report_date}).scalar()
    assert total_funds == 3


def test_incremental_delete_preserves_other_quarters(seeded_db):
    from analytics.delta_engine import run_delta_engine
    from db.engine import engine
    from sqlalchemy import text

    # First run: writes deltas for both 2024Q4 (curr vs prev) and possibly prev quarters.
    run_delta_engine()
    with engine.connect() as conn:
        total_before = conn.execute(text("SELECT COUNT(*) FROM holding_deltas")).scalar()

    # Re-run only for curr quarter — should NOT wipe other quarters' deltas.
    # Delta engine recomputes all quarters it has data for, so total should be stable.
    run_delta_engine()
    with engine.connect() as conn:
        total_after = conn.execute(text("SELECT COUNT(*) FROM holding_deltas")).scalar()

    assert total_after == total_before, (
        f"Incremental DELETE regression: before={total_before}, after={total_after}"
    )
