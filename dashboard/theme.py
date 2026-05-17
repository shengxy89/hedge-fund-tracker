"""Dashboard 全局主题配置：配色、Plotly 模板、Streamlit CSS 注入."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# =============================================================================
# 配色常量 — 机构级深色专业风
# =============================================================================

PRIMARY_BLUE: str = "#1F4E78"
ACCENT_GREEN: str = "#2E7D32"
ACCENT_RED: str = "#C62828"
NEUTRAL_GREY: str = "#9E9E9E"
BG_LIGHT: str = "#FAFAFA"
BG_DARK: str = "#1E1E1E"
TEXT_PRIMARY: str = "#212121"
TEXT_SECONDARY: str = "#616161"
PUT_PURPLE: str = "#7B1FA2"
CALL_ORANGE: str = "#F57C00"
WHITE: str = "#FFFFFF"
BORDER_LIGHT: str = "#E0E0E0"

# Action 颜色映射
ACTION_COLORS: dict[str, str] = {
    "NEW": ACCENT_GREEN,
    "ADD": "#66BB6A",
    "HOLD": NEUTRAL_GREY,
    "REDUCE": "#EF5350",
    "SOLD": ACCENT_RED,
}

# Sector 颜色映射 (GICS 11 大类)
SECTOR_COLORS: dict[str, str] = {
    "Information Technology": "#1976D2",
    "Health Care": "#D32F2F",
    "Financials": "#388E3C",
    "Consumer Discretionary": "#F57C00",
    "Communication Services": "#7B1FA2",
    "Industrials": "#5D4037",
    "Consumer Staples": "#00796B",
    "Energy": "#E65100",
    "Utilities": "#FBC02D",
    "Real Estate": "#C2185B",
    "Materials": "#455A64",
    "Unknown": NEUTRAL_GREY,
}

# Heatmap diverging colorscale (RdYlGn 风格的自定义)
HEATMAP_DIVERGING: list[list[float | str]] = [
    [0.0, ACCENT_RED],
    [0.25, "#FFCDD2"],
    [0.5, NEUTRAL_GREY],
    [0.75, "#C8E6C9"],
    [1.0, ACCENT_GREEN],
]

# =============================================================================
# Plotly 统一模板注册
# =============================================================================

_PLOTLY_TEMPLATE: dict[str, Any] = {
    "layout": {
        "font": {"family": "Inter, -apple-system, BlinkMacSystemFont, sans-serif", "size": 12},
        "title": {"font": {"size": 16, "color": TEXT_PRIMARY}, "x": 0.02},
        "paper_bgcolor": WHITE,
        "plot_bgcolor": WHITE,
        "margin": {"l": 60, "r": 40, "t": 60, "b": 40},
        "colorway": list(SECTOR_COLORS.values()),
        "xaxis": {
            "gridcolor": BORDER_LIGHT,
            "linecolor": BORDER_LIGHT,
            "tickfont": {"size": 11, "color": TEXT_SECONDARY},
        },
        "yaxis": {
            "gridcolor": BORDER_LIGHT,
            "linecolor": BORDER_LIGHT,
            "tickfont": {"size": 11, "color": TEXT_SECONDARY},
        },
        "legend": {
            "font": {"size": 11, "color": TEXT_SECONDARY},
            "bgcolor": "rgba(255,255,255,0.8)",
        },
        "hoverlabel": {
            "bgcolor": TEXT_PRIMARY,
            "font": {"family": "Inter, sans-serif", "size": 13, "color": WHITE},
            "bordercolor": TEXT_PRIMARY,
        },
    },
    "data": {
        "heatmap": [{"colorscale": HEATMAP_DIVERGING, "zmid": 0}],
        "bar": [{"marker": {"line": {"width": 0}}}],
        "pie": [{"textfont": {"size": 11}, "insidetextfont": {"size": 11}}],
    },
}


def register_plotly_template() -> None:
    """注册自定义 Plotly 模板 'alpha_tracker' 并设为默认."""
    pio.templates["alpha_tracker"] = go.layout.Template(_PLOTLY_TEMPLATE)
    pio.templates.default = "plotly_white+alpha_tracker"


# =============================================================================
# Streamlit CSS 注入
# =============================================================================

_CUSTOM_CSS: str = """
<style>
    /* 全局字体 */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* KPI 卡片容器 */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    /* 标题字号微调 */
    h1 {
        font-size: 1.6rem !important;
        font-weight: 600 !important;
        color: #212121 !important;
    }
    h2 {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        color: #212121 !important;
    }
    h3 {
        font-size: 1.05rem !important;
        font-weight: 500 !important;
        color: #424242 !important;
    }

    /* 隐藏 Plotly modebar 中的 lasso/select */
    .modebar-btn[data-val="lasso2d"],
    .modebar-btn[data-val="select2d"] {
        display: none !important;
    }

    /* 表格 hover 行高亮 */
    .stDataFrame tbody tr:hover {
        background-color: #F5F5F5 !important;
    }

    /* 侧边栏标题 */
    .css-1d391kg h1 {
        font-size: 1.1rem !important;
    }
</style>
"""


def inject_custom_css() -> None:
    """向 Streamlit 注入自定义 CSS."""
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# 初始化入口
# =============================================================================

def init_theme() -> None:
    """一键初始化主题：注册 Plotly 模板 + 注入 CSS."""
    register_plotly_template()
    inject_custom_css()
