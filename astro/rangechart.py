"""The Range chart (as the workbook's Range tab): each chosen planet's Dec (-M, left axis) and distance D (-D, dashed,
right axis) from the start (birth) to the end (now), with dots where two -M planets come into an aspect (EA-C, EA-S,
EA-Q, EA-T, EA-O) joined pair by pair and tagged."""
from __future__ import annotations

import plotly.graph_objects as go

from . import core

DOT_COLOUR = {0: "rgb(0,0,0)", 180: "rgb(128,128,128)", 90: "rgb(150,75,0)", 120: "rgb(199,21,133)", 60: "rgb(0,128,128)"}
EA_NAME = {0: "EA-C", 60: "EA-S", 90: "EA-Q", 120: "EA-T", 180: "EA-O"}
MAX_TAGS = 300                                         # more aspects of one kind than this: no tags


def range_figure(dec_on: list[str], dist_on: list[str], ea_on: list[int], jd_from: float, jd_to: float,
                 orbs: core.Orbs) -> tuple[go.Figure, str]:
    """The chart and a note ("" or why some tags are missing)."""
    labels = [p for p in core.BUTTON_ORDER if p in set(dec_on) | set(dist_on)]
    fig = go.Figure()
    note = ""
    if not labels or jd_to <= jd_from:
        fig.update_layout(height=520, annotations=[dict(text="Turn on a planet's -M or -D to draw it.", showarrow=False,
                                                        xref="paper", yref="paper", x=0.5, y=0.5)])
        return fig, note
    rows = core.range_rows(labels, jd_from, jd_to)
    t = [core.jd_to_datetime(j) for j in rows["jd"]]
    for p in core.BUTTON_ORDER:
        if p in dec_on:
            fig.add_trace(go.Scatter(x=t, y=rows[f"{p}-De"], mode="lines", name=f"{p}-M", line=dict(color=core.colour(p), width=1.5),
                                     hovertemplate=f"{p}-M %{{x|%Y-%m-%d %H:%M}}<br>Dec %{{y:+.2f}}<extra></extra>"))
    for p in core.BUTTON_ORDER:
        if p in dist_on:
            fig.add_trace(go.Scatter(x=t, y=rows[f"{p}-D"], mode="lines", name=f"{p}-D", yaxis="y2",
                                     line=dict(color=core.colour(p), width=1.5, dash="dash"),
                                     hovertemplate=f"{p}-D %{{x|%Y-%m-%d %H:%M}}<br>D %{{y:.2f}}<extra></extra>"))
    events = core.aspect_events([p for p in labels if p in dec_on], jd_from, jd_to, ea_on, orbs)
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
                                     mode="text", text=[f"<b>{e.title}</b>" for e in ev], textfont=dict(size=12),
                                     textposition="middle right", hoverinfo="skip", showlegend=False))
        else:
            note = f"Too many {EA_NAME[ang]} aspects to tag: choose a shorter period."
    start, end = core.jd_to_datetime(jd_from), core.jd_to_datetime(jd_to)
    fig.update_layout(
        height=560, margin=dict(l=60, r=70, t=30, b=40), plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=-0.18), hovermode="closest",
        xaxis=dict(range=[start, end], title="Year/Month/Date/Time (UT)", showgrid=True, gridcolor="rgb(235,235,235)"),
        yaxis=dict(range=[-30, 30], dtick=5, title="Dec (degrees)", tickformat="+d", zeroline=True,
                   zerolinecolor="rgb(200,200,200)", gridcolor="rgb(235,235,235)"),
        yaxis2=dict(range=[-10, 110], dtick=10, title="Distance (%)", overlaying="y", side="right", showgrid=False,
                    tickvals=list(range(0, 101, 10))))
    return fig, note
