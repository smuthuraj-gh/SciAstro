"""Equatorial positions (RA / Dec only, no zodiac), distances, sidereal time and the aspect rules.

Ported from the Excel workbook's VBA (modSE, modTable, modMap, modMovement); the rules are the same:
an aspect at an angle holds when the RA separation is within the RA orb of the angle and the Dec is within the Dec
orb of equal (conjunction), mirrored (opposition) or either (every other angle). A pair's orb is the larger of
its two planets' orbs; a house point (CB, CN) takes the planet's.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from . import se

PLANETS = ["Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa"]          # Swiss Ephemeris numbers 0 .. 6
BUTTON_ORDER = ["Sa", "Ju", "Ma", "Ve", "Me", "Su", "Mo"]     # the order of the workbook's buttons and loops
PLANET_ID = {p: i for i, p in enumerate(PLANETS)}
AU_KM = 149597870.7
TRUE_NODE = 11                                                # Swiss Ephemeris number of the Moon's true node

# The recommended colours: the traditional ones (Sun gold, Moon silver, Mars red, Venus green, Jupiter purple, Saturn brown),
# made to show on white and to be told apart, colour-blind viewers too (the Naming Conventions table can change them)
COLOURS = {"Su": "rgb(230,159,0)", "Mo": "rgb(140,140,150)", "Me": "rgb(86,180,233)", "Ve": "rgb(0,158,115)",
           "Ma": "rgb(213,94,0)", "Ju": "rgb(120,60,160)", "Sa": "rgb(120,80,40)", "Ea": "rgb(0,114,178)",
           "NN": "rgb(204,121,167)", "SN": "rgb(102,102,153)", "CB": "rgb(0,0,0)", "CN": "rgb(0,60,140)"}

# geocentric minimum / maximum distance (km) over 1800-2400, as the workbook uses for D
DIST_RANGE = {"Su": (147079476.4, 152116857.5), "Mo": (356371.3, 406720.6), "Me": (82110762.7, 217176258.7),
              "Ve": (39514836.7, 259699120.3), "Ma": (55688407.5, 400407237.2), "Ju": (590130185.9, 966315582.2),
              "Sa": (1200835560.6, 1655050506.1)}

MAJOR = [0, 180, 90, 120, 60]
MINOR = [30, 45, 72, 135, 144, 150]
def colour(name: str) -> str:
    return COLOURS.get(name[:2], "rgb(0,0,0)")


# The Size column of the Naming Conventions table (set each run from the table), and its names and SNs, in lower case, to their SN
SIZE_TEXTS: dict[str, str] = {}
SIZE_WORDS: dict[str, str] = {}
SIZE_STEP = 1.5                   # pixels of radius that "bigger than" and "smaller than" add or take away
TINY_PX = 3.0                     # a Tiny body's radius, in pixels
MARK_PX = 9.0                     # the usual half-size of the nodes' symbols and the places' icons, in pixels
SIZE_PX = (1.0, 40.0)             # the smallest and largest radius a number in Size can ask for


# The Symbol column of the Naming Conventions table (set each run from the table), which the pages show in place of an SN
SYMBOL_TEXTS: dict[str, str] = {}
_ANY_SN = re.compile(r"\b(Su|Mo|Me|Ve|Ma|Ju|Sa|Ea|NN|SN|CB|CN)\b")


def symbol_of(name: str) -> str:
    """What the pages show for an SN: its Symbol, or the SN itself with none. (A single symbol is asked for as text, not as an emoji.)"""
    symbol = SYMBOL_TEXTS.get(name) or name
    return symbol + "\ufe0e" if name in SYMBOL_TEXTS and len(symbol) == 1 and 0x2600 <= ord(symbol) < 0x2700 else symbol


def with_symbols(text: str) -> str:
    """A text with each SN in it shown as its Symbol: 0-Sa-Ju, as it is kept, for the page."""
    return _ANY_SN.sub(lambda m: symbol_of(m[1]), text)


def size_rule(name: str, _seen: tuple = ()) -> dict:
    """How a body is sized, from its Size text: {"px": radius}, or {"of": a planet, "add": pixels}, meaning that planet's angular size
    drawn, plus add. "Angular Size"; "Tiny" (a dot); a number (pixels of radius); "Bigger than X", "Smaller than X" or "Same as X", X an SN or a Name.
    Anything else, or blank: as they have always been drawn, a planet by its angular size and the Earth a little bigger than the Moon."""
    low = SIZE_TEXTS.get(name, "").strip().lower()
    if low == "tiny":                                  # a dot, too small to hold a symbol
        return {"px": TINY_PX}
    number = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:px)?", low)
    if number:
        return {"px": min(max(float(number[1]), SIZE_PX[0]), SIZE_PX[1])}
    relative = re.fullmatch(r"(bigger than|smaller than|same as)\s+(.+)", low)
    target = SIZE_WORDS.get(relative[2].strip()) if relative else None
    if target and target != name and target not in _seen:
        rule = size_rule(target, _seen + (name,))
        add = {"bigger than": SIZE_STEP, "smaller than": -SIZE_STEP, "same as": 0.0}[relative[1]]
        return {"px": max(rule["px"] + add, SIZE_PX[0])} if "px" in rule else {"of": rule["of"], "add": rule["add"] + add}
    if name in PLANET_ID:
        return {"of": name, "add": 0.0}
    return {"of": "Mo", "add": SIZE_STEP} if name == "Ea" else {"px": MARK_PX}   # the nodes and the places: a fixed size


def tag(angle: int) -> str:
    """An aspect's name starts with its angle: 0-Su-Me, 60-Ma-Mo, 135-Sa-Ve (the workbook used C-, S-, Q-, T-, O-)."""
    return f"{angle}-"


def norm360(deg: float) -> float:
    return deg - 360.0 * math.floor(deg / 360.0)


# ---------------------------------------------------------------- time
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


def moon_north_node(jd_ut: float) -> tuple[float, float]:
    """The (RA, Dec) of the Moon's true north node, where its path crosses the Sun's going north. The south node is opposite."""
    x, err = se.calc_ut(jd_ut, TRUE_NODE)
    if x is None:
        raise RuntimeError(f"Swiss Ephemeris: {err}")
    return x[0], x[1]


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
        return self._lookup.get((float(angle), name, is_dec), -1.0)

    def pair(self, angle: float, n1: str, n2: str, is_dec: bool) -> float:
        o = max(self.planet(angle, n1, is_dec), self.planet(angle, n2, is_dec))
        return o if o >= 0 else start_orb(angle, is_dec)


def default_orb_table() -> pd.DataFrame:
    from pathlib import Path
    return pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "orbs_default.csv")


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
    title: str          # e.g. 0-Sa-Ju (in the workbook's planet order)
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
