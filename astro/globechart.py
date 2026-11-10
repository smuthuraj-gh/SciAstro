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
# the seconds one day of the clock takes: an hour, a day, a week, a month (30.44 days) or a year (365.25 days) to a second
SPEEDS = {"1h": 24.0, "1d": 1.0, "1w": 1.0 / 7.0, "1m": 1.0 / 30.44, "1y": 1.0 / 365.25}
EARTH_RADIUS = 165.0              # pixels, in the chart's own layout
SKY_RADIUS = 315.0                # the celestial sphere, pixels (it fits the chart's height with its pole labels)
AXIS_COLOUR = "rgb(60,60,60)"
GRID_DEGREES = 30                 # between the Earth's lines of latitude, and of longitude
GRID_COLOUR = "rgb(120,120,120)"
SKY_FILL = "rgb(244,246,252)"
BACK_OPACITY = 0.3                # the far side of the sphere, seen through it
BODY_RADIUS_KM = {"Su": 695700.0, "Mo": 1737.4, "Me": 2439.7, "Ve": 6051.8, "Ma": 3396.2, "Ju": 71492.0, "Sa": 60268.0}
SIZE_RANGE_ARCSEC = (3.5, 2040.0)     # the smallest (Mars at its farthest) to the largest (the Moon at its nearest) ...
MARKER_RANGE = (7.0, 14.0)            # ... drawn with these marker radii, in pixels (big enough to hold its symbol)
# A path's days (one trip round the sky seen from the Earth: Mercury and Venus keep with the Sun, so a year), points drawn, name
PATH_SPAN = {"Mo": (27.32, 110, "Moon Path"), "Me": (365.25, 365, "Mercury Path"),
             "Ve": (365.25, 365, "Venus Path"), "Ma": (687.0, 400, "Mars Path"),
             "Ju": (4333.0, 400, "Jupiter Path"), "Sa": (10759.0, 400, "Saturn Path")}
BODY_CHOICES = ("Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa")
TRAIL_SPAN = {"Su": (365.25, 120, "Sun Path"), **PATH_SPAN, "NN": (6793.5, 400, "NN Path"), "SN": (6793.5, 400, "SN Path")}
NODE_CHOICES = ("NN", "SN")       # the Moon's north and south nodes, picked with the planets
MANUAL = "Manual"                 # Rotate's option to drag the Earth round by hand
HOUSE_COLOUR = "rgb(0,0,0)"
ASPECT_COLOURS = {False: "rgb(0,0,0)", True: "rgb(110,110,110)"}     # major, minor
HOUSE_VALUE_DEC = (-32.0, -44.0)  # the Dec of each house line's RA value, first and second place shown: low on the line
HOUSE_LABEL_DEC = (55.0, 40.0)    # the Dec of the house names, first and second place shown: on the side tilted toward the viewer, off the planets' way
PLACE_APART = 24.0                # pixels within which the icons of CB and CN would overlap on the Earth, and are moved apart
EARTH_DEGREES_A_DAY = 360.98565  # the Earth's turn against the still sky in one day of the clock
MOTION_DAYS = 26298               # how far time runs (72 years) before it starts again, the trails too, and the tables' reach ...
NODE_STEP_DAYS = 2.0              # the Moon's true node wobbles over days
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
    aspects: tuple = ()               # the angles of the aspects to draw between the bodies shown
    orbs: object = None               # core.Orbs, with aspects
    show_celes: bool = True           # the names NCP, SCP, WCE and ECE, the dots at the poles, the axis and the celestial equator
    show_houses: bool = False         # the twelve house lines from CB and CN, on the sphere, turning with the Earth
    bodies: tuple = BODY_CHOICES      # the bodies to show, with their RA and Dec lines
    paths: tuple = BODY_CHOICES       # the bodies whose paths to draw
    utc_birth: float | None = None    # the UTC offsets the clocks show their moments in, hours (None: in UT)
    utc_now: float | None = None


def _ring(x: float, y: float, r: float) -> str:
    return f"M{x - r} {y}a{r} {r} 0 1 0 {2 * r} 0a{r} {r} 0 1 0 {-2 * r} 0"


# The conventional symbols, as lines about the middle of a place 16 pixels wide, scaled to go inside their markers: drawn, as not
# every font has them all
SYMBOLS = {"Su": _ring(0, 0, 6.5) + _ring(0, 0, 0.8),
           "Mo": "M3 -7A7.4 7.4 0 1 0 3 7A5.6 5.6 0 1 1 3 -7Z",
           "Me": _ring(0, -1.5, 3.2) + "M-3.4 -8A3.5 3.5 0 0 0 3.4 -8M0 1.7V8M-2.6 5H2.6",
           "Ve": _ring(0, -3, 4.2) + "M0 1.2V8M-3 4.8H3",
           "Ma": _ring(-1.8, 1.8, 4.4) + "M1.3 -1.3L6.5 -6.5M2.3 -6.5H6.5V-2.3",
           "Ju": "M-5.5 -3.5C-5.5 -8 1 -8 .5 -2.5C.2 .5 -3 2.5 -6 2.5H6M3 -7V7.5",
           "Sa": "M-4 -5.5H1.2M-1.4 -8V1.8C.5 -2.5 6 -2.5 5.6 1.5C5.3 4.5 1.5 5.5 2.8 8",
           "Ea": _ring(0, 0, 7) + "M-7 0H7M0 -7V7",
           # the place now, a house with a door (the birth place shows its Symbol as it is: the baby emoji)
           "CN": "M-8.5 0L0 -8L8.5 0M-6 -2V8H6V-2M-1.8 8V3H1.8V8",
           # the Moon's nodes: north an arch on two small circles, south the same upside down
           "NN": "M-3.6 4.2C-8.4 -0.8 -6 -7 0 -7C6 -7 8.4 -0.8 3.6 4.2" + _ring(-4.6, 5.4, 1.7) + _ring(4.6, 5.4, 1.7),
           "SN": "M-3.6 -4.2C-8.4 0.8 -6 7 0 7C6 7 8.4 0.8 3.6 -4.2" + _ring(-4.6, -5.4, 1.7) + _ring(4.6, -5.4, 1.7)}
# Which shape each symbol is drawn with, so that the Symbol column of the Naming Conventions table says what is drawn
GLYPHS = {"\u2609": "Su", "\u263d": "Mo", "\u263f": "Me", "\u2640": "Ve", "\u2642": "Ma", "\u2643": "Ju", "\u2644": "Sa", "\u2295": "Ea", "\u2641": "Ea",
          "\u260a": "NN", "\u260b": "SN", "\U0001f3e0": "CN"}


def symbol_shapes() -> dict:
    """What to draw for each row: {"d": a shape} for a symbol above, in the row's colour, or {"text": ..} for anything else, or the SN
    where the Symbol is blank."""
    out = {}
    for name in (*SYMBOLS, "CB"):
        text = core.SYMBOL_TEXTS.get(name, "") or name
        out[name] = {"d": SYMBOLS[GLYPHS[text]]} if text in GLYPHS else {"text": text}
    return out


# The page's part, for both pages: a marker's symbol, in black or white, whichever shows on its colour, or in its colour on a hollow one
SYMBOL_JS = r"""
  const symbolOf = (name) => D.sym[name] || name;
  const inkOn = (colour) => {
    const [r, g, b] = colour.startsWith("#") ? [1, 3, 5].map((i) => parseInt(colour.slice(i, i + 2), 16)) : colour.match(/[0-9]+/g).map(Number);
    return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "black" : "white";
  };
  const drawShape = (parent, name, colour, width) => {   // as the Symbol column says: a shape in its colour, or a text
    const s = D.shapes[name];
    if (s.d) return make("path", parent, {d: s.d, fill: "none", stroke: colour, "stroke-width": width, "stroke-linecap": "round", "stroke-linejoin": "round"});
    const emoji = s.text.codePointAt(0) >= 0x1f000;   // an emoji, as the table shows it, bigger to be seen
    const text = make("text", parent, {x: 0, y: emoji ? 7 : 4.5, "text-anchor": "middle", "font-size": emoji ? 20 : 13, "font-weight": "bold", "font-family": D.family, fill: colour});
    text.textContent = s.text;
    return text;
  };
  const symbolTag = (parent, name, colour, hollow) => {
    const tag = make("g", parent, {style: "pointer-events:none"});
    tag.line = drawShape(tag, name, hollow ? colour : inkOn(colour), 1.5);
    return tag;
  };
  const fitSymbol = (tag, x, y, r) => {            // inside its marker, and as thick whatever the size
    const k = r / 9.5;
    tag.style.display = r < 5 ? "none" : "";       // too small to read: a dot alone
    tag.setAttribute("transform", "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ") scale(" + k.toFixed(3) + ")");
    tag.line.setAttribute("stroke-width", (1.5 / k).toFixed(2));
  };
"""


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


@lru_cache(maxsize=24)
def _motion_table(planet: str, jd: float, days: int = MOTION_DAYS) -> dict:
    """A body's RA, Dec and distance from jd on, for the page to move it by: what it needs to size it and name its Distance(%)
    too. (To true scale the Sun and Moon would be about 3 px wide and the planets far less than 1 px, so the page sizes the
    markers on a logarithmic scale of how wide they look from the Earth: bigger always means looks bigger.)"""
    step = MOTION_STEP_DAYS[planet]
    pts = [core.position(planet, jd + i * step) for i in range(int(days / step) + 2)]
    return {"step": step, "ra": [round(p.ra, 3) for p in pts], "dec": [round(p.dec, 3) for p in pts],
            "dist": [round(p.dist_au, 6) for p in pts], "dec_speed": [round(p.dec_speed, 4) for p in pts],
            "km": BODY_RADIUS_KM[planet],
            "lo": core.DIST_RANGE[planet][0], "hi": core.DIST_RANGE[planet][1]}


@lru_cache(maxsize=24)
def _node_table(jd: float) -> dict:
    """The Moon's north node from jd on, for the page to move NN and SN by (the south node is opposite it)."""
    pts = [core.moon_north_node(jd + i * NODE_STEP_DAYS) for i in range(int(MOTION_DAYS / NODE_STEP_DAYS) + 2)]
    return {"step": NODE_STEP_DAYS, "ra": [round(p[0], 3) for p in pts], "dec": [round(p[1], 3) for p in pts]}


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
        for s, a in ((1, E * tilt_up), (-1, E))) if g.show_celes else ""
    for s, name, dy in ((1, "NCP", -6), (-1, "SCP", 16)) if g.show_celes else ():
        lx, ly = CX + s * (R + 8) * ux, CY - s * (R + 8) * uy + dy
        marks.append(_text(lx, ly, name, AXIS_COLOUR))
        taken.append(_box(lx, ly, name))
        px, py = CX + s * R * tilt_up * ux, CY - s * R * tilt_up * uy
        marks.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{AXIS_COLOUR}"/>')
        taken.append((px - 5, py - 5, px + 5, py + 5))

    # East and West on the celestial equator, at the two ends of the line across the axis: the Earth turns toward ECE
    for s, name in ((1, "ECE"), (-1, "WCE")) if g.show_celes else ():
        lx, ly = CX + s * (R + 24) * uy, CY + s * (R + 24) * ux + 4
        marks.append(_text(lx, ly, name, AXIS_COLOUR))
        taken.append(_box(lx, ly, name))

    # the celestial equator
    circle = [(ra_facing + v, 0.0) for v in range(-180, 181, 2)]
    if g.show_celes:
        _sky_line(circle, ra_facing, AXIS_COLOUR, 1.4, False, "Celestial equator (Dec 0)", near, far)

    hole =f"M{CX - E} {CY}a{E} {E} 0 1 0 {2 * E} 0a{E} {E} 0 1 0 {-2 * E} 0Z"     # the Earth's disc
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'style="position:absolute;left:0;top:0;pointer-events:none">'
            f'<defs><clipPath id="off-earth"><path clip-rule="evenodd" d="M0 0H{WIDTH}V{HEIGHT}H0Z{hole}"/></clipPath></defs>'
            f'<g clip-path="url(#off-earth)"><circle cx="{CX}" cy="{CY}" r="{R}" fill="{SKY_FILL}" stroke="{AXIS_COLOUR}" '
            f'stroke-width="1"/><g opacity="{BACK_OPACITY}">{"".join(far)}<g class="sky-far"></g></g><g class="sky-far-full"></g></g>'
            f'{axis}{"".join(near)}<g class="sky-near"></g>{"".join(marks)}<g class="sky-marks"></g></svg>'), taken


def _paths(g: GlobeInput) -> list[dict]:
    """The paths to draw, for the page, which draws each as a trail behind its body while time runs: where it has really been
    since time started running (solid at birth, dashed now)."""
    out = []
    for show, when, dash, clock in ((g.show_birth, g.jd_birth, False, "DOB"), (g.show_now, g.jd_now, True, "Now")):
        if show and when is not None:
            for p in BODY_CHOICES + NODE_CHOICES:
                if p in g.paths:
                    days, steps, name = TRAIL_SPAN[p]
                    out.append(dict(name=name, body=p, clock=clock, colour=core.colour(p), width=2.4 if p in ("Su", "Mo") else 1.8,
                                    dash=dash, days=days, steps=steps, tip="", pts=[]))
    return out


def _motion_data(g: GlobeInput, day_seconds: float | None, manual: bool = False) -> dict:
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
                                   colour=core.colour(label), set=len(sets)))
            sets.append(dict(clock=name, jd=when, offset=offset, shown=[p for p in core.BUTTON_ORDER if p in g.bodies],
                             tables={p: {**_motion_table(p, when), "colour": core.colour(p)} for p in core.BUTTON_ORDER},
                             node=_node_table(when) if set(NODE_CHOICES) & (set(g.bodies) | set(g.paths)) else None))
    aspects = [dict(angle=a, colour=ASPECT_COLOURS[a in core.MINOR], width=1.0 if a in core.MINOR else 1.5,
                    orbs={f"{p}|{q}": [g.orbs.pair(a, p, q, False), g.orbs.pair(a, p, q, True)]
                          for i, p in enumerate(core.shown_order(core.BUTTON_ORDER)) for q in core.shown_order(core.BUTTON_ORDER)[i + 1:]})
               for a in g.aspects] if g.orbs is not None else []
    svg, taken = sky_svg(g)
    return dict(svg=svg, aspects=aspects, paths=_paths(g), taken=[[round(v, 1) for v in box] for box in taken], sets=sets, places=places,
                key=f"{g.jd_birth}|{g.cb}", ra_facing=core.lst(jd, facing), lon0=facing, tilt=math.radians(lat0),
                roll=math.radians(-roll0), cx=CX, cy=CY, sky=SKY_RADIUS, earth=EARTH_RADIUS, width=WIDTH, height=HEIGHT,
                day_seconds=day_seconds, days=MOTION_DAYS, spin=EARTH_DEGREES_A_DAY, show_ra=g.show_ra, show_dec=g.show_dec,
                au_km=core.AU_KM, sizes=SIZE_RANGE_ARCSEC, radii=MARKER_RANGE, text_w=TEXT_W, text_h=TEXT_H, font=FONT,
                node_names=[n for n in NODE_CHOICES if n in g.bodies], name_order=core.shown_order(core.BUTTON_ORDER), shapes=symbol_shapes(), sym={n: core.symbol_of(n) for n in core.SYMBOL_TEXTS}, place_apart=PLACE_APART, size_rules={p: core.size_rule(p, texts=core.SIZE_TEXTS_GLOBE) for p in core.BUTTON_ORDER + ["NN", "SN", "CB", "CN"]}, family=CHART_FONT_FAMILY, node_colours={n: core.colour(n) for n in ("NN", "SN")}, manual=manual, show_houses=g.show_houses, house_colour=HOUSE_COLOUR,
                house_dec=HOUSE_LABEL_DEC, house_value_dec=HOUSE_VALUE_DEC, step_ms=max(40, int((day_seconds or 60.0) * 2.5)))


def globe_figure(g: GlobeInput) -> go.Figure:
    """The Earth: land and sea, and CB and CN with their RA and Dec lines, which turn with it."""
    fig = go.Figure()
    lats = [v / 2.0 for v in range(-180, 181)]           # a meridian, pole to pole, every half degree
    lons = [v / 2.0 for v in range(-360, 361)]           # a circle of latitude, right round, every half degree
    for label, place, show, jd in (("CB", g.cb, g.show_birth, g.jd_birth), ("CN", g.cn, g.show_now, g.jd_now)):
        if show and place:
            lat, lon = place
            if jd is not None:                                # its RA (the sidereal time there) and Dec (its latitude)
                ra = core.lst(jd, lon)
                for on, text, line_lon, line_lat in ((g.show_ra, f"{core.symbol_of(label)} RA: {ra:.2f}", [lon] * len(lats), lats),
                                                     (g.show_dec, f"{core.symbol_of(label)} Dec/Lati: {lat:+.2f}", lons, [lat] * len(lons))):
                    if not on:
                        continue
                    fig.add_trace(go.Scattergeo(
                        lon=line_lon, lat=line_lat, mode="lines", showlegend=False,
                        line=dict(color=core.colour(label), width=1.4, dash="dash" if label == "CN" else "solid"),
                        hoverinfo="text", text=text, opacity=0.7 if label == "CN" else 0.9))
            fig.add_trace(go.Scattergeo(
                lon=[lon], lat=[lat], mode="markers", showlegend=False, text=[label],
                marker=dict(size=18, color=core.colour(label), opacity=0), hoverinfo="text",   # not seen: there to point at; the page draws its icon
                hovertext=f"<b>{core.symbol_of(label)}</b> {'birth place' if label == 'CB' else 'place now'}<br>"
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
  const farG = sky.querySelector(".sky-far"), farFullG = sky.querySelector(".sky-far-full"), nearG = sky.querySelector(".sky-near"), markG = sky.querySelector(".sky-marks");
  const make = (tag, parent, attrs) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    parent.appendChild(e);
    return e;
  };
  const words = (parent, attrs) => make("text", parent, Object.assign({"font-weight": "bold", "font-size": D.font,
    "font-family": D.family, stroke: "white", "stroke-width": 3, "paint-order": "stroke"}, attrs));
__SYMBOL_JS__
  const cp = Math.cos(D.tilt), sp = Math.sin(D.tilt), cr = Math.cos(D.roll), sr = Math.sin(D.roll);
  let raFacing = D.ra_facing;                      // the RA facing the viewer: the view can be turned by hand (Manual)
  const point = (ra, dec) => {                     // on the chart: x, y, and z above 0 on the side toward the viewer
    const d = (ra - raFacing) * RAD, e = dec * RAD, ce = Math.cos(e);
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
  const line = (colour, dashed, full) => {         // a near part and a far part (faint, unless full), each with its hover title
    const parts = [nearG, full ? farFullG : farG].map((g) => {
      const attrs = {fill: "none", stroke: colour, "stroke-width": 1.4, style: "pointer-events:stroke"};
      if (dashed) attrs["stroke-dasharray"] = dashed === true ? "6 4" : dashed;
      const e = make("path", g, attrs);
      return [e, make("title", e)];
    });
    return (pts, tip, paint, width) => {
      const c = curve(pts);
      parts.forEach(([e, title], i) => {
        e.setAttribute("d", c[i]); title.textContent = tip;
        if (paint) { e.setAttribute("stroke", paint); e.setAttribute("stroke-width", width); }
      });
    };
  };
  const bodies = [];
  D.sets.forEach((s) => s.shown.forEach((p) => {
    const b = s.tables[p];
    const body = {name: p, tipName: symbolOf(p) + " " + s.clock, b, set: s, now: s.clock === "Now"};   // Now: hollow, dashed
    if (D.show_ra) body.raLine = line(b.colour, body.now);
    if (D.show_dec) body.decLine = line(b.colour, body.now);
    bodies.push(body);
  }));
  bodies.forEach((body) => {
    const c = body.b.colour;
    body.mark = make("circle", markG, {fill: body.now ? "white" : c, stroke: c, "stroke-width": 2, style: "pointer-events:auto"});
    body.tip = make("title", body.mark);
    body.label = symbolTag(markG, body.name, c, body.now);
  });
  const houses = [];                               // each of CB's and CN's twelve: its line and its name, in the middle of its span
  if (D.show_houses) D.places.forEach((pl) => {
    for (let k = 0; k !== 12; k++) {
      const label = words(markG, {"text-anchor": "middle", fill: D.house_colour});
      label.textContent = "H" + String((9 + k) % 12 + 1).padStart(2, "0");
      const value = words(markG, {"text-anchor": "start", fill: D.house_colour});
      houses.push({pl, k, label, value, draw: line(D.house_colour, pl.label === "CN")});
    }
  });
  const aspectLines = [];                          // each pair of the bodies shown, at each moment: its line when in aspect
  const named = (s) => D.name_order.filter((p) => s.shown.includes(p));   // each pair named in the order of the buttons: 0-Mo-Su
  if (D.aspects.length) D.sets.forEach((s) => named(s).forEach((p, i) => named(s).slice(i + 1).forEach((q) =>
    aspectLines.push({s, p, q, draw: line("black", s.clock === "Now" ? "2 3" : false),
                      tag: words(markG, {"text-anchor": "middle"})}))));
  const inAspect = (angle, a, b, orb) => {         // the rules of core.aspect_events: within the RA orb of the angle, and the Dec orb
    let sep = Math.abs(a.ra - b.ra);               // of equal (0), mirrored (180) or either (the others)
    if (sep > 180) sep = 360 - sep;
    const same = Math.abs(a.dec - b.dec) <= orb[1], mirrored = Math.abs(a.dec + b.dec) <= orb[1];
    if (angle === 0) return sep <= orb[0] && same;
    if (angle === 180) return Math.abs(sep - 180) <= orb[0] && mirrored;
    return Math.abs(sep - angle) <= orb[0] && (same || mirrored);
  };
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
  const names = (list) => list.sort((a, b) => a[1] - b[1]).map(([p, gap]) => symbolOf(p) + " " + gap.toFixed(1) + "°").join(", ") || "none";
  const moving = (body, s, t) => {                 // the others approaching and leaving it: the gap in Dec closing or opening
    const near = [], away = [];
    Object.entries(body.set.tables).forEach(([q, b]) => {
      if (q === body.name) return;
      const o = sample(b, t), gap = o.dec - s.dec, rate = (o.dec_speed - s.dec_speed) * (gap >= 0 ? 1 : -1);
      if (rate) (rate < 0 ? near : away).push([q, Math.abs(gap)]);
    });
    return "\nApproaching: " + names(near) + "\nLeaving: " + names(away);
  };
  const nodes = [];                                // where the Moon's path crosses the Sun's, north (NN) and south (SN), those picked
  D.sets.forEach((s) => {
    if (!s.node) return;
    const now = s.clock === "Now";
    [["NN", 0, 1, "north"], ["SN", 180, -1, "south"]].filter(([name]) => D.node_names.includes(name)).forEach(([name, turn, sign, pole]) => {
      const colour = D.node_colours[name];
      const mark = make("g", markG, {style: "pointer-events:auto"});
      make("rect", mark, {x: -9, y: -9, width: 18, height: 18, fill: "transparent"});   // to point at, the gaps too
      drawShape(mark, name, colour, now ? 1.2 : 2.2);   // thinner for now, as the planets are hollow
      nodes.push({name, turn, sign, pole, s, mark, tip: make("title", mark),      // with its RA and Dec lines, as the planets'
                  raLine: D.show_ra ? line(colour, now) : null, decLine: D.show_dec ? line(colour, now) : null});
    });
  });
  const nodeAt = (node, t) => {                    // between its two nearest table rows
    const n = node.s.node, u = t / n.step, i = Math.min(Math.floor(u), n.ra.length - 2), f = u - i;
    const change = ((n.ra[i + 1] - n.ra[i] + 540) % 360) - 180;
    return {ra: (n.ra[i] + change * f + node.turn + 720) % 360, dec: node.sign * (n.dec[i] + (n.dec[i + 1] - n.dec[i]) * f)};
  };
  const placeIcons = D.places.map((pl) => {        // the baby at the birth place, the house at the place now, on the Earth
    const tag = make("g", markG, {style: "pointer-events:none"});
    const under = drawShape(tag, pl.label, "white", 3.6);
    if (under.tagName === "text") { under.setAttribute("stroke", "white"); under.setAttribute("stroke-width", 3); under.setAttribute("paint-order", "stroke"); }
    drawShape(tag, pl.label, pl.colour, 1.7);
    return {pl, tag};
  });
  const placeOnEarth = (pl, t) => {                // as the Earth is turned: the place's RA by its longitude, on a sphere of the Earth's size
    const [x, y, z] = point(D.ra_facing + pl.lon - D.lon0 + D.spin * t, pl.lat), k = D.earth / D.sky;
    return [D.cx + (x - D.cx) * k, D.cy + (y - D.cy) * k, z];
  };
  const LOW = Math.log(D.sizes[0]), HIGH = Math.log(D.sizes[1]);
  const radiusAt = (rule, tables, t) => {          // by the Size in the Naming Conventions table: a fixed radius, or a planet's angular size and more
    if (rule.px !== undefined) return rule.px;
    const b = tables[rule.of], arcsec = 2 * Math.atan(b.km / (sample(b, t).dist * D.au_km)) / RAD * 3600;
    const share = Math.max(0, Math.min(1, (Math.log(arcsec) - LOW) / (HIGH - LOW)));
    return Math.max(1, D.radii[0] + (D.radii[1] - D.radii[0]) * share + rule.add);
  };
  const paths = D.paths.map((p) => {               // a path is one colour all round
    const set = D.sets.find((s) => s.clock === p.clock), node = p.body === "NN" || p.body === "SN";
    return Object.assign({}, p, {draw: line(p.colour, p.dash, true), set, table: node ? null : set.tables[p.body], node,
                                 turn: p.body === "SN" ? 180 : 0, sign: p.body === "SN" ? -1 : 1});
  });
  let pathsFacing = null, pathsAt = null, trailFrom = null;
  const TRAIL_MOST = 1500;                         // the most points a trail is drawn with: a long one is thinned, evenly
  const trailAt = (p, s) => {                      // where the body was, s days on
    if (!p.node) { const q = sample(p.table, s); return [q.ra, q.dec]; }
    const n = p.set.node, u = s / n.step, i = Math.min(Math.floor(u), n.ra.length - 2), f = u - i;
    const change = ((n.ra[i + 1] - n.ra[i] + 540) % 360) - 180;
    return [(n.ra[i] + change * f + p.turn + 720) % 360, p.sign * (n.dec[i] + (n.dec[i + 1] - n.dec[i]) * f)];
  };
  const trail = (p, t) => {                        // where the body has really been since time started running
    const run = trailFrom === null ? 0 : t - trailFrom;
    let gap = p.days / p.steps;
    while (run / gap > TRAIL_MOST) gap *= 2;         // (by doubling, so that the points stay where they were as it grows)
    p.pts = [];
    for (let n = 0; n * gap < run; n++) p.pts.push(trailAt(p, trailFrom + n * gap));
    if (run > 0) p.pts.push(trailAt(p, t));         // to the body itself
    const decs = p.pts.map((q) => q[1]), show = (v) => (v >= 0 ? "+" : "") + v.toFixed(2), days = Math.round(run);
    p.tip = p.name + " " + p.clock + ": where it has been since time started running, " + days + (days === 1 ? " day" : " days") +
      (decs.length ? " (Dec between " + show(Math.min(...decs)) + " and " + show(Math.max(...decs)) + ")" : "");
  };
  const drawPaths = () => {                        // named only on pointing at them
    paths.forEach((p) => p.draw(p.pts, p.tip, p.colour, p.width));
    pathsFacing = raFacing;
  };
  const place = (t) => {
    raFacing = D.ra_facing - clock.view;
    if (t !== pathsAt) {
      paths.forEach((p) => trail(p, t));
      pathsAt = t;
      drawPaths();
    } else if (pathsFacing !== raFacing) drawPaths();
    const taken = D.taken.slice();       // in the order of who keeps their place: the planets' tags before the houses', which spin past
    aspectLines.forEach((l) => {                   // the short way round between the two, straight in RA and Dec
      const a = sample(l.s.tables[l.p], t), b = sample(l.s.tables[l.q], t);
      const on = D.aspects.filter((d) => inAspect(d.angle, a, b, d.orbs[l.p + "|" + l.q]));
      l.tagged = on[0] || null;
      if (!on.length) return l.draw([], "");
      const turn = ((b.ra - a.ra + 540) % 360) - 180, pts = [];
      for (let v = 0; v !== 21; v++) pts.push([a.ra + turn * v / 20, a.dec + (b.dec - a.dec) * v / 20]);
      l.draw(pts, on.map((d) => d.angle + "-" + symbolOf(l.p) + "-" + symbolOf(l.q) + " " + l.s.clock).join(", "), on[0].colour, on[0].width);
      l.pts = pts;
    });
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
        for (let v = -180; v !== 183; v += 3) pts.push([raFacing + v, s.dec]);
        body.decLine(pts, body.tipName + " Dec/Lati: " + (s.dec >= 0 ? "+" : "") + s.dec.toFixed(2));
      }
      const arcsec = 2 * Math.atan(b.km / (s.dist * D.au_km)) / RAD * 3600;
      const r = radiusAt(D.size_rules[body.name], body.set.tables, t);
      const hidden = z < 0 && Math.hypot(x - D.cx, y - D.cy) < D.earth;   // behind the Earth
      const fade = z >= 0 ? 1 : 0.55, size = arcsec >= 60 ? (arcsec / 60).toFixed(1) + " arcmin" : arcsec.toFixed(1) + " arcsec";
      const pct = (s.dist * D.au_km - b.lo) / (b.hi - b.lo) * 100;
      Object.assign(body, {x, y, r, hidden, fade});
      body.mark.setAttribute("cx", x.toFixed(1)); body.mark.setAttribute("cy", y.toFixed(1));
      body.mark.setAttribute("r", r.toFixed(1)); body.mark.setAttribute("opacity", fade);
      body.mark.style.display = hidden ? "none" : ""; body.label.style.display = hidden ? "none" : "";
      fitSymbol(body.label, x, y, r);
      body.label.setAttribute("opacity", fade);
      body.tip.textContent = body.tipName + " (" + (z >= 0 ? "near" : "far") + " side of the sphere)\nDec/Lati: " + (s.dec >= 0 ? "+" : "") + s.dec.toFixed(2) +
        "\nRA: " + s.ra.toFixed(2) + "\nAngular Size: " + size +
        "\nDistance from earth: " + Math.max(0, Math.round(pct)) + "%" + moving(body, s, t);
      if (!hidden) taken.push([x - r - 1, y - r - 1, x + r + 1, y + r + 1]);   // no label may cover a marker
    });
    nodes.forEach((node) => {
      const at = nodeAt(node, t), [x, y, z] = point(at.ra, at.dec), tipName = symbolOf(node.name) + " " + node.s.clock;
      if (node.raLine) {
        const pts = [];
        for (let v = -90; v !== 93; v += 3) pts.push([at.ra, v]);
        node.raLine(pts, tipName + " RA: " + at.ra.toFixed(2));
      }
      if (node.decLine) {
        const pts = [];
        for (let v = -180; v !== 183; v += 3) pts.push([raFacing + v, at.dec]);
        node.decLine(pts, tipName + " Dec/Lati: " + (at.dec >= 0 ? "+" : "") + at.dec.toFixed(2));
      }
      const hidden = z < 0 && Math.hypot(x - D.cx, y - D.cy) < D.earth, fade = z >= 0 ? 1 : 0.55;
      Object.assign(node, {x, y, hidden, fade});
      const nr = radiusAt(D.size_rules[node.name], node.s.tables, t);   // by its Size in the Naming Conventions table
      node.mark.setAttribute("transform", "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ") scale(" + (nr / 9).toFixed(3) + ")");
      node.mark.setAttribute("opacity", fade);
      node.mark.style.display = hidden ? "none" : "";
      node.tip.textContent = symbolOf(node.name) + " " + node.s.clock + ": the Moon's " + node.pole + " node (" + (z >= 0 ? "near" : "far") +
        " side of the sphere)\nDec/Lati: " + (at.dec >= 0 ? "+" : "") + at.dec.toFixed(2) + "\nRA: " + at.ra.toFixed(2);
      if (!hidden) taken.push([x - nr, y - nr, x + nr, y + nr]);
    });
    const icons = placeIcons.map((i) => ({i, at: placeOnEarth(i.pl, t)})).filter((q) => {
      const seen = q.at[2] >= 0;
      q.i.tag.style.display = seen ? "" : "none";
      return seen;
    });
    const apart = icons.length === 2 && Math.hypot(icons[0].at[0] - icons[1].at[0], icons[0].at[1] - icons[1].at[1]) < D.place_apart;
    icons.forEach((q, n) => {                      // close together, side by side
      const r = radiusAt(D.size_rules[q.i.pl.label], D.sets[q.i.pl.set].tables, t);   // by its Size in the Naming Conventions table
      const x = q.at[0] + (apart ? (n ? 1 : -1) * (r + 2) : 0), y = q.at[1];
      q.i.tag.setAttribute("transform", "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ") scale(" + (r / 9).toFixed(3) + ")");
      taken.push([x - r - 1, y - r - 1, x + r + 1, y + r + 1]);
    });
    houses.forEach((h) => {                        // named on the near side only, and not where a fixed label is
      const ra = (h.pl.ra + D.spin * t + 30 * h.k) % 360, pts = [];
      for (let v = -90; v !== 93; v += 3) pts.push([ra, v]);
      h.draw(pts, h.label.textContent + " " + symbolOf(h.pl.label) + " RA: " + ra.toFixed(2));
      const [x, y, z] = point(ra + 15, D.house_dec[D.places.indexOf(h.pl)]), box = boxOf(x, y + 4, h.label.textContent);
      const seen = z >= 0 && clear(box, taken);
      h.label.style.display = seen ? "" : "none";
      if (seen) {
        h.label.setAttribute("x", x.toFixed(1)); h.label.setAttribute("y", (y + 4).toFixed(1));
        taken.push(box);
      }
      // its RA, to the right of its line low on the near side
      const text = ra.toFixed(2), [vx, vy, vz] = point(ra, D.house_value_dec[D.places.indexOf(h.pl)]);
      const vBox = boxOf(vx + 5 + text.length * D.text_w / 2, vy + 4, text), show = vz >= 0 && inChart(vBox) && clear(vBox, taken);
      h.value.style.display = show ? "" : "none";
      if (show) {
        h.value.textContent = text;
        h.value.setAttribute("x", (vx + 5).toFixed(1)); h.value.setAttribute("y", (vy + 4).toFixed(1));
        taken.push(vBox);
      }
    });
    aspectLines.forEach((l) => {                   // each its tag, as 0-Ma-Ju, in the first free place along its line; none if none
      l.tag.style.display = "none";
      if (!l.tagged) return;
      const text = l.tagged.angle + "-" + symbolOf(l.p) + "-" + symbolOf(l.q);
      l.tag.textContent = text;
      l.tag.setAttribute("fill", l.tagged.colour);
      // its last place along the line while that stays free, then the nearest to that
      const had = l.tagAt === undefined ? 10 : l.tagAt;
      const along = [10, 7, 13, 4, 16, 2, 18].sort((a, b) => Math.abs(a - had) - Math.abs(b - had));
      const put = (x, y, z, box) => {
        l.tag.setAttribute("x", x.toFixed(1)); l.tag.setAttribute("y", (y + 4).toFixed(1));
        l.tag.setAttribute("opacity", z >= 0 ? 1 : 0.55);
        l.tag.style.display = "";
        taken.push(box);
      };
      const seenAt = (x, y, z) => z >= 0 || Math.hypot(x - D.cx, y - D.cy) >= D.earth;
      for (const v of along) {
        const [x, y, z] = point(l.pts[v][0], l.pts[v][1]);
        const box = boxOf(x, y + 4, text);
        if (seenAt(x, y, z) && inChart(box) && clear(box, taken)) {
          put(x, y, z, box);
          l.tagAt = v;
          return;
        }
      }
      // no room along it (a short line, between two planets close together): the nearest free place beside its middle
      const [mx, my, mz] = point(l.pts[10][0], l.pts[10][1]);
      if (!seenAt(mx, my, mz)) return;
      for (let r = 12; r !== 60; r += 8) {
        for (let k = 0; k !== 8; k++) {
          const a = k * Math.PI / 4, x = mx + r * Math.cos(a) * (1 + text.length * D.text_w / 2 / 12), y = my + r * Math.sin(a);
          const box = boxOf(x, y + 4, text);
          if (inChart(box) && clear(box, taken)) return put(x, y, mz, box);
        }
      }
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
    return tag("b") + symbolOf(pl.label) + tag("/b") + " " + pl.title + NL + "Long: " + signed(pl.lon) + NL + "Dec/Lati: " + signed(pl.lat) +
      NL + "RA: " + (((pl.ra + D.spin * t) % 360 + 360) % 360).toFixed(2) +
      NL + "Approaching: " + names(near) + NL + "Leaving: " + names(away);
  };
  const placeTraces = D.places.map((pl) => gd.data.findIndex((d) =>
    d.mode === "markers" && String(d.text[0]) === pl.label));
  let textsDue = 0;
  const redraw = (t) => {                          // the Earth's turn and, each second, CB's and CN's boxes
    const now = performance.now(), turn = {"geo.projection.rotation.lon": facing(t)}, done = () => { busy = false; };
    busy = true;
    if (D.places.length && now >= textsDue) {
      textsDue = now + 1000;
      Plotly.update(gd, {hovertext: D.places.map((pl) => placeBox(pl, t))}, turn, placeTraces).then(done);
    } else Plotly.relayout(gd, turn).then(done);
  };
  const facing = (t) => (((D.lon0 - D.spin * t - clock.view + 540) % 360) + 360) % 360 - 180;
  if (!window.globeClock || window.globeClock.key !== D.key) window.globeClock = {key: D.key, t: 0, view: 0};
  const clock = window.globeClock;
  // trails only while time runs: from where it started running, kept across the page's redraws while it runs (so pressing
  // another button does not clear them); none while it stands still, and each start begins new ones
  if (!D.day_seconds) clock.trailFrom = null;
  else if (clock.trailFrom === null || clock.trailFrom === undefined || clock.trailFrom > clock.t) clock.trailFrom = clock.t;
  trailFrom = D.day_seconds ? clock.trailFrom : null;
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
      if (clock.t >= D.days) { clock.t = 0; trailFrom = clock.trailFrom = 0; }   // the end of the tables: from the start again, the trails too
      place(clock.t);
      redraw(clock.t);
    }, D.step_ms);
  }
  if (D.manual) {                                  // everything is frozen and moves as one: dragged sideways, the Earth with its
                                                   // lines and the sphere with its lines turn together about the axis, to show the
                                                   // other side. The Earth is drawn first and the sphere straight after, each step
    let from = null, wanted = clock.view;
    const step = () => {
      if (busy || wanted === clock.view) return;
      busy = true;
      clock.view = wanted;
      Plotly.relayout(gd, {"geo.projection.rotation.lon": facing(clock.t)}).then(() => {
        place(clock.t);
        busy = false;
        step();                                    // on to where the pointer has got to
      });
    };
    gd.style.cursor = "grab";
    const follow = (e) => {
      if (!document.body.contains(gd)) {
        window.removeEventListener("pointermove", follow);
        window.removeEventListener("pointerup", letGo);
        return;
      }
      if (from === null) return;
      const scale = gd.getBoundingClientRect().width / D.width;
      wanted += (e.clientX - from) / scale / D.earth / RAD;
      from = e.clientX;
      step();
    };
    const letGo = () => {
      from = null;
      gd.style.cursor = "grab";
    };
    gd.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest(".modebar-container")) return;
      from = e.clientX;
      wanted = clock.view;
      gd.style.cursor = "grabbing";
      e.preventDefault();
    });
    window.addEventListener("pointermove", follow);
    window.addEventListener("pointerup", letGo);
  }
"""


def globe_js(g: GlobeInput, day_seconds: float | None, manual: bool = False) -> str:
    """Puts the celestial sphere over the chart, under Plotly's hover boxes, and moves what is on it; day_seconds is how many
    seconds a day takes, None with no speed picked; with manual, dragging the chart turns the view, time standing still."""
    data = json.dumps(_motion_data(g, day_seconds, manual)).replace("<", chr(92) + "u003c")
    return _MOTION_JS.replace("__SYMBOL_JS__", SYMBOL_JS).replace("__DATA__", data)
