"""AstroClock-3D's 3D view (its 3D button): the Earth in space with the Sun, Moon and planets around it in their real
directions (RA, Dec) and distances, drawn in true 3D that can be turned and zoomed with the mouse (Plotly's 3D scene).
Equatorial only: x toward RA 0, y toward RA 90, z toward the north celestial pole. One moment each for Now and DOB."""
from __future__ import annotations

import math

import plotly.graph_objects as go

from . import core
from .globechart import BODY_CHOICES, NODE_CHOICES, PATH_SPAN, GlobeInput
from .mapchart import CHART_FONT_FAMILY

HEIGHT = 720
EARTH_COLOUR = "rgb(70,130,200)"
LINE_COLOUR = "rgb(120,120,120)"
FIT_EARTH = 0.18                   # Fit: the Earth's radius, in Fit units (each tenfold distance one unit): not to scale
TRUE_EARTH = 0.12                  # True: the Earth's radius, in AU: not to scale (to scale it would not show)
RINGS = {True: (0.01, 1.0, 5.0, 10.0), False: (1.0, 5.0, 10.0)}   # AU rings on the equator plane: Fit, True
PATH_POINTS = 240                  # points a Planet Path is drawn with


def _reach(au: float, fit: bool) -> float:
    """How far from the centre a distance is drawn: Fit as Geo/Helio Model's Fit scale (past the Earth), else in AU."""
    if fit:
        from . import space3d                                 # (here: space3d imports globechart, which this imports)
        return FIT_EARTH + space3d._reach(au, space3d.FIT)
    return au


def _xyz(ra: float, dec: float, r: float) -> tuple[float, float, float]:
    a, d = math.radians(ra), math.radians(dec)
    return r * math.cos(d) * math.cos(a), r * math.cos(d) * math.sin(a), r * math.sin(d)


def _earth(radius: float) -> go.Surface:
    """The Earth: a blue sphere at the centre (its size not to scale)."""
    n = 24
    us = [math.pi * i / n for i in range(n + 1)]
    vs = [2 * math.pi * j / (2 * n) for j in range(2 * n + 1)]
    x = [[radius * math.sin(u) * math.cos(v) for v in vs] for u in us]
    y = [[radius * math.sin(u) * math.sin(v) for v in vs] for u in us]
    z = [[radius * math.cos(u) for _ in vs] for u in us]
    return go.Surface(x=x, y=y, z=z, colorscale=[[0, EARTH_COLOUR], [1, EARTH_COLOUR]], showscale=False, opacity=0.95,
                      hoverinfo="skip", name="Earth")


def _moments(g: GlobeInput) -> list[tuple[str, float, bool, tuple | None]]:
    """(clock, Julian day, hollow, place (lat, lon) of CB or CN) for each moment shown."""
    out = []
    if g.show_birth and g.jd_birth is not None:
        out.append(("DOB", g.jd_birth, True, g.cb))
    if g.show_now:
        out.append(("Now", g.jd_now, False, g.cn))
    return out


def space_figure(g: GlobeInput) -> go.Figure:
    """The 3D view: the Earth, the bodies picked at each moment (DOB hollow), their Planet Paths over one trip from that
    moment, with Ce the celestial axis (NCP, SCP) and equator, rings of distance on the equator plane, and with Co a line from
    CB (DOB) or CN (Now) on the Earth to each body. Fit: on Geo/Helio Model's Fit scale, else in AU (true scale)."""
    fit = g.fit
    earth_r = FIT_EARTH if fit else TRUE_EARTH
    fig = go.Figure()
    fig.add_trace(_earth(earth_r))
    outer = earth_r
    for clock, jd, hollow, place in _moments(g):
        bodies = [b for b in BODY_CHOICES if b in g.bodies]
        nodes = [n for n in NODE_CHOICES if n in g.bodies]
        moon = core.position("Mo", jd)
        pts = {}
        for b in bodies:
            p = core.position(b, jd)
            pts[b] = (p.ra, p.dec, p.dist_au)
        for n in nodes:                                       # on the Moon's path: at the Moon's distance then
            ra, dec = core.moon_north_node(jd)
            pts[n] = ((ra + 180) % 360, -dec, moon.dist_au) if n == "SN" else (ra, dec, moon.dist_au)
        for name, (ra, dec, au) in pts.items():
            r = _reach(au, fit)
            outer = max(outer, r)
            x, y, z = _xyz(ra, dec, r)
            colour = core.colour(name)
            fig.add_trace(go.Scatter3d(
                x=[x], y=[y], z=[z], mode="markers+text", text=[core.symbol_of(name)], textposition="top center",
                textfont=dict(size=14, color=colour, family=CHART_FONT_FAMILY),
                marker=dict(size=9 if name in ("Su", "Mo") else 7, color="white" if hollow else colour, line=dict(color=colour, width=3),
                            symbol="circle-open" if hollow else "circle"),
                name=f"{core.symbol_of(name)} {clock}", showlegend=False,
                hovertemplate=f"{core.symbol_of(name)} {clock}<br>RA: {ra:.2f}<br>Dec/Lati: {dec:+.2f}<br>Distance from earth: "
                              f"{au:.4g} AU<extra></extra>"))
            if g.show_links and place:                        # Co: from CB or CN on the Earth to the body
                px, py, pz = _xyz(core.lst(jd, place[1]), place[0], earth_r)
                fig.add_trace(go.Scatter3d(x=[px, x], y=[py, y], z=[pz, z], mode="lines", hoverinfo="skip", showlegend=False,
                                           line=dict(color=core.colour("CB" if clock == "DOB" else "CN"), width=2)))
        for b in bodies:                                      # Planet Path: one trip round from the moment
            if b not in g.paths or b not in PATH_SPAN:
                continue
            days = PATH_SPAN[b][0]
            path = [core.position(b, jd + days * i / PATH_POINTS) for i in range(PATH_POINTS + 1)]
            xyz = [_xyz(p.ra, p.dec, _reach(p.dist_au, fit)) for p in path]
            outer = max(outer, max(math.sqrt(a * a + b2 * b2 + c * c) for a, b2, c in xyz))
            fig.add_trace(go.Scatter3d(x=[q[0] for q in xyz], y=[q[1] for q in xyz], z=[q[2] for q in xyz], mode="lines",
                                       line=dict(color=core.colour(b), width=3, dash="dash" if hollow else "solid"),
                                       name=f"{PATH_SPAN[b][2]} {clock}", showlegend=False,
                                       hovertemplate=f"{PATH_SPAN[b][2]} {clock}: one trip from then<extra></extra>"))
        if place:                                             # CB or CN on the Earth
            px, py, pz = _xyz(core.lst(jd, place[1]), place[0], earth_r)
            label = "CB" if clock == "DOB" else "CN"
            fig.add_trace(go.Scatter3d(x=[px], y=[py], z=[pz], mode="markers+text", text=[label], textposition="bottom center",
                                       marker=dict(size=5, color=core.colour(label)), showlegend=False,
                                       textfont=dict(size=11, color=core.colour(label)), hovertemplate=f"{label} ({clock})<extra></extra>"))
    span = outer * 1.08
    for au in RINGS[fit]:                                     # distance rings on the equator plane
        r = _reach(au, fit)
        if r > span:
            continue
        ring = [_xyz(360 * i / 96, 0, r) for i in range(97)]
        fig.add_trace(go.Scatter3d(x=[q[0] for q in ring], y=[q[1] for q in ring], z=[0] * 97, mode="lines", hoverinfo="skip",
                                   line=dict(color="rgb(200,200,200)", width=1), showlegend=False))
        fig.add_trace(go.Scatter3d(x=[r], y=[0], z=[0], mode="text", text=[f"{au:g} AU"], hoverinfo="skip", showlegend=False,
                                   textfont=dict(size=10, color=LINE_COLOUR)))
    if g.show_celes:                                          # the celestial axis and equator
        fig.add_trace(go.Scatter3d(x=[0, 0], y=[0, 0], z=[-span, span], mode="lines+text", text=["SCP", "NCP"],
                                   line=dict(color=LINE_COLOUR, width=3), textfont=dict(size=12, color=LINE_COLOUR),
                                   hoverinfo="skip", showlegend=False))
        eq = [_xyz(360 * i / 96, 0, span) for i in range(97)]
        fig.add_trace(go.Scatter3d(x=[q[0] for q in eq], y=[q[1] for q in eq], z=[0] * 97, mode="lines", hoverinfo="skip",
                                   line=dict(color=LINE_COLOUR, width=2), showlegend=False))
        for ra, name in ((0, "RA 0"), (90, "RA 90"), (180, "RA 180"), (270, "RA 270")):
            x, y, _ = _xyz(ra, 0, span * 1.06)
            fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[0], mode="text", text=[name], hoverinfo="skip", showlegend=False,
                                       textfont=dict(size=10, color=LINE_COLOUR)))
    axis = dict(visible=False, range=[-span, span])
    fig.update_layout(height=HEIGHT, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="white",
                      scene=dict(xaxis=axis, yaxis=axis, zaxis=axis, aspectmode="cube", bgcolor="white",
                                 camera=dict(eye=dict(x=1.3, y=1.3, z=0.7))),
                      font=dict(family=CHART_FONT_FAMILY, size=11))
    return fig
