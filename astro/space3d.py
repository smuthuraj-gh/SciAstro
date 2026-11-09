"""The Planets 3D page: the paths of the Sun, Moon and planets around the Earth, each at its real distance, unlike AstroGlobe,
where all are on one sphere. A point is placed by its RA, Dec and distance only (equatorial, no zodiac); north is up and the
Earth's equator is the flat plane. Drawn on the page in SVG, so its labels can be kept apart as it is turned."""
from __future__ import annotations

import json
import math
import uuid

from . import core
from .globechart import PATH_SPAN
from .mapchart import CHART_FONT_FAMILY, FONT

WIDTH, HEIGHT = 1100, 720
RADIUS = 330.0                    # pixels from the Earth to the farthest thing drawn
SCALES = ("Log", "True")
LOG_FROM_AU = 0.001               # on the Log scale, the distance drawn at the Earth: each ring then ten times the last
SPANS = {"Su": (365.25, 120, "Sun Path"), **PATH_SPAN}     # days, points, name: one trip round the sky
RINGS = {"Log": (0.002, 0.01, 0.1, 1.0, 10.0),
         "True": (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)}   # AU; at most RINGS_SHOWN of them
RINGS_SHOWN = 4
RA_MARKS = (0, 90, 180, 270)
SIDES = 96                        # a ring is drawn with this many straight pieces


def _reach(au: float, scale: str) -> float:
    """How far from the Earth a distance is drawn, before fitting to the page."""
    return au if scale == "True" else max(math.log10(au / LOG_FROM_AU), 0.0)


def _xyz(ra: float, dec: float, reach: float) -> list[float]:
    """x toward RA 0, y toward RA 90, z toward the north celestial pole."""
    a, d = math.radians(ra), math.radians(dec)
    return [round(reach * math.cos(d) * math.cos(a), 5), round(reach * math.cos(d) * math.sin(a), 5), round(reach * math.sin(d), 5)]


def space_data(bodies: list[str], moments: list[tuple[str, float]], scale: str) -> dict:
    """For each moment and body: its path and where it is then. moments: (Now or DOB, Julian day)."""
    paths, marks = [], []
    outer = 0.0
    for clock, jd in moments:
        for p in bodies:
            days, steps, name = SPANS[p]
            pts = [core.position(p, jd + days * (v / steps - 0.5)) for v in range(steps + 1)]
            reach = [_reach(q.dist_au, scale) for q in pts]
            outer = max(outer, *reach)
            near, far = min(q.dist_au for q in pts), max(q.dist_au for q in pts)
            paths.append(dict(colour=core.colour(p), dash=clock == "Now", pts=[_xyz(q.ra, q.dec, r) for q, r in zip(pts, reach)],
                              tip=f"{name} {clock}: {days:g} days around {clock} (distance from earth {near:.4g} to {far:.4g} AU)"))
            at = core.position(p, jd)
            marks.append(dict(name=p, colour=core.colour(p), hollow=clock == "Now", at=_xyz(at.ra, at.dec, _reach(at.dist_au, scale)),
                              tip=f"{p} {clock}\nDec/Lati: {at.dec:+.2f}\nRA: {at.ra:.2f}\nDistance from earth: {at.dist_au:.4g} AU"))
    outer = outer or 1.0
    wanted = [au for au in RINGS[scale] if _reach(au, scale) <= outer][-RINGS_SHOWN:]
    circle = [(360.0 * v / SIDES) for v in range(SIDES + 1)]
    rings = [dict(text=f"{au:g} AU", pts=[_xyz(ra, 0.0, _reach(au, scale)) for ra in circle]) for au in wanted]
    return dict(paths=paths, marks=marks, rings=rings, outer=outer, fit=RADIUS / outer, width=WIDTH, height=HEIGHT, font=FONT,
                family=CHART_FONT_FAMILY, ra_marks=[dict(text=f"RA {ra}", at=_xyz(ra, 0.0, outer)) for ra in RA_MARKS])


# (Spaces after every less-than: the page drops a script that seems to have tags in it.)
_JS = r"""
(function () {
  const D = __DATA__, box = document.getElementById("__ID__"), NS = "http://www.w3.org/2000/svg", RAD = Math.PI / 180;
  const make = (tag, parent, attrs) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    parent.appendChild(e);
    return e;
  };
  const svg = make("svg", box, {viewBox: "0 0 " + D.width + " " + D.height, width: "100%",
                                style: "display:block; cursor:grab; touch-action:none; user-select:none"});
  const words = (fill) => make("text", svg, {"font-weight": "bold", "font-size": D.font, "font-family": D.family, stroke: "white",
                                             "stroke-width": 3, "paint-order": "stroke", "text-anchor": "middle", fill});
  const view = window.space3dView || (window.space3dView = {yaw: 30, pitch: 25});
  let X = 0, Y = 0, Z = 0, S = 0, C = 0, s = 0, c = 0;
  const angles = () => { S = Math.sin(view.yaw * RAD); C = Math.cos(view.yaw * RAD); s = Math.sin(view.pitch * RAD); c = Math.cos(view.pitch * RAD); };
  const point = ([x, y, z]) => {                   // on the page: x, y, and how far toward the viewer (+ is near)
    X = x * C - y * S;
    Y = -(x * S + y * C);
    Z = z * s + Y * c;
    const up = z * c - Y * s, grow = 1 / (1 - Z / D.outer / 4);   // a little perspective: nearer is bigger
    return [D.width / 2 + X * D.fit * grow, D.height / 2 - up * D.fit * grow, Z];
  };
  const line = (colour, width, dashed, tip) => {   // the near part full, the far part faint
    const parts = [1, 0.35].map((opacity) => {
      const attrs = {fill: "none", stroke: colour, "stroke-width": width, opacity, style: "pointer-events:stroke"};
      if (dashed) attrs["stroke-dasharray"] = "6 4";
      const e = make("path", svg, attrs);
      if (tip) make("title", e).textContent = tip;
      return e;
    });
    return (pts) => {
      let near = "", far = "", side = null, last = "";
      pts.forEach((q) => {
        const [x, y, z] = point(q), here = z >= 0, at = x.toFixed(1) + " " + y.toFixed(1);
        if (here !== side) {
          const start = (last ? "M" + last + "L" : "M") + at;
          if (here) near += start; else far += start;
          side = here;
        } else if (here) near += "L" + at; else far += "L" + at;
        last = at;
      });
      parts[0].setAttribute("d", near); parts[1].setAttribute("d", far);
    };
  };
  const GREY = "rgb(150,150,150)", DARK = "rgb(60,60,60)";
  const rings = D.rings.map((r) => ({r, draw: line(GREY, 1, false, r.text + " from earth, on the plane of the Earth's equator"), label: words("rgb(110,110,110)")}));
  rings.forEach((g) => { g.label.textContent = g.r.text; });
  const spokes = D.ra_marks.map((m) => ({m, draw: line("rgb(205,205,205)", 1, false, m.text), label: words("rgb(110,110,110)")}));
  spokes.forEach((g) => { g.label.textContent = g.m.text; });
  const axis = line(DARK, 2, false, "The Earth's axis: north celestial pole to south");
  const paths = D.paths.map((p) => ({p, draw: line(p.colour, 1.8, p.dash, p.tip)}));
  const poles = [["NCP", [0, 0, D.outer]], ["SCP", [0, 0, -D.outer]]].map(([name, at]) => {
    const label = words(DARK);
    label.textContent = name;
    return {at, label};
  });
  const earth = make("circle", svg, {r: 8, fill: "rgb(90,140,200)", stroke: DARK, "stroke-width": 1});
  make("title", earth).textContent = "Earth, at the centre";
  const earthLabel = words(DARK);
  earthLabel.textContent = "Earth";
  const marks = D.marks.map((m) => {
    const e = make("circle", svg, {r: 5, fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 2, style: "pointer-events:auto"});
    make("title", e).textContent = m.tip;
    const label = words(m.colour);
    label.textContent = m.name;
    return {m, e, label};
  });
  const boxOf = (x, y, text) => {
    const w = text.length * 8;
    return [x - w / 2 - 3, y - 15, x + w / 2 + 3, y + 3];
  };
  const clear = (a, taken) => taken.every((b) => a[2] < b[0] || b[2] < a[0] || a[3] < b[1] || b[3] < a[1]);
  const inside = (a) => a[0] > 0 && a[1] > 0 && a[2] < D.width && a[3] < D.height;
  const put = (label, spots, taken) => {           // at the first free place near it; left off if there is none
    const text = label.textContent;
    for (const [x, y] of spots) {
      const a = boxOf(x, y, text);
      if (inside(a) && clear(a, taken)) {
        label.setAttribute("x", x.toFixed(1)); label.setAttribute("y", y.toFixed(1));
        label.style.display = "";
        taken.push(a);
        return;
      }
    }
    label.style.display = "none";
  };
  const around = (x, y, r, w) => {
    const out = [];
    for (let reach = 0; reach !== 12; reach++) {
      const d = reach * 10;
      out.push([x, y - r - 6 - d], [x, y + r + 15 + d], [x + r + w + 4 + d, y + 5], [x - r - w - 4 - d, y + 5],
               [x + r + w + d, y - r - 4 - d], [x - r - w - d, y - r - 4 - d], [x + r + w + d, y + r + 13 + d], [x - r - w - d, y + r + 13 + d]);
    }
    return out;
  };
  const draw = () => {
    angles();
    rings.forEach((g) => g.draw(g.r.pts));
    spokes.forEach((g) => g.draw([[0, 0, 0], g.m.at]));
    axis([[0, 0, -D.outer], [0, 0, D.outer]]);
    paths.forEach((g) => g.draw(g.p.pts));
    const placed = marks.map((g) => {
      const [x, y, z] = point(g.m.at);
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      g.e.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      g.label.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      return {g, x, y, z};
    }).sort((a, b) => a.z - b.z);
    const [ex, ey] = point([0, 0, 0]);
    earth.setAttribute("cx", ex.toFixed(1)); earth.setAttribute("cy", ey.toFixed(1));
    // in the order of depth, what is nearest on top; every label kept off every mark and every other label
    placed.forEach((q) => { svg.appendChild(q.g.e); svg.appendChild(q.g.label); });
    const taken = placed.map((q) => [q.x - 7, q.y - 7, q.x + 7, q.y + 7]).concat([[ex - 9, ey - 9, ex + 9, ey + 9]]);
    put(earthLabel, around(ex, ey, 8, 20), taken);
    placed.slice().reverse().forEach((q) => put(q.g.label, around(q.x, q.y, 5, 8), taken));
    poles.forEach((g) => {
      const [x, y] = point(g.at);
      put(g.label, around(x, y, 4, 12), taken);
    });
    spokes.forEach((g) => {
      const [x, y] = point(g.m.at);
      put(g.label, around(x, y, 2, 24), taken);
    });
    rings.forEach((g) => {                         // on the side of the ring nearest the viewer
      let best = null;
      g.r.pts.forEach((q) => { const p = point(q); if (!best || p[1] > best[1]) best = p; });
      put(g.label, around(best[0], best[1], 0, 20), taken);
    });
  };
  draw();
  let from = null, due = false;
  svg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    from = [e.clientX, e.clientY];
    svg.setPointerCapture(e.pointerId);
    svg.style.cursor = "grabbing";
    e.preventDefault();
  });
  svg.addEventListener("pointermove", (e) => {
    if (!from) return;
    view.yaw += (e.clientX - from[0]) * 0.5;
    view.pitch = Math.max(-85, Math.min(85, view.pitch + (e.clientY - from[1]) * 0.5));
    from = [e.clientX, e.clientY];
    if (!due) {
      due = true;
      requestAnimationFrame(() => { due = false; draw(); });
    }
  });
  const letGo = () => { from = null; svg.style.cursor = "grab"; };
  svg.addEventListener("pointerup", letGo);
  svg.addEventListener("pointercancel", letGo);
})();
"""


def space_html(bodies: list[str], moments: list[tuple[str, float]], scale: str) -> str:
    uid = "space-" + uuid.uuid4().hex[:8]
    data = json.dumps(space_data(bodies, moments, scale)).replace("<", chr(92) + "u003c")
    return f'<div id="{uid}"></div><script>{_JS.replace("__DATA__", data).replace("__ID__", uid)}</script>'
