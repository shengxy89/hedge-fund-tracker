"""通用图表组件 — Plotly 封装."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.theme import SECTOR_COLORS


def render_pie_chart(
    df: pd.DataFrame,
    names_col: str,
    values_col: str,
    title: str,
    hole: float = 0.4,
) -> None:
    """渲染环形图."""
    if df.empty:
        st.info("No data available")
        return
    fig = px.pie(
        df,
        names=names_col,
        values=values_col,
        title=title,
        hole=hole,
        color=names_col,
        color_discrete_map=SECTOR_COLORS,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        insidetextfont_size=10,
    )
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, use_container_width=True)


def render_line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None,
    title: str,
    height: int = 500,
) -> None:
    """渲染折线图."""
    if df.empty:
        st.info("No data available")
        return
    if color:
        fig = px.line(df, x=x, y=y, color=color, title=title, markers=True)
    else:
        fig = px.line(df, x=x, y=y, title=title, markers=True)
    fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True)


def render_stacked_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    title: str,
    height: int = 500,
) -> None:
    """渲染堆叠柱状图."""
    if df.empty:
        st.info("No data available")
        return
    fig = px.bar(df, x=x, y=y, color=color, title=title)
    fig.update_layout(barmode="stack", height=height)
    st.plotly_chart(fig, use_container_width=True)


def render_heatmap(
    matrix: pd.DataFrame,
    title: str,
    colorscale: str = "RdYlGn",
    hover_texts: pd.DataFrame | None = None,
    zmid: float | None = 0,
) -> None:
    """渲染热力图."""
    if matrix.empty:
        st.info("No data available")
        return

    customdata = None
    hovertemplate = "Fund: %{y}<br>Stock: %{x}<br>Value: %{z}<extra></extra>"

    if hover_texts is not None:
        hover_texts = hover_texts.reindex(index=matrix.index, columns=matrix.columns)
        customdata = hover_texts.fillna("No data").values
        hovertemplate = "<b>%{y}</b> × <b>%{x}</b><br>%{customdata}<extra></extra>"

    fig = go.Figure(
        data=go.Heatmap(
            z=matrix.values,
            x=matrix.columns,
            y=matrix.index,
            colorscale=colorscale,
            zmid=zmid,
            customdata=customdata,
            hovertemplate=hovertemplate,
        )
    )
    fig.update_layout(
        title=title,
        height=max(600, len(matrix) * 18),
        xaxis_tickfont_size=10,
        yaxis_tickfont_size=10,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_horizontal_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str = "",
    color_map: dict[str, str] | None = None,
    height: int = 400,
) -> None:
    """渲染横向柱状图（Top N 排名用）."""
    if df.empty:
        st.info("No data available")
        return
    fig = px.bar(
        df,
        x=x,
        y=y,
        orientation="h",
        color=color if color else None,
        color_discrete_map=color_map or SECTOR_COLORS,
        title=title,
    )
    fig.update_layout(height=height, yaxis_categoryorder="total ascending")
    st.plotly_chart(fig, use_container_width=True)


def render_area_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    title: str,
    height: int = 400,
) -> None:
    """渲染堆叠面积图（板块轮动用）."""
    if df.empty:
        st.info("No data available")
        return
    fig = px.area(df, x=x, y=y, color=color, title=title)
    fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True)
