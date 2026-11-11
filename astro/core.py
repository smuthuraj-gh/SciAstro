"""Equatorial positions (RA / Dec only, no zodiac), distances, sidereal time and the aspect rules.

Ported from the Excel workbook's VBA (modSE, modTable, modMap, modMovement); the rules are the same:
an aspect at an angle holds when the RA separation is within the orb of the angle and the two Decs are within the
same orb of equal or mirrored (one rule for every angle). A pair's orb is the larger of its two planets' orbs; a house
point (CB, CN) takes the planet's.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import se

PLANETS = ["Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa"]          # Swiss Ephemeris numbers 0 .. 6
BUTTON_ORDER = ["Sa", "Ju", "Ma", "Ve", "Me", "Su", "Mo"]     # the order of the workbook's buttons and loops
SHOWN_ORDER = ["Mo", "Su", "Ea", "Me", "Ve", "Ma", "Ju", "Sa", "NN", "SN"]   # the order the planet buttons are shown in, on every page


def shown_order(names) -> list:
    """These names in the order the planet buttons are shown in (any not in it last, as they were)."""
    names = list(names)
    return sorted(names, key=lambda n: SHOWN_ORDER.index(n) if n in SHOWN_ORDER else len(SHOWN_ORDER) + names.index(n))


def in_order(picked, order) -> list:
    """The buttons picked, back in the order the charts use (the buttons' own order is only for showing)."""
    order = list(order)
    return [n for n in order if n in (picked or [])]
PLANET_ID = {p: i for i, p in enumerate(PLANETS)}
AU_KM = 149597870.7
TRUE_NODE = 11                                                # Swiss Ephemeris number of the Moon's true node
EARTH = 14                                                    # Swiss Ephemeris number of the Earth (as seen from the Sun)

# The recommended colours: the traditional ones (Sun gold, Moon silver, Mars red, Venus green, Jupiter purple, Saturn brown),
# made to show on white and to be told apart, colour-blind viewers too (the Symbols table can change them)
COLOURS = {"Su": "rgb(230,159,0)", "Mo": "rgb(140,140,150)", "Me": "rgb(86,180,233)", "Ve": "rgb(0,158,115)",
           "Ma": "rgb(213,94,0)", "Ju": "rgb(120,60,160)", "Sa": "rgb(120,80,40)", "Ea": "rgb(0,114,178)",
           "NN": "rgb(204,121,167)", "SN": "rgb(102,102,153)", "CB": "rgb(0,0,0)", "CN": "rgb(0,60,140)"}

# geocentric minimum / maximum distance (km) over 1800-2400, as the workbook uses for D
DIST_RANGE = {"Su": (147079476.4, 152116857.5), "Mo": (356371.3, 406720.6), "Me": (82110762.7, 217176258.7),
              "Ve": (39514836.7, 259699120.3), "Ma": (55688407.5, 400407237.2), "Ju": (590130185.9, 966315582.2),
              "Sa": (1200835560.6, 1655050506.1)}

MAJOR = [0, 180, 90, 120, 60]
MINOR = [30, 45, 72, 135, 144, 150]
DEFAULT_COLOURS = dict(COLOURS)   # what a row's colour goes back to when the row is deleted


def colour(name: str) -> str:
    return COLOURS.get(name[:2], "rgb(0,0,0)")


# The Size column of the Symbols table (set each run from the table), and its names and SNs, in lower case, to their SN
SIZE_TEXTS: dict[str, str] = {}
SIZE_WORDS: dict[str, str] = {}
SIZE_TEXTS_HELIO: dict[str, str] = {}   # the Size_Helio column: how the HelioCentric chart sizes each row
SIZE_TEXTS_GLOBE: dict[str, str] = {}   # the Size_Globe column: how the AstroGlobe chart sizes each row
SIZE_TEXTS_CLOCK: dict[str, str] = {}   # the Size_Clock column: how the AstroClock-2D chart sizes each row
SIZE_STEP = 1.5                   # pixels of radius that "bigger than" and "smaller than" add or take away
TINY_PX = 3.0                     # a Tiny body's radius, in pixels
MARK_PX = 9.0                     # the usual half-size of the nodes' symbols and the places' icons, in pixels
SIZE_NAMES = {"tiny": TINY_PX, "small": MARK_PX}   # Size words: Tiny a dot; Small as the nodes and places usually are
SIZE_PX = (1.0, 40.0)             # the smallest and largest radius a number in Size can ask for


# The Symbol column of the Symbols table (set each run from the table), which the pages show in place of an SN
SYMBOL_TEXTS: dict[str, str] = {}
_ANY_SN = re.compile(r"\b(Su|Mo|Me|Ve|Ma|Ju|Sa|Ea|NN|SN|CB|CN)\b")


def symbol_of(name: str) -> str:
    """What the pages show for an SN: its Symbol, or the SN itself with none. (A single symbol is asked for as text, not as an emoji.)"""
    symbol = SYMBOL_TEXTS.get(name) or name
    return symbol + "\ufe0e" if name in SYMBOL_TEXTS and len(symbol) == 1 and 0x2600 <= ord(symbol) < 0x2700 else symbol


def with_symbols(text: str) -> str:
    """A text with each SN in it shown as its Symbol: 0-Ju-Sa, as it is kept, for the page."""
    return _ANY_SN.sub(lambda m: symbol_of(m[1]), text)


def size_rule(name: str, _seen: tuple = (), texts: dict[str, str] | None = None) -> dict:
    """How a body is sized, from its Size text: {"px": radius}, or {"of": a planet, "add": pixels}, meaning that planet's angular size
    drawn, plus add. "Angular Size"; "Tiny" (a dot) or "Small" (9 pixels); a number (pixels of radius); "Bigger than X", "Smaller than X" or "Same as X", X an SN or a Name.
    Anything else, or blank: a planet by its angular size, the Earth a dot (it has no size of its own to go by)."""
    texts = SIZE_TEXTS if texts is None else texts             # Size_Geo, or another Size column (SIZE_TEXTS_HELIO, _GLOBE, _CLOCK)
    low = texts.get(name, "").strip().lower()
    if low in SIZE_NAMES:                              # Tiny: a dot, too small to hold a symbol; Small: the usual mark
        return {"px": SIZE_NAMES[low]}
    number = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:px)?", low)
    if number:
        return {"px": min(max(float(number[1]), SIZE_PX[0]), SIZE_PX[1])}
    relative = re.fullmatch(r"(bigger than|smaller than|same as)\s+(.+)", low)
    target = SIZE_WORDS.get(relative[2].strip()) if relative else None
    if target and target != name and target not in _seen:
        rule = size_rule(target, _seen + (name,), texts)
        add = {"bigger than": SIZE_STEP, "smaller than": -SIZE_STEP, "same as": 0.0}[relative[1]]
        return {"px": max(rule["px"] + add, SIZE_PX[0])} if "px" in rule else {"of": rule["of"], "add": rule["add"] + add}
    if name in PLANET_ID:
        return {"of": name, "add": 0.0}
    # the Earth with no readable Size: the smallest, a dot; the nodes and the places: their usual fixed size
    return {"px": TINY_PX} if name == "Ea" else {"px": MARK_PX}


def size_readable(text: str, words: set[str]) -> bool:
    """Whether size_rule can read a Size text: blank, Angular Size, a size word, a number, or Bigger than / Smaller than / Same as one
    of words (the SNs and Names, in lower case)."""
    low = text.strip().lower()
    if low in ("", "angular size") or low in SIZE_NAMES or re.fullmatch(r"\d+(?:\.\d+)?\s*(?:px)?", low):
        return True
    relative = re.fullmatch(r"(bigger than|smaller than|same as)\s+(.+)", low)
    return bool(relative) and relative[2].strip() in words


def tag(angle: int) -> str:
    """An aspect's name starts with its angle: 0-Su-Me, 60-Mo-Ma, 135-Ve-Sa (the workbook used C-, S-, Q-, T-, O-)."""
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


def helio_position(label: str, jd_ut: float) -> Pos:
    """As position, but seen from the Sun: RA and Dec on the same equatorial frame (the Earth's equator), and the distance from
    the Sun. Ea is the Earth."""
    x, err = se.calc_ut(jd_ut, EARTH if label == "Ea" else PLANET_ID[label], se.CALC_FLAGS | se.FLG_HELCTR)
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
def start_orb(angle: float) -> float:
    """The orb used where the table has none (the same for RA and Dec)."""
    if angle in (0, 180):
        return 8.0
    if angle in (90, 120):
        return 6.0
    if angle == 60:
        return 4.0
    return 2.0


@dataclass
class Orbs:
    """The orb table: a row per aspect (Aspect, Angle, Mo-RA .. Sa-RA, NN-RA, SN-RA). Each orb is used for RA and for Dec alike."""
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
                if len(c) == 5 and (c[:2] in PLANET_ID or c[:2] in ("NN", "SN")) and c[2:].upper() == "-RA":
                    v = pd.to_numeric(row[col], errors="coerce")
                    if pd.notna(v) and v >= 0:
                        self._lookup[(ang, c[:2])] = float(v)

    def planet(self, angle: float, name: str) -> float:
        return self._lookup.get((float(angle), name), -1.0)       # the RA orb, used for Dec too

    def pair(self, angle: float, n1: str, n2: str) -> float:
        o = max(self.planet(angle, n1), self.planet(angle, n2))
        return o if o >= 0 else start_orb(angle)


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
    title: str          # e.g. 0-Ju-Sa (in the order the planet buttons are shown: Mo, Su, Me, Ve, Ma, Ju, Sa, NN, SN)
    de1: float
    de2: float
    ra1: float = 0.0    # the two planets' RA then (degrees), in the order of the title
    ra2: float = 0.0


def aspect_events(labels: list[str], jd_from: float, jd_to: float, angles: list[int], orbs: Orbs) -> list[AspectEvent]:
    """Each time two of the planets come into one of the aspects (C / O / Q / T / S) across the period. The Moon's nodes (NN,
    SN) may be among them, with their own orbs where the Aspect Rules table has them (NN-RA, SN-RA), as the planets', the larger of the pair's;
    NN with SN is never one (they are always opposite)."""
    names = shown_order([p for p in BUTTON_ORDER + ["NN", "SN"] if p in labels])   # named in this order: 0-Mo-Su .. 0-Sa-SN
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
        node = moon_north_node(float(jd)) if {"NN", "SN"} & set(names) else None
        for p in names:
            if p in ("NN", "SN"):                                    # the south node opposite the north
                ra[p][k], de[p][k] = (node[0], node[1]) if p == "NN" else ((node[0] + 180.0) % 360.0, -node[1])
                continue
            x, err = se.calc_ut(float(jd), PLANET_ID[p])
            if x is None:
                raise RuntimeError(f"Swiss Ephemeris: {err}")
            ra[p][k] = x[0]; de[p][k] = x[1]
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if {a, b} == {"NN", "SN"}:
                continue
            sep = np.abs(ra[a] - ra[b])
            sep = np.where(sep > 180.0, 360.0 - sep, sep)
            same, mirror = np.abs(de[a] - de[b]), np.abs(de[a] + de[b])
            for ang in angles:
                o = orbs.pair(ang, a, b)                       # one orb for RA and Dec; one rule for every angle
                h = (np.abs(sep - ang) <= o) & ((same <= o) | (mirror <= o))
                start = h & ~np.concatenate(([False], h[:-1]))      # coming into the aspect
                for k in np.flatnonzero(start):
                    out.append(AspectEvent(float(jds[k]), ang, tag(ang) + a + "-" + b, float(de[a][k]), float(de[b][k]),
                                           float(ra[a][k]), float(ra[b][k])))
    out.sort(key=lambda e: e.jd)
    return out


def jd_to_datetime(jd: float) -> datetime:
    """UT datetime of a Julian day (Gregorian), to the nearest second (a Julian day's last digits are rounding error)."""
    return datetime(2000, 1, 1, 12) + timedelta(seconds=round(float(jd - 2451545.0) * 86400.0))
