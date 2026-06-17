#!/usr/bin/env python3
"""多基金调仓共识信号视图

核心指标：weight_change_pct（权重变化百分比）作为跨基金可比指标，
聚合多基金对同一标的的共识调仓行为。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.data_access import get_consensus_fund_detail, get_consensus_kpi, get_consensus_signals
from dashboard.utils.formatters import format_currency, format_pct, get_action_badge


def _get_total_active_funds() -> int:
    """查询当前追踪中的基金总数（动态获取，避免硬编码）"""
    from sqlalchemy import text
    from db.engine import engine
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM funds WHERE is_active = 1")).scalar() or 1)


def _signal_strength_badge(score: float) -> str:
    """信号强度标签"""
    if score >= 20:
        return "🔥 极强"
    elif score >= 10:
        return "🔴 强"
    elif score >= 5:
        return "🟠 中等"
    return "🟡 弱"


def _crowding_badge(holder_count: int, crowding_score: float) -> str:
    """拥挤度标签（基于 crowding_score 比率判定，不依赖硬编码基金总数）"""
    score = crowding_score or 0
    if score >= 0.375:
        return f"🔥 高度拥挤 ({holder_count})"
    elif score >= 0.20:
        return f"🟠 中度拥挤 ({holder_count})"
    elif score >= 0.10:
        return f"🟡 轻度拥挤 ({holder_count})"
    return f"🟢 冷门 ({holder_count})"


def _weight_change_color(val: float) -> str:
    """权重变化颜色编码"""
    if val is None:
        return "color: gray;"
    if val >= 5:
        return "color: #16a34a; font-weight: 700;"  # 深绿
    if val >= 1:
        return "color: #22c55e; font-weight: 600;"  # 绿
    if val <= -5:
        return "color: #dc2626; font-weight: 700;"  # 深红
    if val <= -1:
        return "color: #ef4444; font-weight: 600;"  # 红
    return "color: #6b7280;"  # 灰


def _render_kpi_cards(kpi: dict) -> None:
    """渲染 KPI 卡片"""
    cols = st.columns(5)
    metrics = [
        ("共识信号总数", kpi.get("total", 0), "total"),
        ("共识建仓", kpi.get("new", 0), "delta_new"),
        ("共识清仓", kpi.get("sold", 0), "delta_sold"),
        ("共识增持", kpi.get("add", 0), "delta_add"),
        ("共识减持", kpi.get("reduce", 0), "delta_reduce"),
    ]
    for col, (label, value, key) in zip(cols, metrics):
        with col:
            st.metric(label, value)


def _render_signals_table(df: pd.DataFrame, quarter: str) -> None:
    """渲染共识信号表格"""
    if df.empty:
        st.info("该筛选条件下暂无共识信号。")
        return

    # 准备展示列
    display_df = df.copy()
    display_df["action_badge"] = display_df["action"].apply(get_action_badge)
    display_df["signal_badge"] = display_df["signal_score"].apply(_signal_strength_badge)

    # 拥挤度标签
    display_df["crowding_badge"] = display_df.apply(
        lambda r: _crowding_badge(int(r.get("holder_count", 0) or 0), r.get("crowding_score", 0) or 0),
        axis=1,
    )

    # 信号描述：一句话总结
    def _signal_desc(row):
        action = row["action"]
        fc = int(row["fund_count"])
        avg_wc = row["avg_weight_change_pct"]
        hc = int(row.get("holder_count", 0) or 0)
        cs = float(row.get("crowding_score", 0) or 0)

        if action == "NEW":
            if cs >= 0.20:
                return f"{fc}家基金**新建仓**已拥挤标的（共{hc}家持有，拥挤度{cs:.0%}）"
            elif cs >= 0.10:
                return f"{fc}家基金**新建仓**轻度拥挤标的（共{hc}家持有，拥挤度{cs:.0%}）"
            else:
                return f"{fc}家基金**新建仓**冷门标的（仅{hc}家持有，拥挤度{cs:.0%}）"
        elif action == "SOLD":
            return f"{fc}家基金**清仓**，原平均权重{abs(avg_wc):.1f}%"
        elif action == "ADD":
            return f"{fc}家基金**加仓**，平均增配{avg_wc:.1f}%权重"
        elif action == "REDUCE":
            return f"{fc}家基金**减仓**，平均减配{abs(avg_wc):.1f}%权重"
        return ""

    display_df["signal_desc"] = display_df.apply(_signal_desc, axis=1)

    # 选择展示列
    show_cols = [
        "action_badge", "ticker", "issuer", "sector",
        "fund_count", "avg_weight_change_pct", "total_weight_change_pct",
        "holder_count", "crowding_score", "signal_badge", "signal_desc",
        "fund_size_tier", "conviction_score",
    ]
    show_df = display_df[show_cols].copy()
    show_df.columns = [
        "动作", "代码", "标的", "板块",
        "基金数", "平均权重变化%", "总权重变化%",
        "持有基金数", "拥挤度", "信号强度", "信号描述",
        "基金规模", "置信度",
    ]

    st.dataframe(
        show_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "动作": st.column_config.TextColumn(width="small"),
            "代码": st.column_config.TextColumn(width="small"),
            "标的": st.column_config.TextColumn(width="medium"),
            "板块": st.column_config.TextColumn(width="small"),
            "基金数": st.column_config.NumberColumn(width="small"),
            "平均权重变化%": st.column_config.NumberColumn(
                width="small",
                format="%.2f%%",
            ),
            "总权重变化%": st.column_config.NumberColumn(
                width="small",
                format="%.2f%%",
            ),
            "持有基金数": st.column_config.NumberColumn(
                width="small",
                help="当前季度共有多少家基金持有该标的（含未调仓的基金）",
            ),
            "拥挤度": st.column_config.ProgressColumn(
                width="small",
                format="%.1%",
                min_value=0,
                max_value=1,
                help=f"持有基金数 / 总追踪基金数（当前 {_get_total_active_funds()} 家）",
            ),
            "信号强度": st.column_config.TextColumn(width="small"),
            "信号描述": st.column_config.TextColumn(width="large"),
            "基金规模": st.column_config.TextColumn(width="small"),
            "置信度": st.column_config.NumberColumn(width="small", format="%.1f"),
        },
    )

    # 展开查看基金明细
    st.markdown("---")
    st.subheader("🔍 标的基金明细")

    selected = st.selectbox(
        "选择标的查看参与基金",
        options=display_df["ticker"] + " — " + display_df["issuer"],
        index=0,
    )
    if selected:
        ticker = selected.split(" — ")[0]
        row = display_df[display_df["ticker"] == ticker].iloc[0]
        cusip = row["cusip"]

        # 显示该标的摘要
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("共识动作", row["action"])
        c2.metric("参与基金数", int(row["fund_count"]))
        c3.metric("当前持有基金数", int(row.get("holder_count", 0) or 0))
        c4.metric("拥挤度", f"{row.get('crowding_score', 0) or 0:.1%}")

        detail_df = get_consensus_fund_detail(quarter, cusip)
        if not detail_df.empty:
            detail_df["动作"] = detail_df["action"].apply(get_action_badge)
            detail_df["权重变化"] = detail_df["weight_change_pct"].apply(
                lambda x: format_pct(x, 2)
            )
            detail_df["原权重"] = detail_df["weight_prev"].apply(lambda x: format_pct(x, 2))
            detail_df["现权重"] = detail_df["weight_curr"].apply(lambda x: format_pct(x, 2))
            detail_df["金额变化"] = detail_df["value_change"].apply(format_currency)

            show_detail = detail_df[[
                "fund_name", "manager", "动作", "权重变化", "原权重", "现权重", "金额变化"
            ]].copy()
            show_detail.columns = ["基金", "经理", "动作", "权重变化", "原权重", "现权重", "金额变化"]

            # 使用样式高亮权重变化列
            def _style_weight_change(val):
                if isinstance(val, str) and "%" in val:
                    try:
                        num = float(val.replace("%", "").replace(",", ""))
                        if num > 0:
                            return "color: #16a34a; font-weight: 600;"
                        elif num < 0:
                            return "color: #dc2626; font-weight: 600;"
                    except ValueError:
                        pass
                return ""

            st.dataframe(
                show_detail.style.map(_style_weight_change, subset=["权重变化"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "权重变化": st.column_config.TextColumn(width="small"),
                    "原权重": st.column_config.TextColumn(width="small"),
                    "现权重": st.column_config.TextColumn(width="small"),
                },
            )
        else:
            st.info("暂无该基金明细数据。")


def render_consensus_view(quarter: str) -> None:
    """渲染共识信号视图主入口"""
    st.header("🎯 多基金调仓共识信号")
    st.caption(
        "基于 **weight_change_pct（权重变化百分比）** 聚合跨基金可比信号，"
        "识别多基金对同一标的的共识调仓行为。"
    )

    total_funds = _get_total_active_funds()

    # 说明
    with st.expander("📖 指标说明", expanded=False):
        st.markdown(f"""
        - **平均权重变化%**: 参与共识的基金，该标的权重变化的平均值。
          - NEW = 建仓后权重（原权重为0）
          - SOLD = -原权重（现权重为0）
          - ADD / REDUCE = 现权重 - 原权重
        - **持有基金数**: 当前季度**总共**有多少家基金持有该标的（不限于调仓的基金）。
        - **拥挤度**: 持有基金数 / 总追踪基金数（当前 {total_funds} 家）。
          - 🔥 ≥37.5%: 高度拥挤
          - 🟠 ≥20%: 中度拥挤
          - 🟡 ≥10%: 轻度拥挤
          - 🟢 <10%: 冷门标的
        - **信号强度** = 参与基金数 × |平均权重变化%|
        """)

    # KPI 卡片
    kpi = get_consensus_kpi(quarter)
    _render_kpi_cards(kpi)

    st.markdown("---")

    # 筛选控件
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        action_filter = st.selectbox(
            "动作类型",
            options=["全部", "NEW", "SOLD", "ADD", "REDUCE"],
            index=0,
        )
    with col2:
        min_funds = st.slider("最少参与基金数", min_value=2, max_value=10, value=3)
    with col3:
        min_score = st.slider("最小信号强度", min_value=0.0, max_value=50.0, value=0.0, step=1.0)
    with col4:
        top_n = st.slider("显示数量", min_value=10, max_value=100, value=50, step=10)

    action = None if action_filter == "全部" else action_filter

    # 查询共识信号
    df = get_consensus_signals(
        quarter=quarter,
        action=action,
        min_funds=min_funds,
        min_score=min_score,
        top_n=top_n,
    )

    # 渲染表格
    _render_signals_table(df, quarter)
