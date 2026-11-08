"""The AstroGlobe page: the Earth turning inside the celestial sphere. The sphere stands still, with each planet at its RA
and Dec, its RA line (the circle of RA through it) and Dec line (the circle of Dec through it), the celestial equator and
the celestial poles; the Earth inside it, with CB and CN on it, turns about the axis that joins those poles. At the start
the Earth is set as it was at that moment, so a planet is straight above the place it was overhead. Equatorial only (RA / Dec)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import plotly.graph_objects as go

from . import core
from .mapchart import CHART_FONT_FAMILY, CHART_TEXT, FONT

WIDTH, HEIGHT = 1100, 720
MARGIN = 10
TILT = 23.44                      # degrees the Earth's axis leans from upright (its obliquity)
LEAN_TOWARD = 45.0                # the way the axis leans: 0 = toward the viewer, 90 = to the right; here between them
SPIN_DEGREES = 6.0                # degrees a second the Earth turns about its axis on screen
EARTH_RADIUS = 165.0              # pixels, in the chart's own layout
SKY_RADIUS = 315.0                # the celestial sphere, pixels (it fits the chart's height with its pole labels)
AXIS_COLOUR = "rgb(60,60,60)"
SKY_FILL = "rgb(244,246,252)"
BACK_OPACITY = 0.3                # the far side of the sphere, seen through it
CX, CY = WIDTH / 2.0, HEIGHT / 2.0
TEXT_W, TEXT_H = 7.6, 15.0        # a character's width and a line's height, for keeping labels apart


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
    show_lines: bool = True


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
    return left, y - TEXT_H + 3, left + w, y + 3


def _clear(box, taken) -> bool:
    return all(box[2] < t[0] or t[2] < box[0] or box[3] < t[1] or t[3] < box[1] for t in taken)


def _label_spot(x: float, y: float, text: str, taken: list) -> tuple[float, float]:
    """The nearest spot around a marker where its label overlaps nothing placed so far."""
    half = len(text) * TEXT_W / 2
    for reach in range(40):
        for dx, dy in ((0, -12), (0, 21), (half + 10, 5), (-half - 10, 5),
                       (half + 10, -10), (-half - 10, -10), (half + 10, 18), (-half - 10, 18)):
            sx = x + dx + (reach * 12 if dx > 0 else -reach * 12 if dx < 0 else 0)
            sy = y + dy + (reach * 14 if dy > 5 else -reach * 14 if dy < 0 else 0)
            box = _box(sx, sy, text)
            if box[0] > 0 and box[2] < WIDTH and box[1] > 0 and box[3] < HEIGHT and _clear(box, taken):
                return sx, sy
    return x, y - 12


def sky_svg(g: GlobeInput) -> str:
    """The celestial sphere, drawn over the Earth's chart: its far side faint and hidden where the Earth is before it,
    its near side in front of the Earth, as through glass. It never moves, so it is drawn once."""
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

    # the celestial equator, named at its near side's right-hand end
    circle = [ra_facing + v for v in range(-180, 181, 2)]
    _sky_line([(a, 0.0) for a in circle], ra_facing, AXIS_COLOUR, 1.4, False, "Celestial equator (Dec 0)", near, far)
    ex, ey, _ = max((_sky_point(a, 0.0, ra_facing) for a in circle if _sky_point(a, 0.0, ra_facing)[2] >= 0),
                    key=lambda p: p[0])
    marks.append(_text(ex + 8, ey + 4, "Celestial Equator", AXIS_COLOUR, "start"))
    taken.append(_box(ex + 8, ey + 4, "Celestial Equator", "start"))

    bodies = []
    if g.show_birth and g.birth:
        bodies += [(p, g.birth[p], False) for p in core.BUTTON_ORDER if p in g.birth]
    if g.show_now and g.now:
        bodies += [(p, g.now[p], True) for p in core.BUTTON_ORDER if p in g.now]
    if g.show_lines:
        for p, (ra, de), now in bodies:
            name, c = p + ("-N" if now else ""), core.colour(p)
            _sky_line([(ra, v) for v in range(-90, 91, 2)], ra_facing, c, 1.4, now, f"{name} RA {ra:.2f}", near, far)
            _sky_line([(ra_facing + v, de) for v in range(-180, 181, 2)], ra_facing, c, 1.4, now,
                      f"{name} Dec {de:+.2f}", near, far)
    shown = []
    for p, (ra, de), now in bodies:
        x, y, z = _sky_point(ra, de, ra_facing)
        if z < 0 and math.hypot(x - CX, y - CY) < E:              # behind the Earth: hidden, as the Earth is before it
            continue
        shown.append((p, ra, de, now, x, y, z))
        taken.append((x - 6, y - 6, x + 6, y + 6))                # no label may cover another's marker
    for p, ra, de, now, x, y, z in shown:
        name, c = p + ("-N" if now else ""), core.colour(p)
        opacity = 1.0 if z >= 0 else 0.55
        side = "near side" if z >= 0 else "far side"
        marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{"white" if now else c}" stroke="{c}" '
                     f'stroke-width="2" opacity="{opacity}" style="pointer-events:auto"><title>{name} ({side} of the '
                     f'sphere)\nRA {ra:.2f}\nDec {de:+.2f}</title></circle>')
        lx, ly = _label_spot(x, y, name, taken)
        taken.append(_box(lx, ly, name))
        marks.append(_text(lx, ly, name, c, opacity=opacity))

    hole = f"M{CX - E} {CY}a{E} {E} 0 1 0 {2 * E} 0a{E} {E} 0 1 0 {-2 * E} 0Z"     # the Earth's disc
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
            f'style="position:absolute;left:0;top:0;pointer-events:none">'
            f'<defs><clipPath id="off-earth"><path clip-rule="evenodd" d="M0 0H{WIDTH}V{HEIGHT}H0Z{hole}"/></clipPath></defs>'
            f'<g clip-path="url(#off-earth)"><circle cx="{CX}" cy="{CY}" r="{R}" fill="{SKY_FILL}" stroke="{AXIS_COLOUR}" '
            f'stroke-width="1"/><g opacity="{BACK_OPACITY}">{"".join(far)}</g></g>'
            f'{axis}{"".join(near)}{"".join(marks)}</svg>')


def globe_figure(g: GlobeInput) -> go.Figure:
    """The Earth: land and sea, and CB and CN with their RA and Dec lines, which turn with it."""
    fig = go.Figure()
    lats = [v / 2.0 for v in range(-180, 181)]           # a meridian, pole to pole, every half degree
    lons = [v / 2.0 for v in range(-360, 361)]           # a circle of latitude, right round, every half degree
    for label, place, symbol, show, jd in (("CB", g.cb, "diamond", g.show_birth, g.jd_birth),
                                           ("CN", g.cn, "triangle-up", g.show_now, g.jd_now)):
        if show and place:
            lat, lon = place
            if g.show_lines and jd is not None:               # its RA (the sidereal time there) and Dec (its latitude)
                ra = core.lst(jd, lon)
                for text, line_lon, line_lat in ((f"{label} RA {ra:.2f}", [lon] * len(lats), lats),
                                                 (f"{label} Dec {lat:+.2f}", lons, [lat] * len(lons))):
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
                 lataxis=dict(showgrid=False), lonaxis=dict(showgrid=False)))
    return fig


def globe_js(g: GlobeInput, rotate: bool) -> str:
    """Puts the celestial sphere over the chart (under Plotly's hover boxes) and, with rotate, turns the Earth inside it
    about its fixed axis, west to east only, while the pointer is not on it: the surface moves eastward, so the longitude
    facing the viewer falls. Run with the chart drawn as gd."""
    step = 0.15                                               # seconds
    return f"""
      const SPIN = {SPIN_DEGREES * step};
      const holder = document.createElement("div");
      holder.innerHTML = {json.dumps(sky_svg(g)).replace("<", chr(92) + "u003c")};  // (the page drops a script with tags in)
      const box = gd.querySelector(".svg-container");
      const tops = box.querySelectorAll(":scope > svg.main-svg");
      tops[tops.length - 1].before(holder.firstChild);
      if ({str(rotate).lower()}) {{
        let paused = false, busy = false;
        gd.addEventListener("mouseenter", () => {{ paused = true; }});
        gd.addEventListener("mouseleave", () => {{ paused = false; }});
        setInterval(() => {{
          if (paused || busy || !document.body.contains(gd)) return;
          const lon = (gd.layout.geo.projection.rotation || {{}}).lon || 0;
          busy = true;
          Plotly.relayout(gd, {{"geo.projection.rotation.lon": ((lon - SPIN + 540) % 360) - 180}})
            .then(() => {{ busy = false; }});
        }}, {int(step * 1000)});
      }}
    """
