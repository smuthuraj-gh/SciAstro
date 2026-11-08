"""The AstroGlobe page: the Earth as a turning globe with each planet where it was overhead (latitude = its Dec, longitude =
its RA less the sidereal time at Greenwich), its RA line (the meridian through it) and Dec line (the circle of latitude
through it), and CB / CN at the birth place and the place now. Equatorial only (RA / Dec)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import plotly.graph_objects as go

from . import core
from .mapchart import CHART_TEXT, FONT

WIDTH, HEIGHT = 1100, 720
MARGIN = 10
TILT = 23.44                      # degrees the Earth's axis leans from upright (its obliquity)
WOBBLE_START = 45.0               # degrees round its circle of wobble that the axis starts (leaning right and forward)
WOBBLE_SECONDS = 40.0             # one circle of wobble on screen (the real precession takes about 25,772 years)
SPIN_DEGREES = 6.0                # degrees a second the Earth turns about its axis on screen
GLOBE_BOTTOM, GLOBE_TOP = 0.10, 0.90      # the globe's part of the chart's height, with room for the axis above, below
AXIS_REACH = 1.13                 # the axis lines end this many globe radii from its centre (their labels just beyond)
AXIS_COLOUR = "rgb(60,60,60)"


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


def _lon(ra: float, jd: float) -> float:
    """Where on the Earth a body of this RA is on the meridian at jd: longitude -180..180."""
    x = core.norm360(ra - core.lst(jd, 0.0))
    return x - 360.0 if x > 180.0 else x


def _view(wobble: float) -> tuple[float, float]:
    """The globe's (lat, roll) rotation when its axis leans TILT from upright, wobble degrees round its circle: the
    north pole then points (sin TILT sin wobble, cos TILT, sin TILT cos wobble) = (right, up, toward the viewer)."""
    t, w = math.radians(TILT), math.radians(wobble)
    return (math.degrees(math.asin(math.sin(t) * math.cos(w))),
            -math.degrees(math.atan2(math.sin(t) * math.sin(w), math.cos(t))))   # (a positive roll leans it left)


def globe_figure(g: GlobeInput) -> go.Figure:
    fig = go.Figure()
    lats = [v / 2.0 for v in range(-180, 181)]           # a meridian, pole to pole, every half degree
    lons = [v / 2.0 for v in range(-360, 361)]           # a circle of latitude, right round, every half degree

    def planets(pts: dict, jd: float, now: bool):
        for p in core.BUTTON_ORDER:
            if p not in pts:
                continue
            ra, de = pts[p]
            lon, c, name = _lon(ra, jd), core.colour(p), p + ("-N" if now else "")
            if g.show_lines:                                  # as on AstroMap: its RA line and its Dec line
                for label, line_lon, line_lat in ((f"{name} RA {ra:.2f}", [lon] * len(lats), lats),
                                                  (f"{name} Dec {de:+.2f}", lons, [de] * len(lons))):
                    fig.add_trace(go.Scattergeo(
                        lon=line_lon, lat=line_lat, mode="lines", showlegend=False,
                        line=dict(color=c, width=1.4, dash="dash" if now else "solid"),
                        hoverinfo="text", text=label, opacity=0.7 if now else 0.9))
            fig.add_trace(go.Scattergeo(
                lon=[lon], lat=[de], mode="markers+text", showlegend=False, text=[f"<b>{name}</b>"],
                textposition="top center", textfont=dict(size=FONT, color=c),
                marker=dict(size=11, color="white" if now else c, line=dict(color=c, width=2),
                            symbol="circle"),
                hoverinfo="text", hovertext=f"<b>{name}</b> overhead here<br>Dec {de:+.2f} (latitude)<br>"
                                            f"RA {ra:.2f} (longitude {lon:+.2f})"))

    if g.show_birth and g.birth and g.jd_birth is not None:
        planets({k: v for k, v in g.birth.items() if k != "CB"}, g.jd_birth, False)
    if g.show_now and g.now:
        planets(g.now, g.jd_now, True)
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
                textposition="bottom center", textfont=dict(size=FONT, color="black"),
                marker=dict(size=12, color="black", symbol=symbol), hoverinfo="text",
                hovertext=f"<b>{label}</b> {'birth place' if label == 'CB' else 'place now'}<br>"
                          f"latitude {lat:+.2f}, longitude {lon:+.2f}"))

    start = g.cb[1] if g.cb else 0.0                          # first facing the birth place
    # The Earth's axis, out of the globe at both poles: globe_js places these lines on the poles at every step
    axis = dict(type="line", xref="paper", yref="paper", x0=0.5, x1=0.5, y0=0.5, y1=0.5,
                line=dict(color=AXIS_COLOUR, width=2.5))
    pole = dict(xref="paper", yref="paper", x=0.5, y=0.5, xanchor="center", showarrow=False,
                font=dict(size=FONT, color=AXIS_COLOUR))
    lat0, roll0 = _view(WOBBLE_START)
    fig.update_layout(
        width=WIDTH, height=HEIGHT, autosize=False, margin=dict(l=MARGIN, r=MARGIN, t=MARGIN, b=MARGIN),
        paper_bgcolor="white", font=dict(size=FONT, color=CHART_TEXT), hoverlabel=dict(font_size=FONT),
        shapes=[axis, axis],
        annotations=[dict(pole, yanchor="bottom", text="<b>North Pole</b>"),
                     dict(pole, yanchor="top", text="<b>South Pole</b>")],
        geo=dict(domain=dict(y=[GLOBE_BOTTOM, GLOBE_TOP]),
                 projection=dict(type="orthographic", rotation=dict(lon=start, lat=lat0, roll=roll0)),
                 showland=True, landcolor="rgb(236,236,230)", showocean=True, oceancolor="rgb(220,232,245)",
                 showcoastlines=True, coastlinecolor="rgb(150,150,150)", showcountries=True,
                 countrycolor="rgb(200,200,200)", showframe=False, bgcolor="white",
                 lataxis=dict(showgrid=False), lonaxis=dict(showgrid=False)))
    return fig


def globe_js(rotate: bool, wobble: bool) -> str:
    """The globe's motion, while the pointer is not on it: it turns about its tilted axis (rotate) and that axis slowly
    circles, keeping its lean (wobble, as precession). The axis lines and their labels are placed on the poles at
    every step, and after a drag by hand. Run with the chart drawn as gd."""
    step = 0.15                                               # seconds
    return f"""
      const TILT = {TILT} * Math.PI / 180, RAD = Math.PI / 180, REACH = {AXIS_REACH};
      const ROTATE = {str(rotate).lower()}, WOBBLE = {str(wobble).lower()};
      const SPIN = {SPIN_DEGREES * step}, TURN = {360.0 / WOBBLE_SECONDS * step};
      const MID_Y = {(GLOBE_TOP + GLOBE_BOTTOM) / 2};
      let wobble = {WOBBLE_START}, paused = false, busy = false, ours = false;
      function view(w) {{                                     // the rotation for the axis at w round its circle
        const c = Math.cos(w * RAD), s = Math.sin(w * RAD);
        return {{lat: Math.asin(Math.sin(TILT) * c) / RAD,
                 roll: -Math.atan2(Math.sin(TILT) * s, Math.cos(TILT)) / RAD}};   // a positive roll leans it left
      }}
      function axisUpdate(lat, roll) {{                       // the lines and labels for this rotation
        const sz = gd._fullLayout._size, R = gd._fullLayout.geo._subplot.projection.scale();
        const up = Math.cos(lat * RAD), ux = -Math.sin(roll * RAD), uy = Math.cos(roll * RAD);
        const px = d => d * R / sz.w, py = d => d * R / sz.h;   // from the globe's radii to parts of the chart
        const nStart = lat >= 0 ? up : 1, sStart = lat <= 0 ? up : 1;   // from the pole, or the edge if it is behind
        const end = (sign, r) => [0.5 + sign * px(r * ux), MID_Y + sign * py(r * uy)];
        const [n0x, n0y] = end(1, nStart), [n1x, n1y] = end(1, REACH);
        const [s0x, s0y] = end(-1, sStart), [s1x, s1y] = end(-1, REACH);
        return {{"shapes[0].x0": n0x, "shapes[0].y0": n0y, "shapes[0].x1": n1x, "shapes[0].y1": n1y,
                 "shapes[1].x0": s0x, "shapes[1].y0": s0y, "shapes[1].x1": s1x, "shapes[1].y1": s1y,
                 "annotations[0].x": n1x, "annotations[0].y": n1y, "annotations[1].x": s1x, "annotations[1].y": s1y}};
      }}
      function apply(update) {{
        busy = true; ours = true;
        return Plotly.relayout(gd, update).then(() => {{ busy = false; ours = false; }});
      }}
      gd.addEventListener("mouseenter", () => {{ paused = true; }});
      gd.addEventListener("mouseleave", () => {{ paused = false; }});
      gd.on("plotly_relayout", () => {{                       // dragged by hand: the lines follow the poles
        if (ours || busy) return;
        const r = gd.layout.geo.projection.rotation || {{}};
        apply(axisUpdate(r.lat || 0, r.roll || 0));
      }});
      const v0 = view(wobble);
      apply(axisUpdate(v0.lat, v0.roll));
      if (ROTATE || WOBBLE) setInterval(() => {{
        if (paused || busy || !document.body.contains(gd)) return;
        const r = gd.layout.geo.projection.rotation || {{}};
        if (WOBBLE) wobble = (wobble + TURN) % 360;
        const v = view(wobble);
        apply(Object.assign({{
          "geo.projection.rotation.lon": ROTATE ? ((r.lon || 0) + SPIN + 540) % 360 - 180 : (r.lon || 0),
          "geo.projection.rotation.lat": v.lat, "geo.projection.rotation.roll": v.roll}}, axisUpdate(v.lat, v.roll)));
      }}, {int(step * 1000)});
    """
