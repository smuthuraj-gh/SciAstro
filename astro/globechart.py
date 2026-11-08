"""The AstroGlobe page: the Earth as a turning globe with each planet where it was overhead (latitude = its Dec, longitude =
its RA less the sidereal time at Greenwich), its RA line (the meridian through it) and Dec line (the circle of latitude
through it), and CB / CN at the birth place and the place now. Equatorial only (RA / Dec)."""
from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go

from . import core
from .mapchart import CHART_TEXT, FONT

WIDTH, HEIGHT = 1100, 720


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
    for label, place, symbol, show in (("CB", g.cb, "diamond", g.show_birth), ("CN", g.cn, "triangle-up", g.show_now)):
        if show and place:
            lat, lon = place
            fig.add_trace(go.Scattergeo(
                lon=[lon], lat=[lat], mode="markers+text", showlegend=False, text=[f"<b>{label}</b>"],
                textposition="bottom center", textfont=dict(size=FONT, color="black"),
                marker=dict(size=12, color="black", symbol=symbol), hoverinfo="text",
                hovertext=f"<b>{label}</b> {'birth place' if label == 'CB' else 'place now'}<br>"
                          f"latitude {lat:+.2f}, longitude {lon:+.2f}"))

    start = g.cb[1] if g.cb else 0.0                          # first facing the birth place
    fig.update_layout(
        width=WIDTH, height=HEIGHT, autosize=False, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="white", font=dict(size=FONT, color=CHART_TEXT), hoverlabel=dict(font_size=FONT),
        geo=dict(projection=dict(type="orthographic", rotation=dict(lon=start, lat=15)),
                 showland=True, landcolor="rgb(236,236,230)", showocean=True, oceancolor="rgb(220,232,245)",
                 showcoastlines=True, coastlinecolor="rgb(150,150,150)", showcountries=True,
                 countrycolor="rgb(200,200,200)", showframe=False, bgcolor="white",
                 lataxis=dict(showgrid=False), lonaxis=dict(showgrid=False)))
    return fig


def rotate_js(on: bool) -> str:
    """Turns the globe slowly (about 6 degrees a second) while the pointer is not on it; drag to spin it by hand."""
    if not on:
        return ""
    return """
      let paused = false, busy = false;
      gd.addEventListener("mouseenter", () => { paused = true; });
      gd.addEventListener("mouseleave", () => { paused = false; });
      setInterval(() => {
        if (paused || busy || !document.body.contains(gd)) return;
        const r = gd.layout.geo.projection.rotation || {lon: 0, lat: 15};
        busy = true;
        Plotly.relayout(gd, {"geo.projection.rotation.lon": ((r.lon || 0) + 1.2 + 540) % 360 - 180})
          .then(() => { busy = false; });
      }, 200);
    """
