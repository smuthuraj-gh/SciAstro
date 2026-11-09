"""Places: coordinates from a Google Maps link, a "lat, lon" pair or a City, State, Country search (Open-Meteo),
the time zone at the coordinates (offline, timezonefinder) and the UTC offset in force at a local time
(zoneinfo / tzdata, with historical daylight saving)."""
from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

UA = {"User-Agent": "RaDe-web/1.0"}
_NUM = r"(-?\d{1,3}(?:\.\d+)?)"
_PATTERNS = [rf"!3d{_NUM}!4d{_NUM}",
             rf"[?&](?:q|query|ll|destination|center|daddr)=(?:loc:)?{_NUM},\s*\+?{_NUM}",
             rf"@{_NUM},{_NUM}",
             rf"^\s*{_NUM}\s*,\s*{_NUM}\s*$"]             # the pin first, the map centre last

OLD_NAMES = {"bangalore": "Bengaluru", "bombay": "Mumbai", "madras": "Chennai", "calcutta": "Kolkata",
             "trivandrum": "Thiruvananthapuram", "cochin": "Kochi", "calicut": "Kozhikode", "tanjore": "Thanjavur",
             "trichinopoly": "Tiruchirappalli", "poona": "Pune", "mysore": "Mysuru", "baroda": "Vadodara",
             "benares": "Varanasi", "pondicherry": "Puducherry", "peking": "Beijing", "saigon": "Ho Chi Minh City"}


class LookupDown(Exception):
    """The place search did not answer. Not the same as a place not found, and not kept: the next try asks again."""


def maps_lat_lon(s: str) -> tuple[float, float] | None:
    """Coordinates from a Google Maps link (short links are followed) or a "lat, lon" pair; None otherwise."""
    if not s:
        return None
    link = urlparse(s.strip())
    if link.scheme in ("http", "https") and link.hostname in ("goo.gl", "maps.app.goo.gl"):   # Google's short links only
        try:
            s = requests.get(s, headers=UA, timeout=10, allow_redirects=True).url
        except requests.RequestException:
            pass
    s = s.replace("%40", "@").replace("%2C", ",").replace("%2c", ",").replace("%21", "!")
    for pat in _PATTERNS:
        m = re.search(pat, s, re.IGNORECASE)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if abs(lat) <= 90 and abs(lon) <= 180:
                return lat, lon
    return None


def _matches(res: dict, part: str) -> bool:
    p = part.strip().lower()
    p = {"usa": "us", "america": "us", "uk": "gb", "uae": "ae"}.get(p.replace(".", ""), p)
    country = (res.get("country") or "").lower()
    code = (res.get("country_code") or "").lower()
    a1 = (res.get("admin1") or "").lower()
    a2 = (res.get("admin2") or "").lower()
    if p in (country, code):
        return True
    if len(p) >= 3:
        return p in country or p in a1 or p in a2
    if a1:
        initials = "".join(w[0] for w in a1.split() if w)
        return p == initials or a1.startswith(p)
    return False


def _search(name: str) -> list[dict]:
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": name, "count": 10, "language": "en", "format": "json"},
                         headers=UA, timeout=15)
        r.raise_for_status()
        return r.json().get("results") or []
    except (requests.RequestException, ValueError) as exc:
        raise LookupDown(str(exc)) from exc


def _pick(results: list[dict], parts: list[str]) -> dict | None:
    rest = [p for p in parts[1:] if p.strip()]
    if not results:
        return None
    if not rest:
        return results[0]
    for res in results:                       # every part matches
        if all(_matches(res, p) for p in rest):
            return res
    for res in results:                       # at least the country (the last part)
        if _matches(res, rest[-1]):
            return res
    return None


@lru_cache(maxsize=512)
def geocode(query: str) -> tuple[float, float] | None:
    """'City, State, Country': the first result matching every part given, else the first in that country."""
    parts = [p.strip() for p in query.split(",")]
    if not parts or not parts[0]:
        return None
    res = _pick(_search(parts[0]), parts)
    if res is None and parts[0].lower() in OLD_NAMES:
        res = _pick(_search(OLD_NAMES[parts[0].lower()]), parts)
    if res is None:
        return None
    return float(res["latitude"]), float(res["longitude"])


def locate(city: str, state: str = "", country: str = "") -> tuple[float, float] | None:
    """A place from its City (a Maps link or "lat, lon" there wins), State and Country."""
    ll = maps_lat_lon(city or "")
    if ll:
        return ll
    query = ", ".join(x for x in (city, state, country) if x and str(x).strip())
    return geocode(query) if query else None


@lru_cache(maxsize=1)
def _finder():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder()


def timezone_at(lat: float, lon: float) -> str | None:
    return _finder().timezone_at(lat=lat, lng=lon)


def utc_offset(tz_name: str, local: datetime) -> float:
    """Hours east of UTC in force at that local time (earlier of two when the clock went back)."""
    off = local.replace(tzinfo=ZoneInfo(tz_name), fold=0).utcoffset()
    return round(off.total_seconds() / 60.0) / 60.0
