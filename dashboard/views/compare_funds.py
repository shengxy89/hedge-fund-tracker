"""View 6: 基金两两对比 — Jaccard 详情 + 共同持仓 + 反向操作."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.charts import render_line_chart
from dashboard.data_access import get_fund_pair_overlap_detail, get_funds_df


def render_compare_funds_view(quarter: str) -> None:
    """渲染基金对比视图."""
    st.header("Fund Comparison")

    funds_df = get_funds_df()
    if funds_df.empty:
        st.info("No funds available.")
        return

    fund_names = funds_df["name"].tolist()
    col1, col2 = st.columns(2)
    with col1:
        fund_a_name = st.selectbox("Fund A", fund_names, key="cmp_a")
    with col2:
        fund_b_name = st.selectbox("Fund B", fund_names, index=min(1, len(fund_names) - 1), key="cmp_b")

    fund_a_id = int(funds_df[funds_df["name"] == fund_a_name]["fund_id"].values[0])
    fund_b_id = int(funds_df[funds_df["name"] == fund_b_name]["fund_id"].values[0])

    if fund_a_id == fund_b_id:
        st.warning("Please select two different funds.")
        return

    detail = get_fund_pair_overlap_detail(fund_a_id, fund_b_id, quarter)

    # KPI
    common_count = len(detail["common_holdings"])
    jaccard_current = (
        detail["jaccard_history"].iloc[0]["jaccard_score"]
        if not detail["jaccard_history"].empty
        else 0
    )
    reverse_count = len(detail["reverse_actions"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Common Holdings", common_count)
    c2.metric("Jaccard Score", f"{jaccard_current:.3f}")
    c3.metric("Reverse Actions", reverse_count, help="One fund NEW while the other SOLD")

    st.markdown("---")

    tabs = st.tabs(["Common Holdings", "Jaccard Trend", "Co-Moves", "Reverse Actions"])

    with tabs[0]:
        _render_common_holdings(detail["common_holdings"], fund_a_name, fund_b_name)
    with tabs[1]:
        _render_jaccard_trend(detail["jaccard_history"])
    with tabs[2]:
        _render_comoves(detail["common_add"], detail["common_reduce"])
    with tabs[3]:
        _render_reverse(detail["reverse_actions"], fund_a_name, fund_b_name)


def _render_common_holdings(df: pd.DataFrame, name_a: str, name_b: str) -> None:
    """共同持仓表格."""
    if df.empty:
        st.info("No common holdings.")
        return

    display = df.copy()
    display.columns = [
        "Ticker", "Name",
        f"Shares ({name_a})", f"Value ({name_a})", f"Weight% ({name_a})",
        f"Shares ({name_b})", f"Value ({name_b})", f"Weight% ({name_b})",
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)


def _render_jaccard_trend(df: pd.DataFrame) -> None:
    """Jaccard 历史趋势."""
    if df.empty:
        st.info("No Jaccard history available.")
        return

    fig_df = df.sort_values("quarter").copy()
    fig_df["Jaccard"] = fig_df["jaccard_score"]
    render_line_chart(fig_df, "quarter", "Jaccard", None, "Jaccard Similarity Over Time")

    st.dataframe(
        df[["quarter", "jaccard_score", "overlap_count"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "jaccard_score": st.column_config.NumberColumn("Jaccard", format="%.3f"),
        },
    )


def _render_comoves(add_df: pd.DataFrame, reduce_df: pd.DataFrame) -> None:
    """共同 ADD / REDUCE."""
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🟢 Common ADD (Both Increased)**")
        if add_df.empty:
            st.caption("No common ADD positions.")
        else:
            st.dataframe(add_df, use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**🔵 Common REDUCE (Both Decreased)**")
        if reduce_df.empty:
            st.caption("No common REDUCE positions.")
        else:
            st.dataframe(reduce_df, use_container_width=True, hide_index=True)


def _render_reverse(df: pd.DataFrame, name_a: str, name_b: str) -> None:
    """反向操作."""
    if df.empty:
        st.info("No reverse actions found.")
        return

    display = df.copy()
    display.columns = [
        "Ticker", f"Action ({name_a})", f"Action ({name_b})",
        f"Value Δ ({name_a})", f"Value Δ ({name_b})",
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown(
        "**Highlighted**: One fund opened a new position while the other closed it. "
        "These represent divergent convictions on the same stock."
    )
