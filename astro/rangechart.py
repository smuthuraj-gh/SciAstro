"""The Planets Cycles chart (the workbook's Range tab; the page was called Range): each chosen planet's Dec (-M) from the start (birth) to the end (now),
with dots where two -M planets come into an aspect (0°, 60°, 90°, 120°, 180°) joined pair by pair and tagged.
The distance lines (-D) have their own chart (distancechart.py)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import core
from .mapchart import FONT, Spots

DOT_COLOUR = {0: "rgb(0,0,0)", 180: "rgb(128,128,128)", 90: "rgb(150,75,0)", 120: "rgb(199,21,133)", 60: "rgb(0,128,128)"}
EA_NAME = {a: f"{a}°" for a in (0, 60, 90, 120, 180)}  # the workbook's EA-C, EA-S, EA-Q, EA-T, EA-O
MAX_PLACED = 1500                                      # more aspects than this: the later ones are not tagged
# A fixed size (scaled down whole to fit a narrower column), so each tag's place is known in pixels and kept clear
WIDTH, HEIGHT = 1100, 600
MARGIN = dict(l=60, r=30, t=20, b=110)
PLOT_W, PLOT_H = WIDTH - MARGIN["l"] - MARGIN["r"], HEIGHT - MARGIN["t"] - MARGIN["b"]


def range_figure(dec_on: list[str], ea_on: list[int], jd_from: float, jd_to: float,
                 orbs: core.Orbs) -> tuple[go.Figure, str]:
    """The chart and a note ("" or why some tags are missing)."""
    labels = [p for p in core.BUTTON_ORDER if p in dec_on]
    fig = go.Figure()
    note = ""
    if not labels or jd_to <= jd_from:
        fig.update_layout(width=WIDTH, height=HEIGHT, autosize=False, font=dict(size=FONT),
                          annotations=[dict(text="Choose a planet to draw it.", showarrow=False,
                                            xref="paper", yref="paper", x=0.5, y=0.5)])
        return fig, note
    rows = core.range_rows(labels, jd_from, jd_to)
    t = [core.jd_to_datetime(j) for j in rows["jd"]]
    for p in labels:
        fig.add_trace(go.Scatter(x=t, y=rows[f"{p}-De"], mode="lines", name=f"{core.symbol_of(p)}-M", line=dict(color=core.colour(p), width=1.5),
                                 hovertemplate=f"{core.symbol_of(p)}-M %{{x|%Y-%m-%d %H:%M}}<br>Dec %{{y:+.2f}}<extra></extra>"))
    events = core.aspect_events(labels, jd_from, jd_to, ea_on, orbs)
    for ang in (0, 60, 90, 120, 180):
        ev = [e for e in events if e.angle == ang]
        if not ev:
            continue
        xs, ys, hov = [], [], []
        for e in ev:
            when = core.jd_to_datetime(e.jd)
            xs += [when, when, None]; ys += [e.de1, e.de2, None]; hov += [core.with_symbols(e.title)] * 2 + [None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=EA_NAME[ang], hovertext=hov,
                                 hovertemplate="%{hovertext}<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
                                 marker=dict(size=7, color=DOT_COLOUR[ang]), line=dict(color=DOT_COLOUR[ang], width=1),
                                 connectgaps=False))

    # Each aspect's tag in the first free place beside its dots (none on another tag or a dot); a tag with no free
    # place is left off and shows when the pointer is on its dot
    span = jd_to - jd_from
    spots = Spots(PLOT_W, PLOT_H, lambda jd, y: ((jd - jd_from) / span * PLOT_W, (y + 30.0) / 60.0 * PLOT_H))
    events = sorted(events, key=lambda e: e.jd)
    for e in events:
        for y in (e.de1, e.de2):
            spots.boxes.append(spots.box(e.jd, y, "", w=10, h=10))
    placed = 0
    for e in events[:MAX_PLACED]:
        lo, hi = sorted((e.de1, e.de2))
        ys = [(lo + hi) / 2, lo + (hi - lo) / 4, hi - (hi - lo) / 4, lo, hi]
        tries = [(e.jd, y, xa, "middle", dx, dy) for dy in (0, 13, -13, 26, -26) for y in ys
                 for xa, dx in (("left", 6), ("right", -6))]
        text = f"<b>{core.with_symbols(e.title)}</b>"
        for jd, y, xa, ya, dx, dy in tries:
            b = spots.box(jd, y, text, xa, ya, dx, dy)
            if spots.free(b):
                spots.boxes.append(b)
                fig.add_annotation(x=core.jd_to_datetime(jd), y=y, text=text, showarrow=False, xanchor=xa,
                                   yanchor=ya, xshift=dx, yshift=dy, font=dict(size=FONT))
                placed += 1
                break
    if placed < len(events):
        note = (f"{len(events) - placed} of {len(events)} aspect tags are left off where there is no room; point at "
                "a dot to see its aspect, or choose a shorter period.")
    start, end = core.jd_to_datetime(jd_from), core.jd_to_datetime(jd_to)
    fig.update_layout(
        width=WIDTH, height=HEIGHT, autosize=False, margin=dict(**MARGIN, autoexpand=False),
        plot_bgcolor="white", paper_bgcolor="white",
        # the legend's top 80 px under the grid: below the dates and the axis title, inside the chart
        legend=dict(orientation="h", yanchor="top", y=-80 / PLOT_H, font=dict(size=FONT)), hovermode="closest",
        font=dict(size=FONT), hoverlabel=dict(font_size=FONT),
        xaxis=dict(range=[start, end], title=dict(text="Year/Month/Date/Time (UT)", font=dict(size=FONT)),
                   tickfont=dict(size=FONT),
                   showgrid=True, gridcolor="rgb(235,235,235)",
                   ticklabelstandoff=8),                 # the first date clear of the -30 beside the corner
        yaxis=dict(range=[-30, 30], dtick=5, title=dict(text="Declination", font=dict(size=FONT)), tickformat="+d",
                   tickfont=dict(size=FONT),
                   zeroline=True,
                   ticklabelstandoff=6,                   # clear of dots on the chart's left edge
                   zerolinecolor="rgb(200,200,200)", gridcolor="rgb(235,235,235)"))
    return fig, note
