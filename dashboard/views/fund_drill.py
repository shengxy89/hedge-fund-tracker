"""View 2: 基金穿透 — 概览 + 持仓 + 调仓 + 板块."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.charts import render_line_chart, render_pie_chart
from dashboard.components.disclaimer import filing_delay_badge, sold_threshold_disclaimer
from dashboard.components.kpi_cards import kpi_fund_cards
from dashboard.data_access import (
    get_available_quarters,
    get_filing_info,
    get_fund_deltas,
    get_fund_holdings,
    get_funds_df,
    get_sector_weights_fund,
)
from dashboard.utils.formatters import display_label, get_action_badge


def render_fund_drill_view(quarter: str) -> None:
    """渲染基金穿透视图."""
    st.header("Fund Drill-down")

    funds_df = get_funds_df()
    if funds_df.empty:
        st.info("No funds available.")
        return

    fund_name = st.selectbox("Select Fund", options=funds_df["name"].tolist(), key="fd_fund")
    fund_id = int(funds_df[funds_df["name"] == fund_name]["fund_id"].values[0])
    fund_info = funds_df[funds_df["name"] == fund_name].iloc[0]

    filing_info = get_filing_info(fund_id, quarter)
    filing_delay_badge(
        filing_info.get("report_date"), filing_info.get("filing_date")
    )

    tabs = st.tabs(["Overview", "Holdings", "Position Changes", "Sector Allocation"])

    with tabs[0]:
        _render_fund_overview(fund_id, fund_info, quarter, filing_info)
    with tabs[1]:
        _render_fund_holdings_tab(fund_id, quarter)
    with tabs[2]:
        _render_fund_deltas_tab(fund_id, quarter)
    with tabs[3]:
        _render_fund_sector_tab(fund_id, quarter)


def _render_fund_overview(
    fund_id: int,
    fund_info: pd.Series,
    quarter: str,
    filing_info: dict,
) -> None:
    """基金概览 Tab."""
    holdings = get_fund_holdings(fund_id, quarter)
    total_val = int(holdings["value"].sum()) if not holdings.empty else 0
    holding_count = len(holdings)
    top10_weight = (
        holdings.head(10)["weight_pct"].sum() / 100 if not holdings.empty else 0
    )

    # 换手率估算
    deltas = get_fund_deltas(fund_id, quarter)
    turnover = None
    if not deltas.empty and holding_count > 0:
        turnover = len(deltas[deltas["action"].isin(["NEW", "SOLD"])]) / holding_count

    kpi_fund_cards(total_val, holding_count, top10_weight, turnover)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Manager", fund_info.get("manager", "N/A") or "N/A")
        st.metric("Strategy", fund_info.get("strategy", "N/A") or "N/A")
    with col2:
        st.metric("Form Type", filing_info.get("form_type", "N/A"))
        st.metric(
            "Amendment",
            "Yes" if filing_info.get("is_amendment") else "No",
        )

    st.caption(
        f"Report Date: {filing_info.get('report_date', 'N/A')}  |  "
        f"Filing Date: {filing_info.get('filing_date', 'N/A')}  |  "
        f"Total Holdings: {filing_info.get('holding_count', 'N/A')}"
    )


def _render_fund_holdings_tab(fund_id: int, quarter: str) -> None:
    """当季持仓 Tab."""
    st.subheader("Current Holdings")

    holdings = get_fund_holdings(fund_id, quarter)
    if holdings.empty:
        st.info("No holdings data.")
        return

    # 搜索 + 筛选
    c1, c2 = st.columns([2, 1])
    with c1:
        search = st.text_input("Search ticker or name", "", key="fd_search")
    with c2:
        min_value = st.number_input(
            "Min Value ($K)", min_value=0, value=0, step=1000, key="fd_min_val"
        )

    filtered = holdings.copy()
    if search:
        mask = (
            filtered["ticker"].astype(str).str.contains(search, case=False, na=False)
            | filtered["stock_name"]
            .astype(str)
            .str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]
    if min_value > 0:
        filtered = filtered[filtered["value"] >= min_value]

    # Action 标签
    filtered["Action"] = filtered["action"].apply(get_action_badge)
    filtered["Display"] = filtered.apply(
        lambda r: display_label(r.get("ticker"), r.get("stock_name")),
        axis=1,
    )

    display = filtered[
        ["Display", "stock_name", "sector", "shares", "value", "weight_pct", "Action", "shares_change_pct"]
    ].copy()
    display.columns = [
        "Ticker", "Name", "Sector", "Shares", "Value($K)", "Weight%", "Action", "Change%",
    ]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Weight%": st.column_config.ProgressColumn("Weight%", format="%.2f%%", min_value=0, max_value=100),
            "Value($K)": st.column_config.NumberColumn("Value($K)", format="%,d"),
        },
    )


def _render_fund_deltas_tab(fund_id: int, quarter: str) -> None:
    """调仓详情 Tab."""
    st.subheader("Position Changes Summary")

    deltas = get_fund_deltas(fund_id, quarter)
    if deltas.empty:
        st.info("No delta data available.")
        return

    actions = ["NEW", "SOLD", "ADD", "REDUCE"]
    cols = st.columns(4)
    for col, action in zip(cols, actions):
        with col:
            st.markdown(f"**{get_action_badge(action)}**")
            sub = deltas[deltas["action"] == action]
            if sub.empty:
                st.caption(f"No {action} positions.")
            else:
                sub = sub.head(5)
                sub["Display"] = sub.apply(
                    lambda r: display_label(r.get("ticker"), r.get("name")),
                    axis=1,
                )
                disp = sub[["Display", "shares_change", "value_change"]].copy()
                disp.columns = ["Ticker", "Shares Δ", "Value Δ($K)"]
                st.dataframe(disp, use_container_width=True, hide_index=True)

    sold_threshold_disclaimer()

    # 历史趋势
    st.subheader("Top 5 Holdings History")
    holdings = get_fund_holdings(fund_id, quarter)
    if not holdings.empty:
        top5 = holdings.head(5)["ticker"].dropna().tolist()
        all_quarters = get_available_quarters()
        hist_data = []
        for q in all_quarters[:8]:
            h = get_fund_holdings(fund_id, q)
            if not h.empty:
                for _, row in h[h["ticker"].isin(top5)].iterrows():
                    hist_data.append({
                        "Quarter": q,
                        "Ticker": row["ticker"],
                        "Value($K)": row["value"],
                    })
        if hist_data:
            hist_df = pd.DataFrame(hist_data)
            render_line_chart(hist_df, "Quarter", "Value($K)", "Ticker", "Top 5 Holdings Trend")


def _render_fund_sector_tab(fund_id: int, quarter: str) -> None:
    """板块配置 Tab."""
    st.subheader("Sector Allocation")

    sw_curr = get_sector_weights_fund(fund_id, quarter)

    col1, col2 = st.columns(2)
    with col1:
        render_pie_chart(sw_curr, "sector", "weight_pct", f"{quarter}")
    with col2:
        from utils import get_prev_quarter
        prev_q = get_prev_quarter(quarter)
        sw_prev = get_sector_weights_fund(fund_id, prev_q)
        render_pie_chart(sw_prev, "sector", "weight_pct", f"{prev_q}")

    # 板块时序
    st.subheader("Sector Weight Trend")
    all_quarters = get_available_quarters()[:8]
    sector_hist = []
    for q in all_quarters:
        sw = get_sector_weights_fund(fund_id, q)
        if not sw.empty:
            for _, row in sw.iterrows():
                sector_hist.append({
                    "Quarter": q,
                    "Sector": row["sector"],
                    "Weight%": row["weight_pct"],
                })
    if sector_hist:
        sh_df = pd.DataFrame(sector_hist)
        render_line_chart(sh_df, "Quarter", "Weight%", "Sector", "Sector Weight Over Time")

    with st.expander("View sector data"):
        st.dataframe(sw_curr, use_container_width=True, hide_index=True)
