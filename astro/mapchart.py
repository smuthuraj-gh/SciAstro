"""The Map chart (as the workbook's Map tab): the planets at birth and now over a world map where Dec = latitude and
RA = longitude + the sky's turn (the sidereal time at Greenwich at birth; now, with Now alone), so CB falls on the
birth place. Birth: filled marks, dashed house lines from CB; Now: hollow marks, dotted lines, solid house lines
from CN. Aspect lines: major (black) and minor (grey), dotted for now. Hovering a mark shows its RA, Dec and D."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from . import core

H = core.ra_de_height


@lru_cache(maxsize=1)
def coastlines() -> pd.DataFrame:
    return pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "coastlines.csv")


def world_map_xy(turn: float) -> tuple[list, list]:
    """The coastlines moved by turn into 0..360 (a line crossing the edge is cut there), heights as the chart's."""
    xs, ys = [], []
    have = False
    px = py = 0.0
    for lon, lat in coastlines().itertuples(index=False):
        if pd.isna(lon):
            xs.append(None); ys.append(None); have = False
            continue
        x, y = core.norm360(lon + turn), H(lat)
        if have and abs(x - px) > 180.0:
            edge = 360.0 if px > x else 0.0
            far = x + 360.0 if px > x else x - 360.0
            ym = py + (edge - px) / (far - px) * (y - py)
            xs += [edge, None, 360.0 - edge]; ys += [ym, None, ym]
        xs.append(x); ys.append(y)
        px, py, have = x, y, True
    return xs, ys


@dataclass
class MapInput:
    birth: dict[str, tuple[float, float]] | None     # Sa .. Mo and CB, or None
    now: dict[str, tuple[float, float]] | None       # Sa .. Mo now, or None
    cn: tuple[float, float] | None                   # City-N (lat, lon), or None
    jd_birth: float | None
    jd_now: float
    d_birth: dict[str, float]                        # D at birth per planet
    d_now: dict[str, float]                          # D-N per planet
    show_birth: bool = True
    show_now: bool = False
    major: bool = True
    minor: bool = True


def _house_lines(fig: go.Figure, ra10: float, is_now: bool):
    tag_y = -87.0 if is_now else 87.0
    sfx = "-N" if is_now else ""
    for k in range(12):
        x = core.norm360(ra10 + 30.0 * k)
        name = f"H{(9 + k) % 12 + 1:02d}{sfx}"
        fig.add_trace(go.Scatter(x=[x, x], y=[-90, 90], mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color="black", width=1.5 if is_now else 1.75,
                                           dash="solid" if is_now else "dash")))
        fig.add_annotation(x=x, y=tag_y + (5 if is_now else -5), text=f"{x:.1f}", showarrow=False, font=dict(size=9),
                           xanchor="right" if x > 341 else "left", xshift=-2 if x > 341 else 2)
        mid = min(max(core.norm360(x + 15.0), 4.0), 356.0)
        fig.add_annotation(x=mid, y=tag_y, text=f"<b>{name}</b>", showarrow=False, font=dict(size=9))


def _point_lines(fig: go.Figure, name: str, ra: float | None, de: float, is_now: bool):
    c = core.colour(name)
    dash = "dot" if is_now else "solid"
    if ra is not None:                                       # CB and CN have no vertical line
        fig.add_trace(go.Scatter(x=[ra, ra], y=[-90, 90], mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color=c, width=0.75, dash=dash)))
    fig.add_trace(go.Scatter(x=[0, 360], y=[H(de), H(de)], mode="lines", hoverinfo="skip", showlegend=False,
                             line=dict(color=c, width=0.75, dash=dash)))
    fig.add_annotation(x=360, y=H(de), text=f"{'<b>' if is_now else ''}{de:+.1f}{'</b>' if is_now else ''}",
                       showarrow=False, xanchor="left", xshift=3, font=dict(size=9, color=c))
    if ra is not None:
        fig.add_annotation(x=ra, y=90, text=f"{'<b>' if is_now else ''}{ra:.1f}{'</b>' if is_now else ''}",
                           showarrow=False, yanchor="bottom", yshift=2, font=dict(size=9, color=c))


def _aspect_line(fig: go.Figure, a: core.AspectLine, is_now: bool, minor: bool):
    ys = [H(v) for v in a.ys]
    xs = list(a.xs)
    for shift in (0.0, -360.0, 360.0):                       # drawn on both sides when it crosses the edge
        sx = [x + shift for x in xs]
        if max(sx) < 0 or min(sx) > 360:
            continue
        fig.add_trace(go.Scatter(x=sx, y=ys, mode="lines", hoverinfo="text", hovertext=a.title, showlegend=False,
                                 line=dict(color="rgb(110,110,110)" if minor else "black", width=1 if minor else 1.5,
                                           dash="dot" if is_now else "solid")))
        mx, my = sum(sx) / len(sx), sum(ys) / len(ys)
        if 0 <= mx <= 360:
            fig.add_annotation(x=mx, y=my, text=f"<b>{a.title}</b>", showarrow=False, font=dict(size=10),
                               bgcolor="rgba(255,255,255,0.75)", xshift=0, yshift=10)


def map_figure(m: MapInput, orbs: core.Orbs) -> go.Figure:
    fig = go.Figure()
    turn = 0.0
    if m.jd_birth is not None:
        turn = core.lst(m.jd_birth, 0.0)
    if m.show_now and not m.show_birth and m.cn is not None:
        turn = core.lst(m.jd_now, 0.0)

    xs, ys = world_map_xy(turn)                               # the world map first, under everything
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="rgb(150,150,150)", width=1),
                             hoverinfo="skip", showlegend=False, connectgaps=False))
    for lon in range(-165, 181, 15):                          # longitudes along the bottom
        fig.add_annotation(x=core.norm360(lon + turn), y=-90, yanchor="top", yshift=-2, showarrow=False,
                           font=dict(size=9), text=str(lon) if lon in (0, 180) else f"{abs(lon)}{'W' if lon < 0 else 'E'}")

    birth = m.birth if (m.show_birth and m.birth) else {}
    now = m.now if (m.show_now and m.now) else {}
    for n, (ra, de) in birth.items():
        _point_lines(fig, n, None if n == "CB" else ra, de, False)
    for n, (ra, de) in now.items():
        _point_lines(fig, n + "-N", ra, de, True)
    cn_x = None
    if m.show_now and m.cn is not None:
        cn_x = core.norm360(m.cn[1] + turn)
        _point_lines(fig, "CN", None, m.cn[0], True)

    if birth:
        for a in core.all_aspects(birth, orbs, False, major=m.major, minor=m.minor):
            _aspect_line(fig, a, False, a.angle in core.MINOR)
        _house_lines(fig, birth["CB"][0], False)
    if now:
        for a in core.all_aspects(now, orbs, True, major=m.major, minor=m.minor):
            _aspect_line(fig, a, True, a.angle in core.MINOR)
    if m.show_now and m.cn is not None:
        _house_lines(fig, core.lst(m.jd_now, m.cn[1]), True)

    def mark(name: str, x: float, de: float, symbol: str, hollow: bool, d_txt: str):
        c = core.colour(name)
        fig.add_trace(go.Scatter(
            x=[x], y=[H(de)], mode="markers+text", name=name, text=[f"<b>{name}</b>"], textposition="top center",
            marker=dict(symbol=symbol, size=11, color="white" if hollow else c, line=dict(color=c, width=2)),
            hovertemplate=f"<b>{name}</b><br>RA {x:.2f}<br>Dec {de:+.2f}{d_txt}<extra></extra>"))

    for n, (ra, de) in birth.items():
        d = m.d_birth.get(n)
        mark(n, ra, de, "diamond" if n == "CB" else "circle", False, f"<br>D {d:.2f}" if d is not None else "")
    for n, (ra, de) in now.items():
        d = m.d_now.get(n)
        mark(n + "-N", ra, de, "circle", True, f"<br>D-N {d:.2f}" if d is not None else "")
    if cn_x is not None:
        mark("CN", cn_x, m.cn[0], "triangle-up", False, f"<br>lat {m.cn[0]:+.2f}, lon {m.cn[1]:+.2f}")

    if birth or now:                                          # names the RA numbers printed above the 90N line
        fig.add_annotation(xref="paper", x=0.5, xanchor="center", y=90, yanchor="bottom", yshift=16,
                           text="<b>Planets RA</b>", showarrow=False, font=dict(size=11))
        # names the Dec numbers printed right of the 360 line: a side title past them, like the left axis title
        fig.add_annotation(xref="paper", x=1, xanchor="left", xshift=44, yref="paper", y=0.5, yanchor="middle",
                           textangle=90, text="<b>Planets Declination</b>", showarrow=False, font=dict(size=11))

    lat_ticks = list(range(-90, 91, 15))
    fig.update_layout(
        height=660, margin=dict(l=60, r=75, t=40, b=60), plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=-0.12), hovermode="closest", dragmode="zoom",
        xaxis=dict(range=[0, 360], showgrid=False, zeroline=False, title="Longitude / Right Ascension (RA)",
                   tickvals=list(range(0, 361, 30)), mirror=True, linecolor="rgb(134,134,134)"),
        yaxis=dict(range=[-90, 90], showgrid=False, zeroline=False, title="Latitude / Declination",
                   tickvals=[H(v) for v in lat_ticks],
                   ticktext=["0" if v == 0 else f"{abs(v)}{'S' if v < 0 else 'N'}" for v in lat_ticks],
                   mirror=True, linecolor="rgb(134,134,134)"))
    return fig
