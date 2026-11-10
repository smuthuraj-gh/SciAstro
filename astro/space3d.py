"""The Geo/Helio page, GeoCentric and HelioCentric: the paths of the Sun, Moon and planets around the Earth, or of the planets and the Earth
around the Sun, each at its real distance, unlike AstroGlobe, where all are on one sphere. A point is placed by its RA, Dec and distance only (equatorial, no zodiac); north is up and the
Earth's equator is the flat plane. Drawn on the page in SVG, so its labels can be kept apart as it is turned."""
from __future__ import annotations

import json
import math
import uuid
from functools import lru_cache

from . import core
from .globechart import MARKER_RANGE, MOTION_DAYS, PATH_SPAN, SIZE_RANGE_ARCSEC, SYMBOL_JS, TILT, _motion_table, symbol_shapes
from .mapchart import CHART_FONT_FAMILY, FONT

WIDTH, HEIGHT = 1100, 900          # taller than the orbits need, for the RA lines beyond them
RADIUS = 300.0                    # pixels from the Earth to the farthest thing drawn
SCALES = (FIT := "Fit", "True")   # Fit: each tenfold distance the same room, without the empty space between the Moon and the planets
GAP = (0.003, 0.25, 0.03)         # Fit: from just past the Moon's farthest (AU) to inside any planet's nearest (Venus about 0.26),
                                  # drawn as only this much (a tenth of a doubling: a thin space)
LOG_FROM_AU = 0.0013              # on Fit, the distance drawn at the Earth (the Moon, about 0.0024-0.0027, close by)
SPANS = {"Su": (365.25, 120, "Sun Path"), **PATH_SPAN}     # days, points, name: one trip round the sky
RINGS = {FIT: (0.005, 0.5, 1.0, 2.5, 5.0, 10.0),            # just past the Moon (in the space taken out, so not to scale there), then the planets
         "True": (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)}   # AU; at most RINGS_SHOWN of them
RINGS_SHOWN = {FIT: 6, "True": 4}   # at most this many rings, the outermost ones
RA_MARKS = (0, 90, 180, 270)
RUN_DAYS = MOTION_DAYS            # how far time runs here (72 years, as on AstroGlobe) before it starts again, with the trails
RA_LONGER = 1.5                   # the RA lines reach this much beyond the farthest orbit
SCP_BEYOND_AU = 15.0              # the axis reaches, both ways on the page, past where a ring this far out would be drawn ...
SCP_PAST_PX = 22                  # ... by this many pixels, NCP and SCP at its ends
SIDES = 96                        # a ring is drawn with this many straight pieces

# HelioCentric: the Sun at the centre, the planets and the Earth round it, and the Moon round the Earth (seen from the Sun it is
# where the Earth is, so it is drawn round the Earth's mark, larger than to scale: in its real direction from the Earth, at
# MOON_AROUND_PX pixels at its mean distance, nearer and farther with its real distance)
HELIO_BODIES = ("Me", "Ve", "Ea", "Mo", "Ma", "Ju", "Sa")
MOON_AROUND_PX = 17.0            # just clear of the Earth's mark, when the Moon is Tiny (its Size_Helio, as it starts)
MOON_MEAN_AU = 0.00257
HELIO_LOG_FROM_AU = 0.12          # on Fit, the distance drawn at the Sun (Mercury, about 0.31-0.47, close by)
HELIO_SPANS = {"Mo": (27.32, 110, "Moon Path"), "Me": (87.97, 200, "Mercury Path"), "Ve": (224.7, 200, "Venus Path"), "Ea": (365.25, 200, "Earth Path"),
               "Ma": (687.0, 300, "Mars Path"), "Ju": (4333.0, 400, "Jupiter Path"), "Sa": (10759.0, 400, "Saturn Path")}   # a year each
HELIO_STEP_DAYS = {"Me": 1.0, "Ve": 2.0, "Ea": 2.0, "Ma": 4.0, "Ju": 20.0, "Sa": 20.0}
HELIO_RINGS = {FIT: (0.5, 1.0, 2.0, 5.0, 10.0),   # all of them (on True those inside 1 AU would be lost in the Sun's mark)
               "True": (1.0, 2.0, 5.0, 10.0)}
NO_GAP = (1.0, 1.0, 0.0)          # nothing taken out
# by the body at the centre: the distance drawn there on Fit, the space taken out, the rings, the paths' spans, and its name in words
CENTRES = {"Ea": dict(log_from=LOG_FROM_AU, gap=GAP, rings=RINGS, rings_shown=RINGS_SHOWN, spans=SPANS, word="earth"),
           "Su": dict(log_from=HELIO_LOG_FROM_AU, gap=NO_GAP, rings=HELIO_RINGS, rings_shown={FIT: 5, "True": 4}, spans=HELIO_SPANS, word="the Sun")}


@lru_cache(maxsize=24)
def _helio_table(planet: str, jd: float, days: int = RUN_DAYS) -> dict:
    """A body's RA, Dec and distance as seen from the Sun, from jd on, for the page to move it by."""
    step = HELIO_STEP_DAYS[planet]
    pts = [core.helio_position(planet, jd + i * step) for i in range(int(days / step) + 2)]
    return {"step": step, "ra": [round(p.ra, 3) for p in pts], "dec": [round(p.dec, 3) for p in pts],
            "dist": [round(p.dist_au, 6) for p in pts], "km": 0.0}


def _reach(au: float, scale: str, log_from: float = LOG_FROM_AU, gap: tuple = GAP) -> float:
    """How far from the centre a distance is drawn, before fitting to the page."""
    if scale == "True":
        return au
    log = max(math.log10(au / log_from), 0.0)
    a, b = math.log10(gap[0] / log_from), math.log10(gap[1] / log_from)
    return log if log <= a else log - (b - a) + gap[2] if log >= b else a + (log - a) / (b - a) * gap[2]


def _xyz(ra: float, dec: float, reach: float) -> list[float]:
    """x toward RA 0, y toward RA 90, z toward the north celestial pole."""
    a, d = math.radians(ra), math.radians(dec)
    return [round(reach * math.cos(d) * math.cos(a), 5), round(reach * math.cos(d) * math.sin(a), 5), round(reach * math.sin(d), 5)]


def space_data(bodies: list[str], moments: list[tuple[str, float, float | None]], scale: str, key: str,
               day_seconds: float | None = None, manual: bool = False, show_au: bool = False, with_paths: tuple | None = None,
               centre: str = "Ea") -> dict:
    """For each moment and body: its table to move it by, and (those in with_paths; all with None) its path, which the page draws
    as a trail behind it, where it has really been since the moment, kept for the whole run (72 years).
    moments: (Now or DOB, Julian day, UTC offset). centre: Ea (GeoCentric) or Su (HelioCentric). The drawing's size does not
    change with the paths shown. The sizes are always by how big a body looks from the Earth (the tables seen from the Earth)."""
    at = CENTRES[centre]
    sizes = core.SIZE_TEXTS if centre == "Ea" else core.SIZE_TEXTS_HELIO      # the Size_Geo or the Size_Helio column
    reach = lambda au: _reach(au, scale, at["log_from"], at["gap"])
    paths, marks, tables, sizing = [], [], {}, {}
    outer = 0.0
    for clock, jd, _ in moments:
        tables[clock], sizing[clock] = {}, {}
        if centre == "Su" and "Mo" in bodies:                 # the Moon goes round the Earth: the Earth's table, shown or not
            whole = _helio_table("Ea", jd, RUN_DAYS)
            tables[clock]["Ea"] = {k: whole[k] for k in ("step", "ra", "dec", "dist", "km")}
            outer = max(outer, reach(max(whole["dist"])))
        for p in bodies:
            around = centre == "Su" and p == "Mo"                # its table as seen from the Earth
            whole = _motion_table(p, jd, RUN_DAYS) if centre == "Ea" or around else _helio_table(p, jd, RUN_DAYS)
            tables[clock][p] = {k: whole[k] for k in ("step", "ra", "dec", "dist", "km")}
            if not around:
                outer = max(outer, reach(max(whole["dist"])))
            rule = core.size_rule(p, texts=sizes)
            marks.append(dict(name=p, colour=core.colour(p), hollow=clock == "Now", clock=clock, rule=rule))
            days, steps, name = at["spans"][p]
            if with_paths is None or p in with_paths:         # the page draws it as time runs, from the body's own table
                paths.append(dict(colour=core.colour(p), dash=clock == "Now", name=name, body=p, clock=clock, days=days, steps=steps, pts=[]))
    # what the sizes are measured from: each body as seen from the Earth (Bigger than Moon needs the Moon's table, shown or not)
    centre_rule = core.size_rule(centre, texts=sizes)
    for clock, jd, _ in moments:
        for p in bodies:
            if p in core.PLANET_ID:
                whole = _motion_table(p, jd, RUN_DAYS)
                sizing[clock][p] = {k: whole[k] for k in ("step", "ra", "dec", "dist", "km")}
        for rule in [centre_rule] + [m["rule"] for m in marks]:
            if "of" in rule and rule["of"] not in sizing[clock]:
                whole = _motion_table(rule["of"], jd, RUN_DAYS)
                sizing[clock][rule["of"]] = {k: whole[k] for k in ("step", "ra", "dec", "dist", "km")}
    if centre == "Ea":                                         # the same tables: not sent twice
        for clock in tables:
            tables[clock].update(sizing[clock])
        sizing = None
    outer = outer or 1.0
    wanted = [au for au in at["rings"][scale] if reach(au) <= outer][-at["rings_shown"][scale]:] if show_au else []
    circle = [(360.0 * v / SIDES) for v in range(SIDES + 1)]
    rings = [dict(text=f"{au:g} AU", pts=[_xyz(ra, 0.0, reach(au)) for ra in circle]) for au in wanted]
    return dict(paths=paths, marks=marks, tables=tables, sizing=sizing, rings=rings, outer=outer, fit=RADIUS / outer, width=WIDTH, height=HEIGHT, font=FONT,
                shapes=symbol_shapes(), sym={n: core.symbol_of(n) for n in core.SYMBOL_TEXTS}, tilt=TILT, centre=centre, centre_word=at["word"],
                centre_rule=centre_rule, centre_clock=moments[0][0], centre_size=sizes.get(centre, ""), centre_colour=core.colour(centre),
                au_km=core.AU_KM, sizes=SIZE_RANGE_ARCSEC, radii=MARKER_RANGE, show_tags=show_au, scale=scale, log_from=at["log_from"], gap=at["gap"],
                scp_ring=reach(SCP_BEYOND_AU), scp_past=SCP_PAST_PX, sides=SIDES, key=centre + key, days=RUN_DAYS, around=centre == "Su", moon_reach=MOON_AROUND_PX / (RADIUS / outer), moon_mean=MOON_MEAN_AU, manual=manual, day_seconds=day_seconds,
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
__SYMBOL_JS__
  const view = window.space3dView || (window.space3dView = {yaw: 90, pitch: 45});
  if (!window.space3dClock || window.space3dClock.key !== D.key) window.space3dClock = {key: D.key, t: 0};
  const clock = window.space3dClock;              // the days run since each moment: kept when a button is pressed
  const sample = (b, t) => {                       // between its two nearest table rows
    const u = t / b.step, i = Math.min(Math.floor(u), b.ra.length - 2), f = u - i;
    const turn = ((b.ra[i + 1] - b.ra[i] + 540) % 360) - 180;
    return {ra: (b.ra[i] + turn * f + 360) % 360, dec: b.dec[i] + (b.dec[i + 1] - b.dec[i]) * f, dist: b.dist[i] + (b.dist[i + 1] - b.dist[i]) * f};
  };
  const xyz = (s) => {                             // as space3d._xyz, at the distance as the scale draws it
    const log = Math.max(Math.log10(s.dist / D.log_from), 0), lo = Math.log10(D.gap[0] / D.log_from), hi = Math.log10(D.gap[1] / D.log_from);
    const r = D.scale === "True" ? s.dist : log <= lo ? log :      // Fit: the gap past the Moon closed up
      log >= hi ? log - (hi - lo) + D.gap[2] : lo + (log - lo) / (hi - lo) * D.gap[2], a = s.ra * RAD, d = s.dec * RAD;
    return [r * Math.cos(d) * Math.cos(a), r * Math.cos(d) * Math.sin(a), r * Math.sin(d)];
  };
  const posAt = (clock, body, t) => {             // where a body is then, and where it is drawn
    const s = sample(D.tables[clock][body], t);
    if (!(D.around && body === "Mo")) return {s, p: xyz(s)};
    const e = xyz(sample(D.tables[clock].Ea, t)), a = s.ra * RAD, d = s.dec * RAD, r = D.moon_reach * s.dist / D.moon_mean;
    return {s, p: [e[0] + r * Math.cos(d) * Math.cos(a), e[1] + r * Math.cos(d) * Math.sin(a), e[2] + r * Math.sin(d)]};
  };
  const fromWord = (body) => (D.around && body === "Mo" ? "earth" : D.centre_word);   // the Moon's distance is from the Earth
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
  const line = (colour, width, dashed, tip, full) => {   // the near part full, the far part faint (unless full)
    const parts = [1, full ? 1 : 0.35].map((opacity) => {
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
  const sizing = (clock) => (D.sizing || D.tables)[clock];   // the tables as seen from the Earth, for the sizes
  const radiusAt = (rule, tables, t) => {          // by the Size in the Naming Conventions table: a fixed radius, or a planet's angular size and more
    if (rule.px !== undefined) return rule.px;
    const b = tables[rule.of], share = Math.max(0, Math.min(1, (Math.log(arcsecOf(b.km, sample(b, t).dist)) - LOW) / (HIGH - LOW)));
    return Math.max(1, D.radii[0] + (D.radii[1] - D.radii[0]) * share + rule.add);
  };
  const GREY = "rgb(150,150,150)", DARK = "rgb(60,60,60)";
  const rings = D.rings.map((r) => ({r, draw: line(GREY, 1, false, r.text + " from " + D.centre_word + ", on the plane of the Earth's equator"), label: words("rgb(110,110,110)")}));
  rings.forEach((g) => { g.label.textContent = g.r.text; });
  const spokes = D.ra_marks.map((m) => ({m, draw: line("rgb(205,205,205)", 1, false, m.text), label: words("rgb(110,110,110)")}));
  spokes.forEach((g) => { g.label.textContent = g.m.text; });
  const axis = line(DARK, 2, false, D.centre === "Ea" ? "The Earth's axis: north celestial pole to south" :
                     "Toward the north celestial pole and the south, as the Earth's axis");
  const paths = D.paths.map((p) => ({p, draw: line(p.colour, 1.8, p.dash, "", true)}));   // a path is one colour all round
  const poles = [["NCP", [0, 0, D.outer]], ["SCP", [0, 0, -D.outer]]].map(([name, at]) => {
    const label = words(DARK);
    label.textContent = name;
    return {at, label};
  });
  const earth = make("circle", svg, {fill: D.centre_colour, stroke: DARK, "stroke-width": 1});   // the body at the centre
  make("title", earth).textContent = symbolOf(D.centre) + ", at the centre (its size is not to scale" + (D.centre_size ? ": " + D.centre_size : "") + ")";
  const earthLabel = symbolTag(svg, D.centre, D.centre_colour, false);
  const marks = D.marks.map((m) => {
    const e = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 2, style: "pointer-events:auto"});
    const tip = make("title", e), label = symbolTag(svg, m.name, m.colour, m.hollow);
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
  const TRAIL_MOST = 2000;                         // the most points a trail is drawn with: a long one is thinned, evenly
  // a trail is drawn only while time runs: from where the body was when it started running (each start clears the last one)
  // (kept across the page's redraws while time runs, so pressing another button does not clear them)
  if (!D.day_seconds) clock.trailFrom = null;
  else if (clock.trailFrom === null || clock.trailFrom === undefined || clock.trailFrom > clock.t) clock.trailFrom = clock.t;
  let trailFrom = D.day_seconds ? clock.trailFrom : null;
  const trail = (p, t) => {                        // where the body has really been since time started running
    const times = [], run = trailFrom === null ? 0 : t - trailFrom;
    let gap = p.days / p.steps;
    while (run / gap > TRAIL_MOST) gap *= 2;         // (by doubling, so that the points stay where they were as it grows)
    for (let n = 0; n * gap < run; n++) times.push(trailFrom + n * gap);
    if (run > 0) times.push(t);                     // to the body itself
    const got = times.map((u) => posAt(p.clock, p.body, u)), samples = got.map((g) => g.s);
    p.pts = got.map((g) => g.p);
    const dists = samples.map((s) => s.dist), days = Math.round(run);
    p.tip = p.name + " " + p.clock + ": where it has been since time started running, " + days + (days === 1 ? " day" : " days") +
      (samples.length ? " (distance from " + fromWord(p.body) + " " + Math.min(...dists).toPrecision(4) + " to " + Math.max(...dists).toPrecision(4) + " AU)" : "");
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
    // the axis reaches, both ways, past where a 15 AU ring would be drawn on the page (round the centre, on the plane of the
    // equator), so that NCP and SCP are out beyond the planets; both halves as long on the page (the one leaning away from the
    // viewer would look shorter), found by halving for the way the drawing is turned now
    const [cx, cy] = point([0, 0, 0]);
    const pageLength = (sign, k) => { const [x, y] = point([0, 0, sign * k * D.outer]); return Math.hypot(x - cx, y - cy); };
    const ringAcross = (sign) => {                   // where that ring crosses the axis's line on the page, that way
      const [px, py] = point([0, 0, sign * D.outer]), toward = Math.atan2(py - cy, px - cx);
      let ring = 0, nearest = 9;
      for (let i = 0; i !== D.sides; i++) {
        const a = 2 * Math.PI * i / D.sides, [rx, ry] = point([D.scp_ring * Math.cos(a), D.scp_ring * Math.sin(a), 0]);
        const off = Math.abs(((Math.atan2(ry - cy, rx - cx) - toward + 3 * Math.PI) % (2 * Math.PI)) - Math.PI);
        if (off < nearest) { nearest = off; ring = Math.hypot(rx - cx, ry - cy); }
      }
      return ring;
    };
    const reachFor = (sign, length) => {             // how far out that half goes to be this long on the page
      const toViewer = sign * point([0, 0, D.outer])[2] / D.outer;   // not so far toward the viewer that the perspective turns over
      let lo = 0.05, hi = toViewer > 0 ? Math.min(12, 3 / toViewer) : 12;
      for (let i = 0; i !== 30; i++) {
        const k = (lo + hi) / 2;
        if (pageLength(sign, k) > length) hi = k; else lo = k;
      }
      return hi;
    };
    const length = Math.max(pageLength(1, 1), ringAcross(1) + D.scp_past, ringAcross(-1) + D.scp_past);
    poles[0].at = [0, 0, reachFor(1, length) * D.outer];
    poles[1].at = [0, 0, -reachFor(-1, length) * D.outer];
    axis([poles[1].at, poles[0].at]);
    const t = clock.t;
    paths.forEach((g) => {
      trail(g.p, t);
      g.draw(g.p.pts, g.p.tip);
    });
    const placed = marks.map((g) => {
      const {s, p: at} = posAt(g.m.clock, g.m.name, t), [x, y, z] = point(at);
      // sized by how wide it looks from the Earth then, on AstroGlobe's logarithmic scale (to true scale the planets would not show)
      const seen = sizing(g.m.clock)[g.m.name], r = radiusAt(g.m.rule, sizing(g.m.clock), t);
      const arcsec = seen ? arcsecOf(seen.km, sample(seen, t).dist) : null;   // how big it looks from the Earth (not for the Earth itself)
      const size = arcsec === null ? "" : "\nAngular Size: " + (arcsec >= 60 ? (arcsec / 60).toFixed(1) + " arcmin" : arcsec.toFixed(1) + " arcsec");
      g.e.setAttribute("r", r.toFixed(1));
      g.tip.textContent = symbolOf(g.m.name) + " " + g.m.clock + "\nDec/Lati: " + signed(s.dec) + "\nRA: " + s.ra.toFixed(2) + size +
        "\nDistance from " + fromWord(g.m.name) + ": " + s.dist.toPrecision(4) + " AU" +
        (D.around && g.m.name === "Mo" ? "\n(drawn round the Earth, farther out than to scale)" : "");
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      g.e.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      g.label.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      fitSymbol(g.label, x, y, r);
      return {g, x, y, z, r};
    }).sort((a, b) => a.z - b.z);
    const [ex, ey] = point([0, 0, 0]), earthR = radiusAt(D.centre_rule, sizing(D.centre_clock), t);
    earth.setAttribute("r", earthR.toFixed(1));
    fitSymbol(earthLabel, ex, ey, earthR);
    earth.setAttribute("cx", ex.toFixed(1)); earth.setAttribute("cy", ey.toFixed(1));
    // in the order of depth, what is nearest on top (only when that changes: moving a mark would lose its hover box);
    // every label kept off every mark and every other label
    const stack = placed.map((q) => q.g.m.name + q.g.m.clock).join();
    if (stack !== lastStack) {
      placed.forEach((q) => { svg.appendChild(q.g.e); svg.appendChild(q.g.label); });
      lastStack = stack;
    }
    const taken = placed.map((q) => [q.x - q.r - 2, q.y - q.r - 2, q.x + q.r + 2, q.y + q.r + 2]).concat([[ex - earthR - 1, ey - earthR - 1, ex + earthR + 1, ey + earthR + 1]]);
    if (!D.show_tags) {                            // AU off: no tags at all (the lines stay)
      poles.concat(spokes).forEach((g) => { g.label.style.display = "none"; });
      showClocks(t);
      return;
    }
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
      if (clock.t >= D.days) { clock.t = 0; trailFrom = clock.trailFrom = 0; }   // the end of the tables: from the start again, the trails too
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
               day_seconds: float | None = None, manual: bool = False, show_au: bool = False, with_paths: tuple | None = None,
               centre: str = "Ea") -> str:
    uid = "space-" + uuid.uuid4().hex[:8]
    data = json.dumps(space_data(bodies, moments, scale, key, day_seconds, manual, show_au, with_paths, centre)).replace("<", chr(92) + "u003c")
    return f'<div id="{uid}"></div><script>{_JS.replace("__SYMBOL_JS__", SYMBOL_JS).replace("__DATA__", data).replace("__ID__", uid)}</script>'
