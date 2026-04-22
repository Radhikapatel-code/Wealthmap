from __future__ import annotations

import plotly.express as px
import pandas as pd


def asset_class_pie(asset_class_breakdown: dict[str, float]):
    frame = pd.DataFrame(
        [{"asset_class": key, "value_inr": value} for key, value in asset_class_breakdown.items()]
    )
    if frame.empty:
        return px.pie(title="No data")
    return px.pie(frame, names="asset_class", values="value_inr", title="Asset Class Mix")


def member_net_worth_bar(member_breakdown: list[dict]):
    frame = pd.DataFrame(member_breakdown)
    if frame.empty:
        return px.bar(title="No data")
    return px.bar(frame, x="name", y="net_worth_inr", color="name", title="Family Net Worth by Member")


def ltcg_timeline(events: list[dict]):
    frame = pd.DataFrame(events)
    if frame.empty:
        return px.scatter(title="No upcoming unlocks")
    frame["unlock_date"] = pd.to_datetime(frame["unlock_date"])
    return px.scatter(
        frame,
        x="unlock_date",
        y="tax_saving_if_waited_inr",
        color="member_id",
        hover_name="symbol",
        title="Upcoming LTCG Unlock Events",
    )
