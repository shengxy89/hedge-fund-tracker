"""导出工具：CSV / PNG / 简单文本报告."""

from __future__ import annotations

import base64

import pandas as pd
import streamlit as st


def to_csv_download(df: pd.DataFrame, filename: str = "export.csv") -> str:
    """将 DataFrame 转为 CSV 下载链接.

    Args:
        df: 数据.
        filename: 下载文件名.

    Returns:
        HTML <a> 标签字符串.
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">⬇️ Download CSV</a>'
    return href


def render_csv_download_button(df: pd.DataFrame, filename: str = "export.csv") -> None:
    """渲染 CSV 下载按钮."""
    if df.empty:
        return
    csv = df.to_csv(index=False)
    st.download_button(
        label="⬇️ Export CSV",
        data=csv,
        file_name=filename,
        mime="text/csv",
    )


def render_pdf_placeholder(title: str = "Report") -> None:
    """PDF 导出占位（预留接口）."""
    st.caption(f"📄 PDF export for '{title}' will be available in a future release.")
