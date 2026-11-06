"""Equatorial positions (RA / Dec only, no zodiac), distances, sidereal time and the aspect rules.

Ported from the Excel workbook's VBA (modSE, modTable, modMap, modMovement); the rules are the same:
an aspect at an angle holds when the RA separation is within the RA orb of the angle and the Dec is within the Dec
orb of equal (conjunction), mirrored (opposition) or either (every other angle). A pair's orb is the larger of
its two planets' orbs; a house point (CB, CN) takes the planet's.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from . import se

PLANETS = ["Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa"]          # Swiss Ephemeris numbers 0 .. 6
BUTTON_ORDER = ["Sa", "Ju", "Ma", "Ve", "Me", "Su", "Mo"]     # the order of the workbook's buttons and loops
PLANET_ID = {p: i for i, p in enumerate(PLANETS)}
AU_KM = 149597870.7

COLOURS = {"Sa": "rgb(255,0,0)", "Ju": "rgb(112,48,160)", "Ma": "rgb(255,165,0)", "Ve": "rgb(0,176,80)",
           "Me": "rgb(146,208,80)", "Su": "rgb(0,112,192)", "Mo": "rgb(0,176,240)", "CN": "rgb(192,0,128)",
           "CB": "rgb(0,0,0)"}

# geocentric minimum / maximum distance (km) over 1800-2400, as the workbook uses for D
DIST_RANGE = {"Su": (147079476.4, 152116857.5), "Mo": (356371.3, 406720.6), "Me": (82110762.7, 217176258.7),
              "Ve": (39514836.7, 259699120.3), "Ma": (55688407.5, 400407237.2), "Ju": (590130185.9, 966315582.2),
              "Sa": (1200835560.6, 1655050506.1)}

MAJOR = [0, 180, 90, 120, 60]
MINOR = [30, 45, 72, 135, 144, 150]
TAG = {0: "C-", 180: "O-", 90: "Q-", 120: "T-", 60: "S-"}


def colour(name: str) -> str:
    return COLOURS.get(name[:2], "rgb(0,0,0)")


def tag(angle: int) -> str:
    return TAG.get(angle, f"{angle}-")


def norm360(deg: float) -> float:
    return deg - 360.0 * math.floor(deg / 360.0)


# ---------------------------------------------------------------- time
def julday(y: int, m: int, d: int, hour_ut: float) -> float:
    return se.julday(y, m, d, hour_ut)


def jd_of_datetime(t: datetime) -> float:
    """Julian day (UT) of a datetime; naive = UT."""
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc).replace(tzinfo=None)
    return se.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600 + t.microsecond / 3.6e9)


def now_jd() -> float:
    return jd_of_datetime(datetime.now(timezone.utc))


def birth_jd(y: int, m: int, d: int, hr: int, mi: int, utc_offset: float) -> float:
    return se.julday(y, m, d, hr + mi / 60.0 - utc_offset)


def lst(jd_ut: float, lon: float) -> float:
    """Local apparent sidereal time in degrees, east-positive longitude."""
    return norm360(se.sidtime(jd_ut) * 15.0 + lon)


# ---------------------------------------------------------------- positions
@dataclass
class Pos:
    ra: float
    dec: float
    dist_au: float
    ra_speed: float
    dec_speed: float
    dist_speed: float


def position(label: str, jd_ut: float) -> Pos:
    x, err = se.calc_ut(jd_ut, PLANET_ID[label])
    if x is None:
        raise RuntimeError(f"Swiss Ephemeris: {err}")
    return Pos(x[0], x[1], x[2], x[3], x[4], x[5])


def distance_pct(label: str, dist_au: float) -> float | None:
    lo, hi = DIST_RANGE.get(label, (None, None))
    if lo is None:
        return None
    return round((dist_au * AU_KM - lo) / (hi - lo) * 100.0, 2)


def birth_points(jd_b: float, lat: float, lon: float) -> dict[str, tuple[float, float]]:
    """The planets at birth and house 10 (as "CB"), RA / Dec rounded to 0.01 as the workbook keeps them.
    CB: RA = the sidereal time at the birth place, Dec = its latitude."""
    pts = {}
    for p in BUTTON_ORDER:
        ps = position(p, jd_b)
        pts[p] = (round(ps.ra, 2), round(ps.dec, 2))
    pts["CB"] = (round(lst(jd_b, round(lon, 2)), 2), round(lat, 2))
    return pts


def now_points(jd_now: float) -> dict[str, tuple[float, float]]:
    out = {}
    for p in BUTTON_ORDER:
        ps = position(p, jd_now)
        out[p] = (ps.ra, ps.dec)
    return out


def ra_de_height(lat: float) -> float:
    """Where a Dec or latitude sits on the chart: 30S..30N take two thirds of the height."""
    if abs(lat) <= 30.0:
        return lat * 2.0
    return math.copysign(60.0 + (abs(lat) - 30.0) / 2.0, lat)


# ---------------------------------------------------------------- orbs
def start_orb(angle: float, is_dec: bool) -> float:
    if is_dec:
        return 1.0
    if angle in (0, 180):
        return 8.0
    if angle in (90, 120):
        return 6.0
    if angle == 60:
        return 4.0
    return 2.0


@dataclass
class Orbs:
    """The orb table: a row per aspect (Aspect, Angle, Su-RA .. Ju-RA, Su-De .. Ju-De)."""
    table: pd.DataFrame
    _lookup: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        for _, row in self.table.iterrows():
            try:
                ang = float(row["Angle"])
            except (TypeError, ValueError):
                continue
            for col in self.table.columns:
                c = str(col).strip()
                if len(c) == 5 and c[:2] in PLANET_ID and c[2:].upper() in ("-RA", "-DE"):
                    v = pd.to_numeric(row[col], errors="coerce")
                    if pd.notna(v) and v >= 0:
                        self._lookup[(ang, c[:2], c[2:].upper() == "-DE")] = float(v)

    def planet(self, angle: float, name: str, is_dec: bool) -> float:
        name = name[:-2] if name.endswith("-N") else name
        return self._lookup.get((float(angle), name, is_dec), -1.0)

    def pair(self, angle: float, n1: str, n2: str, is_dec: bool) -> float:
        o = max(self.planet(angle, n1, is_dec), self.planet(angle, n2, is_dec))
        return o if o >= 0 else start_orb(angle, is_dec)


def default_orb_table() -> pd.DataFrame:
    from pathlib import Path
    return pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "orbs_default.csv")


# ---------------------------------------------------------------- aspects among points
def _sep(r1: float, r2: float) -> float:
    s = abs(r1 - r2)
    return 360.0 - s if s > 180.0 else s


def hit(angle: int, p1: tuple[float, float], p2: tuple[float, float], ra_orb: float, de_orb: float) -> bool:
    sep = _sep(p1[0], p2[0])
    if angle == 0:
        return sep <= ra_orb and abs(p1[1] - p2[1]) <= de_orb
    if angle == 180:
        return abs(sep - 180.0) <= ra_orb and abs(p1[1] + p2[1]) <= de_orb
    return abs(sep - angle) <= ra_orb and (abs(p1[1] - p2[1]) <= de_orb or abs(p1[1] + p2[1]) <= de_orb)


@dataclass
class AspectLine:
    angle: int
    members: list[str]           # in title order (CB first, then nearest; else from the lowest RA)
    title: str                   # e.g. C-CB-Sa, O-Mo-Ju, 30-Sa-Ma; now ones end in -N
    xs: list[float]              # RA of each member, unwrapped so the line goes the short way
    ys: list[float]              # Dec of each member


def conjunctions(pts: dict[str, tuple[float, float]], orbs: Orbs, is_now: bool) -> list[AspectLine]:
    names = list(pts)
    grp = {n: i for i, n in enumerate(names)}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if hit(0, pts[a], pts[b], orbs.pair(0, a, b, False), orbs.pair(0, a, b, True)):
                old = grp[b]
                for n in names:
                    if grp[n] == old:
                        grp[n] = grp[a]
    out = []
    for g in sorted(set(grp.values())):
        mem = [n for n in names if grp[n] == g]
        if len(mem) < 2:
            continue
        x = {n: pts[n][0] for n in mem}
        if max(x.values()) - min(x.values()) > 180.0:
            x = {n: v + 360.0 if v < 180.0 else v for n, v in x.items()}
        if "CB" in mem:
            mem.sort(key=lambda n: -1.0 if n == "CB" else abs(x[n] - x["CB"]))
        else:
            mem.sort(key=lambda n: x[n])
        title = "C-" + "-".join(mem) + ("-N" if is_now else "")
        out.append(AspectLine(0, mem, title, [x[n] for n in mem], [pts[n][1] for n in mem]))
    return out


def pair_lines(pts: dict[str, tuple[float, float]], angle: int, orbs: Orbs, is_now: bool) -> list[AspectLine]:
    names = list(pts)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not hit(angle, pts[a], pts[b], orbs.pair(angle, a, b, False), orbs.pair(angle, a, b, True)):
                continue
            first, second = a, b
            if b == "CB" or (a != "CB" and pts[b][0] < pts[a][0]):
                first, second = b, a
            x0, x2 = pts[first][0], pts[second][0]
            if angle != 180:
                if x2 - x0 > 180.0:
                    x2 -= 360.0
                if x0 - x2 > 180.0:
                    x2 += 360.0
            title = tag(angle) + first + "-" + second + ("-N" if is_now else "")
            out.append(AspectLine(angle, [first, second], title, [x0, x2], [pts[first][1], pts[second][1]]))
    return out


def all_aspects(pts: dict[str, tuple[float, float]], orbs: Orbs, is_now: bool, major: bool = True,
                minor: bool = True) -> list[AspectLine]:
    out: list[AspectLine] = []
    if major:
        out += conjunctions(pts, orbs, is_now)
        for ang in (180, 90, 120, 60):
            out += pair_lines(pts, ang, orbs, is_now)
    if minor:
        for ang in MINOR:
            out += pair_lines(pts, ang, orbs, is_now)
    return out


# ---------------------------------------------------------------- the Range chart's rows and aspect events
MOVE_STEP_DAYS = 2.0
MOVE_MIN_ROWS = 300
MOON_STEP = 0.25


def range_rows(labels: list[str], jd_from: float, jd_to: float) -> pd.DataFrame:
    """Each planet's RA / Dec / D every step (at most 2 days, at least 300 rows), the last row at jd_to."""
    span = jd_to - jd_from
    step = min(span / MOVE_MIN_ROWS, MOVE_STEP_DAYS)
    if step <= 0:
        return pd.DataFrame()
    n = int(math.ceil(span / step)) + 1
    rows = []
    for i in range(n):
        jd = min(jd_from + i * step, jd_to) if i < n - 1 else jd_to
        rec = {"jd": jd}
        for p in labels:
            ps = position(p, jd)
            rec[f"{p}-RA"] = round(ps.ra, 2)
            rec[f"{p}-De"] = round(ps.dec, 2)
            rec[f"{p}-D"] = distance_pct(p, ps.dist_au)
        rows.append(rec)
    return pd.DataFrame(rows)


@dataclass
class AspectEvent:
    jd: float
    angle: int
    title: str          # e.g. C-Sa-Ju (in the workbook's planet order)
    de1: float
    de2: float


def aspect_events(labels: list[str], jd_from: float, jd_to: float, angles: list[int], orbs: Orbs) -> list[AspectEvent]:
    """Each time two of the planets come into one of the aspects (C / O / Q / T / S) across the period."""
    names = [p for p in BUTTON_ORDER if p in labels]
    if len(names) < 2 or not angles:
        return []
    span = jd_to - jd_from
    step = min(span / MOVE_MIN_ROWS, MOVE_STEP_DAYS)
    if step <= 0:
        return []
    if "Mo" in names and step > MOON_STEP:
        step = MOON_STEP
    import numpy as np
    n = int(math.ceil(span / step))
    jds = np.minimum(jd_from + np.arange(n + 1) * step, jd_to)
    ra = {p: np.empty(n + 1) for p in names}
    de = {p: np.empty(n + 1) for p in names}
    for k, jd in enumerate(jds):
        for p in names:
            x, err = se.calc_ut(float(jd), PLANET_ID[p])
            if x is None:
                raise RuntimeError(f"Swiss Ephemeris: {err}")
            ra[p][k] = x[0]; de[p][k] = x[1]
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sep = np.abs(ra[a] - ra[b])
            sep = np.where(sep > 180.0, 360.0 - sep, sep)
            same, mirror = np.abs(de[a] - de[b]), np.abs(de[a] + de[b])
            for ang in angles:
                ra_o, de_o = orbs.pair(ang, a, b, False), orbs.pair(ang, a, b, True)
                if ang == 0:
                    h = (sep <= ra_o) & (same <= de_o)
                elif ang == 180:
                    h = (np.abs(sep - 180.0) <= ra_o) & (mirror <= de_o)
                else:
                    h = (np.abs(sep - ang) <= ra_o) & ((same <= de_o) | (mirror <= de_o))
                start = h & ~np.concatenate(([False], h[:-1]))      # coming into the aspect
                for k in np.flatnonzero(start):
                    out.append(AspectEvent(float(jds[k]), ang, tag(ang) + a + "-" + b, float(de[a][k]), float(de[b][k])))
    out.sort(key=lambda e: e.jd)
    return out


def jd_to_datetime(jd: float) -> datetime:
    """UT datetime of a Julian day (Gregorian)."""
    return datetime(2000, 1, 1, 12) + pd.Timedelta(days=jd - 2451545.0)
