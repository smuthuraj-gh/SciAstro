"""From a customer's record to what the charts need: places, UTC offset, Julian days, positions and D values."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import streamlit as st

from astro import core, places


@dataclass
class Prepared:
    ok: bool
    message: str = ""
    birth_lat: float | None = None
    birth_lon: float | None = None
    tz: str | None = None
    utc: float | None = None
    weekday: str = ""
    jd_birth: float | None = None
    cn: tuple[float, float] | None = None          # now place (lat, lon)
    cn_tz: str | None = None
    birth: dict | None = None
    d_birth: dict | None = None
    now_only: bool = False                         # a member with no birth details yet: the Now charts only


NOW_ONLY = Prepared(True, now_only=True)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def locate_cached(city: str, state: str, country: str):
    return places.locate(city or "", state or "", country or "")


@st.cache_data(ttl=24 * 3600, show_spinner="Working out the birth chart...")
def prepare(rec_items: tuple) -> Prepared:
    rec = dict(rec_items)
    try:
        y, m, d = (int(rec[k]) for k in ("year", "mon", "day"))
        # the birth time is optional: unknown (no hour) is taken as 12:00 noon, no minutes as :00
        h = 12 if rec.get("hr") is None else int(rec["hr"])
        mi = 0 if rec.get("mn") is None or rec.get("hr") is None else int(rec["mn"])
        when = datetime(y, m, d, h, mi)
    except (TypeError, ValueError, KeyError):
        return Prepared(False, "The birth date is incomplete.")
    ll = locate_cached(rec.get("city"), rec.get("state"), rec.get("country"))
    if ll is None:
        return Prepared(False, f"The birth place '{rec.get('city')}, {rec.get('state')}, {rec.get('country')}' was not found.")
    tz = places.timezone_at(*ll)
    utc = rec.get("utc")
    if utc is None:
        if not tz:
            return Prepared(False, "No time zone was found for the birth place: check its City, State and Country.")
        utc = places.utc_offset(tz, when)
    jd = core.birth_jd(y, m, d, h, mi, utc)
    birth = core.birth_points(jd, ll[0], ll[1])
    d_birth = {p: core.distance_pct(p, core.position(p, jd).dist_au) for p in core.PLANETS}
    cn = None
    cn_tz = None
    if rec.get("city_n"):
        cn = locate_cached(rec.get("city_n"), rec.get("state_n"), rec.get("country_n"))
        if cn:
            cn_tz = places.timezone_at(*cn)
    return Prepared(True, "", round(ll[0], 2), round(ll[1], 2), tz, utc, when.strftime("%a"), jd, cn, cn_tz, birth, d_birth)


def now_values(jd_now: float) -> tuple[dict, dict]:
    pts = core.now_points(jd_now)
    d = {p: core.distance_pct(p, core.position(p, jd_now).dist_au) for p in core.PLANETS}
    return pts, d
