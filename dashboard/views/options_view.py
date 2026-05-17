"""View 5: 期权专属视图 — PUT/CALL 持仓分析."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.data_access import get_options_summary
from dashboard.theme import CALL_ORANGE, PUT_PURPLE
from dashboard.utils.formatters import format_currency, format_shares


def render_options_view(quarter: str) -> None:
    """渲染期权专属视图."""
    st.header("Options Positions")

    call_df = get_options_summary(quarter, "CALL")
    put_df = get_options_summary(quarter, "PUT")

    # KPI
    call_notional = int(call_df["total_value"].sum()) if not call_df.empty else 0
    put_notional = int(put_df["total_value"].sum()) if not put_df.empty else 0
    call_funds = call_df["holder_count"].nunique() if not call_df.empty else 0
    put_funds = put_df["holder_count"].nunique() if not put_df.empty else 0
    total_option_funds = call_funds + put_funds
    pc_ratio = put_notional / call_notional if call_notional > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "CALL Notional Value",
        format_currency(call_notional),
        help="Sum of value across all CALL positions",
    )
    col2.metric(
        "PUT Notional Value",
        format_currency(put_notional),
        help="Sum of value across all PUT positions",
    )
    col3.metric(
        "Put/Call Ratio",
        f"{pc_ratio:.2f}",
        help="PUT notional / CALL notional. >1 means more bearish positioning.",
    )
    col4.metric(
        "Funds with Options",
        f"{total_option_funds}",
        help="Unique funds holding CALL or PUT",
    )

    st.markdown("---")

    # 双 Tab
    tab_call, tab_put = st.tabs(["🟠 CALL Positions", "🟣 PUT Positions"])

    with tab_call:
        _render_option_table(call_df, "CALL", CALL_ORANGE)

    with tab_put:
        _render_option_table(put_df, "PUT", PUT_PURPLE)


def _render_option_table(df: pd.DataFrame, option_type: str, color: str) -> None:
    """渲染期权持仓表."""
    if df.empty:
        st.info(f"No {option_type} positions for this quarter.")
        return

    st.write(f"{len(df)} distinct underlyings with {option_type} positions")

    display = df.head(20).copy()
    display["Notional Value"] = display["total_value"].apply(format_currency)
    display["Total Shares"] = display["total_shares"].apply(format_shares)

    st.dataframe(
        display[
            ["ticker", "stock_name", "sector", "holder_count", "total_shares", "total_value", "avg_weight_pct"]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker"),
            "stock_name": st.column_config.TextColumn("Name"),
            "sector": st.column_config.TextColumn("Sector"),
            "holder_count": st.column_config.NumberColumn("Funds", format="%d"),
            "total_shares": st.column_config.NumberColumn("Total Shares", format="%,d"),
            "total_value": st.column_config.NumberColumn("Notional ($K)", format="%,d"),
            "avg_weight_pct": st.column_config.NumberColumn("Avg Weight%", format="%.2f%%"),
        },
    )

    # Top 10 持有基金条形图
    st.subheader(f"Top 10 {option_type} Underlyings by Notional")
    top10 = display.head(10).copy()
    top10["label"] = top10.apply(
        lambda r: r["ticker"] if pd.notna(r["ticker"]) else f"🌐 {str(r['stock_name'])[:12]}",
        axis=1,
    )

    import plotly.express as px
    fig = px.bar(
        top10,
        x="total_value",
        y="label",
        orientation="h",
        color_discrete_sequence=[color],
        title=f"Top 10 {option_type} by Notional Value",
    )
    fig.update_layout(height=400, yaxis_categoryorder="total ascending")
    st.plotly_chart(fig, use_container_width=True)
