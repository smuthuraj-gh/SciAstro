"""The Planets Cycles chart (the workbook's Range tab; the page was called Range): each chosen planet's Dec (-M) from the start (birth) to the end (now),
with dots where two -M planets come into an aspect (Co, Sx, Sq, Tr, Op) joined pair by pair and tagged.
The distance lines (-D) have their own chart (distancechart.py)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import core

DOT_COLOUR = {0: "rgb(0,0,0)", 180: "rgb(128,128,128)", 90: "rgb(150,75,0)", 120: "rgb(199,21,133)", 60: "rgb(0,128,128)"}
EA_NAME = {0: "Co", 60: "Sx", 90: "Sq", 120: "Tr", 180: "Op"}     # the workbook's EA-C, EA-S, EA-Q, EA-T, EA-O
MAX_TAGS = 300                                         # more aspects of one kind than this: no tags


def range_figure(dec_on: list[str], ea_on: list[int], jd_from: float, jd_to: float,
                 orbs: core.Orbs) -> tuple[go.Figure, str]:
    """The chart and a note ("" or why some tags are missing)."""
    labels = [p for p in core.BUTTON_ORDER if p in dec_on]
    fig = go.Figure()
    note = ""
    if not labels or jd_to <= jd_from:
        fig.update_layout(height=520, annotations=[dict(text="Choose a planet's -M to draw it.", showarrow=False,
                                                        xref="paper", yref="paper", x=0.5, y=0.5)])
        return fig, note
    rows = core.range_rows(labels, jd_from, jd_to)
    t = [core.jd_to_datetime(j) for j in rows["jd"]]
    for p in labels:
        fig.add_trace(go.Scatter(x=t, y=rows[f"{p}-De"], mode="lines", name=f"{p}-M", line=dict(color=core.colour(p), width=1.5),
                                 hovertemplate=f"{p}-M %{{x|%Y-%m-%d %H:%M}}<br>Dec %{{y:+.2f}}<extra></extra>"))
    events = core.aspect_events(labels, jd_from, jd_to, ea_on, orbs)
    for ang in (0, 60, 90, 120, 180):
        ev = [e for e in events if e.angle == ang]
        if not ev:
            continue
        xs, ys, hov = [], [], []
        for e in ev:
            when = core.jd_to_datetime(e.jd)
            xs += [when, when, None]; ys += [e.de1, e.de2, None]; hov += [e.title, e.title, None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=EA_NAME[ang], hovertext=hov,
                                 hovertemplate="%{hovertext}<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
                                 marker=dict(size=7, color=DOT_COLOUR[ang]), line=dict(color=DOT_COLOUR[ang], width=1),
                                 connectgaps=False))
        if len(ev) <= MAX_TAGS:
            fig.add_trace(go.Scatter(x=[core.jd_to_datetime(e.jd) for e in ev], y=[(e.de1 + e.de2) / 2 for e in ev],
                                     mode="text", text=[f"<b>{e.title}</b>" for e in ev], textfont=dict(size=11),
                                     textposition="middle right", hoverinfo="skip", showlegend=False))
        else:
            note = f"Too many {EA_NAME[ang]} aspects to tag: choose a shorter period."
    start, end = core.jd_to_datetime(jd_from), core.jd_to_datetime(jd_to)
    fig.update_layout(
        height=560, margin=dict(l=60, r=30, t=30, b=40), plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=-0.18), hovermode="closest",
        xaxis=dict(range=[start, end], title="Year/Month/Date/Time (UT)", showgrid=True, gridcolor="rgb(235,235,235)"),
        yaxis=dict(range=[-30, 30], dtick=5, title="Declination", tickformat="+d", zeroline=True,
                   zerolinecolor="rgb(200,200,200)", gridcolor="rgb(235,235,235)"))
    return fig, note
