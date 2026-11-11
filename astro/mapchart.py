"""What the charts share: the text size, keeping labels apart (Spots), the page's chart holder (fit_html) and the Distance(%) rows."""
from __future__ import annotations

import html
import math
import re

import plotly.graph_objects as go

from . import core

FONT = 13                         # all text on all pages, charts too (pixels)
ROW = round(FONT * 1.3)           # pixels per line of text (Plotly's line height)
TEXT_H = ROW + 1                  # the height Plotly gives a line of text (its box, with padding)
# The charts have a fixed width, so every label's place is known in pixels and can be kept clear of the others
WIDTH = 1100
# The widest each character is at 12 px in Verdana, Arial or Open Sans, plain or bold (measured in a browser): Plotly
# uses the first of these the viewer has, so a label is never wider than this says
_CHAR_PX = {**dict.fromkeys("0123456789", 8.53), ".": 4.37, "+": 10.41, "-": 5.76, " ": 4.4, "N": 10.16, "S": 8.53,
            "E": 8.2, "W": 13.54, "H": 10.05, "C": 8.68, "O": 10.2, "Q": 10.2, "T": 8.18, "I": 6.55, "a": 8.02,
            "e": 7.97, "o": 8.24, "u": 8.55, "J": 6.67, "M": 11.37, "V": 9.16, "B": 9.14, "D": 9.96}


def text_px(text: str) -> float:
    """The widest a 12-pixel label can be, in pixels (any tags such as <b> left out)."""
    widths = sum(_CHAR_PX.get(ch, 10.0) for ch in re.sub(r"<[^>]+>", "", text))
    return widths * FONT / 12.0 + 4.0                    # the table is for 12 px; + the box Plotly draws round it


class Spots:
    """The places (pixel boxes from the grid's bottom-left corner) taken by marks and labels inside the grid, so that
    a new label can go to a place that is free. to_px turns a chart point into pixels."""

    def __init__(self, plot_w: float, plot_h: float, to_px):
        self.w, self.h, self.px, self.boxes = plot_w, plot_h, to_px, []

    def box(self, x, y, text, xanchor="center", yanchor="middle", dx=0.0, dy=0.0, w=None, h=TEXT_H):
        cx, cy = self.px(x, y)
        cx, cy, w = cx + dx, cy + dy, text_px(text) if w is None else w
        x0 = {"left": cx, "right": cx - w}.get(xanchor, cx - w / 2)
        y0 = {"bottom": cy, "top": cy - h}.get(yanchor, cy - h / 2)
        return x0, y0, x0 + w, y0 + h

    def free(self, b) -> bool:
        if b[0] < 0 or b[2] > self.w or b[1] < 0 or b[3] > self.h:
            return False
        g = 1.0                                              # at least a pixel between any two
        return all(b[2] + g <= o[0] or b[0] >= o[2] + g or b[3] + g <= o[1] or b[1] >= o[3] + g for o in self.boxes)


# The page's text column is narrower than the charts by these (pixels of the 1100-px chart), and each chart reaches out
# past it by the same on both sides
INSET_L, INSET_R = 15, 11


def fit_html(fig: go.Figure, after_js: str = "") -> str:
    """The chart as HTML scaled as a whole to the page's zoom, exactly as laid out (so no label can come to overlap
    another), reaching INSET_L / INSET_R past the text column. Any chart with a fixed layout width and height."""
    import uuid
    from plotly.offline import get_plotlyjs_version
    w, h = int(fig.layout.width), int(fig.layout.height)
    uid = "chart-" + uuid.uuid4().hex[:8]
    cdn = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"   # the version this Plotly package draws with
    # (Plotly's hover toolbar moved in from the chart's right edge)
    return f"""<style>#{uid} .modebar-container {{ right: {INSET_R}px !important; }}</style>
<div id="{uid}" style="overflow:hidden">
<div id="{uid}-in" style="width:{w}px; height:{h}px; transform-origin:0 0"></div></div>
<script>
(function () {{
  const outer = document.getElementById("{uid}"), inner = document.getElementById("{uid}-in");
  const watching = [new ResizeObserver(fit), new ResizeObserver(fit)];
  function fit() {{
    if (!outer.isConnected) {{                // this chart has been replaced: nothing is left watching for it
      watching.forEach((w) => w.disconnect());
      window.removeEventListener("resize", fit);
      return;
    }}
    // The page is zoomed (CSS zoom) to the window, but Plotly cannot follow the pointer through a CSS zoom (pointing
    // at a planet showed nothing or another planet): so the chart undoes the page zoom and is scaled by a transform
    // instead, which Plotly allows for. Same size on screen: the column's width plus the insets, in screen pixels.
    const z = parseFloat(document.documentElement.style.zoom) || 1;
    outer.style.zoom = 1 / z;
    const col = (outer.parentElement || outer).getBoundingClientRect().width;     // on screen
    const width = col + ({INSET_L + INSET_R}) * z;
    outer.style.width = width + "px";
    outer.style.marginLeft = (-{INSET_L} * z) + "px";
    const s = width / {w};                 // the page zoom: the column is laid out so that this is it exactly
    inner.style.transform = "scale(" + s + ")";
    outer.style.height = Math.ceil({h} * s) + "px";
  }}
  // again whenever the column's width changes, and once the page has settled (its scroll bar may appear late)
  watching[0].observe(outer.parentElement || outer);
  watching[1].observe(document.documentElement);
  window.addEventListener("resize", fit);
  fit(); setTimeout(fit, 300); setTimeout(fit, 1500);
  if (!window.Plotly && !document.getElementById("plotly-js")) {{     // Plotly's script, once per page
    const s = document.createElement("script");
    s.id = "plotly-js"; s.src = "{cdn}"; document.head.appendChild(s);
  }}
  const fig = {fig.to_json()};
  (function draw() {{
    if (!window.Plotly) return setTimeout(draw, 50);
    // (the mouse wheel scrolls the page, never zooms a chart; a globe has no zoom or reset buttons: it stays as it is)
    Plotly.newPlot(inner, fig.data, fig.layout, {{displaylogo: false, responsive: false, scrollZoom: false,
                                                 modeBarButtonsToRemove: ["zoomInGeo", "zoomOutGeo", "resetGeo"]}}).then(function (gd) {{
      {after_js}
    }});
  }})();
}})();
</script>"""


def _marker_radius(name: str, pcts: dict) -> float:
    """A planet's marker radius, as AstroClock-2D draws it, by its Size_Clock in the Symbols table, at the distances (%) of this row."""
    from .globechart import BODY_RADIUS_KM, MARKER_RANGE, SIZE_RANGE_ARCSEC
    rule = core.size_rule(name, texts=core.SIZE_TEXTS_CLOCK)
    if "px" in rule:
        return rule["px"]
    low, high = core.DIST_RANGE[rule["of"]]
    km = low + (high - low) * pcts[rule["of"]] / 100.0
    arcsec = math.degrees(2 * math.atan(BODY_RADIUS_KM[rule["of"]] / km)) * 3600
    share = (math.log(arcsec) - math.log(SIZE_RANGE_ARCSEC[0])) / (math.log(SIZE_RANGE_ARCSEC[1]) - math.log(SIZE_RANGE_ARCSEC[0]))
    return max(1.0, MARKER_RANGE[0] + (MARKER_RANGE[1] - MARKER_RANGE[0]) * min(max(share, 0.0), 1.0) + rule["add"])


def _ink_on(colour: str) -> str:
    """Black or white, whichever shows on a colour (as the pages' symbols are)."""
    if colour.startswith("#"):
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    else:
        r, g, b = map(int, re.findall(r"[0-9]+", colour)[:3])
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def _marker_svg(name: str, pcts: dict, shape: dict) -> str:
    """A planet's round marker, in its colour and sized as on the charts, with its symbol inside."""
    r = _marker_radius(name, pcts)
    k, half, colour = r / 9.5, r + 1, core.colour(name)
    ink = _ink_on(colour)
    inside = (f'<path d="{shape["d"]}" fill="none" stroke="{ink}" stroke-width="{1.5 / k:.2f}" stroke-linecap="round" stroke-linejoin="round"/>'
              if "d" in shape else
              f'<text y="4.5" text-anchor="middle" font-size="13" font-weight="bold" fill="{ink}">{html.escape(shape["text"])}</text>')
    return (f'<svg width="{2 * half:.1f}" height="{2 * half:.1f}" viewBox="{-half:.1f} {-half:.1f} {2 * half:.1f} {2 * half:.1f}" style="display:block">'
            f'<circle r="{r:.1f}" fill="{colour}"/><g transform="scale({k:.3f})">{inside}</g></svg>')


def _key_row(items: list[tuple[str, float | None]], label: str = "") -> str:
    """One row of the key: the row's title above, then each planet's marker, with a value beneath (blank for none)."""
    from .globechart import symbol_shapes
    shapes, pcts = symbol_shapes(), {n: v for n, v in items if v is not None}

    def item(n: str, v: float | None) -> str:
        value = f"{v:.1f}" if v is not None else "&nbsp;"
        return (f'<span style="display:inline-block; text-align:center; margin-right:{KEY_GAP_HTML}px; vertical-align:top; line-height:1.4">'
                f'<span style="display:flex; height:{MARKER_ROOM}px; align-items:center; justify-content:center">{_marker_svg(n, pcts, shapes[n])}</span>'
                f'<span style="font-size:{FONT}px">{value}</span></span>')
    head = (f'<div style="font-size:{FONT}px; line-height:1.2; margin-bottom:3px">'
            f'<b style="font-weight:700">{label}</b>'
            f'</div>' if label else "")
    # in the charts' own font (Plotly's) and text colour
    return (f'<div style="white-space:nowrap; font-size:{FONT}px; font-family:{CHART_FONT_FAMILY}; '
            f'color:{CHART_TEXT}">' + head + "".join(item(*i) for i in items) + "</div>")


CHART_FONT_FAMILY = "'Open Sans', verdana, arial, sans-serif"     # Plotly's default, which the charts are drawn in
CHART_TEXT = "#444"                                              # Plotly's text colour
MARKER_ROOM = 30                 # pixels high for the markers in the Distance(%) rows, the biggest fitting
# The space between one planet and the next in the Distance(%) rows, so that the three fit on one line
KEY_GAP_HTML = 8


def average_key_html(d_birth: dict, d_now: dict) -> str:
    """Each planet's Distance(%) from earth (DOB+Now)/2: the average of D at birth and D-N now, from the least to the greatest.
    Empty if none has both."""
    da = [(n, round((d_birth[n] + d_now[n]) / 2, 2)) for n in core.PLANETS
          if d_birth.get(n) is not None and d_now.get(n) is not None]
    da.sort(key=lambda i: i[1])                                  # by its value: the nearest first
    return _key_row(da, "Distance(%) from earth (DOB+Now)/2") if da else ""


def globe_key_html(d_birth: dict, d_now: dict, show_dob: bool, show_now: bool = False) -> str:
    """AstroClock-2D's rows, side by side (wrapping only where the page is too narrow): with Now chosen Distance(%) from earth at
    Now, with DOB chosen on DOB, then (DOB+Now)/2."""
    dob = sorted(((n, d_birth[n]) for n in core.PLANETS if d_birth.get(n) is not None), key=lambda i: i[1])   # the nearest first
    now = sorted(((n, d_now[n]) for n in core.PLANETS if d_now.get(n) is not None), key=lambda i: i[1])
    rows = [_key_row(now, "Distance(%) from earth at Now") if now and show_now else "",
            _key_row(dob, "Distance(%) from earth on DOB") if dob and show_dob else "", average_key_html(d_birth, d_now)]
    return '<div style="display:flex; flex-wrap:wrap; justify-content:flex-end; column-gap:28px; row-gap:6px">' + "".join(rows) + "</div>"
