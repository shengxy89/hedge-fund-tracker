"""KPI 指标卡组件：4 列布局的标准化指标展示."""

from __future__ import annotations

import streamlit as st

from dashboard.utils.formatters import format_currency, format_delta, format_pct


def render_kpi_cards(metrics: list[dict]) -> None:
    """渲染一行 KPI 指标卡.

    Args:
        metrics: 每个 dict 包含 label, value, delta(可选), help(可选).
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            delta = m.get("delta")
            delta_str = None
            if delta is not None:
                if isinstance(delta, (int, float)):
                    delta_str = format_delta(delta, as_pct=True) if abs(delta) < 10 else format_delta(delta)
                else:
                    delta_str = str(delta)
            st.metric(
                label=m["label"],
                value=m["value"],
                delta=delta_str,
                help=m.get("help"),
            )


def kpi_overview_cards(kpi: dict) -> None:
    """Overview 首页的 4 个 KPI 卡.

    Args:
        kpi: get_overview_kpi() 返回的 dict.
    """
    total_value_str = format_currency(kpi.get("total_value", 0))
    delta_pct = kpi.get("value_change_pct")

    metrics = [
        {
            "label": "Tracking Funds",
            "value": f"{kpi.get('total_funds', 0)}",
            "help": f"Latest quarter: {kpi.get('quarter', '')}",
        },
        {
            "label": "Total Portfolio Value",
            "value": total_value_str,
            "delta": delta_pct,
            "help": "QoQ change based on aggregate holdings",
        },
        {
            "label": "New Positions This Quarter",
            "value": f"{kpi.get('new_stock_count', 0)}",
            "help": "Distinct stocks with NEW action",
        },
        {
            "label": "Most Crowded Stock",
            "value": kpi.get("crowded_ticker", "—") or "—",
            "delta": f"{kpi.get('crowded_count', 0)} holders",
            "help": "Stock held by the most funds",
        },
    ]
    render_kpi_cards(metrics)


def kpi_fund_cards(
    total_value: int,
    holding_count: int,
    top10_weight: float,
    turnover: float | None,
) -> None:
    """基金穿透页的 4 个 KPI 卡.

    Args:
        total_value: 总市值（千美元）.
        holding_count: 持仓数量.
        top10_weight: Top 10 集中度（小数）.
        turnover: 换手率（小数）.
    """
    metrics = [
        {"label": "Total Value", "value": format_currency(total_value)},
        {"label": "Holdings", "value": f"{holding_count}"},
        {
            "label": "Top 10 Concentration",
            "value": format_pct(top10_weight),
            "help": "Weight % of largest 10 positions",
        },
        {
            "label": "Turnover",
            "value": format_pct(turnover) if turnover is not None else "—",
            "help": "(NEW + SOLD) / total positions",
        },
    ]
    render_kpi_cards(metrics)


def kpi_stock_cards(
    holder_count: int,
    total_value: int,
    total_shares: int,
    crowding_rank: int | None,
) -> None:
    """个股穿透页的 4 个 KPI 卡.

    Args:
        holder_count: 持有基金数.
        total_value: 总持有市值（千美元）.
        total_shares: 总持有股数.
        crowding_rank: 拥挤度排名.
    """
    metrics = [
        {"label": "Holding Funds", "value": f"{holder_count}"},
        {"label": "Total Value", "value": format_currency(total_value)},
        {"label": "Total Shares", "value": f"{total_shares:,.0f}"},
        {
            "label": "Crowding Rank",
            "value": f"#{crowding_rank}" if crowding_rank else "—",
            "help": "Rank among all stocks by holder count",
        },
    ]
    render_kpi_cards(metrics)
