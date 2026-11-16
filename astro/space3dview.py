"""Geo/Helio Model's 3D view (its 3D button): the Earth (Geo) or the Sun (Helio) in the middle with the bodies around it in
their real directions (RA, Dec) and distances, drawn in true 3D that can be turned and zoomed with the mouse (Plotly's 3D
scene). Equatorial only: x toward RA 0, y toward RA 90, z toward the north celestial pole. One moment each for Now and DOB."""
from __future__ import annotations

import json
import math
import random
import re

import plotly.graph_objects as go

from . import core, space3d
from .mapchart import CHART_FONT_FAMILY, SYMBOL_FONT_FAMILY

WIDTH, HEIGHT = 820, 720           # a fixed size, shown at the top left of the page (not stretched to its width)
# the look: a night sky with fixed stars; soft lines and rings, so that the planets stand out; text 10 to 12 px
SKY = "rgb(8,12,28)"
LINE_COLOUR = "rgba(190,200,225,0.75)"     # the axis, the equator, NCP / SCP and the RA names
RING_COLOUR = "rgba(150,165,205,0.45)"     # the AU rings
PLANE_COLOUR = "rgb(120,150,220)"          # the plane of the equator, faint
TEXT_COLOUR = "rgb(220,226,240)"
STARS = 450                                # fixed stars in the background (the same every time)
MARK_SCALE = 2.0                           # a mark's diameter: its Size radius times this, as on AstroClock-3D (twice the radius)
SYMBOL_PX = 12 / 9.5                       # the symbol inside it: its font size for each pixel of the mark's radius, as AstroClock-3D
SYMBOL_LEAST = 5                           # scales its symbols (9.5 px radius: 12 px); a mark of a smaller radius shows no symbol
SYMBOL_FONT = (10, 12)                     # but kept within the pages' text sizes (10 to 12 px): still inside the smallest mark (14 px)
# the body at the centre: its colour, its radius (in Fit units: each tenfold distance one unit; not to scale); the Fit scale's distance drawn at it and space taken out; AU rings on Fit and on True; the paths' spans
CENTRE = {"Ea": dict(colour="rgb(70,130,200)", fit_r=1.4, log_from=space3d.LOG_FROM_AU, gap=space3d.GAP,   # (a big globe, as on
                                                                                                   # AstroClock-3D: distances count from its surface)
                     rings=(0.01, 1.0, 5.0, 10.0), spans=space3d.SPANS, name="Earth"),
          "Su": dict(colour="rgb(250,190,40)", fit_r=0.15, log_from=space3d.HELIO_LOG_FROM_AU, gap=space3d.NO_GAP,
                     rings=(0.5, 1.0, 5.0, 10.0), spans=space3d.HELIO_SPANS, name="Sun")}
PATH_POINTS = 240                  # points a Planet Path is drawn with


def size_texts(centre: str) -> dict:
    """The Symbols table's Size column the flat drawing of this centre sizes its marks by: Size_Geo, or Size_Helio."""
    return core.SIZE_TEXTS if centre == "Ea" else core.SIZE_TEXTS_HELIO


def marker_radius(rule: dict, jd: float) -> float:
    """A mark's radius in pixels by its Size rule (core.size_rule), as on the flat drawing (space3d's radiusAt): a fixed
    radius, or the angular size of rule["of"] seen from the Earth then, on a logarithmic scale, plus rule["add"]."""
    from .globechart import BODY_RADIUS_KM, MARKER_RANGE, SIZE_RANGE_ARCSEC
    if "px" in rule:
        return rule["px"]
    au = core.position(rule["of"], jd).dist_au
    arcsec = 2 * math.degrees(math.atan(BODY_RADIUS_KM[rule["of"]] / (au * core.AU_KM))) * 3600
    lo, hi = math.log(SIZE_RANGE_ARCSEC[0]), math.log(SIZE_RANGE_ARCSEC[1])
    share = max(0.0, min(1.0, (math.log(arcsec) - lo) / (hi - lo)))
    return max(1.0, MARKER_RANGE[0] + (MARKER_RANGE[1] - MARKER_RANGE[0]) * share + rule["add"])


def _light(colour: str, share: float = 0.55) -> str:
    """A colour made lighter (this share of the way to white), to show on the night sky; as it is when not rgb(..)."""
    m = re.fullmatch(r"\s*rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+).*\)\s*", colour or "")
    if not m:
        m2 = re.fullmatch(r"\s*#([0-9a-fA-F]{6})\s*", colour or "")
        if not m2:
            return colour
        rgb = [int(m2[1][i:i + 2], 16) for i in (0, 2, 4)]
    else:
        rgb = [int(v) for v in m.groups()]
    return "rgb(" + ",".join(str(round(v + (255 - v) * share)) for v in rgb) + ")"


def _ink(colour: str) -> str:
    """The symbol's colour on a filled mark of this colour: black on a light one, white on a dark one (AstroClock-3D's inkOn)."""
    m = re.fullmatch(r"\s*rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+).*\)\s*", colour or "")
    m2 = None if m else re.fullmatch(r"\s*#([0-9a-fA-F]{6})\s*", colour or "")
    if not (m or m2):
        return "white"
    r, g, b = [int(v) for v in m.groups()] if m else [int(m2[1][i:i + 2], 16) for i in (0, 2, 4)]
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def _reach(au: float, c: dict) -> float:
    """How far from the centre a distance is drawn: Fit as Geo/Helio Model's Fit scale (past the centre body), else in AU."""
    return c["fit_r"] + space3d._reach(au, space3d.FIT, c["log_from"], c["gap"])


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


def space_figure(centre: str, bodies, paths, moments, places: dict | None = None, moving: bool = False,
                 show_au: bool = True, show_links: bool = False, show_celes: bool = True, show_spokes: bool = False) -> go.Figure:
    """The 3D view round centre (Ea or Su): bodies at each of moments ((clock, Julian day), DOB hollow), the Planet Paths of
    paths over one trip from that moment (DOB dashed), the celestial axis and equator with RA 0..270, rings of distance on
    the equator plane, and (Geo) CB and CN on the Earth (places: {clock: (label, lat, lon)}). On Geo/Helio Model's Fit
    scale. moving: time will run (space_js), so the view reaches far enough for all, with room for the clock.
    show_au: the rings of distance on the plane of the equator (the page's AU button); show_celes: the celestial
    coordinates, the plane of the equator, the axis with NCP and SCP, the equator and its RA names (its Ce button). show_links (SpC, Geo): a line from CB (DOB) or CN (Now) on the Earth
    to each body of its moment. show_spokes (Sp): a dashed line from the centre through each body out to the edge of the
    view, at the body's RA and Dec."""
    c = CENTRE[centre]
    ball_r = c["fit_r"]
    fig = go.Figure()
    fig.add_trace(_ball(ball_r, c["colour"], c["name"]))       # (first: the page's script finds the Earth as the first surface)
    outer = ball_r
    jd_globe = globe_moment(moments)
    spokes = []                                               # Sp: each body's direction, drawn once the view's reach is known
    for clock, jd in moments:
        hollow = clock == "DOB"
        at = {}                                               # each body's place, for the SpC lines
        for name in bodies:
            ra, dec, au = _place(centre, name, jd)
            r = _reach(au, c)
            outer = max(outer, r)
            x, y, z = at[name] = _xyz(ra, dec, r)
            spokes.append((clock, name, ra, dec))
            colour, sym = core.colour(name), core.symbol_of(name)
            radius = marker_radius(core.size_rule(name, texts=size_texts(centre)), jd)
            fig.add_trace(go.Scatter3d(     # its symbol inside it, as on AstroClock-3D: in its colour on a hollow DOB mark
                x=[x], y=[y], z=[z], mode="markers+text", text=[sym if radius >= SYMBOL_LEAST else ""], textposition="middle center",
                showlegend=False, name=f"{sym} {clock}",
                textfont=dict(size=min(max(SYMBOL_PX * radius, SYMBOL_FONT[0]), SYMBOL_FONT[1]), color=colour if hollow else _ink(colour), family=SYMBOL_FONT_FAMILY),
                marker=dict(size=MARK_SCALE * radius,   # (a diameter)
                            color=SKY if hollow else colour,   # (DOB: hollow, its rim in its colour; Now: a white rim)
                            line=dict(color=colour if hollow else "rgba(255,255,255,0.85)", width=2 if hollow else 1),
                            symbol="circle-open" if hollow else "circle", opacity=1),
                hovertemplate=f"{sym} {clock}<br>RA: {ra:.2f}<br>Dec/Lati: {dec:+.2f}<br>Distance from {c['name'].lower()}: "
                              f"{au:.4g} AU<extra></extra>"))
        for name in paths:                                    # Planet Path: one trip round from the moment
            if name not in c["spans"] or name not in bodies:
                continue
            days, _, title = c["spans"][name]
            xyz = []
            for i in range(PATH_POINTS + 1):
                ra, dec, au = _place(centre, name, jd + days * i / PATH_POINTS)
                xyz.append(_xyz(ra, dec, _reach(au, c)))
            outer = max(outer, max(math.sqrt(a * a + b * b + d * d) for a, b, d in xyz))
            fig.add_trace(go.Scatter3d(x=[q[0] for q in xyz], y=[q[1] for q in xyz], z=[q[2] for q in xyz], mode="lines",
                                       line=dict(color=core.colour(name), width=2.5, dash="dash" if hollow else "solid"),
                                       opacity=0.8,
                                       name=f"{title} {clock}", showlegend=False,
                                       hovertemplate=f"{title} {clock}: one trip from then<extra></extra>"))
        got = (places or {}).get(clock)
        if centre == "Ea" and got:                            # CB or CN at its place on the Earth (as the globe is turned)
            label, lat, lon = got
            px, py, pz = _xyz(core.lst(jd_globe, lon), lat, ball_r * 1.01)
            for name in bodies if show_links else ():         # SpC: from the place to each body (named for the page to move them)
                bx, by, bz = at[name]
                fig.add_trace(go.Scatter3d(x=[px, bx], y=[py, by], z=[pz, bz], mode="lines", hoverinfo="skip", showlegend=False,
                                           name=f"Co {core.symbol_of(name)} {clock}", opacity=0.75,
                                           line=dict(color=_light(core.colour(label)), width=2)))
            fig.add_trace(go.Scatter3d(x=[px], y=[py], z=[pz], mode="markers+text", text=[label], textposition="bottom center",
                                       marker=dict(size=5, color=_light(core.colour(label))), showlegend=False, name=f"{label} on the Earth",
                                       textfont=dict(size=11, color=_light(core.colour(label))), hovertemplate=f"{label} ({clock})<extra></extra>"))
    span = max(outer, _reach(FAR_AU, c) if moving else 0) * 1.08
    for clock, name, ra, dec in spokes if show_spokes else ():   # Sp: from the centre through the body to the view's edge
        ex, ey, ez = _xyz(ra, dec, span)
        fig.add_trace(go.Scatter3d(x=[0, ex], y=[0, ey], z=[0, ez], mode="lines", hoverinfo="skip", showlegend=False,
                                   name=f"Sp {core.symbol_of(name)} {clock}", opacity=0.9,   # (named for the page to move it)
                                   line=dict(color=_light(core.colour(name)), width=3, dash="dash")))
    stars = random.Random(7)                                  # fixed stars, far out (the same each time)
    sx, sy, sz = [], [], []
    for _ in range(STARS):
        u, v, r = stars.uniform(-1, 1), stars.uniform(0, 2 * math.pi), span * stars.uniform(0.93, 1.0)
        sx.append(r * math.sqrt(1 - u * u) * math.cos(v)); sy.append(r * math.sqrt(1 - u * u) * math.sin(v)); sz.append(r * u)
    fig.add_trace(go.Scatter3d(x=sx, y=sy, z=sz, mode="markers", hoverinfo="skip", showlegend=False, name="stars",
                               marker=dict(size=[stars.choice((1.2, 1.6, 2.2)) for _ in range(STARS)], color="white", opacity=0.6)))
    if show_celes:                                            # Ce: the celestial coordinates (the plane of the equator, the
                                                              # axis with NCP and SCP, the equator and its RA names)
        n = 48                                                    # the plane of the equator: a faint disc, north above it
        rs, angs = [span * i / 4 for i in range(5)], [2 * math.pi * j / n for j in range(n + 1)]
        fig.add_trace(go.Surface(x=[[r * math.cos(a) for a in angs] for r in rs], y=[[r * math.sin(a) for a in angs] for r in rs],
                                 z=[[0.0] * (n + 1) for _ in rs], colorscale=[[0, PLANE_COLOUR], [1, PLANE_COLOUR]], showscale=False,
                                 opacity=0.07, hoverinfo="skip", name="the plane of the equator"))
        pole = span * 0.62                                        # the celestial axis: just past the planets, not up into empty space
        fig.add_trace(go.Scatter3d(x=[0, 0], y=[0, 0], z=[-pole, pole], mode="lines+text", text=["SCP", "NCP"],   # the celestial axis
                                   line=dict(color=LINE_COLOUR, width=2), textfont=dict(size=12, color=TEXT_COLOUR),
                                   hoverinfo="skip", showlegend=False))
        eq = [_xyz(360 * i / 96, 0, span) for i in range(97)]     # and the celestial equator
        fig.add_trace(go.Scatter3d(x=[q[0] for q in eq], y=[q[1] for q in eq], z=[0] * 97, mode="lines", hoverinfo="skip",
                                   line=dict(color=LINE_COLOUR, width=1.5), showlegend=False))
        for ra in (0, 90, 180, 270):
            x, y, _ = _xyz(ra, 0, span * 1.06)
            fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[0], mode="text", text=[f"RA {ra}"], hoverinfo="skip", showlegend=False,
                                       textfont=dict(size=10, color=TEXT_COLOUR)))
    if show_au:                                               # AU: the rings of distance, on the plane of the equator
        for au in c["rings"]:                                  # distance rings on the equator plane (AU)
            r = _reach(au, c)
            if r > span:
                continue
            ring = [_xyz(360 * i / 96, 0, r) for i in range(97)]
            fig.add_trace(go.Scatter3d(x=[q[0] for q in ring], y=[q[1] for q in ring], z=[0] * 97, mode="lines", hoverinfo="skip",
                                       line=dict(color=RING_COLOUR, width=1.5, dash="dot"), showlegend=False))
            fig.add_trace(go.Scatter3d(x=[r], y=[0], z=[0], mode="text", text=[f"{au:g} AU"], hoverinfo="skip", showlegend=False,
                                       textfont=dict(size=10, color=TEXT_COLOUR)))
    axis = dict(visible=False, range=[-span, span])
    fig.update_layout(width=WIDTH, height=HEIGHT, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=SKY, autosize=False,
                      scene=dict(xaxis=axis, yaxis=axis, zaxis=axis, aspectmode="cube", bgcolor=SKY, dragmode="turntable",
                                 camera=dict(eye=dict(x=0.85, y=0.85, z=0.55))),   # close, a little from above: north above the plane
                      hoverlabel=dict(font=dict(size=11)), font=dict(family=CHART_FONT_FAMILY, size=11, color=TEXT_COLOUR))
    return fig


def globe_moment(moments) -> float | None:
    """The one moment the Earth is drawn turned as: Now if shown, else DOB."""
    return dict(moments).get("Now", moments[0][1] if moments else None)


def space_js(centre: str, bodies, moments, day_seconds: float | None, places: dict | None = None,
             offsets: dict | None = None, show_links: bool = False) -> str:
    """Rotate in 1s, for the 3D view: time runs from each moment, day_seconds a day of it (the speed picked), and each body's
    marker moves to where it really was then, its hover box with it; the clock of each moment at the top. The tables are
    the same as the other pages' (72 years of RA, Dec and distance), and the markers are found by their names. Geo: the
    Earth drawn as a globe, land and sea from Plotly's own world map (the one its map charts load, from cdn.plot.ly), with
    coastlines, lines of latitude and longitude every 30 degrees, and CB and CN at their places, turned as at the globe's
    moment and turning with time."""
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
    globe = None
    if centre == "Ea" and moments:
        jd_globe = globe_moment(moments)
        globe = dict(gst0=core.lst(jd_globe, 0.0), r=c["fit_r"], spin=globechart.EARTH_DEGREES_A_DAY,
                     places={f"{label} on the Earth": [lat, lon] for label, lat, lon in (places or {}).values()},
                     # SpC: each line's trace, its body's marker and its place (moved with them as time runs)
                     links=[dict(line=f"Co {core.symbol_of(name)} {clock}", body=f"{core.symbol_of(name)} {clock}",
                                 place=[places[clock][1], places[clock][2]])
                            for clock, _ in moments if show_links and (places or {}).get(clock) for name in bodies])
    # the sizes, as the Symbols table's Size column says: each mark's rule, and the tables (as seen from the Earth) of the
    # planets whose angular size it goes by
    from .globechart import BODY_RADIUS_KM, MARKER_RANGE, SIZE_RANGE_ARCSEC
    rules, sizing = {}, {}
    for clock, jd in moments:
        sizing[clock] = {}
        for name in bodies:
            if name in ("NN", "SN") and centre != "Ea":
                continue
            rule = core.size_rule(name, texts=size_texts(centre))
            rules[f"{core.symbol_of(name)} {clock}"] = dict(rule, clock=clock)
            if "of" in rule and rule["of"] not in sizing[clock]:
                tb = globechart._motion_table(rule["of"], jd)
                sizing[clock][rule["of"]] = dict(step=tb["step"], dist=tb["dist"], shift=tb["shift"], ra=tb["ra"][:2], dec=tb["dec"][:2],
                                                 km=BODY_RADIUS_KM[rule["of"]])
    # the clock beside the customer's name, as the drawing's: each moment's date and time at its place's UTC offset
    clocks = [dict(clock=clock, jd=jd, offset=(offsets or {}).get(clock)) for clock, jd in moments]
    data = dict(tables=tables, day_seconds=day_seconds, days=space3d.RUN_DAYS, clocks=clocks,
                fit_r=c["fit_r"], log_from=c["log_from"], gap=list(c["gap"]), word=c["name"].lower(), globe=globe,
                rules=rules, sizing=sizing, mark_scale=MARK_SCALE, symbol_px=SYMBOL_PX, symbol_least=SYMBOL_LEAST, symbol_font=list(SYMBOL_FONT), au_km=core.AU_KM, arcsec=list(SIZE_RANGE_ARCSEC), radii=list(MARKER_RANGE))
    return ("const M = " + json.dumps(data, separators=(",", ":")).replace("<", "\\u003c") + ";\n" + """
  const RAD = Math.PI / 180;
  const reach = (au) => {                          // as space3dview._reach
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
  // Geo: the Earth as a globe (land and sea, coastlines, a 30-degree grid, CB and CN), turned as at the globe's moment
  const G = M.globe, STEP = 3, OCEAN = "rgb(25,70,150)", LAND = "rgb(85,150,80)";
  let globe = null;
  const lonLatXYZ = (lon, lat, r, gst) => {        // a place on the Earth, in the sky's frame: RA = sidereal time + longitude
    const ra = (gst + lon) * RAD, la = lat * RAD;
    return [r * Math.cos(la) * Math.cos(ra), r * Math.cos(la) * Math.sin(ra), r * Math.sin(la)];
  };
  const lines3d = (lines, r, gst) => {             // lines of [lon, lat] as one trace's x, y, z (null between them)
    const x = [], y = [], z = [];
    lines.forEach((ln) => { ln.forEach(([lo, la]) => { const p = lonLatXYZ(lo, la, r, gst); x.push(p[0]); y.push(p[1]); z.push(p[2]); });
                            x.push(null); y.push(null); z.push(null); });
    return [x, y, z];
  };
  const turnGlobe = (gst) => {                     // the globe and what is on it, turned to this sidereal time
    if (!globe) return;
    const X = [], Y = [], Z = [];
    globe.lats.forEach((la) => {
      const xr = [], yr = [], zr = [];
      globe.lons.forEach((lo) => { const p = lonLatXYZ(lo, la, G.r, gst); xr.push(p[0]); yr.push(p[1]); zr.push(p[2]); });
      X.push(xr); Y.push(yr); Z.push(zr);
    });
    const c = lines3d(globe.coast, G.r * 1.004, gst), g = lines3d(globe.grid, G.r * 1.002, gst);
    const xs = [X, c[0], g[0]], ys = [Y, c[1], g[1]], zs = [Z, c[2], g[2]], at = [globe.earth, globe.coastAt, globe.gridAt];
    Object.entries(G.places).forEach(([name, [la, lo]]) => {
      const i = gd.data.findIndex((d) => d.name === name);
      if (i >= 0) { const p = lonLatXYZ(lo, la, G.r * 1.01, gst); xs.push([p[0]]); ys.push([p[1]]); zs.push([p[2]]); at.push(i); }
    });
    Plotly.restyle(gd, {x: xs, y: ys, z: zs}, at);
  };
  const makeGlobe = (topo) => {                    // land and sea from the world map's land shapes, its coastlines
    const [sx, sy] = topo.transform.scale, [tx, ty] = topo.transform.translate;
    const arcs = topo.arcs.map((a) => { let x = 0, y = 0; return a.map(([dx, dy]) => { x += dx; y += dy; return [x * sx + tx, y * sy + ty]; }); });
    const arc = (i) => (i >= 0 ? arcs[i] : arcs[~i].slice().reverse());
    const join = (ids) => ids.reduce((pts, i) => pts.concat(pts.length ? arc(i).slice(1) : arc(i)), []);
    const rings = [];
    topo.objects.land.geometries.forEach((g) => {
      (g.type === "Polygon" ? [g.arcs] : g.type === "MultiPolygon" ? g.arcs : []).forEach((poly) => poly.forEach((ids) => {
        const pts = join(ids), lo = pts.map((p) => p[0]), la = pts.map((p) => p[1]);
        rings.push({pts, box: [Math.min(...lo), Math.max(...lo), Math.min(...la), Math.max(...la)]});
      }));
    });
    const isLand = (lo, la) => {                   // inside an odd number of the land's rings (even-odd, so lakes are holes)
      if (la < -84) return true;                   // (the map stops short of the south pole: Antarctica)
      let inside = false;
      rings.forEach(({pts, box}) => {
        if (lo < box[0] || lo > box[1] || la < box[2] || la > box[3]) return;
        for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
          const [xi, yi] = pts[i], [xj, yj] = pts[j];
          if ((yi > la) !== (yj > la) && lo < (xj - xi) * (la - yi) / (yj - yi) + xi) inside = !inside;
        }
      });
      return inside;
    };
    const lats = [], lons = [];
    for (let la = -90; la <= 90; la += STEP) lats.push(la);
    for (let lo = -180; lo <= 180; lo += STEP) lons.push(lo);
    const colour = lats.map((la) => lons.map((lo) => (isLand(lo, la) ? 1 : 0)));
    const coast = [];
    topo.objects.coastlines.geometries.forEach((g) => {
      (g.type === "LineString" ? [g.arcs] : g.type === "MultiLineString" ? g.arcs : []).forEach((ids) => coast.push(join(ids)));
    });
    const grid = [];
    for (let la = -60; la <= 60; la += 30) { const ln = []; for (let lo = -180; lo <= 180; lo += 5) ln.push([lo, la]); grid.push(ln); }
    for (let lo = -180; lo < 180; lo += 30) { const ln = []; for (let la = -90; la <= 90; la += 5) ln.push([lo, la]); grid.push(ln); }
    const earth = gd.data.findIndex((d) => d.type === "surface");
    const n = gd.data.length;
    Plotly.restyle(gd, {surfacecolor: [colour], cmin: 0, cmax: 1, opacity: 1,
                        colorscale: [[[0, OCEAN], [0.5, OCEAN], [0.5, LAND], [1, LAND]]]}, [earth]);
    Plotly.addTraces(gd, [
      {type: "scatter3d", mode: "lines", x: [], y: [], z: [], line: {color: "rgba(225,240,220,0.85)", width: 1.5}, hoverinfo: "skip", showlegend: false, name: "coastlines"},
      {type: "scatter3d", mode: "lines", x: [], y: [], z: [], line: {color: "rgba(255,255,255,0.25)", width: 1}, hoverinfo: "skip", showlegend: false, name: "latitude and longitude"}]);
    globe = {lats, lons, coast, grid, earth, coastAt: n, gridAt: n + 1};
    turnGlobe(G.gst0);
  };
  if (G) {
    const known = window.PlotlyGeoAssets && window.PlotlyGeoAssets.topojson && window.PlotlyGeoAssets.topojson.world_110m;
    if (known) makeGlobe(known);
    else fetch("https://cdn.plot.ly/un/world_110m.json").then((r) => r.json()).then(makeGlobe).catch(() => {});   // (none: a plain blue Earth)
  }
  const idx = [], keys = [];
  gd.data.forEach((d, i) => { if (M.tables[d.name]) { idx.push(i); keys.push(d.name); } });
  const spokes = [];                               // Sp: each spoke's trace, its body and its length (to the view's edge)
  gd.data.forEach((d, i) => {
    const k = d.name && d.name.startsWith("Sp ") ? keys.indexOf(d.name.slice(3)) : -1;
    if (k >= 0) spokes.push({i, k, len: Math.hypot(d.x[1], d.y[1], d.z[1])});
  });
  const pad2 = (v) => (v >= 0 ? "+" : "-") + Math.abs(v).toFixed(2);
  const clockLine = (s, t) => {                    // as the drawing's: its date and time, at its place's UTC offset
    const known = s.offset !== null && s.offset !== undefined, off = known ? s.offset : 0;
    const ms = (s.jd + t - 2440587.5) * 86400000 + off * 3600000 + 500;       // to the nearest second
    return s.clock + " " + new Date(ms).toISOString().slice(0, 19).replace("T", " ") + (known ? " UTC" + pad2(off) : " UT");
  };
  const showClocks = (t) => {                      // in the page's clock, beside the customer's name
    const box = document.querySelector(".globe-clock");
    if (box) box.textContent = M.clocks.map((s) => clockLine(s, t)).join("    ");
  };
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
    const radii = keys.map((k) => {                // by the Symbols table's Size, as on the flat drawing
      const rule = M.rules[k];
      if (!rule) return 7;
      if (rule.px !== undefined) return rule.px;
      const b = M.sizing[rule.clock][rule.of], u = (t + b.shift) / b.step, i = Math.max(0, Math.min(Math.floor(u), b.dist.length - 2));
      const au = b.dist[i] + (b.dist[i + 1] - b.dist[i]) * (u - i), arcsec = 2 * Math.atan(b.km / (au * M.au_km)) / RAD * 3600;
      const lo = Math.log(M.arcsec[0]), hi = Math.log(M.arcsec[1]);
      const share = Math.max(0, Math.min(1, (Math.log(arcsec) - lo) / (hi - lo)));
      return Math.max(1, M.radii[0] + (M.radii[1] - M.radii[0]) * share + rule.add);
    });
    // each mark (a diameter) and its symbol inside it, sized with it (none on a mark too small to read)
    Plotly.restyle(gd, {x: xs, y: ys, z: zs, hovertemplate: tips, "marker.size": radii.map((r) => M.mark_scale * r),
                        "textfont.size": radii.map((r) => Math.min(Math.max(M.symbol_px * r, M.symbol_font[0]), M.symbol_font[1])),
                        text: keys.map((k, n) => [radii[n] >= M.symbol_least ? gd.data[idx[n]].name.split(" ")[0] : ""])}, idx);
    if (G) turnGlobe(G.gst0 + G.spin * t);         // the Earth turning with time
    if (spokes.length) {                           // Sp: from the centre through the body as it moves, to the view's edge
      Plotly.restyle(gd, {x: spokes.map((p) => [0, xs[p.k][0] * p.len / Math.hypot(xs[p.k][0], ys[p.k][0], zs[p.k][0])]),
                          y: spokes.map((p) => [0, ys[p.k][0] * p.len / Math.hypot(xs[p.k][0], ys[p.k][0], zs[p.k][0])]),
                          z: spokes.map((p) => [0, zs[p.k][0] * p.len / Math.hypot(xs[p.k][0], ys[p.k][0], zs[p.k][0])])},
                     spokes.map((p) => p.i));
    }
    if (G && G.links.length) {                     // SpC: from CB or CN, turning with the Earth, to the body as it moves
      const gst = G.gst0 + G.spin * t, lx = [], ly = [], lz = [], li = [];
      G.links.forEach((l) => {
        const i = gd.data.findIndex((d) => d.name === l.line), k = keys.indexOf(l.body);
        if (i < 0 || k < 0) return;
        const p = lonLatXYZ(l.place[1], l.place[0], G.r * 1.01, gst);
        lx.push([p[0], xs[k][0]]); ly.push([p[1], ys[k][0]]); lz.push([p[2], zs[k][0]]); li.push(i);
      });
      if (li.length) Plotly.restyle(gd, {x: lx, y: ly, z: lz}, li);
    }
    showClocks(t);
    setTimeout(tick, 250);
  };
  if (M.day_seconds) tick(); else showClocks(0);   // (standing still: the moment's own time)
""")
