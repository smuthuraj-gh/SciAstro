"""The Geo/Helio page, GeoCentric and HelioCentric: the paths of the Sun, Moon and planets around the Earth, or of the planets and the Earth
around the Sun, each at its real distance, unlike Equatorial-3D, where all are on one sphere. A point is placed by its RA, De and distance only (equatorial, no zodiac); north is up and the
Earth's equator is the flat plane. Drawn on the page in SVG, so its labels can be kept apart as it is turned."""
from __future__ import annotations

import json
import math
import uuid
from functools import lru_cache

from . import core
from .globechart import (MARKER_RANGE, MOTION_DAYS, MOTION_HALF, NODE_CHOICES, PATH_SPAN, SIZE_RANGE_ARCSEC, SYMBOL_JS, TILT, _motion_rows, _motion_table,
                         _node_rows, _node_table, day_start, symbol_shapes, ASPECT_COLOURS, ASPECT_NAMES, EARTH_DEGREES_A_DAY, HOUSE_COLOUR)
from .mapchart import FONT, SYMBOL_FONT_FAMILY

WIDTH, HEIGHT = 1100, 900          # taller than the orbits need, for the RA lines beyond them
RADIUS = 300.0                    # pixels from the Earth to the farthest thing drawn
VIEW = (130, 110, WIDTH, HEIGHT - 110)       # the part of the drawing shown (left, top, width, height): the drawing at the top left
FLAT_VIEW = (30, 50, WIDTH, HEIGHT - 50)    # the same for the flat page
FIT = "Fit"                       # the scale: each tenfold distance the same room, without the empty space between the Moon and the planets
GAP = (0.003, 0.25, 0.03)         # Fit: from just past the Moon's farthest (AU) to inside any planet's nearest (Venus about 0.26),
                                  # drawn as only this much (a tenth of a doubling: a thin space)
LOG_FROM_AU = 0.0013              # on Fit, the distance drawn at the Earth (the Moon, about 0.0024-0.0027, close by)
SPANS = {"Su": (365.25, 120, "Sun Path"), **PATH_SPAN}     # days, points, name: one trip round the sky
RINGS = (0.01, 0.5, 1.0, 2.5, 5.0, 10.0)   # AU: just past the Moon (in the space taken out, so not to scale there), then the planets
RINGS_SHOWN = 6                   # at most this many rings, the outermost ones
RA_MARKS = (0, 90, 180, 270)
RUN_HALF = MOTION_HALF            # the tables reach this far each side of the moment (36 years), as Equatorial-3D's
RUN_DAYS = MOTION_DAYS            # how far time runs here (72 years, as on Equatorial-3D) before it starts again, with the trails
RA_LONGER = 1.5                   # the RA lines reach this much beyond the farthest orbit
SMALL_FONT = 12                   # the rings' AU tags, in pixels
POLE_FONT = 12                    # NCP, SCP and the RA names, in pixels
SCP_BEYOND_AU = 20.0              # the axis reaches, both ways on the page, past where a ring this far out would be drawn ...
SCP_PAST_PX = 22                  # ... by this many pixels, NCP and SCP at its ends
SIDES = 96                        # a ring is drawn with this many straight pieces
# Flat (the Equatorial-2D page): GeoCentric seen from above the north celestial pole, each body at its RA and its distance
# from the Earth (its De in its hover box only); only the FLAT_RING_AU circle, at the edge, with an RA scale round it,
# 1 to 360 (a tick every degree, longer every 5, numbered every 10)
FLAT_RING_AU = 12.0
OUTER_RING_AU = 20.0              # Geo and Helio: a circle beyond the planets, with the AU button
FLAT_RADIUS = 360.0               # pixels from the Earth to that circle
ONE_CIRCLE_AT = 0.72                # Equatorial-2D's Aspect: every body this far out, of the way to the 12 AU circle
FLAT_DRAG_DAYS = 0.25             # the flat page with no speed picked: how many days a pixel of dragging moves time
FLAT_FONT = 12                    # the RA numbers, in pixels
SIGNS = (("Aries", "♈"), ("Taurus", "♉"), ("Gemini", "♊"), ("Cancer", "♋"), ("Leo", "♌"), ("Virgo", "♍"),
         ("Libra", "♎"), ("Scorpio", "♏"), ("Sagittarius", "♐"), ("Capricorn", "♑"), ("Aquarius", "♒"), ("Pisces", "♓"))


def ecliptic_ra(lon: float) -> float:
    """The RA (degrees) of the point of the ecliptic at this longitude (degrees)."""
    lam = math.radians(lon)
    return math.degrees(math.atan2(math.sin(lam) * math.cos(math.radians(TILT)), math.cos(lam))) % 360


def zodiac_signs(ayanamsa: float = 0.0) -> list[dict]:
    """The twelve signs, each 30 degrees of the ecliptic, as RA spans: where each starts and ends, and its middle, in RA
    (so not all 30 degrees wide in RA). ayanamsa 0: Tropical, Aries from the March equinox; else Sidereal, each sign that
    many degrees further on along the ecliptic (Aries from the ayanamsa)."""
    kind = "Tropical" if not ayanamsa else f"Sidereal, Lahiri ayanamsa {ayanamsa:.2f}"
    return [dict(name=n, sym=s + "︎", ra0=round(ecliptic_ra(30 * i + ayanamsa), 3), ra1=round(ecliptic_ra(30 * i + 30 + ayanamsa), 3),
                 mid=round(ecliptic_ra(30 * i + 15 + ayanamsa), 3), kind=kind,
                 lon0=round((30 * i + ayanamsa) % 360, 2), lon1=round((30 * i + 30 + ayanamsa) % 360, 2),
                 tag="Tr" if not ayanamsa else "Si", lord=SIGN_LORDS[n]) for i, (n, s) in enumerate(SIGNS)]


# each sign's lord (its traditional ruler); the 13 constellations' by the sign of the same name (Ophiuchus: none)
SIGN_LORDS = {"Aries": "Ma", "Taurus": "Ve", "Gemini": "Me", "Cancer": "Mo", "Leo": "Su", "Virgo": "Me", "Libra": "Ve",
              "Scorpio": "Ma", "Sagittarius": "Ju", "Capricorn": "Sa", "Aquarius": "Sa", "Pisces": "Ju",
              "Scorpius": "Ma", "Capricornus": "Sa", "Ophiuchus": None}


# Op (once 13): the constellations the ecliptic passes through, Ophiuchus among them, each from where the ecliptic enters it (the IAU
# boundaries, Tropical ecliptic longitude for J2000: so not all the same width), Aries first
CONSTELLATIONS = (("Aries", "\u2648", 29.09), ("Taurus", "\u2649", 53.47), ("Gemini", "\u264a", 90.43), ("Cancer", "\u264b", 118.26),
                  ("Leo", "\u264c", 138.18), ("Virgo", "\u264d", 174.15), ("Libra", "\u264e", 218.03), ("Scorpius", "\u264f", 241.14),
                  ("Ophiuchus", "\u26ce", 247.70), ("Sagittarius", "\u2650", 266.30), ("Capricornus", "\u2651", 299.69),
                  ("Aquarius", "\u2652", 327.48), ("Pisces", "\u2653", 351.57))


def constellations(jd: float) -> list[dict]:
    """Op: the 13 constellations on the ecliptic as RA spans, their J2000 boundaries moved on by the precession to jd (the
    stars stay; the equinox moves back among them, about 1 degree in 72 years)."""
    t = (jd - 2451545.0) / 36525.0
    shift = (5028.796195 * t + 1.1054348 * t * t) / 3600.0      # (the general precession in longitude, degrees)
    out = []
    for i, (n, s, lon) in enumerate(CONSTELLATIONS):
        start, end = lon + shift, CONSTELLATIONS[(i + 1) % 13][2] + shift
        end += 360 if end < start else 0
        out.append(dict(name=n, sym=s + "\ufe0e", ra0=round(ecliptic_ra(start), 3), ra1=round(ecliptic_ra(end), 3),
                        mid=round(ecliptic_ra((start + end) / 2), 3), kind="13 constellations, IAU boundaries",
                        lon0=round(start % 360, 2), lon1=round(end % 360, 2), tag="Op", lord=SIGN_LORDS[n]))
    return out


SYSTEMS_OUTER = 394.0             # Systems: how far out its outermost ring reaches; the circle as big as leaves room for the
                                  # rings shown (Ec, Tr's and Si's signs, Na's stars), at most FLAT_RADIUS
EC_RING = 38                      # Systems: how wide the Ec ring is, in pixels
SIGN_RING = 26                    # Systems: how wide each ring of signs is, in pixels
VEDIC_RING = 28                   # Systems: how wide Na's ring of the 27 stars (nakshatras) is, in pixels
NAKSHATRAS = ("Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha",
              "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula",
              "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati")
# Na: the same stars by their South Indian (Tamil) names, in the same order
NAKSHATRAS_SOUTH = ("Ashwini", "Bharani", "Karthigai", "Rohini", "Mirugaseersham", "Thiruvathirai", "Punarpoosam", "Poosam", "Ayilyam",
                    "Magam", "Pooram", "Uthiram", "Hastham", "Chithirai", "Swathi", "Visakam", "Anusham", "Kettai", "Moolam",
                    "Pooradam", "Uthiradam", "Thiruvonam", "Avittam", "Sadhayam", "Poorattathi", "Uthirattathi", "Revathi")


def nakshatras(ayanamsa: float) -> list[dict]:
    """Na: the 27 stars (nakshatras), each 13 degrees 20 minutes of the Sidereal ecliptic from Ashwini at its 0 (that many
    degrees on from the Tropical 0: the ayanamsa), as RA spans: where each starts and ends, and its middle."""
    step = 360 / 27
    return [dict(name=f"{NAKSHATRAS_SOUTH[i]} ({n})", n=i + 1, ra0=round(ecliptic_ra(step * i + ayanamsa), 3), ra1=round(ecliptic_ra(step * i + step + ayanamsa), 3),
                 mid=round(ecliptic_ra(step * i + step / 2 + ayanamsa), 3), sid0=round(step * i, 2), sid1=round(step * i + step, 2),
                 padas=[round(ecliptic_ra(step * i + step * q / 4 + ayanamsa), 3) for q in range(4)],   # its four quarters' starts
                 short=NAKSHATRAS_SOUTH[i][:10],   # (its South Indian name, on one line, at most 10 letters: with the gap and its lord, 12)
                 lord=VIMSHOTTARI[i % 9][0], colour=core.colour(VIMSHOTTARI[i % 9][0]),   # its star lord (Ketu, Venus .. as KP's)
                 ayanamsa=round(ayanamsa, 2)) for i, n in enumerate(NAKSHATRAS)]


KP_RING = 52                      # Systems: how wide KP's ring is, in pixels: its subs' colours (inner), its sub lords' symbols (outer, three lanes)
KP_SUB = 16                       # (the subs' coloured band, inside the symbols' three lanes)
VIMSHOTTARI = (("SN", 7), ("Ve", 20), ("Su", 6), ("Mo", 10), ("Ma", 7), ("NN", 18), ("Ju", 16), ("Sa", 19), ("Me", 17))   # (Ke, Ra: SN, NN)


def kp_stars(ayanamsa: float) -> dict:
    """KP: the 27 stars (nakshatras), each 13 degrees 20 minutes of the Sidereal ecliptic (by the KP ayanamsa) from Ashwini,
    each with its star lord (Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn, Mercury, then again) and its nine subs,
    each the share of the star its lord's Vimshottari years are of 120, from the star's own lord on; as RA spans."""
    step, out = 360 / 27, []
    for i, name in enumerate(NAKSHATRAS):
        start, subs = step * i, []
        for k in range(9):
            lord, years = VIMSHOTTARI[(i + k) % 9]
            width = step * years / 120
            subs.append(dict(lord=lord, colour=core.colour(lord), sid0=round(start, 3), sid1=round(start + width, 3),
                             ra0=round(ecliptic_ra(start + ayanamsa), 3), ra1=round(ecliptic_ra(start + width + ayanamsa), 3)))
            start += width
        lord = VIMSHOTTARI[i % 9][0]
        out.append(dict(name=name, n=i + 1, lord=lord, colour=core.colour(lord), sid0=round(step * i, 3), sid1=round(step * i + step, 3),
                        ra0=round(ecliptic_ra(step * i + ayanamsa), 3), ra1=round(ecliptic_ra(step * i + step + ayanamsa), 3),
                        mid=round(ecliptic_ra(step * i + step / 2 + ayanamsa), 3), subs=subs))
    return dict(ayanamsa=round(ayanamsa, 3), stars=out)


def systems_radius(ecliptic: bool, signs: int, vedic: bool, kp: bool = False, kp_houses: bool = False) -> float:
    """Systems: the circle's radius, as big as leaves room (to SYSTEMS_OUTER) for the rings shown round it, as the page
    draws them: Ec next to it, then the rings of signs, then Na's (each 2 pixels from the last; the first, without Ec, 4)."""
    edge = EC_RING if ecliptic else 0
    for _ in range(signs):
        edge += (2 if edge else 4) + SIGN_RING
    if vedic:
        edge += (2 if edge else 4) + VEDIC_RING
    if kp:
        edge += (2 if edge else 4) + KP_RING + (16 if kp_houses else 0)   # (Ho: the Placidus houses' names outside it)
    return min(FLAT_RADIUS, SYSTEMS_OUTER - edge)
FLAT_DEC = (30.0, -30.0)          # the Declination graph left of the circle, as tall as it: its top and bottom, in degrees

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
HELIO_RINGS = (0.5, 1.0, 2.5, 5.0, 10.0)   # AU
NO_GAP = (1.0, 1.0, 0.0)          # nothing taken out
# by the body at the centre: the distance drawn there on Fit, the space taken out, the rings, the paths' spans, and its name in words
CENTRES = {"Ea": dict(log_from=LOG_FROM_AU, gap=GAP, rings=RINGS, rings_shown=RINGS_SHOWN, spans=SPANS, word="earth"),
           "Su": dict(log_from=HELIO_LOG_FROM_AU, gap=NO_GAP, rings=HELIO_RINGS, rings_shown=5, spans=HELIO_SPANS, word="the Sun")}


TABLE_KEYS = ("step", "ra", "dec", "dist", "km", "shift", "at0")   # what the page reads of a table


@lru_cache(maxsize=48)
def _helio_rows(planet: str, start: float, days: int) -> dict:
    step = HELIO_STEP_DAYS[planet]
    pts = [core.helio_position(planet, start + i * step) for i in range(int((days + 1) / step) + 2)]   # (a day more: the shift)
    return {"step": step, "ra": [round(p.ra, 3) for p in pts], "dec": [round(p.dec, 3) for p in pts],
            "dist": [round(p.dist_au, 6) for p in pts], "km": 0.0}


def _helio_table(planet: str, jd: float, days: int = RUN_DAYS) -> dict:
    """A body's RA, De and distance as seen from the Sun, from jd on, for the page to move it by (rows from jd's day_start,
    shift and at0, as globechart._motion_table)."""
    start, p = day_start(jd), core.helio_position(planet, jd)
    return {**_helio_rows(planet, start, days), "shift": jd - start,
            "at0": {"ra": round(p.ra, 3), "dec": round(p.dec, 3), "dist": round(p.dist_au, 6)}}


def _node_geo_table(name: str, jd: float, days: int = RUN_DAYS) -> dict:
    """NN or SN as a body round the Earth (the flat page): on the Moon's path, so at the Moon's distance then, at the node's
    own RA and De (the south node opposite the north)."""
    moon, node = _motion_table("Mo", jd, days), _node_table(jd)
    ra0, dec0 = node["at0"] if name == "NN" else ((node["at0"][0] + 180.0) % 360.0, -node["at0"][1])
    return {**_node_geo_rows(name, day_start(jd), days), "shift": moon["shift"],
            "at0": {"ra": round(ra0, 3), "dec": round(dec0, 3), "dist": moon["at0"]["dist"]}}


@lru_cache(maxsize=8)
def _node_geo_rows(name: str, start: float, days: int) -> dict:
    """On the node's own table's times (every NODE_STEP_DAYS: a quarter of the Moon's rows), with the Moon's distance then."""
    moon, node = _motion_rows("Mo", start, days), _node_rows(start)
    flip = name != "NN"                                       # the south node: opposite the north
    dist = []
    for i in range(len(node["ra"])):
        u = i * node["step"] / moon["step"]
        k = min(int(u), len(moon["dist"]) - 2)
        f = u - k
        dist.append(round(moon["dist"][k] + (moon["dist"][k + 1] - moon["dist"][k]) * f, 8))
    return {"step": node["step"], "ra": [round((r + 180.0) % 360.0, 3) if flip else r for r in node["ra"]],
            "dec": [-d if flip else d for d in node["dec"]], "dist": dist, "km": 0.0}


def _reach(au: float, scale: str = FIT, log_from: float = LOG_FROM_AU, gap: tuple = GAP) -> float:
    """How far from the centre a distance is drawn on the Fit scale, before fitting to the page."""
    log = max(math.log10(au / log_from), 0.0)
    a, b = math.log10(gap[0] / log_from), math.log10(gap[1] / log_from)
    return log if log <= a else log - (b - a) + gap[2] if log >= b else a + (log - a) / (b - a) * gap[2]


def _xyz(ra: float, dec: float, reach: float) -> list[float]:
    """x toward RA 0, y toward RA 90, z toward the north celestial pole."""
    a, d = math.radians(ra), math.radians(dec)
    return [round(reach * math.cos(d) * math.cos(a), 5), round(reach * math.cos(d) * math.sin(a), 5), round(reach * math.sin(d), 5)]


def _geo_table(planet: str, jd: float) -> dict:
    """A body's table as seen from the Earth, from jd (RUN_HALF before the moment) on, as the page reads it, with its exact
    place at the moment (at0, RUN_HALF on). (Each table merged into the page's must carry the moment's place: one with the
    tables' start's, 36 years earlier, put the planets in the wrong places when time stood at the moment.)"""
    whole = _motion_table(planet, jd, RUN_DAYS)
    return {**{k: whole[k] for k in TABLE_KEYS}, "at0": _motion_table(planet, jd + RUN_HALF, 2)["at0"]}


def space_data(bodies: list[str], moments: list[tuple[str, float, float | None]], scale: str, key: str,
               day_seconds: float | None = None, manual: bool = False, show_au: bool = False, with_paths: tuple | None = None,
               centre: str = "Ea", flat: bool = False, places: dict | None = None, ave_jds: dict | None = None,
               aspects: tuple = (), orbs: core.Orbs | None = None, one_circle: bool = False, show_celes: bool = True,
               reverse: bool = False, asc: dict | None = None) -> dict:
    """For each moment and body: its table to move it by, and (those in with_paths; all with None) its path, which the page draws
    as a trail behind it, where it has really been since the moment, kept for the whole run (72 years).
    moments: (Now or DOB, Julian day, UTC offset). centre: Ea (GeoCentric) or Su (HelioCentric). The drawing's size does not
    change with the paths shown. The sizes are always by how big a body looks from the Earth (the tables seen from the Earth).
    ave_jds (the flat page): {"DOB": Julian day, "Now": Julian day}, for the Ave planets on the Distance(%) graph, each the
    average of its Distance(%) at DOB and at Now as time runs (the tables of a moment not shown are sent for them alone)."""
    at = CENTRES[centre]
    sizes = core.SIZE_TEXTS_CLOCK if flat else core.SIZE_TEXTS if centre == "Ea" else core.SIZE_TEXTS_HELIO   # the Size_Clock-2D, Size_Geo or Size_Helio column
    reach = lambda au: _reach(au, scale, at["log_from"], at["gap"])
    paths, marks, tables, sizing = [], [], {}, {}
    outer = 0.0
    for clock, jd, _ in moments:
        tables[clock], sizing[clock] = {}, {}
        if centre == "Su" and "Mo" in bodies:                 # the Moon goes round the Earth: the Earth's table, shown or not
            whole = _helio_table("Ea", jd, RUN_DAYS)
            tables[clock]["Ea"] = {**{k: whole[k] for k in TABLE_KEYS}, "at0": _helio_table("Ea", jd + RUN_HALF, 2)["at0"]}
            outer = max(outer, reach(max(whole["dist"])))
        for p in bodies:
            around = centre == "Su" and p == "Mo"                # its table as seen from the Earth
            table = (_node_geo_table if p in NODE_CHOICES else       # (the flat page's NN, SN)
                     _motion_table if centre == "Ea" or around else _helio_table)
            whole = table(p, jd, RUN_DAYS)
            # (its exact place at the moment, RUN_HALF on: shown there rather than one read between table rows)
            tables[clock][p] = {**{k: whole[k] for k in TABLE_KEYS}, "at0": table(p, jd + RUN_HALF, 2)["at0"]}
            if not around:
                outer = max(outer, reach(max(whole["dist"])))
            rule = core.size_rule(p, texts=sizes)
            marks.append(dict(name=p, colour=core.colour(p), hollow=clock == "DOB", clock=clock, rule=rule))
            if (with_paths is None or p in with_paths) and p in at["spans"]:   # the page draws it as time runs, from the
                                                                              # body's own table (NN and SN: no path)
                days, steps, name = at["spans"][p]
                paths.append(dict(colour=core.colour(p), dash=clock == "DOB", name=name, body=p, clock=clock, days=days, steps=steps, pts=[]))
    # what the sizes are measured from: each body as seen from the Earth (Bigger than Moon needs the Moon's table, shown or not)
    centre_rule = core.size_rule(centre, texts=sizes)
    for clock, jd, _ in moments:
        for p in bodies:
            if p in core.PLANET_ID:
                sizing[clock][p] = _geo_table(p, jd)
        for rule in [centre_rule] + [m["rule"] for m in marks]:
            if "of" in rule and rule["of"] not in sizing[clock]:
                sizing[clock][rule["of"]] = _geo_table(rule["of"], jd)
    if centre == "Ea":                                         # the same tables: not sent twice
        for clock in tables:
            tables[clock].update(sizing[clock])
        sizing = None
    ave_marks, ave_tables = [], {}
    if flat and ave_jds:                                      # the Ave planets: from both moments' tables, as seen from the Earth
        for p in [b for b in bodies if b in core.PLANETS]:
            rule = core.size_rule(p, texts=sizes)
            ave_marks.append(dict(name=p, colour=core.colour(p), rule=rule))
            for clock, jd in ave_jds.items():
                for q in {p, rule.get("of", p)}:
                    if q not in tables.get(clock, {}):
                        ave_tables.setdefault(clock, {})[q] = _geo_table(q, jd)
    outer = outer or 1.0
    wanted = [au for au in at["rings"] if reach(au) <= outer][-at["rings_shown"]:] if show_au else []
    if show_au:                                               # the outer circle too, beyond the planets
        wanted = wanted + [OUTER_RING_AU]
    if flat:                                                  # only the 12 AU circle, always, at the edge
        wanted, outer = [FLAT_RING_AU], reach(FLAT_RING_AU)
    else:                                                     # the drawing sized to the outer circle, shown or not
        outer = max(outer, reach(OUTER_RING_AU))
    circle = [(360.0 * v / SIDES) for v in range(SIDES + 1)]
    rings = [dict(text=f"{au:g} AU", pts=[_xyz(ra, 0.0, reach(au)) for ra in circle]) for au in wanted]
    aspect_rows = [dict(angle=a, colour=ASPECT_COLOURS[a in core.MINOR], width=1.0 if a in core.MINOR else 1.5,
                        orbs={f"{p}|{q}": orbs.pair(a, p, q) for i, p in enumerate(ASPECT_NAMES) for q in ASPECT_NAMES[i + 1:] if {p, q} != set(NODE_CHOICES)},
                        dec_orbs={f"{p}|{q}": orbs.pair(a, p, q, is_dec=True) for i, p in enumerate(ASPECT_NAMES) for q in ASPECT_NAMES[i + 1:] if {p, q} != set(NODE_CHOICES)})
                   for a in aspects] if orbs is not None else []
    return dict(paths=paths, marks=marks, tables=tables, sizing=sizing, rings=rings, outer=outer, aspects=aspect_rows, name_order=ASPECT_NAMES,
                fit=(FLAT_RADIUS if flat else RADIUS) / outer, width=WIDTH, height=HEIGHT, font=FONT, flat=flat, drag_days=FLAT_DRAG_DAYS, view=FLAT_VIEW if flat else VIEW, flat_font=FLAT_FONT, flat_dec=FLAT_DEC, dist_range={p: (lo / core.AU_KM, hi / core.AU_KM) for p, (lo, hi) in core.DIST_RANGE.items()},
                ave_marks=ave_marks, ave_tables=ave_tables, node_colour=core.colour("NN"), spin=EARTH_DEGREES_A_DAY, house_colour=HOUSE_COLOUR,
                houses=[dict(clock=c, place=places[c][0], ra=core.lst(jd, places[c][1])) for c, jd, _ in moments if c in (places or {})],
                asc=[dict(clock=c, place=asc[c][0], ra=core.lst(jd, asc[c][1]), lat=asc[c][2]) for c, jd, _ in moments if c in (asc or {})],
                shapes=symbol_shapes(), sym={n: core.symbol_of(n) for n in core.SYMBOL_TEXTS}, tilt=TILT, centre=centre, centre_word=at["word"],
                centre_rule=centre_rule, centre_clock=moments[0][0], centre_size=sizes.get(centre, ""), centre_colour=core.colour(centre),
                au_km=core.AU_KM, sizes=SIZE_RANGE_ARCSEC, radii=MARKER_RANGE, show_tags=show_au, show_celes=show_celes, log_from=at["log_from"], gap=at["gap"],
                scp_ring=reach(SCP_BEYOND_AU), scp_past=SCP_PAST_PX, sides=SIDES, small_font=SMALL_FONT, pole_font=POLE_FONT, key=("flat" if flat else "") + centre + key, days=RUN_DAYS, start=RUN_HALF, around=centre == "Su", moon_reach=MOON_AROUND_PX / (RADIUS / outer), moon_mean=MOON_MEAN_AU, manual=manual, day_seconds=day_seconds,
                reverse=bool(reverse and day_seconds), step_ms=max(40, min(1000, int((day_seconds or 60.0) * 2.5))), clocks=[dict(clock=c, jd=jd, offset=o) for c, jd, o in moments],
                family=SYMBOL_FONT_FAMILY, one_circle=bool(flat and one_circle), one_circle_at=ONE_CIRCLE_AT, ra_marks=[] if flat else [dict(text=f"RA {ra}", at=_xyz(ra, 0.0, outer * RA_LONGER)) for ra in RA_MARKS])


# (Spaces after every less-than: the page drops a script that seems to have tags in it.)
_JS = r"""
(function () {
  const D = __DATA__, box = document.getElementById("__ID__"), NS = "http://www.w3.org/2000/svg", RAD = Math.PI / 180;
  // the flat pages (Equatorial-2D, Systems) seen mirrored, as the sky from below: RA 0 left, 90 up, 180 right, so that RA and the
  // signs run clockwise and time runs left to right across the top (MX: -1 there); SWEEP, the arcs' sweep for RA growing
  const MX = D.flat ? -1 : 1, SWEEP = MX > 0 ? 0 : 1;
  const make = (tag, parent, attrs) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v));
    parent.appendChild(e);
    return e;
  };
  // the column's width, at any window's width: the whole drawing in view (on a phone too, its text then smaller)
  const svg = make("svg", box, {viewBox: D.view.join(" "), width: "100%",
                                style: "display:block; cursor:grab; touch-action:none; user-select:none"});
  const words = (fill, size) => make("text", svg, {"font-weight": "bold", "font-size": size || D.font, "font-family": D.family, stroke: "white",
                                             "stroke-width": 3, "paint-order": "stroke", "text-anchor": "middle", fill});
__SYMBOL_JS__
  const view = window.space3dView || (window.space3dView = {yaw: 90, pitch: 45});
  // the days since the tables' start (D.start: the moment), kept as they are whatever is pressed (stopping time, R, a
  // speed) until RS (a new key) puts the Timer back at the moment
  if (!window.space3dClock || window.space3dClock.key !== D.key) window.space3dClock = {key: D.key, t: D.start};
  const clock = window.space3dClock;
  const sample = (b, t) => {                       // between its two nearest table rows (its exact place at the start)
    if (t === D.start && b.at0) return b.at0;
    const u = (t + (b.shift || 0)) / b.step, i = Math.min(Math.floor(u), b.ra.length - 2), f = u - i;
    const turn = ((b.ra[i + 1] - b.ra[i] + 540) % 360) - 180;
    return {ra: (b.ra[i] + turn * f + 360) % 360, dec: b.dec[i] + (b.dec[i + 1] - b.dec[i]) * f, dist: b.dist[i] + (b.dist[i + 1] - b.dist[i]) * f};
  };
  const xyz = (s) => {                             // as space3d._xyz, at the distance as the scale draws it
    const log = Math.max(Math.log10(s.dist / D.log_from), 0), lo = Math.log10(D.gap[0] / D.log_from), hi = Math.log10(D.gap[1] / D.log_from);
    const r = log <= lo ? log :                    // Fit: the gap past the Moon closed up
      log >= hi ? log - (hi - lo) + D.gap[2] : lo + (log - lo) / (hi - lo) * D.gap[2], a = s.ra * RAD, d = s.dec * RAD;
    if (D.flat) {                                  // flat: at its RA and distance (the De left out); Aspect: all at one distance
      const rr = D.one_circle ? D.outer * D.one_circle_at : r;
      return [rr * Math.cos(a), rr * Math.sin(a), 0];
    }
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
  const clockLine = (s, t) => {                   // Timer: the date and time the chart shows, from DOB or Now, as
    const known = s.offset !== null && s.offset !== undefined, off = known ? s.offset : 0;   // 1968-05-29 08:45:00
    const ms = (s.jd + t - 2440587.5) * 86400000 + off * 3600000 + 500;       // (at its place's UTC offset, else UT;
    return "Timer " + new Date(ms).toISOString().slice(0, 19).replace("T", " ");   // to the nearest second; no zone written)
  };
  const showClocks = (t) => {                      // in the page's clock, beside the customer's name
    const box = document.querySelector(".globe-clock");
    const one = D.clocks.find((s) => s.clock === "Now") || D.clocks[0];   // one Timer: Now if shown, else DOB, in its own zone
    if (box) box.textContent = one ? clockLine(one, t) : "";
  };
  let X = 0, Y = 0, Z = 0, S = 0, C = 0, s = 0, c = 0;
  const LEAN_S = Math.sin(D.tilt * RAD), LEAN_C = Math.cos(D.tilt * RAD);
  const angles = () => { S = Math.sin(view.yaw * RAD); C = Math.cos(view.yaw * RAD); s = Math.sin(view.pitch * RAD); c = Math.cos(view.pitch * RAD); };
  const point = ([x, y, z]) => {                   // on the page: x, y, and how far toward the viewer (+ is near)
    if (D.flat) return [D.width / 2 + MX * x * D.fit, D.height / 2 - y * D.fit, 0];   // RA 0 left, 90 up (mirrored: MX)
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
  const radiusAt = (rule, tables, t) => {          // by the Size in the Symbols table: a fixed radius, or a planet's angular size and more
    if (rule.px !== undefined) return rule.px;
    const b = tables[rule.of], share = Math.max(0, Math.min(1, (Math.log(arcsecOf(b.km, sample(b, t).dist)) - LOW) / (HIGH - LOW)));
    return Math.max(1, D.radii[0] + (D.radii[1] - D.radii[0]) * share + rule.add);
  };
  const GREY = "rgb(150,150,150)", DARK = "rgb(60,60,60)";
  const rings = D.rings.map((r) => ({r, draw: line(GREY, 1, false, r.text + " from " + D.centre_word + ", on the plane of the Earth's equator"), label: words("rgb(110,110,110)", D.small_font)}));
  rings.forEach((g) => { g.label.textContent = g.r.text; });
  const spokes = D.ra_marks.map((m) => ({m, draw: line("rgb(205,205,205)", 1, false, m.text), label: words("rgb(110,110,110)", D.pole_font)}));
  spokes.forEach((g) => { g.label.textContent = g.m.text; });
  const axis = D.flat ? null : line(DARK, 2, false, D.centre === "Ea" ? "The Earth's axis: north celestial pole to south" :
                     "Toward the north celestial pole and the south, as the Earth's axis");
  const paths = D.paths.map((p) => ({p, draw: line(p.colour, 1.8, p.dash, "", true)}));   // a path is one colour all round
  const poles = (D.flat ? [] : [["NCP", [0, 0, D.outer]], ["SCP", [0, 0, -D.outer]]]).map(([name, at]) => {
    const label = words(DARK, D.pole_font);
    label.textContent = name;
    return {at, label};
  });
  const earth = make("circle", svg, {fill: D.centre_colour, stroke: DARK, "stroke-width": 1});   // the body at the centre
  make("title", earth).textContent = symbolOf(D.centre) + ", at the centre (its size is not to scale" + (D.centre_size ? ": " + D.centre_size : "") + ")";
  const earthLabel = symbolTag(svg, D.centre, D.centre_colour, false);
  // NN and SN, at each moment both are shown, joined by a line: 180 degrees apart, through the Earth (under the marks)
  const nodeLines = [...new Set(D.marks.map((m) => m.clock))]
    .filter((c) => D.marks.some((m) => m.clock === c && m.name === "NN") && D.marks.some((m) => m.clock === c && m.name === "SN"))
    .map((c) => {
      const e = make("path", svg, {fill: "none", stroke: D.node_colour, "stroke-width": 1.5, style: "pointer-events:stroke"});
      if (c === "DOB") e.setAttribute("stroke-dasharray", "6 4");
      make("title", e).textContent = symbolOf("NN") + " to " + symbolOf("SN") + " " + c + ": 180 degrees apart";
      return {c, e};
    });
  // flat: the twelve house lines of CB and CN, as on Equatorial-3D: 30 degrees apart from the place's RA, turning with the Earth
  const houses = D.flat ? D.houses.flatMap((h, n) => [...Array(12).keys()].map((k) => {
    const e = make("path", svg, {fill: "none", stroke: D.house_colour, "stroke-width": 1, style: "pointer-events:stroke"});
    if (h.place === "CB") e.setAttribute("stroke-dasharray", "2 3");
    const head = D.ra_inside ? make("path", svg, {fill: D.house_colour, stroke: "none"}) : null;   // (Systems: out past the rings, as As)
    return {h, n, k, e, head, tip: make("title", e), name: "H" + String((9 + k) % 12 + 1).padStart(2, "0")};
  })) : [];
  // Systems, Ho with any of Ec, Tr, Si, Op, Na, KP: twelve equal houses from each Ascendant, H01 to H12, 30 degrees of ecliptic longitude each (H01's
  // cusp is the As line itself, so eleven lines more), from the Earth to the circle; under the marks, as the Eq house lines
  const AS_RED = "rgb(200,30,30)", HOUSE_INK = "rgb(30,60,160)";   // (Tr, Si, Op's whole-sign houses and KP's Placidus cusps: blue)
  const ecliptical = (D.ecliptic || []).length || (D.zodiac || []).length || (D.vedic || []).length || D.kp;   // (Ec, Tr, Si, Op, Na or KP on)
  const ascHouses = (ecliptical ? D.asc || [] : []).flatMap((h, n) => [...Array(12).keys()].map((k) => {
    const e = k ? make("path", svg, {fill: "none", stroke: AS_RED, "stroke-width": 1, style: "pointer-events:stroke"}) : null;
    if (e && h.clock === "DOB") e.setAttribute("stroke-dasharray", "5 3");
    const head = e ? make("path", svg, {fill: AS_RED, stroke: "none"}) : null;   // (out past the rings, as As)
    return {h, n, k, e, head, tip: e ? make("title", e) : null, name: "H" + String(k + 1).padStart(2, "0")};
  }));
  // flat: a line from the Earth through each body, out to the circle, to read its RA on the scale (under the marks)
  const rays = (D.flat ? D.marks : []).map((m) => {
    const e = make("path", svg, {fill: "none", stroke: m.colour, "stroke-width": D.ra_inside ? 2 : 1, style: "pointer-events:stroke"});   // (Systems: as As's)
    if (m.hollow) e.setAttribute("stroke-dasharray", "6 4");
    const head = make("path", svg, {fill: m.colour, stroke: "none"});   // its arrow head, the tip just touching the circle
    return {m, e, head, tip: make("title", e)};
  });
  houses.forEach((g) => { g.label = words(D.house_colour, D.flat_font); g.label.textContent = g.name; });   // above the lines
  ascHouses.forEach((g) => {                       // (its name, with its tooltip, set once: set again, the tooltip would go)
    g.label = words(AS_RED, D.flat_font); g.label.textContent = g.name; g.label.style.pointerEvents = "auto"; g.labelTip = make("title", g.label);
  });
  if (D.flat) { svg.appendChild(earth); svg.appendChild(earthLabel); }   // the Earth stays on top of the lines
  const DEC_X = 95, DEC_LEAD = 36;                 // flat: the Declination graph's line, left of the circle, and how far its marks stand from it
  const decY = (dec) => D.height / 2 + D.outer * D.fit * (2 * (D.flat_dec[0] - dec) / (D.flat_dec[0] - D.flat_dec[1]) - 1);
  const decMarks = (D.flat ? D.marks : []).map((m) => {   // each body on the Declination graph, joined to its place on the line
    const lead = make("path", svg, {fill: "none", stroke: m.colour, "stroke-width": 1});
    if (m.hollow) lead.setAttribute("stroke-dasharray", "3 2");
    const e = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 1.5, style: "pointer-events:auto"});
    return {m, lead, e, tip: make("title", e), label: symbolTag(svg, m.name, m.colour, m.hollow)};
  });
  // Systems: the Ecliptic latitude graph, right of the circle (in the Distance(%) graph's place), as the Declination graph
  // left of it: its line near the right edge, its numbers left of the line, each body to the right of it, joined to its place
  const LAT_X = D.width - 95, LAT_LEAD = 36, LAT_MAX = 10;   // (from -10 to +10 degrees: Venus, the farthest, about 8.8)
  const latY = (b) => D.height / 2 + D.outer * D.fit * (2 * (LAT_MAX - b) / (2 * LAT_MAX) - 1);
  const eclipticLat = (s) => {                     // from its RA and Dec, on the ecliptic tilted D.tilt to the equator
    const a = s.ra * RAD, d = s.dec * RAD, e = D.tilt * RAD;
    return Math.asin(Math.sin(d) * Math.cos(e) - Math.cos(d) * Math.sin(e) * Math.sin(a)) / RAD;
  };
  const latMarks = (D.flat && D.lat_bar ? D.marks : []).map((m) => {
    const lead = make("path", svg, {fill: "none", stroke: m.colour, "stroke-width": 1});
    if (m.hollow) lead.setAttribute("stroke-dasharray", "3 2");
    const e = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 1.5, style: "pointer-events:auto"});
    return {m, lead, e, tip: make("title", e), label: symbolTag(svg, m.name, m.colour, m.hollow)};
  });
  // flat: the Distance(%) graph's line, right of the circle, with all its planets to its right, beyond its numbers: the time
  // picked (DOB, Now) in the first column, then Ave; DIST_FIRST, DIST_STEP: the first column's distance from it, and between them
  const DIST_X = D.width - 106, DIST_FIRST = 44, DIST_STEP = 58;   // (Average that far from DOB / Now: Distance(%) spans the two names)
  const DIST_AU = 56, AU_NUM = 8;                  // and left of it an AU scale: its numbers AU_NUM from the bar, and the same planets again
                                                   // DIST_AU from it, left of the numbers
  // the AU scale, left of the bar, as tall as it, not to scale: its marks AU_MARKS evenly up the bar, the first at the bottom
  // and the last, 11 (Saturn at its farthest), at the top; between two marks a planet stands in proportion, on a logarithmic
  // scale, to where its AU falls between them
  const AU_MARKS = [0.002, 0.003, 0.3, 0.4, 0.5, 1, 2, 5, 10, 11];   // (none between 0.003 and 0.3: Venus, which can come in to 0.26, then stands between those two)
  const auY = (au) => {
    const n = AU_MARKS.length - 1, v = Math.max(AU_MARKS[0], Math.min(AU_MARKS[n], au));
    let i = 0;
    while (i < n - 1 && v > AU_MARKS[i + 1]) i++;
    const f = (Math.log10(v) - Math.log10(AU_MARKS[i])) / (Math.log10(AU_MARKS[i + 1]) - Math.log10(AU_MARKS[i]));
    return distY(0) - (i + f) / n * (distY(0) - distY(100));
  };   // flat: the Distance(%) graph's line, right of the circle; how far right of it the Ave planets stand (beyond its numbers), and how far left DOB's (beyond Now's)
  const distY = (pct) => D.height / 2 + D.outer * D.fit * (2 * (100 - pct) / 100 - 1);
  const distMarks = (D.flat && D.dist ? D.marks.filter((m) => D.dist_range[m.name]) : []).map((m) => {   // each planet on it: DOB and, nearer the line, Now to its left
    const lead = make("path", svg, {fill: "none", stroke: m.colour, "stroke-width": 1});
    if (m.hollow) lead.setAttribute("stroke-dasharray", "3 2");
    const e = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 1.5, style: "pointer-events:auto"});
    // left of the bar: the planet again, at its distance from the Earth on the AU scale, joined to the bar by a solid line
    const auLead = make("path", svg, {fill: "none", stroke: m.colour, "stroke-width": 1});
    const auE = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 1.5, style: "pointer-events:auto"});
    return {m, lead, e, tip: make("title", e), label: symbolTag(svg, m.name, m.colour, m.hollow),
            auLead, auE, auTip: make("title", auE), auLabel: symbolTag(svg, m.name, m.colour, m.hollow)};
  });
  // flat: each pair of the planets shown, at each moment: its line and tag when in aspect (under the planets, drawn after)
  const aspectLines = [];
  if (D.flat && D.aspects.length) D.clocks.forEach(({clock: c}) => {
    const here = D.name_order.filter((n) => D.marks.some((m) => m.clock === c && m.name === n));
    here.forEach((p, i) => here.slice(i + 1).forEach((q) => {
      if (p[1] === "N" && q[1] === "N" && p.length === 2 && q.length === 2) return;   // NN-SN: always opposite
      const e = make("path", svg, {fill: "none", style: "pointer-events:stroke"});
      if (c === "DOB") e.setAttribute("stroke-dasharray", "2 3");
      aspectLines.push({c, p, q, e, tip: make("title", e), tag: words("black")});
    }));
  });
  const inAspect = (angle, a, b, orb, decOrb) => {   // the rule of core.aspect_events: RA within the RA orb of the angle, De values within the De orb of equal or mirrored
    let sep = Math.abs(a.ra - b.ra);
    if (sep > 180) sep = 360 - sep;
    return Math.abs(sep - angle) <= orb && (Math.abs(a.dec - b.dec) <= decOrb || Math.abs(a.dec + b.dec) <= decOrb);
  };
  const aveTable = (clock, p) => (D.tables[clock] && D.tables[clock][p]) || D.ave_tables[clock][p];
  const pctAt = (clock, p, t) => {                 // a planet's Distance(%) from earth at that moment, t days on
    const [lo, hi] = D.dist_range[p];
    return Math.max(0, Math.min(100, (sample(aveTable(clock, p), t).dist - lo) / (hi - lo) * 100));
  };
  const avePct = (p, t) => (pctAt("DOB", p, t) + pctAt("Now", p, t)) / 2;
  const aveRadius = (rule, t) => {                 // as radiusAt, the planet at its Ave distance
    if (rule.px !== undefined) return rule.px;
    const [lo, hi] = D.dist_range[rule.of], au = lo + (hi - lo) * avePct(rule.of, t) / 100;
    const share = Math.max(0, Math.min(1, (Math.log(arcsecOf(aveTable("Now", rule.of).km, au)) - LOW) / (HIGH - LOW)));
    return Math.max(1, D.radii[0] + (D.radii[1] - D.radii[0]) * share + rule.add);
  };
  const aveMarks = (D.flat && D.dist ? D.ave_marks : []).map((m) => {   // each planet's Ave: the average of its DOB and Now, moving as time runs
    const lead = make("path", svg, {fill: "none", stroke: m.colour, "stroke-width": 1, "stroke-dasharray": "1 2"});
    const e = make("circle", svg, {fill: m.colour, stroke: m.colour, "stroke-width": 1.5, style: "pointer-events:auto"});
    return {m, lead, e, tip: make("title", e), label: symbolTag(svg, m.name, m.colour, false)};
  });
  // the Distance(%) graph's columns: the times shown (DOB before Now), then Ave
  const distClocks = ["DOB", "Now"].filter((c) => distMarks.some((g) => g.m.clock === c));
  const distCol = (name) => DIST_X + DIST_FIRST + DIST_STEP * (name === "Ave" ? distClocks.length : Math.max(0, distClocks.indexOf(name)));
  const marks = D.marks.map((m) => {
    const e = make("circle", svg, {fill: m.hollow ? "white" : m.colour, stroke: m.colour, "stroke-width": 2, style: "pointer-events:auto"});
    const tip = make("title", e), label = symbolTag(svg, m.name, m.colour, m.hollow);
    return {m, e, tip, label, table: D.tables[m.clock][m.name]};
  });
  const boxOf = (x, y, text, size) => {             // the room a tag takes, by its font size (13 px: 8 a character, 18 high)
    const k = (size || D.font) / 13, w = text.length * 8 * k;
    return [x - w / 2 - 3, y - 15 * k, x + w / 2 + 3, y + 3 * k];
  };
  const scaleBoxes = [];                           // flat: the RA scale round the circle, 1 to 360 (drawn once: it does not turn)
  const sysRings = [];                             // Systems: the rings round the circle, inner first ({kind, r0, r1, ring}), for As
  const signHouses = [];                           // Systems, Ho: each sign's whole-sign house name ({ring, i, label, tip, base, last})
  let kpHouses = null;                             // Systems, Ho with KP: the Placidus cusps on the KP ring ({r0, r1, cusps})
  const ascs = (D.asc || []).map((h) => {          // Systems, As: each place's Ascendant, a line across the circle's edge and the rings
    const e = make("path", svg, {fill: "none", stroke: "rgb(200,30,30)", "stroke-width": 2, style: "pointer-events:stroke"});
    if (h.clock === "DOB") e.setAttribute("stroke-dasharray", "5 3");
    // (its tooltip on the line, its arrow head and its name alike, the line being thin to point at)
    const head = make("path", svg, {fill: "rgb(200,30,30)", stroke: "none", style: "pointer-events:auto"}), name = words("rgb(200,30,30)");
    name.style.pointerEvents = "auto"; name.textContent = "As";   // (its text once: set again, it would take its tooltip off)
    return {h, e, head, tip: make("title", e), headTip: make("title", head), name, nameTip: make("title", name)};
  });
  const ascLon = (h, t) => {                       // the ecliptic longitude rising in the east there then: from the sidereal time
    const th = ((h.ra + D.spin * t) % 360) * RAD, e = D.tilt * RAD, phi = h.lat * RAD;   // (RAMC), the latitude and the tilt
    return ((Math.atan2(Math.cos(th), -(Math.sin(th) * Math.cos(e) + Math.tan(phi) * Math.sin(e))) / RAD) % 360 + 360) % 360;
  };
  // KP's houses, Placidus: the cusps H01 to H12 in ecliptic longitude: H10 the MC, H01 the Ascendant; H11 and H12 a third
  // and two thirds of the diurnal semi-arc east of the meridian, H02 and H03 two thirds and a third of the nocturnal one before
  // the IC (each found by turns, its semi-arc hanging on its own declination); H04 to H09 opposite those (null past the
  // polar circles, where some points never rise)
  const placidus = (h, t) => {
    const ramc = ((h.ra + D.spin * t) % 360 + 360) % 360, e = D.tilt * RAD, tp = Math.tan(h.lat * RAD);
    const lonOf = (ra) => ((Math.atan2(Math.sin(ra * RAD), Math.cos(ra * RAD) * Math.cos(e)) / RAD) % 360 + 360) % 360;
    const cusp = (f, upper) => {
      let ra = upper ? ramc + 90 * f : ramc + 180 - 90 * f;
      for (let i = 0; i < 30; i++) {
        const x = tp * Math.tan(Math.asin(Math.sin(e) * Math.sin(lonOf(ra) * RAD)));
        if (Math.abs(x) >= 1) return null;
        const ad = Math.asin(x) / RAD;
        ra = upper ? ramc + f * (90 + ad) : ramc + 180 - f * (90 - ad);
      }
      return lonOf(ra);
    };
    const c = [ascLon(h, t), cusp(2 / 3, false), cusp(1 / 3, false), null, null, null, null, null, null, lonOf(ramc), cusp(1 / 3, true), cusp(2 / 3, true)];
    if (c.some((v, k) => v === null && (k < 3 || k > 8))) return null;
    for (let k = 3; k < 9; k++) c[k] = (c[(k + 6) % 12] + 180) % 360;
    return c;
  };
  const outLine = (g, ra) => {                     // Systems: a line from Ea out past the rings, its arrow head outside (as As's)
    const R = D.outer * D.fit, cx = D.width / 2, cy = D.height / 2, a = ra * RAD, out = sysRings.length ? sysRings[sysRings.length - 1].r1 : R;
    const side = (r, w) => [cx + MX * (r * Math.cos(a) - w * Math.sin(a)), cy - r * Math.sin(a) - w * Math.cos(a)].map((v) => v.toFixed(1)).join(" ");
    g.e.setAttribute("d", "M" + cx + " " + cy + "L" + side(out + 1, 0));
    g.head.setAttribute("d", "M" + side(out + 11, 0) + "L" + side(out + 1, 4) + "L" + side(out + 1, -4) + "Z");
  };
  const lonRA = (lon) => ((Math.atan2(Math.sin(lon * RAD) * Math.cos(D.tilt * RAD), Math.cos(lon * RAD)) / RAD) % 360 + 360) % 360;
  const raDecLon = (ra, dec) => {                  // the ecliptic longitude (Tropical) of a place given by its RA and Dec
    const a = ra * RAD, d = dec * RAD, e = D.tilt * RAD;
    return ((Math.atan2(Math.sin(a) * Math.cos(e) + Math.tan(d) * Math.sin(e), Math.cos(a)) / RAD) % 360 + 360) % 360;
  };
  const kpLords = (lon) => {                       // KP: where an ecliptic longitude falls: its sub lord
    if (!D.kp) return "";
    const sid = ((lon - D.kp.ayanamsa) % 360 + 360) % 360, v = D.kp.stars[Math.min(26, Math.floor(sid / (360 / 27)))];
    const u = v.subs.find((x) => sid >= x.sid0 && sid < x.sid1) || v.subs[8];
    return "\nKP: sub lord " + symbolOf(u.lord);   // (its sub lord alone: the sign and star are on the other lines)
  };
  const systemsInfo = (lon) => {                   // Systems: where an ecliptic longitude falls in each system shown, a line each
    let out = "";
    (D.zodiac || []).forEach((ring) => {           // Tr, Si, Op: its sign (or constellation), how far into it, and its lord
      const z = ring.find((x) => (x.lon1 > x.lon0 ? lon >= x.lon0 && lon < x.lon1 : lon >= x.lon0 || lon < x.lon1)) || ring[0];
      out += "\n" + z.tag + ": " + z.name + " " + (((lon - z.lon0) % 360 + 360) % 360).toFixed(1) + (z.lord ? ", lord " + symbolOf(z.lord) : "");
    });
    if (D.vedic && D.vedic.length) {               // Na: its star, the star's lord, and the quarter
      const sid = ((lon - D.vedic[0].ayanamsa) % 360 + 360) % 360, v = D.vedic[Math.min(26, Math.floor(sid / (360 / 27)))];
      out += "\nNa: " + v.name + ", quarter " + (Math.floor((sid - v.sid0) / (360 / 108)) + 1) + ", star lord " + symbolOf(v.lord);   // (its lord last)
    }
    return out + kpLords(lon);                     // KP: its sub lord
  };
  if (D.flat) {
    const R = D.outer * D.fit, cx = D.width / 2, cy = D.height / 2;
    let ticks = "";
    for (let ra = 1; ra !== 361; ra++) {
      const a = ra * RAD, long = (ra % 10 === 0 ? 10 : ra % 5 === 0 ? 7 : 4) * (D.ra_inside ? -1 : 1);   // (Systems: inward)
      ticks += "M" + (cx + MX * R * Math.cos(a)).toFixed(1) + " " + (cy - R * Math.sin(a)).toFixed(1) +
               "L" + (cx + MX * (R + long) * Math.cos(a)).toFixed(1) + " " + (cy - (R + long) * Math.sin(a)).toFixed(1);
      if (ra % 10 === 0 && D.ra_values) {          // (Systems: only while Eq is on)
        const at = D.ra_inside ? R - 24 : R + 22;    // its number outside the circle and its ticks (Systems: inside them)
        const x = cx + MX * at * Math.cos(a), y = cy - at * Math.sin(a) + D.flat_font / 3;
        const n = words("rgb(90,90,90)", D.flat_font);
        n.setAttribute("x", x.toFixed(1)); n.setAttribute("y", y.toFixed(1)); n.textContent = ra;
        scaleBoxes.push(boxOf(x, y, String(ra), D.flat_font));
      }
    }
    const scale = make("path", svg, {d: ticks, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
    make("title", scale).textContent = "RA, 1 to 360 degrees";
    const tag = words("rgb(90,90,90)");            // what the scale is, below the clock
    tag.setAttribute("x", cx); tag.setAttribute("y", (cy + R + 56).toFixed(1)); tag.textContent = "RA";
    if (!D.ra_values) tag.style.display = "none";   // (Systems with Eq off: no RA numbers, nor their names)
    else if (D.ra_inside) {                        // Systems: Eq (the equator's scale), just above its 360, inside the circle
      const x = cx + MX * (R - 24), y = cy + D.flat_font / 3 - 16;
      tag.setAttribute("x", x.toFixed(1)); tag.setAttribute("y", y.toFixed(1)); tag.textContent = "Eq";
      scaleBoxes.push(boxOf(x, y, "Eq"));
      const ra = words("rgb(90,90,90)"), yb = cy + D.flat_font / 3 + 18;   // and RA just below it
      ra.setAttribute("x", x.toFixed(1)); ra.setAttribute("y", yb.toFixed(1)); ra.textContent = "RA";
      scaleBoxes.push(boxOf(x, yb, "RA"));
    }
    // Systems: the twelve signs (Tropical or Sidereal) in a ring just outside the circle, each over its RA span (fixed: it does not turn)
    const at = (r, ra) => [cx + MX * r * Math.cos(ra * RAD), cy - r * Math.sin(ra * RAD)];
    // Systems, Ec: the ecliptic longitude, 0 to 360 (Tropical), in a ring just outside the circle, each degree at the RA it
    // falls at (so not evenly spaced): a tick every degree, longer every 5 and 10, numbered every 10
    const EIN = R + 2, EOUT = R + D.ec_ring;         // (wide enough for the numbers, 180 lying across it at the sides)
    if (D.ecliptic.length) {
      sysRings.push({kind: "ec", r0: EIN, r1: EOUT});
      let eTicks = "";
      D.ecliptic.forEach((ra, lon) => {
        const long = lon % 10 === 0 ? 10 : lon % 5 === 0 ? 7 : 4, [x0, y0] = at(EIN, ra), [x1, y1] = at(EIN + long, ra);
        eTicks += "M" + x0.toFixed(1) + " " + y0.toFixed(1) + "L" + x1.toFixed(1) + " " + y1.toFixed(1);
        if (lon % 10 === 0) {
          const [x, y] = at(EIN + 23, ra), n = words("rgb(90,90,90)", D.flat_font);   // (between the ticks and the edge)
          n.setAttribute("x", x.toFixed(1)); n.setAttribute("y", (y + D.flat_font / 3).toFixed(1)); n.textContent = lon;
          scaleBoxes.push(boxOf(x, y + D.flat_font / 3, String(lon), D.flat_font));
        }
      });
      const eScale = make("path", svg, {d: eTicks, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
      make("title", eScale).textContent = "Ecliptic longitude (Tropical), 0 to 360 degrees, each at the RA it falls at";
      make("circle", svg, {cx, cy, r: EOUT, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
      // its name, Ec, just after its 0 (above it, as the numbers go), as Eq above the circle's 360
      const [ex, ey] = at(EIN + 23, D.ecliptic[0]), ecName = words("rgb(90,90,90)");
      ecName.setAttribute("x", ex.toFixed(1)); ecName.setAttribute("y", (ey + D.flat_font / 3 - 16).toFixed(1)); ecName.textContent = "Ec";
      scaleBoxes.push(boxOf(ex, ey + D.flat_font / 3 - 16, "Ec"));
      const lo = words("rgb(90,90,90)"), ly = ey + D.flat_font / 3 + 18;   // and Lg (longitude) just below its 0, as RA below 360
      lo.setAttribute("x", ex.toFixed(1)); lo.setAttribute("y", ly.toFixed(1)); lo.textContent = "Lg";
      scaleBoxes.push(boxOf(ex, ly, "Lg"));
    }
    // and the rings of signs outside it (or, without Ec, just outside the circle), one on another: Tr's, then Si's
    let ZIN = D.ecliptic.length ? EOUT + 2 : R + 4, ZOUT = ZIN + D.sign_ring;
    (D.zodiac || []).forEach((ring, k) => {
     if (k) { ZIN = ZOUT + 2; ZOUT = ZIN + D.sign_ring; }
     sysRings.push({kind: "signs", r0: ZIN, r1: ZOUT, ring});
     ring.forEach((z, i) => {
      const a1 = z.ra1 > z.ra0 + 1 ? z.ra1 : z.ra1 + 360, f = (p) => p[0].toFixed(1) + " " + p[1].toFixed(1);
      const d = "M" + f(at(ZOUT, z.ra0)) + "A" + ZOUT + " " + ZOUT + " 0 0 " + SWEEP + " " + f(at(ZOUT, a1)) +
                "L" + f(at(ZIN, a1)) + "A" + ZIN + " " + ZIN + " 0 0 " + (1 - SWEEP) + " " + f(at(ZIN, z.ra0)) + "Z";
      const sector = make("path", svg, {d, fill: i % 2 ? "rgb(244,244,244)" : "white", stroke: "rgb(120,120,120)", "stroke-width": 1, style: "pointer-events:auto"});
      const sectorTip = make("title", sector);
      sectorTip.textContent = z.name + (z.lord ? ", lord " + symbolOf(z.lord) : "") + " (" + z.kind + "; " + z.lon0 + " to " + z.lon1 + " degrees of Tropical ecliptic longitude): RA " + z.ra0.toFixed(2) + " to " + z.ra1.toFixed(2);
      // its symbol and its lord's (dark ink), side by side along the ring, inside it, two letters apart; the sign first as
      // seen: left of its lord, or above it where the ring runs up and down (the sides). Ophiuchus has no lord
      const zm = (ZIN + ZOUT) / 2, SW = 13, CH = 5.2, LR = 6, total = z.lord ? SW + 2 * CH + 2 * LR : SW;
      const tx = -MX * Math.sin(z.mid * RAD), ty = -Math.cos(z.mid * RAD);   // (the way the ring runs as RA grows, on the page)
      const zside = Math.abs(tx) > 0.3 ? Math.sign(tx) : Math.sign(ty) || 1;   // (so that the lord falls right of, or below, the sign)
      const zalong = (px) => z.mid + zside * px / zm / RAD;
      const [x, y] = at(zm, zalong(-total / 2 + SW / 2)), sign = words("rgb(60,60,60)", 15);
      sign.setAttribute("x", x.toFixed(1)); sign.setAttribute("y", (y + 5).toFixed(1)); sign.textContent = z.sym;
      sign.style.pointerEvents = "none";
      scaleBoxes.push(boxOf(x, y + 5, "XX", 15));
      if (z.lord) {
        const [lx, ly] = at(zm, zalong(total / 2 - LR));
        fitSymbol(symbolTag(svg, z.lord, "rgb(40,40,40)", true), lx, ly, LR);
        scaleBoxes.push([lx - LR, ly - LR, lx + LR, ly + LR]);
      }
      if ((D.asc || []).length) {                  // Ho: its whole-sign house, H01 the sign As is in, after its lord along the ring
        const HW = 9, need = total / 2 + 2 * CH + 2 * HW, half = ((z.ra1 - z.ra0 + 360) % 360) / 2 * RAD * zm - 2;
        let label = null;                          // (none where the sign is too narrow for it: point at the sign)
        if (need <= half) {
          const pos = zalong(total / 2 + 2 * CH + HW), [hx, hy] = at(zm, pos);
          let turn = ((MX * (90 - pos)) % 360 + 360) % 360;   // along the ring, never upside down
          if (turn > 90 && turn <= 270) turn -= 180; else if (turn > 270) turn -= 360;
          label = words(HOUSE_INK, 9);
          label.setAttribute("x", hx.toFixed(1)); label.setAttribute("y", (hy + 3).toFixed(1)); label.setAttribute("stroke-width", 2);
          label.setAttribute("transform", "rotate(" + turn.toFixed(1) + " " + hx.toFixed(1) + " " + hy.toFixed(1) + ")");
          label.style.pointerEvents = "none";
          scaleBoxes.push([hx - HW, hy - HW, hx + HW, hy + HW]);
        }
        signHouses.push({ring, i, label, tip: sectorTip, base: sectorTip.textContent, last: ""});
      }
      if (i === 0) {                               // Tr, Si or Op: its tag at the start of Aries, just inside the sign
        const name = z.tag;
        const [tx, ty] = at((ZIN + ZOUT) / 2, z.ra0 + 5), si = words("rgb(90,90,90)", D.flat_font);
        si.setAttribute("x", tx.toFixed(1)); si.setAttribute("y", (ty + D.flat_font / 3).toFixed(1)); si.textContent = name;
        si.style.pointerEvents = "none";
        scaleBoxes.push(boxOf(tx, ty + D.flat_font / 3, name, D.flat_font));
      }
     });
    });
    // Na: the 27 stars (nakshatras) in a ring outside the others, each named along the ring (two words on two lines),
    // never upside down
    const VIN = (D.zodiac.length ? ZOUT : D.ecliptic.length ? EOUT : R) + (D.zodiac.length || D.ecliptic.length ? 2 : 4), VOUT = VIN + D.vedic_ring;
    if (D.vedic.length) sysRings.push({kind: "na", r0: VIN, r1: VOUT, ring: D.vedic});
    D.vedic.forEach((v, i) => {
      const a1 = v.ra1 > v.ra0 + 1 ? v.ra1 : v.ra1 + 360, f = (p) => p[0].toFixed(1) + " " + p[1].toFixed(1);
      const d = "M" + f(at(VOUT, v.ra0)) + "A" + VOUT + " " + VOUT + " 0 0 " + SWEEP + " " + f(at(VOUT, a1)) +
                "L" + f(at(VIN, a1)) + "A" + VIN + " " + VIN + " 0 0 " + (1 - SWEEP) + " " + f(at(VIN, v.ra0)) + "Z";
      const sector = make("path", svg, {d, fill: i % 2 ? "rgb(240,236,226)" : "rgb(250,248,242)", stroke: "rgb(120,120,120)", "stroke-width": 1, style: "pointer-events:auto"});
      make("title", sector).textContent = v.name + " (Vedic star " + v.n + " of 27; Sidereal, Lahiri ayanamsa " + v.ayanamsa + ": " +
                                            v.sid0 + " to " + v.sid1 + " degrees, in four quarters of 3.33): RA " + v.ra0.toFixed(2) + " to " + v.ra1.toFixed(2) +
                                            ", star lord " + symbolOf(v.lord);   // (its lord last)
      let turn = ((MX * (90 - v.mid)) % 360 + 360) % 360;
      const flip = turn > 90 && turn <= 270;
      if (flip) turn -= 180; else if (turn > 270) turn -= 360;
      // its name on one line (P.Phalguni ..), and after it, as read, its star lord's symbol, in dark ink (no colour)
      // (CH: a letter's width, the gap; all of it made smaller, k, only when the star's span on the ring is too short for it)
      const mid = (VIN + VOUT) / 2, room = ((v.ra1 - v.ra0 + 360) % 360) * RAD * mid - 4;
      const k = Math.min(1, room / (v.short.length * 5.2 + 5.2 + 14)), CH = 5.2 * k, mr = 7 * k;
      const w = v.short.length * CH, total = w + CH + 2 * mr, side = (flip ? 1 : -1) * MX;
      const along = (px) => v.mid + side * px / mid / RAD;   // (so many pixels along the ring, the way the name reads)
      const [x, y] = at(mid, along(-total / 2 + w / 2)), t = words("rgb(60,60,60)", 9 * k);
      t.setAttribute("x", x.toFixed(1)); t.setAttribute("y", (y + 3).toFixed(1)); t.textContent = v.short;
      t.setAttribute("transform", "rotate(" + turn.toFixed(1) + " " + x.toFixed(1) + " " + y.toFixed(1) + ")");
      t.setAttribute("stroke-width", 2); t.style.pointerEvents = "none";
      const [lx, ly] = at(mid, along(total / 2 - mr));
      fitSymbol(symbolTag(svg, v.lord, "rgb(40,40,40)", true), lx, ly, Math.max(5, mr));   // (in the ink given; at least 5, to show)
      const [bx, by] = at(mid, v.mid);
      scaleBoxes.push([bx - 14, by - 14, bx + 14, by + 14]);
      // its four quarters (padas, 3 degrees 20 minutes each): a short tick at each one's start, on both edges of the ring
      let ticks = "";
      v.padas.forEach((ra) => [[VIN, VIN + 5], [VOUT - 5, VOUT]].forEach(([r0, r1]) => {
        const [x0, y0] = at(r0, ra), [x1, y1] = at(r1, ra);
        ticks += "M" + x0.toFixed(1) + " " + y0.toFixed(1) + "L" + x1.toFixed(1) + " " + y1.toFixed(1);
      }));
      make("path", svg, {d: ticks, fill: "none", stroke: "rgb(90,90,90)", "stroke-width": 1, style: "pointer-events:none"});
    });
    // KP: its ring outside all the others: the 27 stars' 243 subs, each in its sub lord's colour (planets' divisions inside
    // planets' divisions), a line at each star's start
    if (D.kp) {
      const edge = D.vedic.length ? VOUT : D.zodiac.length ? ZOUT : D.ecliptic.length ? EOUT : R;
      const KIN = edge + (edge === R ? 4 : 2), KSYM = KIN + D.kp_sub, KOUT = KIN + D.kp_ring;   // (colours, then symbols outside them)
      const LANES = [1, 3, 5].map((k) => KSYM + k * (KOUT - KSYM) / 6), SR = 5;   // the sub lords' symbols, in three lanes, one sub in each by turns
      let nth = 0;                                 // (so that a narrow sub's symbol has its neighbours' room too)
      const band = (r0, r1, ra0, ra1) => {         // an arc of a band, ra0 to ra1 (which may pass 360)
        const a1 = ra1 > ra0 ? ra1 : ra1 + 360, f = (p) => p[0].toFixed(1) + " " + p[1].toFixed(1), big = a1 - ra0 > 180 ? 1 : 0;
        return "M" + f(at(r1, ra0)) + "A" + r1 + " " + r1 + " 0 " + big + " " + SWEEP + " " + f(at(r1, a1)) +
               "L" + f(at(r0, a1)) + "A" + r0 + " " + r0 + " 0 " + big + " " + (1 - SWEEP) + " " + f(at(r0, ra0)) + "Z";
      };
      D.kp.stars.forEach((v, i) => {
        v.subs.forEach((u) => {
          const sub = make("path", svg, {d: band(KIN, KSYM, u.ra0, u.ra1), fill: u.colour, "fill-opacity": 0.6, stroke: "white", "stroke-width": 0.5, style: "pointer-events:auto"});
          make("title", sub).textContent = "Sub lord " + symbolOf(u.lord) + " in " + v.name + " (star lord " + symbolOf(v.lord) + "; KP ayanamsa " +
                                           D.kp.ayanamsa.toFixed(2) + "): " + u.sid0.toFixed(2) + " to " + u.sid1.toFixed(2) + " degrees Sidereal";
          const [sx, sy] = at(LANES[nth++ % 3], u.ra0 + ((u.ra1 - u.ra0 + 360) % 360) / 2);   // its sub lord's symbol, dark ink (three subs on, the same lane: room for each)
          fitSymbol(symbolTag(svg, u.lord, "rgb(40,40,40)", true), sx, sy, SR);
        });
        const [x0, y0] = at(KIN, v.ra0), [x1, y1] = at(KOUT, v.ra0);   // (each star's start: a line across the band)
        make("path", svg, {d: "M" + x0.toFixed(1) + " " + y0.toFixed(1) + "L" + x1.toFixed(1) + " " + y1.toFixed(1), stroke: "rgb(60,60,60)", "stroke-width": 1.5, style: "pointer-events:none"});
      });
      [KIN, KSYM, KOUT].forEach((r) => make("circle", svg, {cx, cy, r, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 0.5}));
      sysRings.push({kind: "kp", r0: KIN, r1: KOUT, kp: D.kp});
      if ((D.asc || []).length)                    // Ho: the twelve Placidus cusps (KP's houses), each a line across the ring, its name outside it
        kpHouses = {r0: KIN, r1: KOUT, cusps: [...Array(12).keys()].map((k) => {
          const e = make("path", svg, {fill: "none", stroke: HOUSE_INK, "stroke-width": 2.5, style: "pointer-events:stroke"});
          const label = words(HOUSE_INK, 9);
          label.setAttribute("stroke-width", 2); label.style.pointerEvents = "none"; label.textContent = "H" + String(k + 1).padStart(2, "0");
          return {k, e, tip: make("title", e), label};
        })};
    }
    if (D.ra_inside) {                             // Systems: the planets' lines over the rings (drawn since), the planets and the Earth over them
      rays.forEach((g) => svg.appendChild(g.e));
      houses.concat(ascHouses).forEach((g) => { if (g.e) { svg.appendChild(g.e); svg.appendChild(g.head); } });   // (Ho: the house lines too)
      ascs.forEach((g) => { svg.appendChild(g.e); svg.appendChild(g.head); svg.appendChild(g.name); });   // (once: moved in every frame, no tooltip would show)
      marks.forEach((g) => { svg.appendChild(g.e); svg.appendChild(g.label); });
      svg.appendChild(earth); svg.appendChild(earthLabel);
    }
    // the Declination graph, as tall as the circle: a tick every degree, longer every 5, numbered every 5 and at its ends
    let decTicks = "";
    for (let v = D.flat_dec[1]; v !== D.flat_dec[0] + 1; v++) {
      const long = v === 0 ? 10 : v % 5 === 0 ? 8 : 4, y = decY(v).toFixed(1);
      decTicks += "M" + DEC_X + " " + y + "L" + (DEC_X + long) + " " + y;
      if (v % 5 === 0 || v === D.flat_dec[0] || v === D.flat_dec[1]) {
        const n = words("rgb(90,90,90)", D.flat_font);
        n.setAttribute("text-anchor", "start"); n.setAttribute("x", DEC_X + 12); n.setAttribute("y", (decY(v) + D.flat_font / 3).toFixed(1)); n.textContent = (v > 0 ? "+" : "") + v;
      }
    }
    const decScale = make("path", svg, {d: "M" + DEC_X + " " + decY(D.flat_dec[0]).toFixed(1) + "V" + decY(D.flat_dec[1]).toFixed(1) + decTicks, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
    make("title", decScale).textContent = "Declination, " + D.flat_dec[1] + " to +" + D.flat_dec[0] + " degrees";
    const decTag = words("rgb(90,90,90)");
    decTag.setAttribute("x", DEC_X); decTag.setAttribute("y", (cy + R + 56).toFixed(1)); decTag.textContent = "Declination";
    if (D.lat_bar) {                               // Systems: the Ecliptic latitude graph, as tall as the circle: a tick every
      let latTicks = "";                           // degree, longer every 5, numbered every 2 (left of its line)
      for (let v = -LAT_MAX; v !== LAT_MAX + 1; v++) {
        const long = v === 0 ? 10 : v % 5 === 0 ? 8 : 4, y = latY(v).toFixed(1);
        latTicks += "M" + LAT_X + " " + y + "L" + (LAT_X - long) + " " + y;
        if (v % 2 === 0) {
          const n = words("rgb(90,90,90)", D.flat_font);
          n.setAttribute("text-anchor", "end"); n.setAttribute("x", LAT_X - 12); n.setAttribute("y", (latY(v) + D.flat_font / 3).toFixed(1)); n.textContent = (v > 0 ? "+" : "") + v;
        }
      }
      const latScale = make("path", svg, {d: "M" + LAT_X + " " + latY(LAT_MAX).toFixed(1) + "V" + latY(-LAT_MAX).toFixed(1) + latTicks, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
      make("title", latScale).textContent = "Ecliptic latitude, -" + LAT_MAX + " to +" + LAT_MAX + " degrees: north (+) or south (-) of the ecliptic";
      const latTag = words("rgb(90,90,90)");
      latTag.setAttribute("x", LAT_X); latTag.setAttribute("y", (cy + R + 56).toFixed(1)); latTag.textContent = "Ecliptic latitude";
    }
    if (D.dist) {                                  // (not on Systems: no Distance(%) graph, nor its AU scale)
    // the Distance(%) graph, as tall as the circle: 100 (farthest) at the top, a tick every 1, longer every 5, numbered every 5
    let distTicks = "";
    for (let v = 0; v !== 101; v++) {
      const long = v % 10 === 0 ? 10 : v % 5 === 0 ? 8 : 4, y = distY(v).toFixed(1);
      distTicks += "M" + DIST_X + " " + y + "L" + (DIST_X + long) + " " + y;
      if (v % 5 === 0) {
        const n = words("rgb(90,90,90)", D.flat_font);
        n.setAttribute("text-anchor", "start"); n.setAttribute("x", DIST_X + 12); n.setAttribute("y", (distY(v) + D.flat_font / 3).toFixed(1)); n.textContent = v;   // (between DOB's planets and Now's)
      }
    }
    const distScale = make("path", svg, {d: "M" + DIST_X + " " + distY(100).toFixed(1) + "V" + distY(0).toFixed(1) + distTicks, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
    make("title", distScale).textContent = "Distance(%) from earth, 0 nearest to 100 farthest: the planets at the time picked, then Average, to the right";
    const distTag = words("rgb(90,90,90)");
    distTag.setAttribute("text-anchor", "start");   // (above its columns' names: from DOB's or Now's front to Ave's back)
    distTag.setAttribute("y", (cy + R + 39).toFixed(1)); distTag.textContent = "Distance(%)";
    distTag.setAttribute("x", DIST_X + 12);         // (the bar's numbers' left, as its 0)
    if (distMarks.length) {                        // the AU scale, left of the bar: a tick at each mark, numbered left of the planets
      let auTicks = "";
      AU_MARKS.forEach((v) => {
        const y = auY(v);
        auTicks += "M" + DIST_X + " " + y.toFixed(1) + "L" + (DIST_X - 6) + " " + y.toFixed(1);
        const n = words("rgb(90,90,90)", D.flat_font);
        n.setAttribute("text-anchor", "end"); n.setAttribute("x", DIST_X - AU_NUM); n.setAttribute("y", (y + D.flat_font / 3).toFixed(1)); n.textContent = v;
      });
      const auScale = make("path", svg, {d: auTicks, fill: "none", stroke: "rgb(120,120,120)", "stroke-width": 1});
      make("title", auScale).textContent = "Distance from earth in AU (not to scale: its marks evenly spaced): the planets at the time picked, to the left";
      const auName = words("rgb(90,90,90)");
      auName.setAttribute("x", DIST_X - DIST_AU / 2); auName.setAttribute("y", (cy + R + 56).toFixed(1)); auName.textContent = "AU";   // (on the line of De and RA)
    }
    const sides = [...distClocks, "Ave"].filter((name) => name !== "Ave" || aveMarks.length).map((name, i) => {   // which column is which, below that tag
      const x = i === 0 ? DIST_X + 12 : distCol(name);   // (the first, DOB or Now, and so Distance(%) above it: from the bar's numbers' left, as its 0)
      const side = words("rgb(90,90,90)");
      if (i === 0) side.setAttribute("text-anchor", "start");
      side.setAttribute("x", x); side.setAttribute("y", (cy + R + 56).toFixed(1)); side.textContent = name === "Ave" ? "Average" : name;   // (on the line of De and RA)
      return side;
    });
    if (sides.length && sides[0].getBBox) {         // Distance(%): its front over DOB's or Now's front, its back over Ave's back
      const front = sides[0].getBBox(), back = sides[sides.length - 1].getBBox();
      distTag.setAttribute("x", front.x.toFixed(1));
      if (sides.length > 1) {
        distTag.setAttribute("textLength", (back.x + back.width - front.x).toFixed(1));
        distTag.setAttribute("lengthAdjust", "spacing");
      }
    }
    }
  }
  const clear = (a, taken) => taken.every((b) => a[2] < b[0] || b[2] < a[0] || a[3] < b[1] || b[3] < a[1]);
  const inside = (a) => a[0] > D.view[0] && a[1] > D.view[1] && a[2] < D.view[0] + D.view[2] && a[3] < D.view[1] + D.view[3];
  const put = (label, spots, taken) => {           // its last place while that stays free, else the first free near it; left off if none
    const text = label.textContent;
    const free = (i) => {
      const [x, y] = spots[i], a = boxOf(x, y, text, +label.getAttribute("font-size"));
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
  else if (clock.trailFrom === null || clock.trailFrom === undefined || (D.reverse ? clock.trailFrom < clock.t : clock.trailFrom > clock.t)) clock.trailFrom = clock.t;
  let trailFrom = D.day_seconds ? clock.trailFrom : null;
  const trail = (p, t) => {                        // where the body has really been since time started running
    const times = [], run = trailFrom === null ? 0 : Math.abs(t - trailFrom), way = t >= (trailFrom || 0) ? 1 : -1;   // (R: back in time)
    let gap = p.days / p.steps;
    while (run / gap > TRAIL_MOST) gap *= 2;         // (by doubling, so that the points stay where they were as it grows)
    for (let n = 0; n * gap < run; n++) times.push(trailFrom + way * n * gap);
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
    spokes.forEach((g) => g.draw(D.show_celes ? [[0, 0, 0], g.m.at] : []));   // CM: the RA spokes
    // the axis reaches, both ways, past where a 20 AU ring would be drawn on the page (round the centre, on the plane of the
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
    if (!D.flat) {
      const length = Math.max(pageLength(1, 1), ringAcross(1) + D.scp_past, ringAcross(-1) + D.scp_past);
      poles[0].at = [0, 0, reachFor(1, length) * D.outer];
      poles[1].at = [0, 0, -reachFor(-1, length) * D.outer];
      axis(D.show_celes ? [poles[1].at, poles[0].at] : []);   // CM: the axis
    }
    const t = clock.t;
    paths.forEach((g) => {
      trail(g.p, t);
      g.draw(g.p.pts, g.p.tip);
    });
    const states = marks.map((g) => posAt(g.m.clock, g.m.name, t).s);
    const inSpace = (s) => {                         // a body's place in space (AU), from its RA, De and distance
      const ra = s.ra * Math.PI / 180, dec = s.dec * Math.PI / 180;
      return [s.dist * Math.cos(dec) * Math.cos(ra), s.dist * Math.cos(dec) * Math.sin(ra), s.dist * Math.sin(dec)];
    };
    const node = (n) => n === "NN" || n === "SN";
    const apart = (i) => {                           // Geo/Helio: how far it is from each other body of the same moment, in AU
      if (D.flat || node(marks[i].m.name)) return "";
      const here = inSpace(states[i]);
      const lines = marks.map((o, j) => {
        if (j === i || o.m.clock !== marks[i].m.clock || node(o.m.name)) return null;
        const there = inSpace(states[j]);
        return "\n  " + symbolOf(o.m.name) + ": " + Math.hypot(here[0] - there[0], here[1] - there[1], here[2] - there[2]).toPrecision(4) + " AU";
      }).filter(Boolean);
      return lines.length ? "\nDistance to the others:" + lines.join("") : "";
    };
    const placed = marks.map((g, i) => {
      const {s, p: at} = posAt(g.m.clock, g.m.name, t), [x, y, z] = point(at);
      // sized by how wide it looks from the Earth then, on Equatorial-3D's logarithmic scale (to true scale the planets would not show)
      const seen = sizing(g.m.clock)[g.m.name], r = radiusAt(g.m.rule, sizing(g.m.clock), t);
      const arcsec = seen && seen.km ? arcsecOf(seen.km, sample(seen, t).dist) : null;   // how big it looks from the Earth (not for the Earth itself)
      const size = arcsec === null ? "" : "\nAngular Size: " + (arcsec >= 60 ? (arcsec / 60).toFixed(1) + " arcmin" : arcsec.toFixed(1) + " arcsec");
      g.e.setAttribute("r", r.toFixed(1));
      g.tip.textContent = symbolOf(g.m.name) + " " + g.m.clock + "\nDec/Lati: " + signed(s.dec) + "\nRA: " + s.ra.toFixed(2) +
        (D.ra_inside ? "\nEcliptic longitude: " + raDecLon(s.ra, s.dec).toFixed(2) : "") + size +   // (Systems: below RA, Tropical)
        "\nDistance from " + fromWord(g.m.name) + ": " + s.dist.toPrecision(4) + " AU" +
        (D.around && g.m.name === "Mo" ? "\n(drawn round the Earth, farther out than to scale)" : "") +
        (g.m.name === "NN" || g.m.name === "SN" ? "\n(on the Moon's path: at the Moon's distance)" : "") + apart(i) +
        systemsInfo(raDecLon(s.ra, s.dec));         // (Systems: where it falls in each system shown, with its lords)
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      g.e.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      g.label.setAttribute("opacity", z >= 0 ? 1 : 0.6);
      fitSymbol(g.label, x, y, r);
      return {g, x, y, z, r, ra: s.ra};
    }).sort((a, b) => b.r - a.r || a.z - b.z);       // the biggest first, so that a small planet is drawn over a big one
    // the Declination graph, each mark sized as on the clock, all in one column on lines of one length: marks at the same
    // De overlap, which shows a possible conjunction
    decMarks.forEach((g) => {
      const s = posAt(g.m.clock, g.m.name, t).s, r = radiusAt(g.m.rule, sizing(g.m.clock), t);
      const y = decY(Math.max(D.flat_dec[1], Math.min(D.flat_dec[0], s.dec))), x = DEC_X - DEC_LEAD;
      g.e.setAttribute("r", r.toFixed(1));
      g.lead.setAttribute("d", "M" + x.toFixed(1) + " " + y.toFixed(1) + "H" + DEC_X);
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      fitSymbol(g.label, x, y, r);
      g.tip.textContent = symbolOf(g.m.name) + " " + g.m.clock + "\nDec: " + signed(s.dec);
    });
    // Systems: the Ecliptic latitude graph, the same way: marks at the same latitude overlap
    latMarks.forEach((g) => {
      const s = posAt(g.m.clock, g.m.name, t).s, r = radiusAt(g.m.rule, sizing(g.m.clock), t), b = eclipticLat(s);
      const y = latY(Math.max(-LAT_MAX, Math.min(LAT_MAX, b))), x = LAT_X + LAT_LEAD;
      g.e.setAttribute("r", r.toFixed(1));
      g.lead.setAttribute("d", "M" + LAT_X + " " + y.toFixed(1) + "H" + x.toFixed(1));
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      fitSymbol(g.label, x, y, r);
      g.tip.textContent = symbolOf(g.m.name) + " " + g.m.clock + "\nEcliptic latitude: " + signed(b);
    });
    // the Distance(%) graph, the same way: marks at the same distance overlap
    distMarks.forEach((g) => {
      const s = posAt(g.m.clock, g.m.name, t).s, r = radiusAt(g.m.rule, sizing(g.m.clock), t), [lo, hi] = D.dist_range[g.m.name];
      const pct = Math.max(0, Math.min(100, (s.dist - lo) / (hi - lo) * 100)), y = distY(pct), x = distCol(g.m.clock);
      g.e.setAttribute("r", r.toFixed(1));
      g.lead.setAttribute("d", "M" + x.toFixed(1) + " " + y.toFixed(1) + "H" + DIST_X);
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      fitSymbol(g.label, x, y, r);
      g.tip.textContent = symbolOf(g.m.name) + " " + g.m.clock + "\nDistance(%) from earth: " + pct.toFixed(1) + "\nDistance from earth: " + s.dist.toPrecision(4) + " AU";
      g.auTip.textContent = g.tip.textContent;
      const ax = DIST_X - DIST_AU, ay = auY(s.dist);   // left of the bar: at its AU on the scale, moving as time runs
      g.auE.setAttribute("r", r.toFixed(1)); g.auE.setAttribute("cx", ax.toFixed(1)); g.auE.setAttribute("cy", ay.toFixed(1));
      g.auLead.setAttribute("d", "M" + ax.toFixed(1) + " " + ay.toFixed(1) + "H" + DIST_X);
      fitSymbol(g.auLabel, ax, ay, r);
    });
    aveMarks.forEach((g) => {
      const pct = avePct(g.m.name, t), r = aveRadius(g.m.rule, t), y = distY(pct), x = distCol("Ave");
      g.e.setAttribute("r", r.toFixed(1));
      g.lead.setAttribute("d", "M" + x.toFixed(1) + " " + y.toFixed(1) + "H" + DIST_X);
      g.e.setAttribute("cx", x.toFixed(1)); g.e.setAttribute("cy", y.toFixed(1));
      fitSymbol(g.label, x, y, r);
      g.tip.textContent = symbolOf(g.m.name) + " Average\nDistance(%) from earth: " + pct.toFixed(1);
    });
    [decMarks, latMarks, distMarks, aveMarks].forEach((list) => {   // on each graph too, the smallest on top (only when that changes, as below)
      const order = [...list].sort((a, b) => b.e.getAttribute("r") - a.e.getAttribute("r"));
      const stack = order.map((g) => g.m.name + g.m.clock).join();
      if (stack !== list.stack) { order.forEach((g) => { svg.appendChild(g.e); svg.appendChild(g.label); if (g.auE) { svg.appendChild(g.auE); svg.appendChild(g.auLabel); } }); list.stack = stack; }
    });
    rays.forEach((g) => {
      // (Systems: on through the rings round the circle, to the outermost's edge)
      const q = placed.find((p) => p.g.m === g.m), R = sysRings.length ? sysRings[sysRings.length - 1].r1 : D.outer * D.fit, a = q.ra * RAD;
      const at = (r, side) => (D.width / 2 + MX * (r * Math.cos(a) - side * Math.sin(a))).toFixed(1) + " " + (D.height / 2 - r * Math.sin(a) - side * Math.cos(a)).toFixed(1);
      if (D.ra_inside) {                           // Systems: the line out to the outermost ring, its arrow head on top of it (outside)
        g.e.setAttribute("d", "M" + at(0, 0) + "L" + at(R + 1, 0));
        g.head.setAttribute("d", "M" + at(R + 11, 0) + "L" + at(R + 1, 4) + "L" + at(R + 1, -4) + "Z");
      } else {
        g.e.setAttribute("d", "M" + at(0, 0) + "L" + at(R - 8, 0));        // to the arrow head's base
        g.head.setAttribute("d", "M" + at(R, 0) + "L" + at(R - 10, 4) + "L" + at(R - 10, -4) + "Z");
      }
      g.tip.textContent = symbolOf(g.m.name) + " " + g.m.clock + ": RA " + q.ra.toFixed(2);
    });
    nodeLines.forEach((g) => {
      const [n, s] = ["NN", "SN"].map((name) => placed.find((q) => q.g.m.clock === g.c && q.g.m.name === name));
      g.e.setAttribute("d", "M" + n.x.toFixed(1) + " " + n.y.toFixed(1) + "L" + s.x.toFixed(1) + " " + s.y.toFixed(1));
    });
    const [ex, ey] = point([0, 0, 0]), earthR = radiusAt(D.centre_rule, sizing(D.centre_clock), t);
    earth.setAttribute("r", earthR.toFixed(1));
    fitSymbol(earthLabel, ex, ey, earthR);
    earth.setAttribute("cx", ex.toFixed(1)); earth.setAttribute("cy", ey.toFixed(1));
    // the smallest on top, then what is nearest (only when that changes: moving a mark would lose its hover box);
    // every label kept off every mark and every other label
    const stack = placed.map((q) => q.g.m.name + q.g.m.clock).join();
    if (stack !== lastStack) {
      placed.forEach((q) => { svg.appendChild(q.g.e); svg.appendChild(q.g.label); });
      lastStack = stack;
    }
    const taken = placed.map((q) => [q.x - q.r - 2, q.y - q.r - 2, q.x + q.r + 2, q.y + q.r + 2]).concat([[ex - earthR - 1, ey - earthR - 1, ex + earthR + 1, ey + earthR + 1]], scaleBoxes);
    aspectLines.forEach((l) => {                   // straight between the two; its tag, as 0-Ma-Ju, in the first free place along it
      const [a, b] = [l.p, l.q].map((n) => placed.find((q) => q.g.m.clock === l.c && q.g.m.name === n));
      const on = D.aspects.filter((d) => inAspect(d.angle, posAt(l.c, l.p, t).s, posAt(l.c, l.q, t).s, d.orbs[l.p + "|" + l.q], d.dec_orbs[l.p + "|" + l.q]));
      l.tag.style.display = "none";
      if (!on.length) { l.e.setAttribute("d", ""); return; }
      l.e.setAttribute("d", "M" + a.x.toFixed(1) + " " + a.y.toFixed(1) + "L" + b.x.toFixed(1) + " " + b.y.toFixed(1));
      l.e.setAttribute("stroke", on[0].colour); l.e.setAttribute("stroke-width", on[0].width);
      l.tip.textContent = on.map((d) => d.angle + "-" + symbolOf(l.p) + "-" + symbolOf(l.q) + " " + l.c).join(", ");
      const text = on[0].angle + "-" + symbolOf(l.p) + "-" + symbolOf(l.q);
      l.tag.textContent = text; l.tag.setAttribute("fill", on[0].colour);
      const had = l.tagAt === undefined ? 0.5 : l.tagAt;
      const putTag = (x, y, box) => {
        l.tag.setAttribute("x", x.toFixed(1)); l.tag.setAttribute("y", y.toFixed(1));
        l.tag.style.display = ""; taken.push(box);
      };
      for (const f of [0.5, 0.35, 0.65, 0.2, 0.8].sort((u, v) => Math.abs(u - had) - Math.abs(v - had))) {
        const x = a.x + (b.x - a.x) * f, y = a.y + (b.y - a.y) * f + 4, box = boxOf(x, y, text);
        if (inside(box) && clear(box, taken)) { putTag(x, y, box); l.tagAt = f; return; }
      }
      // no room along it (two planets close together, as in a conjunction): the nearest free place beside its middle,
      // outward from the Earth first, so that the tag stays by the two planets
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, out = Math.atan2(my - D.height / 2, mx - D.width / 2);
      for (let r = Math.max(a.r, b.r) + 12; r <= 90; r += 8) {
        for (const k of [0, 1, -1, 2, -2, 3, -3, 4]) {
          const ang = out + k * Math.PI / 4, x = mx + r * Math.cos(ang), y = my + r * Math.sin(ang) + 4, box = boxOf(x, y, text);
          if (inside(box) && clear(box, taken)) { putTag(x, y, box); return; }
        }
      }
    });
    ascs.forEach((g) => {                          // As: each place's Ascendant, from inside the circle out across the rings
      const R = D.outer * D.fit, cx = D.width / 2, cy = D.height / 2, lon = ascLon(g.h, t), ra = lonRA(lon), a = ra * RAD;
      const out = sysRings.length ? sysRings[sysRings.length - 1].r1 : R;
      const pt = (r, da) => [cx + MX * r * Math.cos(a + (da || 0) * RAD), cy - r * Math.sin(a + (da || 0) * RAD)];
      const [x0, y0] = pt(0), [x1, y1] = pt(out + 1);   // (from the Earth, Ea, in the middle, to the outermost ring)
      g.e.setAttribute("d", "M" + x0.toFixed(1) + " " + y0.toFixed(1) + "L" + x1.toFixed(1) + " " + y1.toFixed(1));
      const side = (r, w) => [cx + MX * (r * Math.cos(a) - w * Math.sin(a)), cy - r * Math.sin(a) - w * Math.cos(a)].map((v) => v.toFixed(1)).join(" ");
      g.head.setAttribute("d", "M" + side(out + 11, 0) + "L" + side(out + 1, 4) + "L" + side(out + 1, -4) + "Z");   // its arrow head, outside (as the planets' have)
      g.tip.textContent = "As " + symbolOf(g.h.place) + " (" + g.h.clock + "): Ascendant\nRA: " + ra.toFixed(2) +   // (each on its line, as the planets')
                          "\nEcliptic longitude: " + lon.toFixed(2) + systemsInfo(lon);
      g.headTip.textContent = g.nameTip.textContent = g.tip.textContent;
      const [nx, ny] = pt(R - 52);
      g.name.setAttribute("x", nx.toFixed(1)); g.name.setAttribute("y", (ny + D.flat_font / 3).toFixed(1));
    });
    if (signHouses.length) {                       // Ho: whole-sign houses, Tr, Si and Op each its own: H01 the sign As is in
      const lon = ascLon(D.asc[0], t), within = (x) => (x.lon1 > x.lon0 ? lon >= x.lon0 && lon < x.lon1 : lon >= x.lon0 || lon < x.lon1);
      signHouses.forEach((g) => {
        const n = g.ring.length, first = Math.max(0, g.ring.findIndex(within)), name = "H" + String((g.i - first + n) % n + 1).padStart(2, "0");
        if (name === g.last) return;               // (set only when it changes: so its tooltip stays)
        g.last = name;
        if (g.label) g.label.textContent = name;
        g.tip.textContent = g.base + "\nWhole-sign house " + name + " (H01: the sign the Ascendant is in)";
      });
    }
    if (kpHouses) {                                // Ho with KP: the Placidus cusps (KP's houses), from the first place's sidereal time
      const cusps = placidus(D.asc[0], t), R = D.outer * D.fit, cx = D.width / 2, cy = D.height / 2;
      kpHouses.cusps.forEach((g) => {
        const lon = cusps && cusps[g.k];
        g.e.style.display = g.label.style.display = lon === null || lon === undefined ? "none" : "";   // (none past the polar circles)
        if (g.e.style.display) return;
        const a = lonRA(lon) * RAD, p = (r, b) => [cx + MX * r * Math.cos(b), cy - r * Math.sin(b)].map((v) => v.toFixed(1)).join(" ");
        g.e.setAttribute("d", "M" + p(kpHouses.r0, a) + "L" + p(kpHouses.r1 + 4, a));
        const next = cusps[(g.k + 1) % 12], mid = lonRA((lon + ((next - lon + 360) % 360) / 2) % 360), r = kpHouses.r1 + 11;
        const [x, y] = [cx + MX * r * Math.cos(mid * RAD), cy - r * Math.sin(mid * RAD)];   // its name outside the ring, mid-house
        let turn = ((MX * (90 - mid)) % 360 + 360) % 360;
        if (turn > 90 && turn <= 270) turn -= 180; else if (turn > 270) turn -= 360;
        g.label.setAttribute("x", x.toFixed(1)); g.label.setAttribute("y", (y + 3).toFixed(1));
        g.label.setAttribute("transform", "rotate(" + turn.toFixed(1) + " " + x.toFixed(1) + " " + y.toFixed(1) + ")");
        g.tip.textContent = "H" + String(g.k + 1).padStart(2, "0") + " " + symbolOf(D.asc[0].place) + " (" + D.asc[0].clock +
                            "): Placidus cusp (KP's houses), ecliptic longitude " + lon.toFixed(2) + systemsInfo(lon);
      });
    }
    ascHouses.forEach((g) => {                     // As's equal houses: each cusp 30 degrees of ecliptic longitude on from the last
      const R = D.outer * D.fit, cx = D.width / 2, cy = D.height / 2, lon0 = (ascLon(g.h, t) + 30 * g.k) % 360, ra = lonRA(lon0), a = ra * RAD;
      const tip = g.name + " " + symbolOf(g.h.place) + " (" + g.h.clock + "): equal house of 30 degrees from the Ascendant, ecliptic longitude " +
                  lon0.toFixed(2) + " to " + ((lon0 + 30) % 360).toFixed(2) + systemsInfo(lon0);
      if (g.e) {
        outLine(g, ra);
        g.tip.textContent = tip;
      }
      g.labelTip.textContent = tip;
      // its name in the middle of the house (15 degrees of longitude on from its cusp), inside the Eq houses' names; where
      // that is taken, nearer the Earth
      const mid = lonRA((lon0 + 15) % 360), half = g.name.length * 4 * D.flat_font / 13 + 3, r0 = R - (g.n ? 128 : 104);
      let spot = null;
      for (const r of [r0, r0 - 28, r0 - 56, r0 - 84]) {
        const b = mid * RAD, x = cx + MX * r * Math.cos(b), y = cy - r * Math.sin(b), box = [x - half, y - half, x + half, y + half];
        if (clear(box, taken)) { spot = {x, y, box}; break; }
      }
      g.label.style.display = spot ? "" : "none";
      if (spot) {
        let turn = ((MX * (90 - mid)) % 360 + 360) % 360;   // along the circle, and never upside down
        if (turn > 90 && turn <= 270) turn -= 180; else if (turn > 270) turn -= 360;
        g.label.setAttribute("x", spot.x.toFixed(1)); g.label.setAttribute("y", (spot.y + D.flat_font / 3).toFixed(1));
        g.label.setAttribute("transform", "rotate(" + turn.toFixed(1) + " " + spot.x.toFixed(1) + " " + spot.y.toFixed(1) + ")");
        taken.push(spot.box);
      }
    });
    houses.forEach((g) => {                        // each from the Earth to the circle, named in the middle of its span where there is room
      const R = D.outer * D.fit, cx = D.width / 2, cy = D.height / 2, ra = (g.h.ra + D.spin * t + 30 * g.k) % 360, a = ra * RAD;
      if (g.head) outLine(g, ra);                  // (Systems: out past the rings, as As)
      else g.e.setAttribute("d", "M" + cx + " " + cy + "L" + (cx + MX * R * Math.cos(a)).toFixed(1) + " " + (cy - R * Math.sin(a)).toFixed(1));
      g.tip.textContent = g.name + " " + symbolOf(g.h.place) + " RA: " + ra.toFixed(2);
      // its name in the middle of its span, near the circle; where that is taken (a planet, an aspect's tag), the first free
      // spot elsewhere in the span (nearer the Earth, or toward either end of it), so that all twelve are shown, as on
      // Equatorial-3D; hidden only when the whole span is full
      // (Systems: on their own circle inside the RA numbers, R - 24, and their ticks, not among them)
      const half = g.name.length * 4 * D.flat_font / 13 + 3, r0 = D.ra_inside ? R - (g.n ? 72 : 48) : R - (g.n ? 48 : 26);
      let spot = null;
      for (const r of [r0, r0 - 28, r0 - 56, r0 - 84, r0 - 112]) {
        for (const off of [15, 9, 21, 5, 25]) {
          const b = (ra + off) * RAD, x = cx + MX * r * Math.cos(b), mid = cy - r * Math.sin(b), box = [x - half, mid - half, x + half, mid + half];
          if (clear(box, taken)) { spot = {x, mid, box, off}; break; }   // (room for it at any turn)
        }
        if (spot) break;
      }
      g.label.style.display = spot ? "" : "none";
      if (spot) {
        // along the circle, and never upside down
        let turn = ((MX * (90 - ra - spot.off)) % 360 + 360) % 360;
        if (turn > 90 && turn <= 270) turn -= 180; else if (turn > 270) turn -= 360;
        g.label.setAttribute("x", spot.x.toFixed(1)); g.label.setAttribute("y", (spot.mid + D.flat_font / 3).toFixed(1));
        g.label.setAttribute("transform", "rotate(" + turn.toFixed(1) + " " + spot.x.toFixed(1) + " " + spot.mid.toFixed(1) + ")");
        taken.push(spot.box);
      }
    });
    if (!D.show_celes) poles.concat(spokes).forEach((g) => { g.label.style.display = "none"; });   // CM off: no NCP, SCP, RA names
    else {
      poles.forEach((g) => {
        const [x, y] = point(g.at);
        put(g.label, around(x, y, 4, 12), taken);
      });
      spokes.forEach((g) => {
        const [x, y] = point(g.m.at);
        put(g.label, around(x, y, 2, 24), taken);
      });
    }
    if (D.show_tags) rings.forEach((g) => {        // AU: the rings' AU tags, on the side of the ring nearest the viewer
      if (D.flat) { g.label.style.display = "none"; return; }   // flat: the circle has no tag (its hover box says what it is)
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
      clock.t += (D.reverse ? -1 : 1) * (now - last) / 1000 / D.day_seconds;   // (R: back in time)
      last = now;
      if (clock.t >= D.days) clock.t = D.days;     // the tables' end, 36 years after the moment, or their start, 36 years
      if (clock.t <= 0) clock.t = 0;               // before it: time holds there (only RS puts the Timer back)
      draw();
    }, D.step_ms);
  }
  if (D.flat ? D.day_seconds : !D.manual) { svg.style.cursor = "default"; return; }
  let from = null, due = false;                    // Manual: time stands still, and dragging turns the drawing (flat, with no speed: moves time)
  svg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    from = [e.clientX, e.clientY];
    svg.setPointerCapture(e.pointerId);
    svg.style.cursor = "grabbing";
    e.preventDefault();
  });
  svg.addEventListener("pointermove", (e) => {
    if (!from) return;
    if (D.flat) clock.t = Math.max(0, Math.min(D.days, clock.t + (e.clientX - from[0]) * D.drag_days));   // right: later; left: back, as far as the start
    else {
      view.yaw += (e.clientX - from[0]) * 0.5;
      view.pitch = Math.max(-85, Math.min(85, view.pitch + (e.clientY - from[1]) * 0.5));
    }
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
               centre: str = "Ea", flat: bool = False, places: dict | None = None, ave_jds: dict | None = None,
               aspects: tuple = (), orbs: core.Orbs | None = None, one_circle: bool = False, show_celes: bool = True,
               reverse: bool = False, show_dist: bool = True, ra_inside: bool = False, zodiac: tuple = (), ecliptic: bool = False, vedic: float | None = None, thirteen: float | None = None, asc: dict | None = None, kp: float | None = None, ra_values: bool = True) -> str:
    """show_au (AU): the rings of distance and their AU tags; show_celes (CM): the celestial coordinates, the axis with NCP
    and SCP and the RA spokes with their names; show_dist (the flat page): the Distance(%) graph, with its AU scale (not on Systems); ra_inside (the flat page, Systems):
    the RA scale's ticks and numbers inside the circle, not outside it, and an Ecliptic latitude graph right of it; zodiac (the flat page, Systems): rings of the twelve
    signs outside the circle, one on another, each sign over its RA span: one ring per number, 0 Tropical, the ayanamsa
    Sidereal (none: no ring); ecliptic
    (Systems, Ec): a ring of ecliptic longitude, 0 to 360 (Tropical), at the RA each degree falls at, between the circle
    and the signs; thirteen (Systems, Op): the Julian day, for a ring of the 13 constellations on the ecliptic, after the
    signs (None: none); vedic (Systems, Na): the ayanamsa, for a ring of the 27 stars (nakshatras) outside the others (None: none).
    ra_values (Systems: Eq on): the RA scale's numbers, with Eq and RA by its 360 (off: its ticks alone).
    kp (Systems, KP): the KP ayanamsa, for a ring of the 27 stars and their subs outside all the others (None: none).
    asc (Systems, As): {"DOB" or "Now": (place, longitude, latitude)}: each place's Ascendant, a line across the rings
    with its value on each. ra_inside (Systems) also draws the circle as big as leaves room for those rings (systems_radius)."""
    uid = "space-" + uuid.uuid4().hex[:8]
    # the tables from RUN_HALF before each moment to RUN_HALF after it (the clock starts in their middle, at the moment, and
    # is kept as it is, R or not, running or not, until RS)
    moments = [(c, jd - RUN_HALF, o) for c, jd, o in moments]
    ave_jds = {c: jd - RUN_HALF for c, jd in ave_jds.items()} if ave_jds else ave_jds
    d = space_data(bodies, moments, scale, key, day_seconds, manual, show_au, with_paths, centre, flat, places, ave_jds,
                   aspects, orbs, one_circle, show_celes, reverse, asc)
    d |= {"dist": show_dist, "ra_inside": ra_inside, "lat_bar": ra_inside, "ra_values": ra_values, "zodiac": [zodiac_signs(a) for a in zodiac] + ([constellations(thirteen)] if thirteen is not None else []), "sign_ring": SIGN_RING, "ec_ring": EC_RING, "vedic_ring": VEDIC_RING,
          "vedic": nakshatras(vedic) if vedic is not None else [],
          "kp": kp_stars(kp) if kp is not None else None, "kp_ring": KP_RING, "kp_sub": KP_SUB,
          "ecliptic": [round(ecliptic_ra(lon), 3) for lon in range(360)] if ecliptic else []}
    if ra_inside:                                     # Systems: the circle as big as leaves room for its rings round it
        d["fit"] = systems_radius(ecliptic, len(zodiac) + (thirteen is not None), vedic is not None, kp is not None, bool(asc)) / d["outer"]
    data = json.dumps(d).replace("<", chr(92) + "u003c")
    return f'<div id="{uid}"></div><script>{_JS.replace("__SYMBOL_JS__", SYMBOL_JS).replace("__DATA__", data).replace("__ID__", uid)}</script>'
