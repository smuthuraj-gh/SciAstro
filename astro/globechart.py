"""The AstroGlobe page: the Earth turning inside the celestial sphere. The sphere stands still, with the celestial equator
and the celestial poles; the Earth inside it, with CB and CN on it, turns about the axis that joins those poles. As it turns,
time runs, and each planet moves over the sphere as it really did, with its RA line (the circle of RA through it), Dec line
(the circle of Dec through it) and size. At the start the Earth is set as it was at that moment, so a planet is straight
above the place it was overhead. Equatorial only (RA / Dec)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

import plotly.graph_objects as go

from . import core
from .mapchart import CHART_FONT_FAMILY, CHART_TEXT, FONT

WIDTH, HEIGHT = 1100, 720
MARGIN = 10
TILT = 23.44                      # degrees the Earth's axis leans from upright (its obliquity)
LEAN_TOWARD = 45.0                # the way the axis leans: 0 = toward the viewer, 90 = to the right; here between them
# the seconds one day of the clock takes: an hour, a day, a week or a month (30.44 days) to a second
SPEEDS = {"1h=1sec": 24.0, "1d=1sec": 1.0, "1w=1sec": 1.0 / 7.0, "1m=1sec": 1.0 / 30.44}
EARTH_RADIUS = 165.0              # pixels, in the chart's own layout
SKY_RADIUS = 315.0                # the celestial sphere, pixels (it fits the chart's height with its pole labels)
AXIS_COLOUR = "rgb(60,60,60)"
GRID_DEGREES = 30                 # between the Earth's lines of latitude, and of longitude
GRID_COLOUR = "rgb(120,120,120)"
SKY_FILL = "rgb(244,246,252)"
BACK_OPACITY = 0.3                # the far side of the sphere, seen through it
BODY_RADIUS_KM = {"Su": 695700.0, "Mo": 1737.4, "Me": 2439.7, "Ve": 6051.8, "Ma": 3396.2, "Ju": 71492.0, "Sa": 60268.0}
SIZE_RANGE_ARCSEC = (3.5, 2040.0)     # the smallest (Mars at its farthest) to the largest (the Moon at its nearest) ...
MARKER_RANGE = (3.0, 11.0)            # ... drawn with these marker radii, in pixels
# A path's days (one trip round the sky seen from the Earth: Mercury and Venus keep with the Sun, so a year), points drawn, name
PATH_SPAN = {"Mo": (27.32, 110, "Path of the Moon"), "Me": (365.25, 365, "Path of Mercury"),
             "Ve": (365.25, 365, "Path of Venus"), "Ma": (687.0, 400, "Path of Mars"),
             "Ju": (4333.0, 400, "Path of Jupiter"), "Sa": (10759.0, 400, "Path of Saturn")}
BODY_CHOICES = ("Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa")
EARTH_DEGREES_A_DAY = 360.98565   # the Earth's turn against the still sky in one day of the clock
MOTION_DAYS = 1461                # how far time runs (4 years) before it starts again, and the tables' reach ...
MOTION_STEP_DAYS = {"Mo": 0.5, "Me": 2.0, "Ve": 4.0, "Su": 5.0, "Ma": 5.0, "Ju": 20.0, "Sa": 20.0}    # ... and their steps
CX, CY = WIDTH / 2.0, HEIGHT / 2.0
TEXT_W, TEXT_H = 8.0, 18.0      # a character's width and a line's height, for keeping labels apart


@dataclass
class GlobeInput:
    birth: dict | None            # planet -> (RA, Dec) at birth, CB included
    now: dict | None              # planet -> (RA, Dec) now
    jd_birth: float | None
    jd_now: float
    cb: tuple[float, float] | None    # birth place (lat, lon)
    cn: tuple[float, float] | None    # place now (lat, lon)
    show_birth: bool = True
    show_now: bool = False
    show_ra: bool = True
    show_dec: bool = True
    show_latitude: bool = False       # the Earth's lines of latitude and of longitude, which turn with it
    show_longitude: bool = False
    bodies: tuple = BODY_CHOICES      # the bodies to show, with their RA and Dec lines
    paths: tuple = BODY_CHOICES       # the bodies whose paths to draw
    utc_birth: float | None = None    # the UTC offsets the clocks show their moments in, hours (None: in UT)
    utc_now: float | None = None


def _view() -> tuple[float, float]:
    """The fixed (lat, roll) rotation of the view: the axis leans TILT from upright, the way LEAN_TOWARD says. The north pole
    then points (sin TILT sin LEAN, cos TILT, sin TILT cos LEAN) = (right, up, toward the viewer)."""
    t, w = math.radians(TILT), math.radians(LEAN_TOWARD)
    return (math.degrees(math.asin(math.sin(t) * math.cos(w))),
            -math.degrees(math.atan2(math.sin(t) * math.sin(w), math.cos(t))))   # (a positive roll leans it left)


def _start(g: GlobeInput) -> tuple[float, float]:
    """The moment the Earth starts at and the longitude then facing the viewer: the birth, or now with only Now shown."""
    if g.show_now and g.cn and not g.show_birth:
        return g.jd_now, g.cn[1]
    return (g.jd_birth if g.jd_birth is not None else g.jd_now), (g.cb[1] if g.cb else 0.0)


def _sky_point(ra: float, dec: float, ra_facing: float) -> tuple[float, float, float]:
    """A point of the celestial sphere on the chart: x, y in pixels, and z > 0 on the side toward the viewer."""
    lat0, roll0 = _view()
    d, de = math.radians(ra - ra_facing), math.radians(dec)
    x, y, z = math.cos(de) * math.sin(d), math.sin(de), math.cos(de) * math.cos(d)
    p, r = math.radians(lat0), math.radians(-roll0)
    y, z = y * math.cos(p) - z * math.sin(p), y * math.sin(p) + z * math.cos(p)
    x, y = x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)
    return CX + SKY_RADIUS * x, CY - SKY_RADIUS * y, z


@lru_cache(maxsize=64)
def _motion_table(planet: str, jd: float) -> dict:
    """A body's RA, Dec and distance from jd on, for the page to move it by: what it needs to size it and name its Distance(%)
    too. (To true scale the Sun and Moon would be about 3 px wide and the planets far less than 1 px, so the page sizes the
    markers on a logarithmic scale of how wide they look from the Earth: bigger always means looks bigger.)"""
    step = MOTION_STEP_DAYS[planet]
    pts = [core.position(planet, jd + i * step) for i in range(int(MOTION_DAYS / step) + 2)]
    return {"step": step, "ra": [round(p.ra, 3) for p in pts], "dec": [round(p.dec, 3) for p in pts],
            "dist": [round(p.dist_au, 6) for p in pts], "dec_speed": [round(p.dec_speed, 4) for p in pts],
            "km": BODY_RADIUS_KM[planet], "colour": core.colour(planet),
            "lo": core.DIST_RANGE[planet][0], "hi": core.DIST_RANGE[planet][1]}


def _sun_path(angle: float) -> tuple[float, float]:
    """The (RA, Dec) a given angle round the Sun's yearly path, counted from where it crosses the celestial equator going
    north. Only the circle is drawn: the angle itself is never shown."""
    a, t = math.radians(angle), math.radians(TILT)
    return (math.degrees(math.atan2(math.cos(t) * math.sin(a), math.cos(a))) % 360.0,
            math.degrees(math.asin(math.sin(t) * math.sin(a))))


def _planet_path(planet: str, jd: float) -> list[tuple[float, float]]:
    """The (RA, Dec) of a body from the Earth over one trip round the sky with jd in the middle, loops included. The Moon's
    is closed into a ring; a planet's does not quite meet, as a planet comes back to a different place."""
    days, steps, _ = PATH_SPAN[planet]
    pts = [core.position(planet, jd + days * (v / steps - 0.5)) for v in range(steps + 1)]
    pts = [(p.ra, p.dec) for p in pts]
    return pts + pts[:1] if planet == "Mo" else pts


def _sky_line(pts: list[tuple[float, float]], ra_facing: float, colour: str, width: float, dash: bool, tip: str,
              near: list[str], far: list[str]) -> None:
    """A line along the sphere, cut where it passes between the near side and the far side."""
    runs: list[tuple[bool, list[str]]] = []
    for ra, dec in pts:
        x, y, z = _sky_point(ra, dec, ra_facing)
        if not runs or runs[-1][0] != (z >= 0):
            runs.append((z >= 0, [runs[-1][1][-1]] if runs else []))
        runs[-1][1].append(f"{x:.1f},{y:.1f}")
    for front, run in runs:
        (near if front else far).append(
            f'<polyline points="{" ".join(run)}" fill="none" stroke="{colour}" stroke-width="{width}"'
            f'{" stroke-dasharray=" + chr(34) + "6 4" + chr(34) if dash else ""} style="pointer-events:stroke">'
            f"<title>{tip}</title></polyline>")


def _text(x: float, y: float, text: str, colour: str, anchor: str = "middle", opacity: float = 1.0) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" fill="{colour}" font-weight="bold" '
            f'font-size="{FONT}" opacity="{opacity}" font-family="{CHART_FONT_FAMILY}" stroke="white" stroke-width="3" '
            f'paint-order="stroke">{text}</text>')


def _box(x: float, y: float, text: str, anchor: str = "middle") -> tuple[float, float, float, float]:
    """The room a label takes: left, top, right, bottom (y is its baseline)."""
    w = len(text) * TEXT_W
    left = x - w / 2 if anchor == "middle" else x if anchor == "start" else x - w
    return left - 3, y - TEXT_H + 3, left + w + 3, y + 3      # (a little to spare at each side)


def _clear(box, taken) -> bool:
    return all(box[2] < t[0] or t[2] < box[0] or box[3] < t[1] or t[3] < box[1] for t in taken)


def sky_svg(g: GlobeInput) -> tuple[str, list]:
    """The celestial sphere, drawn over the Earth's chart: its far side faint and hidden where the Earth is before it,
    its near side in front of the Earth, as through glass. It never moves, so it is drawn once, with empty groups for the
    page to put the moving bodies and their lines in. Also the room its labels take, for the moving labels to keep off."""
    jd, facing = _start(g)
    ra_facing = core.lst(jd, facing)
    lat0, roll0 = _view()
    tilt_up = math.cos(math.radians(lat0))
    ux, uy = -math.sin(math.radians(roll0)), math.cos(math.radians(roll0))      # the axis's way on the chart, up
    R, E = SKY_RADIUS, EARTH_RADIUS
    near: list[str] = []
    far: list[str] = []
    marks: list[str] = []
    taken: list = []

    # the axis, from the poles of the Earth to the poles of the sky; the south pole of the Earth is behind it, so from its edge
    axis = "".join(
        f'<line x1="{CX + s * a * ux:.1f}" y1="{CY - s * a * uy:.1f}" x2="{CX + s * (R + 4) * ux:.1f}" '
        f'y2="{CY - s * (R + 4) * uy:.1f}" stroke="{AXIS_COLOUR}" stroke-width="2.5"/>'
        for s, a in ((1, E * tilt_up), (-1, E)))
    for s, name, dy in ((1, "North Celestial Pole", -6), (-1, "South Celestial Pole", 16)):
        lx, ly = CX + s * (R + 8) * ux, CY - s * (R + 8) * uy + dy
        marks.append(_text(lx, ly, name, AXIS_COLOUR))
        taken.append(_box(lx, ly, name))
        px, py = CX + s * R * tilt_up * ux, CY - s * R * tilt_up * uy
        marks.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{AXIS_COLOUR}"/>')
        taken.append((px - 5, py - 5, px + 5, py + 5))

    def path_label(points: list, name: str, colour: str, right: bool = False) -> None:
        """Names a line at its near side's left-hand (or right-hand) end, or as near there as is free."""
        px, py, _ = (max if right else min)((p for p in (_sky_point(a, d, ra_facing) for a, d in points) if p[2] >= 0),
                                            key=lambda p: p[0])
        lx, anchor = (px + 8, "start") if right else (px - 8, "end")
        ly = next(y for y in (py + 4 + v * 19 * s for v in range(90) for s in (1, -1))
                  if 16 < y < HEIGHT - 4 and _clear(_box(lx, y, name, anchor), taken))
        marks.append(_text(lx, ly, name, colour, anchor))
        taken.append(_box(lx, ly, name, anchor))

    # the celestial equator
    circle = [(ra_facing + v, 0.0) for v in range(-180, 181, 2)]
    _sky_line(circle, ra_facing, AXIS_COLOUR, 1.4, False, "Celestial equator (Dec 0)", near, far)
    path_label(circle, "Celestial Equator", AXIS_COLOUR, right=True)

    if "Su" in g.paths:
        # the Sun's path over a year: the circle tilted TILT to the celestial equator
        path = [_sun_path(v) for v in range(0, 361, 2)]
        _sky_line(path, ra_facing, core.colour("Su"), 2.4, False,
                  f"Path of the Sun over a year (Dec between {-TILT:+.2f} and {TILT:+.2f})", near, far)
        path_label(path, "Path of the Sun", core.colour("Su"))

    # the others, which shift over the years: one trip round the sky around the birth and, dashed, around now
    for show, when, what, dash in ((g.show_birth, g.jd_birth, "birth", False), (g.show_now, g.jd_now, "now", True)):
        if show and when is not None:
            for p, (days, _steps, name) in PATH_SPAN.items():
                if p not in g.paths:
                    continue
                path = _planet_path(p, when)
                _sky_line(path, ra_facing, core.colour(p), 2.4 if p == "Mo" else 1.8, dash,
                          f"{name}: {days:g} days around {what} "
                          f"(Dec between {min(d for _, d in path):+.2f} and {max(d for _, d in path):+.2f})", near, far)
                path_label(path, name, core.colour(p))

    hole =f"M{CX - E} {CY}a{E} {E} 0 1 0 {2 * E} 0a{E} {E} 0 1 0 {-2 * E} 0Z"     # the Earth's disc
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'style="position:absolute;left:0;top:0;pointer-events:none">'
            f'<defs><clipPath id="off-earth"><path clip-rule="evenodd" d="M0 0H{WIDTH}V{HEIGHT}H0Z{hole}"/></clipPath></defs>'
            f'<g clip-path="url(#off-earth)"><circle cx="{CX}" cy="{CY}" r="{R}" fill="{SKY_FILL}" stroke="{AXIS_COLOUR}" '
            f'stroke-width="1"/><g opacity="{BACK_OPACITY}">{"".join(far)}<g class="sky-far"></g></g></g>'
            f'{axis}{"".join(near)}<g class="sky-near"></g>{"".join(marks)}<g class="sky-marks"></g></svg>'), taken


def _motion_data(g: GlobeInput, day_seconds: float | None) -> dict:
    """All the page needs to place the bodies at any moment after the start."""
    jd, facing = _start(g)
    lat0, roll0 = _view()
    sets, places = [], []
    for show, when, name, offset, label, title, place in (
            (g.show_birth, g.jd_birth, "DOB", g.utc_birth, "CB", "birth place", g.cb),
            (g.show_now, g.jd_now, "Now", g.utc_now, "CN", "place now", g.cn)):
        if show and when is not None:
            if place:                                         # its box: the planets moving to and from it are all seven
                places.append(dict(label=label, title=title, lat=place[0], lon=place[1], ra=core.lst(when, place[1]),
                                   set=len(sets)))
            sets.append(dict(clock=name, jd=when, offset=offset, shown=[p for p in core.BUTTON_ORDER if p in g.bodies],
                             tables={p: _motion_table(p, when) for p in core.BUTTON_ORDER}))
    svg, taken = sky_svg(g)
    return dict(svg=svg, taken=[[round(v, 1) for v in box] for box in taken], sets=sets, places=places,
                key=f"{g.jd_birth}|{g.cb}", ra_facing=core.lst(jd, facing), lon0=facing, tilt=math.radians(lat0),
                roll=math.radians(-roll0), cx=CX, cy=CY, sky=SKY_RADIUS, earth=EARTH_RADIUS, width=WIDTH, height=HEIGHT,
                day_seconds=day_seconds, days=MOTION_DAYS, spin=EARTH_DEGREES_A_DAY, show_ra=g.show_ra, show_dec=g.show_dec,
                au_km=core.AU_KM, sizes=SIZE_RANGE_ARCSEC, radii=MARKER_RANGE, text_w=TEXT_W, text_h=TEXT_H, font=FONT,
                family=CHART_FONT_FAMILY, step_ms=max(40, int((day_seconds or 60.0) * 2.5)))


def globe_figure(g: GlobeInput) -> go.Figure:
    """The Earth: land and sea, and CB and CN with their RA and Dec lines, which turn with it."""
    fig = go.Figure()
    lats = [v / 2.0 for v in range(-180, 181)]           # a meridian, pole to pole, every half degree
    lons = [v / 2.0 for v in range(-360, 361)]           # a circle of latitude, right round, every half degree
    for label, place, symbol, show, jd in (("CB", g.cb, "diamond", g.show_birth, g.jd_birth),
                                           ("CN", g.cn, "triangle-up", g.show_now, g.jd_now)):
        if show and place:
            lat, lon = place
            if jd is not None:                                # its RA (the sidereal time there) and Dec (its latitude)
                ra = core.lst(jd, lon)
                for on, text, line_lon, line_lat in ((g.show_ra, f"{label} RA: {ra:.2f}", [lon] * len(lats), lats),
                                                     (g.show_dec, f"{label} Dec/Lati: {lat:+.2f}", lons, [lat] * len(lons))):
                    if not on:
                        continue
                    fig.add_trace(go.Scattergeo(
                        lon=line_lon, lat=line_lat, mode="lines", showlegend=False,
                        line=dict(color="black", width=1.4, dash="dash" if label == "CN" else "solid"),
                        hoverinfo="text", text=text, opacity=0.7 if label == "CN" else 0.9))
            fig.add_trace(go.Scattergeo(
                lon=[lon], lat=[lat], mode="markers+text", showlegend=False, text=[f"<b>{label}</b>"],
                textposition="bottom center" if label == "CB" else "top center",   # apart even in the same place
                textfont=dict(size=FONT, color="black"),
                marker=dict(size=12, color="black", symbol=symbol), hoverinfo="text",
                hovertext=f"<b>{label}</b> {'birth place' if label == 'CB' else 'place now'}<br>"
                          f"latitude {lat:+.2f}, longitude {lon:+.2f}"))

    lat0, roll0 = _view()
    half = EARTH_RADIUS / (HEIGHT - 2 * MARGIN)               # the Earth's part of the chart's height, about its middle
    fig.update_layout(
        dragmode=False,                                       # fixed on its axis: it cannot be dragged off it
        width=WIDTH, height=HEIGHT, autosize=False, margin=dict(l=MARGIN, r=MARGIN, t=MARGIN, b=MARGIN),
        paper_bgcolor="white", font=dict(size=FONT, color=CHART_TEXT), hoverlabel=dict(font_size=FONT),
        geo=dict(domain=dict(y=[0.5 - half, 0.5 + half]),
                 projection=dict(type="orthographic", rotation=dict(lon=_start(g)[1], lat=lat0, roll=roll0)),
                 showland=True, landcolor="rgb(236,236,230)", showocean=True, oceancolor="rgb(220,232,245)",
                 showcoastlines=True, coastlinecolor="rgb(150,150,150)", showcountries=True,
                 countrycolor="rgb(200,200,200)", showframe=False, bgcolor="rgba(0,0,0,0)",
                 lataxis=dict(showgrid=g.show_latitude, dtick=GRID_DEGREES, gridcolor=GRID_COLOUR, gridwidth=1),
                 lonaxis=dict(showgrid=g.show_longitude, dtick=GRID_DEGREES, gridcolor=GRID_COLOUR, gridwidth=1)))
    return fig


# The page's part, run with the chart drawn as gd. Time runs from each shown moment by the same days t: the Earth turns inside
# the still sphere, west to east, and each body moves over the sphere as it really did, by the clock, so the speed holds
# however long a redraw takes. t is kept across the page's redraws, so a button does not send it back, and holds when Rotate
# is off. (Spaces after every less-than: the page drops a script that seems to have tags in it.)
_MOTION_JS = r"""
  const D = __DATA__;
  const holder = document.createElement("div");
  holder.innerHTML = D.svg;
  const sky = holder.firstChild;
  const tops = gd.querySelector(".svg-container").querySelectorAll(":scope > svg.main-svg");
  tops[tops.length - 1].before(sky);
  const NS = "http://www.w3.org/2000/svg", RAD = Math.PI / 180;
  const farG = sky.querySelector(".sky-far"), nearG = sky.querySelector(".sky-near"), markG = sky.querySelector(".sky-marks");
  const make = (tag, parent, attrs) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    parent.appendChild(e);
    return e;
  };
  const words = (parent, attrs) => make("text", parent, Object.assign({"font-weight": "bold", "font-size": D.font,
    "font-family": D.family, stroke: "white", "stroke-width": 3, "paint-order": "stroke"}, attrs));
  const cp = Math.cos(D.tilt), sp = Math.sin(D.tilt), cr = Math.cos(D.roll), sr = Math.sin(D.roll);
  const point = (ra, dec) => {                     // on the chart: x, y, and z above 0 on the side toward the viewer
    const d = (ra - D.ra_facing) * RAD, e = dec * RAD, ce = Math.cos(e);
    const x = ce * Math.sin(d), y = Math.sin(e), z = ce * Math.cos(d);
    const y1 = y * cp - z * sp, z1 = y * sp + z * cp;
    return [D.cx + D.sky * (x * cr + y1 * sr), D.cy - D.sky * (-x * sr + y1 * cr), z1];
  };
  const sample = (b, t) => {                       // between its two nearest table rows
    const u = t / b.step, i = Math.min(Math.floor(u), b.ra.length - 2), f = u - i;
    const turn = ((b.ra[i + 1] - b.ra[i] + 540) % 360) - 180;
    return {ra: (b.ra[i] + turn * f + 360) % 360, dec: b.dec[i] + (b.dec[i + 1] - b.dec[i]) * f,
            dist: b.dist[i] + (b.dist[i + 1] - b.dist[i]) * f,
            dec_speed: b.dec_speed[i] + (b.dec_speed[i + 1] - b.dec_speed[i]) * f};
  };
  const curve = (pts) => {                         // the path data of a line's near side and of its far side
    let near = "", far = "", side = null, last = "";
    pts.forEach(([ra, dec]) => {
      const [x, y, z] = point(ra, dec), here = z >= 0, at = x.toFixed(1) + " " + y.toFixed(1);
      if (here !== side) {
        const start = (last ? "M" + last + "L" : "M") + at;
        if (here) near += start; else far += start;
        side = here;
      } else if (here) near += "L" + at; else far += "L" + at;
      last = at;
    });
    return [near, far];
  };
  const line = (colour, dashed) => {               // a near part and a far part, each with its hover title
    const parts = [nearG, farG].map((g) => {
      const attrs = {fill: "none", stroke: colour, "stroke-width": 1.4, style: "pointer-events:stroke"};
      if (dashed) attrs["stroke-dasharray"] = "6 4";
      const e = make("path", g, attrs);
      return [e, make("title", e)];
    });
    return (pts, tip) => {
      const c = curve(pts);
      parts.forEach(([e, title], i) => { e.setAttribute("d", c[i]); title.textContent = tip; });
    };
  };
  const bodies = [];
  D.sets.forEach((s) => s.shown.forEach((p) => {
    const b = s.tables[p];
    const body = {name: p, tipName: p + " " + s.clock, b, set: s, now: s.clock === "Now"};   // Now: hollow, dashed
    if (D.show_ra) body.raLine = line(b.colour, body.now);
    if (D.show_dec) body.decLine = line(b.colour, body.now);
    bodies.push(body);
  }));
  bodies.forEach((body) => {
    const c = body.b.colour;
    body.mark = make("circle", markG, {fill: body.now ? "white" : c, stroke: c, "stroke-width": 2, style: "pointer-events:auto"});
    body.tip = make("title", body.mark);
    body.label = words(markG, {"text-anchor": "middle", fill: c});
    body.label.textContent = body.name;
  });
  const pad2 = (n) => (n >= 0 ? "+" : "-") + Math.abs(n).toFixed(2);
  const clockLine = (s, t) => {                    // its date and time, at its place's UTC offset
    const known = s.offset !== null && s.offset !== undefined, off = known ? s.offset : 0;
    const ms = (s.jd + t - 2440587.5) * 86400000 + off * 3600000 + 30000;     // to the nearest minute
    return s.clock + " " + new Date(ms).toISOString().slice(0, 16).replace("T", " ") + (known ? " UTC" + pad2(off) : " UT");
  };
  const showClocks = (t) => {                      // in the page's clock, beside the customer's name
    const box = document.querySelector(".globe-clock");
    if (box) box.textContent = D.sets.map((s) => clockLine(s, t)).join("    ");
  };
  const boxOf = (x, y, text) => {
    const w = text.length * D.text_w;
    return [x - w / 2 - 3, y - D.text_h + 3, x + w / 2 + 3, y + 3];
  };
  const clear = (a, taken) => taken.every((b) => a[2] < b[0] || b[2] < a[0] || a[3] < b[1] || b[3] < a[1]);
  const inChart = (a) => a[0] > 0 && a[1] > 0 && a[2] < D.width && a[3] < D.height;
  const spot = (body, x, y, r, taken) => {         // its last way round the marker while that stays free, else the nearest free
    const side = body.name.length * D.text_w / 2 + r + 5;
    const ways = [[0, -r - 6], [0, r + 15], [side, 5], [-side, 5], [side, -r - 4], [-side, -r - 4], [side, r + 13], [-side, r + 13]];
    const at = (w, reach) => {
      const [dx, dy] = ways[w];
      return [x + dx + (dx > 0 ? reach * 12 : dx < 0 ? -reach * 12 : 0), y + dy + (dy > 5 ? reach * 14 : dy < 0 ? -reach * 14 : 0)];
    };
    const ok = (p) => { const a = boxOf(p[0], p[1], body.name); return inChart(a) && clear(a, taken); };
    if (body.way !== undefined && ok(at(body.way, 0))) return at(body.way, 0);
    for (let reach = 0; reach !== 40; reach++) for (let w = 0; w !== 8; w++) {
      const p = at(w, reach);
      if (ok(p)) { body.way = w; return p; }
    }
    return at(0, 0);
  };
  const names = (list) => list.sort((a, b) => a[1] - b[1]).map(([p, gap]) => p + " " + gap.toFixed(1) + "°").join(", ") || "none";
  const moving = (body, s, t) => {                 // the others approaching and leaving it: the gap in Dec closing or opening
    const near = [], away = [];
    Object.entries(body.set.tables).forEach(([q, b]) => {
      if (q === body.name) return;
      const o = sample(b, t), gap = o.dec - s.dec, rate = (o.dec_speed - s.dec_speed) * (gap >= 0 ? 1 : -1);
      if (rate) (rate < 0 ? near : away).push([q, Math.abs(gap)]);
    });
    return "\nApproach: " + names(near) + "\nLeave: " + names(away);
  };
  const LOW = Math.log(D.sizes[0]), HIGH = Math.log(D.sizes[1]);
  const place = (t) => {
    const taken = D.taken.slice();
    bodies.forEach((body) => {
      const b = body.b, s = sample(b, t);
      const [x, y, z] = point(s.ra, s.dec);
      if (body.raLine) {
        const pts = [];
        for (let v = -90; v !== 93; v += 3) pts.push([s.ra, v]);
        body.raLine(pts, body.tipName + " RA: " + s.ra.toFixed(2));
      }
      if (body.decLine) {
        const pts = [];
        for (let v = -180; v !== 183; v += 3) pts.push([D.ra_facing + v, s.dec]);
        body.decLine(pts, body.tipName + " Dec/Lati: " + (s.dec >= 0 ? "+" : "") + s.dec.toFixed(2));
      }
      const arcsec = 2 * Math.atan(b.km / (s.dist * D.au_km)) / RAD * 3600;
      const share = Math.max(0, Math.min(1, (Math.log(arcsec) - LOW) / (HIGH - LOW)));
      const r = D.radii[0] + (D.radii[1] - D.radii[0]) * share;
      const hidden = z < 0 && Math.hypot(x - D.cx, y - D.cy) < D.earth;   // behind the Earth
      const fade = z >= 0 ? 1 : 0.55, size = arcsec >= 60 ? (arcsec / 60).toFixed(1) + " arcmin" : arcsec.toFixed(1) + " arcsec";
      const pct = (s.dist * D.au_km - b.lo) / (b.hi - b.lo) * 100;
      Object.assign(body, {x, y, r, hidden, fade});
      body.mark.setAttribute("cx", x.toFixed(1)); body.mark.setAttribute("cy", y.toFixed(1));
      body.mark.setAttribute("r", r.toFixed(1)); body.mark.setAttribute("opacity", fade);
      body.mark.style.display = hidden ? "none" : ""; body.label.style.display = hidden ? "none" : "";
      body.tip.textContent = body.tipName + " (" + (z >= 0 ? "near" : "far") + " side of the sphere)\nRA: " + s.ra.toFixed(2) +
        "\nDec/Lati: " + (s.dec >= 0 ? "+" : "") + s.dec.toFixed(2) + "\nAngular Size: " + size +
        "\nDistance from earth: " + Math.max(0, Math.round(pct)) + "%" + moving(body, s, t);
      if (!hidden) taken.push([x - r - 1, y - r - 1, x + r + 1, y + r + 1]);   // no label may cover a marker
    });
    bodies.forEach((body) => {
      if (body.hidden) return;
      const [lx, ly] = spot(body, body.x, body.y, body.r, taken);
      taken.push(boxOf(lx, ly, body.name));
      body.label.setAttribute("x", lx.toFixed(1)); body.label.setAttribute("y", ly.toFixed(1));
      body.label.setAttribute("opacity", body.fade);
    });
    showClocks(t);
  };
  const signed = (v) => (v >= 0 ? "+" : "") + v.toFixed(2);
  const tag = (name) => String.fromCharCode(60) + name + String.fromCharCode(62);   // (no tags written out in this script)
  const NL = tag("br");
  const placeBox = (pl, t) => {                    // CB's or CN's box: approaching = the gap in Dec to its latitude is closing
    const near = [], away = [];
    Object.entries(D.sets[pl.set].tables).forEach(([p, b]) => {
      const s = sample(b, t), gap = s.dec - pl.lat, rate = s.dec_speed * (gap >= 0 ? 1 : -1);
      if (rate) (rate < 0 ? near : away).push([p, Math.abs(gap)]);
    });
    return tag("b") + pl.label + tag("/b") + " " + pl.title + NL + "Long: " + signed(pl.lon) + NL + "Dec/Lati: " + signed(pl.lat) +
      NL + "RA: " + (((pl.ra + D.spin * t) % 360 + 360) % 360).toFixed(2) +
      NL + "Approaching: " + names(near) + NL + "Leaving: " + names(away);
  };
  const placeTraces = D.places.map((pl) => gd.data.findIndex((d) =>
    d.mode === "markers+text" && String(d.text[0]).includes(pl.label)));
  let textsDue = 0;
  const redraw = (t) => {                          // the Earth's turn and, each second, CB's and CN's boxes
    const now = performance.now(), turn = {"geo.projection.rotation.lon": facing(t)}, done = () => { busy = false; };
    busy = true;
    if (D.places.length && now >= textsDue) {
      textsDue = now + 1000;
      Plotly.update(gd, {hovertext: D.places.map((pl) => placeBox(pl, t))}, turn, placeTraces).then(done);
    } else Plotly.relayout(gd, turn).then(done);
  };
  const facing = (t) => (((D.lon0 - D.spin * t + 540) % 360) + 360) % 360 - 180;
  if (!window.globeClock || window.globeClock.key !== D.key) window.globeClock = {key: D.key, t: 0};
  const clock = window.globeClock;
  place(clock.t);
  let busy = false;
  redraw(clock.t);
  if (D.day_seconds) {
    let last = performance.now();
    const timer = setInterval(() => {
      if (!document.body.contains(gd)) return clearInterval(timer);
      if (busy) return;
      const now = performance.now();
      clock.t += (now - last) / 1000 / D.day_seconds;
      last = now;
      if (clock.t >= D.days) clock.t = 0;           // the end of the tables: from the start again
      place(clock.t);
      redraw(clock.t);
    }, D.step_ms);
  }
"""


def globe_js(g: GlobeInput, day_seconds: float | None) -> str:
    """Puts the celestial sphere over the chart, under Plotly's hover boxes, and moves what is on it; day_seconds is how many
    seconds a day takes, None with Rotate off."""
    return _MOTION_JS.replace("__DATA__", json.dumps(_motion_data(g, day_seconds)).replace("<", chr(92) + "u003c"))
