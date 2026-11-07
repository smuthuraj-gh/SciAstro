"""The Planets Distance(%) chart (moved here from the Planets Cycles chart, then called Range): each chosen planet's distance D (-D) from the start (birth) to
the end (now), as the percentage between its least and greatest distance over 1800-2400 (0 = nearest, 100 = farthest)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import core
from .mapchart import FONT

# A fixed size, like the other charts: shown with mapchart.fit_html, so it zooms with the page as one picture
WIDTH, HEIGHT = 1100, 600
MARGIN = dict(l=60, r=30, t=30, b=110)


def distance_figure(dist_on: list[str], jd_from: float, jd_to: float) -> go.Figure:
    labels = [p for p in core.BUTTON_ORDER if p in dist_on]
    fig = go.Figure()
    if not labels or jd_to <= jd_from:
        fig.update_layout(width=WIDTH, height=HEIGHT, autosize=False, font=dict(size=FONT), annotations=[dict(text="Choose a planet's -D to draw it.", showarrow=False,
                                                        xref="paper", yref="paper", x=0.5, y=0.5)])
        return fig
    rows = core.range_rows(labels, jd_from, jd_to)
    t = [core.jd_to_datetime(j) for j in rows["jd"]]
    for p in labels:
        fig.add_trace(go.Scatter(x=t, y=rows[f"{p}-D"], mode="lines", name=f"{p}-D",
                                 line=dict(color=core.colour(p), width=1.5),
                                 hovertemplate=f"{p}-D %{{x|%Y-%m-%d %H:%M}}<br>D %{{y:.2f}}<extra></extra>"))
    fig.update_layout(
        width=WIDTH, height=HEIGHT, autosize=False, margin=dict(**MARGIN, autoexpand=False),
        plot_bgcolor="white", paper_bgcolor="white",
        # the legend's top 80 px under the grid: below the dates and the axis title, inside the chart
        legend=dict(orientation="h", yanchor="top", y=-80 / (HEIGHT - MARGIN["t"] - MARGIN["b"]),
                    font=dict(size=FONT)), hovermode="closest",
        font=dict(size=FONT), hoverlabel=dict(font_size=FONT),
        xaxis=dict(range=[core.jd_to_datetime(jd_from), core.jd_to_datetime(jd_to)],
                   title=dict(text="Year/Month/Date/Time (UT)", font=dict(size=FONT)), tickfont=dict(size=FONT),
                   showgrid=True, gridcolor="rgb(235,235,235)"),
        yaxis=dict(range=[-5, 105], tickvals=list(range(0, 101, 10)), tickfont=dict(size=FONT),
                   title=dict(text="Distance (%)", font=dict(size=FONT)),
                   gridcolor="rgb(235,235,235)"))
    return fig
