"""The Celestial Sphere 3D page: the paths of the Sun, Moon and planets around the Earth, each at its real distance, unlike AstroGlobe,
where all are on one sphere. A point is placed by its RA, Dec and distance only (equatorial, no zodiac); north is up and the
Earth's equator is the flat plane. Drawn on the page in SVG, so its labels can be kept apart as it is turned."""
from __future__ import annotations

import json
import math
import uuid

from . import core
from .globechart import MARKER_RANGE, MOTION_DAYS, PATH_SPAN, SIZE_RANGE_ARCSEC, SYMBOLS, TILT, _motion_table
from .mapchart import CHART_FONT_FAMILY, FONT

WIDTH, HEIGHT = 1100, 900          # taller than the orbits need, for the RA lines beyond them
RADIUS = 300.0                    # pixels from the Earth to the farthest thing drawn
SCALES = ("Log", "True", MO_LOG := "Mo Log")   # Mo Log: the Moon as on Log, at the same place on the page; the others as on True
LOG_FROM_AU = 0.001               # on the Log scale, the distance drawn at the Earth: each ring then ten times the last
SPANS = {"Su": (365.25, 120, "Sun Path"), **PATH_SPAN}     # days, points, name: one trip round the sky
RINGS = {"Log": (0.002, 0.01, 0.1, 1.0, 10.0),
         "True": (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)}   # AU; at most RINGS_SHOWN of them
RINGS[MO_LOG] = RINGS["True"]
LOG_FULL_AU = 11.1                # about the farthest Saturn comes: all the Log scale's page
RINGS_SHOWN = 4
RA_MARKS = (0, 90, 180, 270)
RA_LONGER = 1.5                   # the RA lines reach this much beyond the farthest orbit
SIDES = 96                        # a ring is drawn with this many straight pieces


def _reach(au: float, scale: str) -> float:
    """How far from the Earth a distance is drawn, before fitting to the page."""
    return max(math.log10(au / LOG_FROM_AU), 0.0) if scale == "Log" else au


def _xyz(ra: float, dec: float, reach: float) -> list[float]:
    """x toward RA 0, y toward RA 90, z toward the north celestial pole."""
    a, d = math.radians(ra), math.radians(dec)
    return [round(reach * math.cos(d) * math.cos(a), 5), round(reach * math.cos(d) * math.sin(a), 5), round(reach * math.sin(d), 5)]


def space_data(bodies: list[str], moments: list[tuple[str, float, float | None]], scale: str, key: str,
               day_seconds: float | None = None, manual: bool = False, show_au: bool = False) -> dict:
    """For each moment and body: its path, and its table to move it by. moments: (Now or DOB, Julian day, UTC offset)."""
    paths, marks, tables = [], [], {}
    outer = 0.0
    if scale == MO_LOG and set(bodies) == {"Mo"}:             # nothing to be true to: as Log
        scale = "Log"
    for clock, jd, _ in moments:
        tables[clock] = {}
        for p in bodies:
            whole = _motion_table(p, jd)
            tables[clock][p] = {k: whole[k] for k in ("step", "ra", "dec", "dist", "km")}
            if p != "Mo" or scale != MO_LOG:
                outer = max(outer, _reach(max(whole["dist"]), scale))
            marks.append(dict(name=p, colour=core.colour(p), hollow=clock == "Now", clock=clock, rule=core.size_rule(p)))
            days, steps, name = SPANS[p]
            if p == "Mo":                                     # the page works it out as time runs, from the Moon's table
                paths.append(dict(colour=core.colour(p), dash=clock == "Now", pts=[], tip="", name=name, moon=clock))
                continue
            pts = [core.position(p, jd + days * (v / steps - 0.5)) for v in range(steps + 1)]
            reach = [_reach(q.dist_au, scale) for q in pts]
            outer = max(outer, *reach)
            near, far = min(q.dist_au for q in pts), max(q.dist_au for q in pts)
            paths.append(dict(colour=core.colour(p), dash=clock == "Now", pts=[_xyz(q.ra, q.dec, r) for q, r in zip(pts, reach)],
                              tip=f"{name} {clock}: {days:g} days around {clock} (distance from earth {near:.4g} to {far:.4g} AU)"))
    # what the sizes are measured from (Bigger than Moon needs the Moon's table, shown or not)
    earth_rule = core.size_rule("Ea")
    for clock, jd, _ in moments:
        for rule in [earth_rule] + [m["rule"] for m in marks]:
            if "of" in rule and rule["of"] not in tables[clock]:
                whole = _motion_table(rule["of"], jd)
                tables[clock][rule["of"]] = {k: whole[k] for k in ("step", "ra", "dec", "dist", "km")}
    outer = outer or 1.0
    wanted = [au for au in RINGS[scale] if _reach(au, scale) <= outer][-RINGS_SHOWN:] if show_au else []
    circle = [(360.0 * v / SIDES) for v in range(SIDES + 1)]
    rings = [dict(text=f"{au:g} AU", pts=[_xyz(ra, 0.0, _reach(au, scale)) for ra in circle]) for au in wanted]
    return dict(paths=paths, marks=marks, tables=tables, rings=rings, outer=outer, fit=RADIUS / outer, width=WIDTH, height=HEIGHT, font=FONT,
                symbols=SYMBOLS, tilt=TILT, earth_rule=earth_rule, earth_clock=moments[0][0], earth_size=core.SIZE_TEXTS.get("Ea", ""), earth_colour=core.colour("Ea"), moon_share=outer / _reach(LOG_FULL_AU, "Log"), au_km=core.AU_KM, sizes=SIZE_RANGE_ARCSEC, radii=MARKER_RANGE, scale=scale, log_from=LOG_FROM_AU, key=key, days=MOTION_DAYS, moon_month=SPANS["Mo"][0], manual=manual, day_seconds=day_seconds,
                step_ms=max(40, int((day_seconds or 60.0) * 2.5)), clocks=[dict(clock=c, jd=jd, offset=o) for c, jd, o in moments],
                family=CHART_FONT_FAMILY, ra_marks=[dict(text=f"RA {ra}", at=_xyz(ra, 0.0, outer * RA_LONGER)) for ra in RA_MARKS])


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
  const symbolTag = (name, colour) => {           // a planet's tag: placed by x and y, as a text would be, and named in its title
    const tag = make("svg", svg, {overflow: "visible"});
    make("title", tag).textContent = name;
    const lines = make("g", tag, {transform: "translate(0 -5)"});
    [["white", 4], [colour, 1.8]].forEach(([stroke, width]) => make("path", lines, {d: D.symbols[name], fill: "none", stroke, "stroke-width": width,
      "stroke-linecap": "round", "stroke-linejoin": "round"}));
    return tag;
  };
  const view = window.space3dView || (window.space3dView = {yaw: 90, pitch: 45});
  if (!window.space3dClock || window.space3dClock.key !== D.key) window.space3dClock = {key: D.key, t: 0};
  const clock = window.space3dClock;              // the days run since each moment: kept when a button is pressed
  const sample = (b, t) => {                       // between its two nearest table rows
    const u = t / b.step, i = Math.min(Math.floor(u), b.ra.length - 2), f = u - i;
    const turn = ((b.ra[i + 1] - b.ra[i] + 540) % 360) - 180;
    return {ra: (b.ra[i] + turn * f + 360) % 360, dec: b.dec[i] + (b.dec[i + 1] - b.dec[i]) * f, dist: b.dist[i] + (b.dist[i + 1] - b.dist[i]) * f};
  };
  const xyz = (s, moon) => {                       // as space3d._xyz, at the distance as the scale draws it
    const log = Math.max(Math.log10(s.dist / D.log_from), 0);
    const r = D.scale === "Log" ? log : D.scale === "True" || !moon ? s.dist : log * D.moon_share, a = s.ra * RAD, d = s.dec * RAD;
    return [r * Math.cos(d) * Math.cos(a), r * Math.cos(d) * Math.sin(a), r * Math.sin(d)];
  };
  const signed = (v) => (v >= 0 ? "+" : "") + v.toFixed(2);
  const pad2 = (n) => (n >= 0 ? "+" : "-") + Math.abs(n).toFixed(2);
  const clockLine = (s, t) => {                    // its date and time, at its place's UTC offset
    const known = s.offset !== null && s.offset !== undefined, off = known ? s.offset : 0;
    const ms = (s.jd + t - 2440587.5) * 86400000 + off * 3600000 + 30000;     // to the nearest minute
    return s.clock + " " + new Date(ms).toISOString().slice(0, 16).replace("T", " ") + (known ? " UTC" + pad2(off) : " UT");
  };
  const showClocks = (t) => {                      // in the page's clock, beside the customer's name
    const box = document.querySelector(".globe-clock");
    if (box) box.textContent = D.clocks.map((s) => clockLine(s, t)).join("    ");
  };
  let X = 0, Y = 0, Z = 0, S = 0, C = 0, s = 0, c = 0;
  const LEAN_S = Math.sin(D.tilt * RAD), LEAN_C = Math.cos(D.tilt * RAD);
  const angles = () => { S = Math.sin(view.yaw * RAD); C = Math.cos(view.yaw * RAD); s = Math.sin(view.pitch * RAD); c = Math.cos(view.pitch * RAD); };
  const point = ([x, y, z]) => {                   // on the page: x, y, and how far toward the viewer (+ is near)
    X = x * C - y * S;
    Y = -(x * S + y * C);
    Z = z * s + Y * c;
    const up = z * c - Y * s, grow = 1 / (1 - Z / D.outer / 4);   // a little perspective: nearer is bigger
    // the whole drawing leans on the page, so that the axis from NCP to SCP is tilted
    const across = X * LEAN_C + up * LEAN_S, high = up * LEAN_C - X * LEAN_S;
    return [D.width / 2 + across * D.fit * grow, D.height / 2 - high * D.fit * grow, Z];
  };
  const line = (colour, width, dashed, tip) => {   // the near part full, the far part faint
    const parts = [1, 0.35].map((opacity) => {
      const attrs = {fill: "none", stroke: colour, "stroke-width": width, opacity, style: "pointer-events:stroke"};
      if (dashed) attrs["stroke-dasharray"] = "6 4";
      const e = make("path", svg, attrs);
      if (tip) make("title", e).textContent = tip;
      return e;
    });
    return (pts, newTip) => {
      if (newTip) parts.forEach((e) => { (e.firstChild || make("title", e)).textContent = newTip; });
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
  const LOW = Math.log(D.sizes[0]), HIGH = Math.log(D.sizes[1]);
  const arcsecOf = (km, au) => 2 * Math.atan(km / (au * D.au_km)) / RAD * 3600;
  const radiusAt = (rule, tables, t) => {          // by the Size in the Naming Conventions table: a fixed radius, or a planet's angular size and more
    if (rule.px !== undefined) return rule.px;
    const b = tables[rule.of], share = Math.max(0, Math.min(1, (Math.log(arcsecOf(b.km, sample(b, t).dist)) - LOW) / (HIGH - LOW)));
    return Math.max(1, D.radii[0] + (D.radii[1] - D.radii[0]) * share + rule.add);
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
  const earth = make("circle", svg, {fill: D.earth_colour, stroke: DARK, "stroke-width": 1});
  make("title", earth).textContent = "Ea, at the centre (its size is not to scale" + (D.earth_size ? ": " + D.earth_size : "") + ")";
  const earthLabel = symbolTag("Ea", D.earth_colour);
  const marks = D.marks.map((m) => {
    const e = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 2, style: "pointer-events:auto"});
    const tip = make("title", e), label = symbolTag(m.name, m.colour);
    return {m, e, tip, label, table: D.tables[m.clock][m.name]};
  });
  const boxOf = (x, y, text) => {
    const w = text.length * 8;
    return [x - w / 2 - 3, y - 15, x + w / 2 + 3, y + 3];
  };
  const clear = (a, taken) => taken.every((b) => a[2] < b[0] || b[2] < a[0] || a[3] < b[1] || b[3] < a[1]);
  const inside = (a) => a[0] > 0 && a[1] > 0 && a[2] < D.width && a[3] < D.height;
  const put = (label, spots, taken) => {           // its last place while that stays free, else the first free near it; left off if none
    const text = label.textContent;
    const free = (i) => {
      const [x, y] = spots[i], a = boxOf(x, y, text);
      if (!inside(a) || !clear(a, taken)) return false;
      label.setAttribute("x", x.toFixed(1)); label.setAttribute("y", y.toFixed(1));
      label.style.display = "";
      label.lastPlace = i;
      taken.push(a);
      return true;
    };
    const last = label.lastPlace;
    const away = (i) => Math.hypot(spots[i][0] - spots[last][0], spots[i][1] - spots[last][1]);
    if (last >= WAYS) {                            // pushed out: back in beside its mark as soon as there is room, by the shortest way
      const closer = spots.map((_, i) => i).slice(0, last - last % WAYS).sort((a, b) => away(a) - away(b));
      for (const i of closer) if (free(i)) return;
    }
    if (last !== undefined && free(last)) return;
    // blocked: the free place the least way from where it was beside its mark
    const order = spots.map((_, i) => i);
    if (last !== undefined) order.sort((a, b) => away(a) - away(b));
    for (const i of order) if (free(i)) return;
    label.style.display = "none";
  };
  const moonPath = (p, t) => {                     // the Moon's month around the clock's date
    const b = D.tables[p.moon].Mo, first = Math.max(0, Math.min(t - D.moon_month / 2, D.days - D.moon_month));
    const samples = [];
    for (let v = 0; v !== 56; v++) samples.push(sample(b, first + v * D.moon_month / 55));
    p.pts = samples.map((s) => xyz(s, true));
    const dists = samples.map((s) => s.dist);
    p.tip = p.name + " " + p.moon + ": the month around the clock's date (distance from earth " + Math.min(...dists).toPrecision(4) +
      " to " + Math.max(...dists).toPrecision(4) + " AU)";
  };
  const WAYS = 8;                                  // the places round a mark, at each reach
  const around = (x, y, r, w) => {
    const out = [];
    for (let reach = 0; reach !== 12; reach++) {
      const d = reach * 10;
      out.push([x, y - r - 6 - d], [x, y + r + 15 + d], [x + r + w + 4 + d, y + 5], [x - r - w - 4 - d, y + 5],
               [x + r + w + d, y - r - 4 - d], [x - r - w - d, y - r - 4 - d], [x + r + w + d, y + r + 13 + d], [x - r - w - d, y + r + 13 + d]);
    }
    return out;
  };
  let lastStack = "";
  const draw = () => {
    angles();
    rings.forEach((g) => g.draw(g.r.pts));
    spokes.forEach((g) => g.draw([[0, 0, 0], g.m.at]));
    axis([[0, 0, -D.outer], [0, 0, D.outer]]);
    const t = clock.t;
    paths.forEach((g) => {
      if (g.p.moon) moonPath(g.p, t);
      g.draw(g.p.pts, g.p.moon ? g.p.tip : null);
    });
    const placed = marks.map((g) => {
      const s = sample(g.table, t), [x, y, z] = point(xyz(s, g.m.name === "Mo"));
      // sized by how wide it looks from the Earth then, on AstroGlobe's logarithmic scale (to true scale the planets would not show)
      const arcsec = arcsecOf(g.table.km, s.dist), r = radiusAt(g.m.rule, D.tables[g.m.clock], t);
      const size = arcsec >= 60 ? (arcsec / 60).toFixed(1) + " arcmin" : arcsec.toFixed(1) + " arcsec";
      g.e.setAttribute("r", r.toFixed(1));
      g.tip.textContent = g.m.name + " " + g.m.clock + "\nDec/Lati: " + signed(s.dec) + "\nRA: " + s.ra.toFixed(2) + "\nAngular Size: " + size +
        "\nDistance from earth: " + s.dist.toPrecision(4) + " AU";
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      g.e.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      g.label.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      return {g, x, y, z, r};
    }).sort((a, b) => a.z - b.z);
    const [ex, ey] = point([0, 0, 0]), earthR = radiusAt(D.earth_rule, D.tables[D.earth_clock], t);
    earth.setAttribute("r", earthR.toFixed(1));
    earth.setAttribute("cx", ex.toFixed(1)); earth.setAttribute("cy", ey.toFixed(1));
    // in the order of depth, what is nearest on top (only when that changes: moving a mark would lose its hover box);
    // every label kept off every mark and every other label
    const stack = placed.map((q) => q.g.m.name + q.g.m.clock).join();
    if (stack !== lastStack) {
      placed.forEach((q) => { svg.appendChild(q.g.e); svg.appendChild(q.g.label); });
      lastStack = stack;
    }
    const taken = placed.map((q) => [q.x - q.r - 2, q.y - q.r - 2, q.x + q.r + 2, q.y + q.r + 2]).concat([[ex - earthR - 1, ey - earthR - 1, ex + earthR + 1, ey + earthR + 1]]);
    put(earthLabel, around(ex, ey, earthR, 8), taken);
    // always in the same order, so that a tag does not lose its place to another as the drawing turns
    marks.forEach((g) => {
      const q = placed.find((p) => p.g === g);
      put(g.label, around(q.x, q.y, q.r, 8), taken);
    });
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
    showClocks(t);
  };
  draw();
  if (D.day_seconds) {                             // time runs: the planets move along their paths
    let last = performance.now();
    const timer = setInterval(() => {
      if (!document.body.contains(svg)) return clearInterval(timer);
      const now = performance.now();
      clock.t += (now - last) / 1000 / D.day_seconds;
      last = now;
      if (clock.t >= D.days) clock.t = 0;          // the end of the tables: from the start again
      draw();
    }, D.step_ms);
  }
  if (!D.manual) { svg.style.cursor = "default"; return; }
  let from = null, due = false;                    // Manual: time stands still, and dragging turns the drawing
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


def space_html(bodies: list[str], moments: list[tuple[str, float, float | None]], scale: str, key: str,
               day_seconds: float | None = None, manual: bool = False, show_au: bool = False) -> str:
    uid = "space-" + uuid.uuid4().hex[:8]
    data = json.dumps(space_data(bodies, moments, scale, key, day_seconds, manual, show_au)).replace("<", chr(92) + "u003c")
    return f'<div id="{uid}"></div><script>{_JS.replace("__DATA__", data).replace("__ID__", uid)}</script>'
