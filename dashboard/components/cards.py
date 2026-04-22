from __future__ import annotations

import streamlit as st


def metric_row(metrics: list[tuple[str, str]]) -> None:
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)
