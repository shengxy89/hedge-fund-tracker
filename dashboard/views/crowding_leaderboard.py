"""View 4: 拥挤度排行 — Top N + Sector 分组 + 趋势."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text

from dashboard.data_access import get_crowding_df
from dashboard.utils.exporters import render_csv_download_button
from dashboard.utils.formatters import display_label
from db.engine import engine
from utils import get_prev_quarter, quarter_to_dates


def render_crowding_view(quarter: str) -> None:
    """渲染拥挤度排行榜视图."""
    st.header("Crowding Leaderboard")
    st.markdown("Stocks held by the most funds — potential consensus trades.")

    df = get_crowding_df(quarter)
    if df.empty:
        st.info("No crowding data available.")
        return

    # 顶部分组开关
    group_mode = st.radio(
        "View Mode",
        options=["All Sectors", "By Sector"],
        horizontal=True,
        key="cr_group",
    )

    if group_mode == "All Sectors":
        _render_all_sectors(df, quarter)
    else:
        _render_by_sector(df)

    st.markdown("---")

    # 真实环比变化：本季 NEW 净流入 vs SOLD 净流出
    _render_movers(quarter)


def _render_all_sectors(df: pd.DataFrame, quarter: str) -> None:
    """全部 sector 的主表."""
    st.subheader("Top 50 Most Crowded Stocks")

    top50 = df.head(50).copy()
    top50["Rank"] = range(1, len(top50) + 1)

    st.dataframe(
        top50[[
            "Rank", "ticker", "name", "sector",
            "holder_count", "crowding_score", "avg_weight", "total_value",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "crowding_score": st.column_config.ProgressColumn(
                "Crowding", format="%.1%", min_value=0, max_value=1,
            ),
            "avg_weight": st.column_config.NumberColumn("Avg Weight%", format="%.2f%%"),
            "total_value": st.column_config.NumberColumn("Total Value($K)", format="%,d"),
        },
    )

    render_csv_download_button(top50, f"crowding_top50_{quarter}.csv")


def _render_by_sector(df: pd.DataFrame) -> None:
    """按 Sector 分组的子 Tab."""
    sectors = sorted(df["sector"].dropna().unique().tolist())
    if not sectors:
        st.info("No sector data.")
        return

    sub_tabs = st.tabs(sectors)
    for tab, sector in zip(sub_tabs, sectors):
        with tab:
            sub = df[df["sector"] == sector].head(20).copy()
            if sub.empty:
                st.caption("No data.")
                continue
            st.dataframe(
                sub[["ticker", "name", "holder_count", "crowding_score", "avg_weight", "total_value"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "crowding_score": st.column_config.ProgressColumn("Crowding", format="%.1%"),
                },
            )


def _get_holder_count_changes(quarter: str) -> pd.DataFrame:
    """计算本季 vs 上季各 ticker 的持有基金数变化（NEW - SOLD）。

    Returns:
        DataFrame: ticker, name, sector, new_count, sold_count, net_change
    """
    prev_q = get_prev_quarter(quarter)
    _, curr_end = quarter_to_dates(quarter)
    _, prev_end = quarter_to_dates(prev_q)
    curr_rd = curr_end.isoformat()
    prev_rd = prev_end.isoformat()

    query = """
    WITH curr_holders AS (
        SELECT ticker, MAX(name) as name, COUNT(DISTINCT fund_id) as curr_count
        FROM holdings
        WHERE report_date = :curr_rd
          AND (put_call IS NULL OR put_call = '' OR put_call = 'NONE')
          AND ticker IS NOT NULL
        GROUP BY ticker
    ),
    prev_holders AS (
        SELECT ticker, COUNT(DISTINCT fund_id) as prev_count
        FROM holdings
        WHERE report_date = :prev_rd
          AND (put_call IS NULL OR put_call = '' OR put_call = 'NONE')
          AND ticker IS NOT NULL
        GROUP BY ticker
    ),
    sector_map AS (
        SELECT ticker, MAX(sector) as sector
        FROM securities
        WHERE ticker IS NOT NULL AND sector IS NOT NULL
        GROUP BY ticker
    )
    SELECT
        c.ticker,
        c.name,
        COALESCE(s.sector, 'Unknown') as sector,
        COALESCE(p.prev_count, 0) as prev_count,
        c.curr_count,
        (c.curr_count - COALESCE(p.prev_count, 0)) as net_change
    FROM curr_holders c
    LEFT JOIN prev_holders p ON c.ticker = p.ticker
    LEFT JOIN sector_map s ON s.ticker = c.ticker
    ORDER BY net_change DESC
    """
    with engine.connect() as conn:
        return pd.read_sql(
            text(query), conn,
            params={"curr_rd": curr_rd, "prev_rd": prev_rd},
        )


def _render_movers(quarter: str) -> None:
    """本季持有人数上升/下降最快的股票（基于环比变化）。"""
    st.subheader("Quarter-over-Quarter Holder Count Change")

    changes = _get_holder_count_changes(quarter)
    if changes.empty:
        st.info("No QoQ change data available (need at least 2 quarters of data).")
        return

    rising = changes[changes["net_change"] > 0].head(10)
    falling = changes[changes["net_change"] < 0].sort_values("net_change").head(10)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**🔥 Rising — {len(rising)} stocks with net new holders**")
        if rising.empty:
            st.caption("No stocks gained holders this quarter.")
        else:
            disp = rising.copy()
            disp["Display"] = disp.apply(
                lambda r: display_label(r.get("ticker"), r.get("name")), axis=1
            )
            st.dataframe(
                disp[["Display", "sector", "prev_count", "curr_count", "net_change"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "net_change": st.column_config.NumberColumn("Net Δ", format="+%d"),
                },
            )

    with col2:
        st.markdown(f"**❄️ Falling — {len(falling)} stocks with net lost holders**")
        if falling.empty:
            st.caption("No stocks lost holders this quarter.")
        else:
            disp = falling.copy()
            disp["Display"] = disp.apply(
                lambda r: display_label(r.get("ticker"), r.get("name")), axis=1
            )
            st.dataframe(
                disp[["Display", "sector", "prev_count", "curr_count", "net_change"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "net_change": st.column_config.NumberColumn("Net Δ", format="+%d"),
                },
            )
