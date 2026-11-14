"""Geo/Helio Model's 3D view (its 3D button): the Earth (Geo) or the Sun (Helio) in the middle with the bodies around it in
their real directions (RA, Dec) and distances, drawn in true 3D that can be turned and zoomed with the mouse (Plotly's 3D
scene). Equatorial only: x toward RA 0, y toward RA 90, z toward the north celestial pole. One moment each for Now and DOB."""
from __future__ import annotations

import json
import math

import plotly.graph_objects as go

from . import core, space3d
from .mapchart import CHART_FONT_FAMILY

WIDTH, HEIGHT = 820, 720           # a fixed size, shown at the top left of the page (not stretched to its width)
LINE_COLOUR = "rgb(120,120,120)"
# the body at the centre: its colour, its radius on Fit (in Fit units: each tenfold distance one unit) and on True (in AU),
# neither to scale; the Fit scale's distance drawn at it and space taken out; AU rings on Fit and on True; the paths' spans
CENTRE = {"Ea": dict(colour="rgb(70,130,200)", fit_r=0.18, true_r=0.12, log_from=space3d.LOG_FROM_AU, gap=space3d.GAP,
                     rings={True: (0.01, 1.0, 5.0, 10.0), False: (1.0, 5.0, 10.0)}, spans=space3d.SPANS, name="Earth"),
          "Su": dict(colour="rgb(250,190,40)", fit_r=0.15, true_r=0.15, log_from=space3d.HELIO_LOG_FROM_AU, gap=space3d.NO_GAP,
                     rings={True: (0.5, 1.0, 5.0, 10.0), False: (1.0, 5.0, 10.0)}, spans=space3d.HELIO_SPANS, name="Sun")}
PATH_POINTS = 240                  # points a Planet Path is drawn with


def _reach(au: float, fit: bool, c: dict) -> float:
    """How far from the centre a distance is drawn: Fit as Geo/Helio Model's Fit scale (past the centre body), else in AU."""
    return c["fit_r"] + space3d._reach(au, space3d.FIT, c["log_from"], c["gap"]) if fit else au


def _xyz(ra: float, dec: float, r: float) -> tuple[float, float, float]:
    a, d = math.radians(ra), math.radians(dec)
    return r * math.cos(d) * math.cos(a), r * math.cos(d) * math.sin(a), r * math.sin(d)


def _ball(radius: float, colour: str, name: str) -> go.Surface:
    """The body at the centre: a sphere (its size not to scale)."""
    n = 24
    us = [math.pi * i / n for i in range(n + 1)]
    vs = [2 * math.pi * j / (2 * n) for j in range(2 * n + 1)]
    return go.Surface(x=[[radius * math.sin(u) * math.cos(v) for v in vs] for u in us],
                      y=[[radius * math.sin(u) * math.sin(v) for v in vs] for u in us],
                      z=[[radius * math.cos(u) for _ in vs] for u in us],
                      colorscale=[[0, colour], [1, colour]], showscale=False, opacity=0.95, name=name,
                      hovertemplate=name + " (at the centre; not to scale)<extra></extra>")


def _place(centre: str, name: str, jd: float) -> tuple[float, float, float]:
    """(RA, Dec, distance in AU) of a body seen from the centre; NN and SN on the Moon's path, at the Moon's distance."""
    if name in ("NN", "SN"):
        ra, dec = core.moon_north_node(jd)
        moon = core.position("Mo", jd).dist_au
        return ((ra + 180) % 360, -dec, moon) if name == "SN" else (ra, dec, moon)
    p = core.helio_position(name, jd) if centre == "Su" else core.position(name, jd)
    return p.ra, p.dec, p.dist_au


FAR_AU = 11.0                      # running: the view reaches out to here (past Saturn at its farthest), so none runs out of it


def space_figure(centre: str, bodies, paths, moments, fit: bool, places: dict | None = None, moving: bool = False,
                 show_au: bool = True) -> go.Figure:
    """The 3D view round centre (Ea or Su): bodies at each of moments ((clock, Julian day), DOB hollow), the Planet Paths of
    paths over one trip from that moment (DOB dashed), the celestial axis and equator with RA 0..270, rings of distance on
    the equator plane, and (Geo) CB and CN on the Earth (places: {clock: (label, lat, lon)}). Fit: Geo/Helio Model's Fit
    scale, else in AU. moving: time will run (space_js), so the view reaches far enough for all, with room for the clock.
    show_au: the rings of distance (the page's AU button)."""
    c = CENTRE[centre]
    ball_r = c["fit_r"] if fit else c["true_r"]
    fig = go.Figure()
    fig.add_trace(_ball(ball_r, c["colour"], c["name"]))
    outer = ball_r
    for clock, jd in moments:
        hollow = clock == "DOB"
        for name in bodies:
            ra, dec, au = _place(centre, name, jd)
            r = _reach(au, fit, c)
            outer = max(outer, r)
            x, y, z = _xyz(ra, dec, r)
            colour, sym = core.colour(name), core.symbol_of(name)
            fig.add_trace(go.Scatter3d(
                x=[x], y=[y], z=[z], mode="markers+text", text=[sym], textposition="top center", showlegend=False,
                textfont=dict(size=14, color=colour, family=CHART_FONT_FAMILY), name=f"{sym} {clock}",
                marker=dict(size=9 if name in ("Su", "Mo", "Ea") else 7, color="white" if hollow else colour,
                            line=dict(color=colour, width=3), symbol="circle-open" if hollow else "circle"),
                hovertemplate=f"{sym} {clock}<br>RA: {ra:.2f}<br>Dec/Lati: {dec:+.2f}<br>Distance from {c['name'].lower()}: "
                              f"{au:.4g} AU<extra></extra>"))
        for name in paths:                                    # Planet Path: one trip round from the moment
            if name not in c["spans"] or name not in bodies:
                continue
            days, _, title = c["spans"][name]
            xyz = []
            for i in range(PATH_POINTS + 1):
                ra, dec, au = _place(centre, name, jd + days * i / PATH_POINTS)
                xyz.append(_xyz(ra, dec, _reach(au, fit, c)))
            outer = max(outer, max(math.sqrt(a * a + b * b + d * d) for a, b, d in xyz))
            fig.add_trace(go.Scatter3d(x=[q[0] for q in xyz], y=[q[1] for q in xyz], z=[q[2] for q in xyz], mode="lines",
                                       line=dict(color=core.colour(name), width=3, dash="dash" if hollow else "solid"),
                                       name=f"{title} {clock}", showlegend=False,
                                       hovertemplate=f"{title} {clock}: one trip from then<extra></extra>"))
        got = (places or {}).get(clock)
        if centre == "Ea" and got:                            # CB or CN on the Earth, turned as it was then
            label, lat, lon = got
            px, py, pz = _xyz(core.lst(jd, lon), lat, ball_r)
            fig.add_trace(go.Scatter3d(x=[px], y=[py], z=[pz], mode="markers+text", text=[label], textposition="bottom center",
                                       marker=dict(size=5, color=core.colour(label)), showlegend=False,
                                       textfont=dict(size=11, color=core.colour(label)), hovertemplate=f"{label} ({clock})<extra></extra>"))
    span = max(outer, _reach(FAR_AU, fit, c) if moving else 0) * 1.08
    for au in c["rings"][fit] if show_au else ():            # distance rings on the equator plane (AU)
        r = _reach(au, fit, c)
        if r > span:
            continue
        ring = [_xyz(360 * i / 96, 0, r) for i in range(97)]
        fig.add_trace(go.Scatter3d(x=[q[0] for q in ring], y=[q[1] for q in ring], z=[0] * 97, mode="lines", hoverinfo="skip",
                                   line=dict(color="rgb(200,200,200)", width=1), showlegend=False))
        fig.add_trace(go.Scatter3d(x=[r], y=[0], z=[0], mode="text", text=[f"{au:g} AU"], hoverinfo="skip", showlegend=False,
                                   textfont=dict(size=10, color=LINE_COLOUR)))
    fig.add_trace(go.Scatter3d(x=[0, 0], y=[0, 0], z=[-span, span], mode="lines+text", text=["SCP", "NCP"],   # the celestial axis
                               line=dict(color=LINE_COLOUR, width=3), textfont=dict(size=12, color=LINE_COLOUR),
                               hoverinfo="skip", showlegend=False))
    eq = [_xyz(360 * i / 96, 0, span) for i in range(97)]     # and the celestial equator
    fig.add_trace(go.Scatter3d(x=[q[0] for q in eq], y=[q[1] for q in eq], z=[0] * 97, mode="lines", hoverinfo="skip",
                               line=dict(color=LINE_COLOUR, width=2), showlegend=False))
    for ra in (0, 90, 180, 270):
        x, y, _ = _xyz(ra, 0, span * 1.06)
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[0], mode="text", text=[f"RA {ra}"], hoverinfo="skip", showlegend=False,
                                   textfont=dict(size=10, color=LINE_COLOUR)))
    axis = dict(visible=False, range=[-span, span])
    fig.update_layout(width=WIDTH, height=HEIGHT, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="white", autosize=False,
                      scene=dict(xaxis=axis, yaxis=axis, zaxis=axis, aspectmode="cube", bgcolor="white",
                                 camera=dict(eye=dict(x=1.3, y=1.3, z=0.7))),
                      font=dict(family=CHART_FONT_FAMILY, size=11))
    return fig


def space_js(centre: str, bodies, moments, fit: bool, day_seconds: float | None) -> str:
    """Rotate in 1s, for the 3D view: time runs from each moment, day_seconds a day of it (the speed picked), and each body's
    marker moves to where it really was then, its hover box with it; the clock of each moment at the top. The tables are
    the same as the other pages' (72 years of RA, Dec and distance), and the markers are found by their names."""
    from . import globechart, space3d
    c = CENTRE[centre]
    tables = {}
    for clock, jd in moments:
        for name in bodies:
            if name in ("NN", "SN"):
                if centre != "Ea":
                    continue
                tb = space3d._node_geo_table(name, jd)
            elif centre == "Su":                              # (the Moon from the Sun: as the Earth, under 0.003 AU off)
                tb = space3d._helio_table("Ea" if name == "Mo" else name, jd)
            else:
                tb = globechart._motion_table(name, jd)
            tables[f"{core.symbol_of(name)} {clock}"] = dict(step=tb["step"], ra=tb["ra"], dec=tb["dec"], dist=tb["dist"],
                                                           shift=tb["shift"], name=name)
    data = dict(tables=tables, jd={clock: jd for clock, jd in moments}, day_seconds=day_seconds, days=space3d.RUN_DAYS, fit=fit,
                fit_r=c["fit_r"], log_from=c["log_from"], gap=list(c["gap"]), word=c["name"].lower())
    return ("const M = " + json.dumps(data, separators=(",", ":")).replace("<", "\\u003c") + ";\n" + """
  const RAD = Math.PI / 180;
  const reach = (au) => {                          // as space3dview._reach
    if (!M.fit) return au;
    const log = Math.max(Math.log10(Math.max(au, 1e-9) / M.log_from), 0);
    const a = Math.log10(M.gap[0] / M.log_from), b = Math.log10(M.gap[1] / M.log_from);
    return M.fit_r + (log <= a ? log : log >= b ? log - (b - a) + M.gap[2] : a + (log - a) / (b - a) * M.gap[2]);
  };
  const sample = (tb, t) => {                      // between its two nearest table rows
    const u = (t + tb.shift) / tb.step, i = Math.max(0, Math.min(Math.floor(u), tb.ra.length - 2)), f = u - i;
    const turn = ((tb.ra[i + 1] - tb.ra[i] + 540) % 360) - 180;
    return {ra: (tb.ra[i] + turn * f + 360) % 360, dec: tb.dec[i] + (tb.dec[i + 1] - tb.dec[i]) * f,
            dist: tb.dist[i] + (tb.dist[i + 1] - tb.dist[i]) * f};
  };
  const idx = [], keys = [];
  gd.data.forEach((d, i) => { if (M.tables[d.name]) { idx.push(i); keys.push(d.name); } });
  const when = (jd) => new Date((jd - 2440587.5) * 86400000).toISOString().slice(0, 16).replace("T", " ") + " UT";
  const started = performance.now();
  const tick = () => {
    if (!gd.isConnected) return;                   // (a newer drawing has replaced this one)
    const t = ((performance.now() - started) / 1000 / M.day_seconds) % M.days;   // days on from each moment
    const xs = [], ys = [], zs = [], tips = [];
    keys.forEach((k) => {
      const tb = M.tables[k], s = sample(tb, t), r = reach(s.dist), cd = Math.cos(s.dec * RAD);
      xs.push([r * cd * Math.cos(s.ra * RAD)]); ys.push([r * cd * Math.sin(s.ra * RAD)]); zs.push([r * Math.sin(s.dec * RAD)]);
      // (no "<" before a letter in this script: st.html's sanitizer would drop the whole script, so written as \\u003c)
      tips.push(k + "\\u003cbr>RA: " + s.ra.toFixed(2) + "\\u003cbr>Dec/Lati: " + (s.dec >= 0 ? "+" : "") + s.dec.toFixed(2) +
                "\\u003cbr>Distance from " + M.word + ": " + s.dist.toPrecision(4) + " AU\\u003cextra>\\u003c/extra>");
    });
    Plotly.restyle(gd, {x: xs, y: ys, z: zs, hovertemplate: tips}, idx);
    Plotly.relayout(gd, {"title.text": Object.entries(M.jd).map(([c, jd]) => c + " " + when(jd + t)).join("   ")});
    setTimeout(tick, 250);
  };
  if (M.day_seconds) tick();
""")
