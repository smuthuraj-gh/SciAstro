"""What the charts share: the text size, keeping labels apart (Spots), and the page's chart holder (fit_html)."""
from __future__ import annotations

import re

import plotly.graph_objects as go


FONT = 12                         # all text on all pages, charts too (pixels; the most allowed, the least is 10)
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


CHART_FONT_FAMILY = "'Open Sans', verdana, arial, sans-serif"     # Plotly's default, which the charts are drawn in
# the same, for the drawings' own text (tags as 0-Ma-Ju): the planet symbols taken from a symbol font before Arial, whose
# thin Venus and Mars (it has no bold ones) looked faint beside the others
SYMBOL_FONT_FAMILY = "'Open Sans', verdana, 'Segoe UI Symbol', 'Apple Symbols', 'Noto Sans Symbols', arial, sans-serif"
CHART_TEXT = "#444"                                              # Plotly's text colour

