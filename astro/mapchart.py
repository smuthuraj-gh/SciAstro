"""The Map chart (as the workbook's Map tab): the planets at birth and now over a world map where Dec = latitude and
RA = longitude + the sky's turn (the sidereal time at Greenwich at birth; now, with Now alone), so CB falls on the
birth place. Birth: filled marks, solid house lines from CB; Now: hollow marks, dotted lines, semi-solid (long-dash)
house lines from CN. Aspect lines: major (black) and minor (grey), dotted for now. Hovering a mark shows its RA, Dec and D."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from . import core

H = core.ra_de_height
FONT = 12                         # the smallest text on the chart (pixels)
TITLE_FONT = dict(size=FONT)      # the chart's titles: Planets-RA, Planets-Declination and both axis titles, in bold
GAP = 5                           # pixels between the grid and the text beside it
ROW = 16                          # pixels per line of text
TEXT_H = 15                       # the height of a line of text
# The chart has a fixed size, so every label's place is known in pixels and can be kept clear of the others
WIDTH, HEIGHT = 1100, 660
MARGIN_L, MARGIN_R, MARGIN_B = 72, 85, 75
PLOT_W = WIDTH - MARGIN_L - MARGIN_R

# The widest each character is at 12 px in Verdana, Arial or Open Sans, plain or bold (measured in a browser): Plotly
# uses the first of these the viewer has, so a label is never wider than this says
_CHAR_PX = {**dict.fromkeys("0123456789", 8.53), ".": 4.37, "+": 10.41, "-": 5.76, " ": 4.4, "N": 10.16, "S": 8.53,
            "E": 8.2, "W": 13.54, "H": 10.05, "C": 8.68, "O": 10.2, "Q": 10.2, "T": 8.18, "I": 6.55, "a": 8.02,
            "e": 7.97, "o": 8.24, "u": 8.55, "J": 6.67, "M": 11.37, "V": 9.16, "B": 9.14, "D": 9.96}


def text_px(text: str) -> float:
    """The widest a 12-pixel label can be, in pixels (any tags such as <b> left out)."""
    return sum(_CHAR_PX.get(ch, 10.0) for ch in re.sub(r"<[^>]+>", "", text)) + 2.0


class _Spots:
    """The places (pixel boxes from the grid's bottom-left corner) taken by marks and labels inside the grid, so that
    each new label goes to the first of its candidate places that is free."""

    def __init__(self, plot_h: float):
        self.w, self.h, self.boxes = PLOT_W, plot_h, []

    def px(self, x: float, y: float) -> tuple[float, float]:
        return x / 360.0 * self.w, (y + 90.0) / 180.0 * self.h

    def box(self, x, y, text, xanchor="center", yanchor="middle", dx=0.0, dy=0.0, w=None, h=TEXT_H):
        cx, cy = self.px(x, y)
        cx, cy, w = cx + dx, cy + dy, text_px(text) if w is None else w
        x0 = {"left": cx, "right": cx - w}.get(xanchor, cx - w / 2)
        y0 = {"bottom": cy, "top": cy - h}.get(yanchor, cy - h / 2)
        return x0, y0, x0 + w, y0 + h

    def free(self, b) -> bool:
        if b[0] < 0 or b[2] > self.w or b[1] < 0 or b[3] > self.h:
            return False
        return all(b[2] <= o[0] or b[0] >= o[2] or b[3] <= o[1] or b[1] >= o[3] for o in self.boxes)

    def place(self, fig: go.Figure, x: float, y: float, text: str, tries, font: dict, **kw) -> bool:
        """Puts the label at (x, y) by the first free try (xanchor, yanchor, xshift, yshift); False when none is."""
        return self.place_any(fig, text, [(x, y, *t) for t in tries], font, **kw)

    def place_any(self, fig: go.Figure, text: str, tries, font: dict, **kw) -> bool:
        """As place, each try with its own point: (x, y, xanchor, yanchor, xshift, yshift)."""
        for x, y, xa, ya, dx, dy in tries:
            b = self.box(x, y, text, xa, ya, dx, dy)
            if self.free(b):
                self.boxes.append(b)
                fig.add_annotation(x=x, y=y, text=text, showarrow=False, xanchor=xa, yanchor=ya, xshift=dx,
                                   yshift=dy, font=font, **kw)
                return True
        return False


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
    show_map: bool = True                            # the world map (coastlines)


def _house_lines(fig: go.Figure, ra10: float, is_now: bool):
    for k in range(12):
        x = core.norm360(ra10 + 30.0 * k)
        fig.add_trace(go.Scatter(x=[x, x], y=[-90, 90], mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color="black", width=1.5 if is_now else 1.75,   # now: long dashes, small gaps
                                           dash="12px,3px" if is_now else "solid")))


def _house_labels(fig: go.Figure, spots: _Spots, ra10: float, is_now: bool):
    """Each house's name in the middle of its span and its line's RA beside the line: birth houses in rows down from
    the top edge, houses now in rows up from the bottom edge, each in the first row where it is clear."""
    sfx = "-N" if is_now else ""
    y, ya, sign = (-90.0, "bottom", 1) if is_now else (90.0, "top", -1)
    rows = [sign * (3 + ROW * i) for i in range(10)]
    for k in range(12):
        x = core.norm360(ra10 + 30.0 * k)
        mid = core.norm360(x + 15.0)
        end = core.norm360(x + 30.0)
        # within the house's own span: its middle, or against either of its lines; a span across the 0 / 360 edge
        # also against that edge, on whichever side has room
        points = [(mid, "center", 0), (mid, "center", -14), (mid, "center", 14), (x, "left", 3), (end, "right", -3)]
        if end < x:
            points += [(0.0, "left", 3), (360.0, "right", -3)]
        spots.place_any(fig, f"<b>H{(9 + k) % 12 + 1:02d}{sfx}</b>",
                        [(px, y, xa, ya, dx, dy) for dy in rows for px, xa, dx in points], dict(size=FONT))
    for k in range(12):
        x = core.norm360(ra10 + 30.0 * k)
        spots.place(fig, x, y, f"{x:.1f}", [(xa, ya, dx, dy) for dy in rows for xa, dx in (("left", 3), ("right", -3))],
                    dict(size=FONT))


def _point_lines(fig: go.Figure, name: str, ra: float | None, de: float, is_now: bool, top: list, side: list):
    """The point's RA and Dec lines; its RA number (for above 90N) and Dec number (for right of 360) go to top / side."""
    c = core.colour(name)
    dash = "dot" if is_now else "solid"
    if ra is not None:                                       # CB and CN have no vertical line
        fig.add_trace(go.Scatter(x=[ra, ra], y=[-90, 90], mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color=c, width=0.75, dash=dash)))
    fig.add_trace(go.Scatter(x=[0, 360], y=[H(de), H(de)], mode="lines", hoverinfo="skip", showlegend=False,
                             line=dict(color=c, width=0.75, dash=dash)))
    side.append((H(de), f"{de:+.1f}", c))                    # plain text, at birth and now alike
    if ra is not None:
        top.append((ra, f"{ra:.1f}", c))


def _top_numbers(fig: go.Figure, top: list) -> int:
    """The RA numbers just above 90N, each beside its line: to the right of it, or to the left when the right is
    taken (or runs past 360); when both sides are taken it goes up a row. Returns the number of rows used."""
    rows: list[list[tuple[float, float]]] = []               # the pixel spans already taken in each row
    for ra, text, c in sorted(top):
        x, w = ra / 360.0 * PLOT_W, text_px(text)
        spans = {"right": (x + 2, x + 2 + w), "left": (x - 2 - w, x - 2)}
        sides = [s for s in ("right", "left") if -MARGIN_L <= spans[s][0] and spans[s][1] <= PLOT_W + MARGIN_R]
        for row in range(len(rows) + 1):
            if row == len(rows):
                rows.append([])
            side = next((s for s in sides
                         if all(spans[s][1] + 2 <= a or spans[s][0] >= b + 2 for a, b in rows[row])), None)
            if side:
                rows[row].append(spans[side])
                break
        fig.add_annotation(x=ra, y=90, text=text, showarrow=False, yanchor="bottom", yshift=1 + ROW * row,
                           xanchor="left" if side == "right" else "right", xshift=2 if side == "right" else -2,
                           font=dict(size=FONT, color=c))
    return max(len(rows), 1)


def _side_numbers(fig: go.Figure, side: list, px_per_unit: float):
    """The Dec numbers right of 360, top to bottom; one too close to the one above is moved down to clear it."""
    prev = None                                              # pixel height of the number placed above
    for y, text, c in sorted(side, reverse=True):
        want = y * px_per_unit
        at = want if prev is None or prev - want >= ROW else prev - ROW
        prev = at
        fig.add_annotation(x=360, y=y, yshift=at - want, text=text, showarrow=False, xanchor="left", xshift=GAP + 2,
                           font=dict(size=FONT, color=c))


def _aspect_line(fig: go.Figure, a: core.AspectLine, is_now: bool, minor: bool, tags: list):
    """The aspect's line; where its tag may go (points along the visible part of the line) is added to tags."""
    ys = [H(v) for v in a.ys]
    xs = list(a.xs)
    for shift in (0.0, -360.0, 360.0):                       # drawn on both sides when it crosses the edge
        sx = [x + shift for x in xs]
        if max(sx) < 0 or min(sx) > 360:
            continue
        fig.add_trace(go.Scatter(x=sx, y=ys, mode="lines", hoverinfo="text", hovertext=a.title, showlegend=False,
                                 line=dict(color="rgb(110,110,110)" if minor else "black", width=1 if minor else 1.5,
                                           dash="dot" if is_now else "solid")))
        (x0, y0), (x1, y1) = (sx[0], ys[0]), (sx[-1], ys[-1])
        points = [(x0 + t * (x1 - x0), y0 + t * (y1 - y0)) for t in (0.5, 0.35, 0.65, 0.2, 0.8)]
        points = [(x, y) for x, y in points if 0 <= x <= 360]
        if points:
            tags.append((a.title, points))
            break                                            # one tag per aspect


def fit_html(fig: go.Figure) -> str:
    """The chart as HTML that shows it at its full fixed size when there is room, and otherwise scales the whole chart
    down to the width it has, exactly as laid out (so no label can come to overlap another), its height following."""
    import uuid
    from plotly.offline import get_plotlyjs_version
    uid = "astromap-" + uuid.uuid4().hex[:8]
    cdn = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"   # the version this Plotly package draws with
    return f"""<div id="{uid}" style="width:100%; overflow:hidden">
<div id="{uid}-in" style="width:{WIDTH}px; height:{HEIGHT}px; transform-origin:0 0"></div></div>
<script>
(function () {{
  const outer = document.getElementById("{uid}"), inner = document.getElementById("{uid}-in");
  function fit() {{
    const s = Math.min(1, outer.clientWidth / {WIDTH});
    inner.style.transform = "scale(" + s + ")";
    outer.style.height = Math.ceil({HEIGHT} * s) + "px";
  }}
  new ResizeObserver(fit).observe(outer);
  fit();
  if (!window.Plotly && !document.getElementById("plotly-js")) {{     // Plotly's script, once per page
    const s = document.createElement("script");
    s.id = "plotly-js"; s.src = "{cdn}"; document.head.appendChild(s);
  }}
  const fig = {fig.to_json()};
  (function draw() {{
    if (!window.Plotly) return setTimeout(draw, 50);
    Plotly.newPlot(inner, fig.data, fig.layout, {{displaylogo: false, responsive: false}});
  }})();
}})();
</script>"""


def key_html(m: MapInput) -> str:
    """The key to the marks on the chart (planets, CB, CN), in the marks' colours and shapes, for beside the buttons."""
    lines = []                                                # birth marks on one line, the marks now on the next
    if m.show_birth and m.birth:
        lines.append([(n, "&#9670;" if n == "CB" else "&#9679;") for n in m.birth])     # diamond / filled circle
    if m.show_now and m.now:
        lines.append([(n + "-N", "&#9675;") for n in m.now]                             # hollow circle
                     + ([("CN", "&#9650;")] if m.cn is not None else []))               # triangle

    def item(n: str, sym: str) -> str:
        return f'<span style="color:{core.colour(n)}">{sym}</span>&nbsp;{n}'
    return "<br>".join('<span style="white-space:nowrap">' + "&nbsp; ".join(item(*i) for i in line) + "</span>"
                       for line in lines)


def map_figure(m: MapInput, orbs: core.Orbs) -> go.Figure:
    fig = go.Figure()
    turn = 0.0
    if m.jd_birth is not None:
        turn = core.lst(m.jd_birth, 0.0)
    if m.show_now and not m.show_birth and m.cn is not None:
        turn = core.lst(m.jd_now, 0.0)

    if m.show_map:                                            # the world map first, under everything
        xs, ys = world_map_xy(turn)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="rgb(150,150,150)", width=1),
                                 hoverinfo="skip", showlegend=False, connectgaps=False))
    for lon in range(-165, 181, 15):                          # longitudes along the bottom
        fig.add_annotation(x=core.norm360(lon + turn), y=-90, yanchor="top", yshift=-GAP, showarrow=False,  # above the RA ticks
                           font=dict(size=FONT), text=str(lon) if lon in (0, 180) else f"{abs(lon)}{'W' if lon < 0 else 'E'}")

    birth = m.birth if (m.show_birth and m.birth) else {}
    now = m.now if (m.show_now and m.now) else {}
    top, side = [], []                                        # the RA / Dec numbers, placed together below
    for n, (ra, de) in birth.items():
        _point_lines(fig, n, None if n == "CB" else ra, de, False, top, side)
    for n, (ra, de) in now.items():
        _point_lines(fig, n + "-N", ra, de, True, top, side)
    cn_x = None
    if m.show_now and m.cn is not None:
        cn_x = core.norm360(m.cn[1] + turn)
        _point_lines(fig, "CN", None, m.cn[0], True, top, side)
    rows = _top_numbers(fig, top)
    margin_t = 1 + ROW * rows + GAP + ROW + GAP               # the RA rows, then Planets-RA above them
    plot_h = HEIGHT - margin_t - MARGIN_B
    _side_numbers(fig, side, plot_h / 180.0)

    tags: list = []
    if birth:
        for a in core.all_aspects(birth, orbs, False, major=m.major, minor=m.minor):
            _aspect_line(fig, a, False, a.angle in core.MINOR, tags)
        _house_lines(fig, birth["CB"][0], False)
    if now:
        for a in core.all_aspects(now, orbs, True, major=m.major, minor=m.minor):
            _aspect_line(fig, a, True, a.angle in core.MINOR, tags)
    if m.show_now and m.cn is not None:
        _house_lines(fig, core.lst(m.jd_now, m.cn[1]), True)

    marks = []                                                # (name, RA, Dec), for their name labels below
    def mark(name: str, x: float, de: float, symbol: str, hollow: bool, d_txt: str):
        c = core.colour(name)
        fig.add_trace(go.Scatter(                             # their key is shown beside the buttons (key_html)
            x=[x], y=[H(de)], mode="markers", name=name, showlegend=False,
            marker=dict(symbol=symbol, size=11, color="white" if hollow else c, line=dict(color=c, width=2)),
            hovertemplate=f"<b>{name}</b><br>RA {x:.2f}<br>Dec {de:+.2f}{d_txt}<extra></extra>"))
        marks.append((name, x, de))

    for n, (ra, de) in birth.items():
        d = m.d_birth.get(n)
        mark(n, ra, de, "diamond" if n == "CB" else "circle", False, f"<br>D {d:.2f}" if d is not None else "")
    for n, (ra, de) in now.items():
        d = m.d_now.get(n)
        mark(n + "-N", ra, de, "circle", True, f"<br>D-N {d:.2f}" if d is not None else "")
    if cn_x is not None:
        mark("CN", cn_x, m.cn[0], "triangle-up", False, f"<br>lat {m.cn[0]:+.2f}, lon {m.cn[1]:+.2f}")

    # Labels inside the grid, each in the first free place: first the marks themselves are kept clear, then each
    # mark's name goes beside it, then the house names and RAs along the edges, then the aspect tags
    spots = _Spots(plot_h)
    for _, x, de in marks:
        spots.boxes.append(spots.box(x, H(de), "", w=15, h=15))
    near = [("center", "bottom", 0, 8), ("center", "top", 0, -8), ("left", "middle", 9, 0), ("right", "middle", -9, 0),
            ("left", "bottom", 6, 5), ("right", "bottom", -6, 5), ("left", "top", 6, -5), ("right", "top", -6, -5)]
    far = [(xa, ya, dx * k, dy * k) for k in (2, 3, 4) for xa, ya, dx, dy in near]
    for name, x, de in marks:
        spots.place(fig, x, H(de), f"<b>{name}</b>", near + far, dict(size=FONT, color=core.colour(name)))
    if birth:
        _house_labels(fig, spots, birth["CB"][0], False)
    if m.show_now and m.cn is not None:
        _house_labels(fig, spots, core.lst(m.jd_now, m.cn[1]), True)
    shifts = [(0, dy) for dy in (0, 12, -12, 24, -24, 36, -36)] + \
             [(dx, dy) for dy in (0, 18, -18, 36, -36, 54, -54, 72, -72) for dx in (40, -40, 80, -80)]
    for title, points in tags:                                # a tag with no free place is left off (it shows on hover)
        spots.place_any(fig, f"<b>{title}</b>",
                        [(x, y, "center", "middle", dx, dy) for dx, dy in shifts for x, y in points],
                        dict(size=FONT), bgcolor="rgba(255,255,255,0.75)")

    if birth or now:                                          # names the RA numbers printed above the 90N line
        fig.add_annotation(xref="paper", x=0.5, xanchor="center", y=90, yanchor="bottom",
                           yshift=1 + ROW * rows + GAP, text="<b>Planets-RA</b>", showarrow=False, font=TITLE_FONT)
        # names the Dec numbers printed right of the 360 line: a side title past them, like the left axis title
        fig.add_annotation(xref="paper", x=1, xanchor="left", xshift=50, yref="paper", y=0.5, yanchor="middle",
                           textangle=90, text="<b>Planets-Declination</b>", showarrow=False, font=TITLE_FONT)

    lat_ticks = list(range(-90, 91, 15))
    fig.update_layout(
        width=WIDTH, height=HEIGHT, autosize=False, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=MARGIN_L, r=MARGIN_R, t=margin_t, b=MARGIN_B, autoexpand=False),
        showlegend=False, hovermode="closest", dragmode="zoom",
        xaxis=dict(range=[0, 360], showgrid=False, zeroline=False,
                   title=dict(text="<b>Longitude/Right Ascension (RA)</b>", standoff=14, font=TITLE_FONT),
                   tickvals=list(range(0, 361, 30)), ticklabelstandoff=GAP + ROW - 1,  # RA numbers just under the longitudes
                   mirror=True, linecolor="rgb(134,134,134)"),
        yaxis=dict(range=[-90, 90], showgrid=False, zeroline=False, ticklabelstandoff=0,   # close to the grid
                   title=dict(text="<b>Latitude/Declination</b>", standoff=10, font=TITLE_FONT),
                   tickvals=[H(v) for v in lat_ticks],
                   ticktext=["0" if v == 0 else f"{abs(v)}{'S' if v < 0 else 'N'}" for v in lat_ticks],
                   mirror=True, linecolor="rgb(134,134,134)"))
    return fig
