"""Where the visitor is: City, State, Country from their IP address (for the Logins table's Location column).

The IP comes from the X-Forwarded-For header (the hosted app sits behind a proxy), else the connection itself. It is looked
up once per visit with ipapi.co (approximate, no prompt to the visitor); a private or local address is "Local", and a
failed lookup leaves the Location blank.
"""
from __future__ import annotations

import ipaddress

import requests
import streamlit as st

LOOKUP = "https://ipapi.co/{ip}/json/"
UA = {"User-Agent": "equatorial-charts/1.0"}


def _visitor_ip() -> str | None:
    try:
        forwarded = st.context.headers.get("X-Forwarded-For") or ""
        ip = forwarded.split(",")[0].strip() or st.context.ip_address
    except Exception:                                         # (not in a page run)
        return None
    return ip or None


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _place_of(ip: str) -> str:
    """City, State, Country of a public IP; raises when the lookup fails (so a failure is not kept)."""
    r = requests.get(LOOKUP.format(ip=ip), headers=UA, timeout=4)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise ValueError(data.get("reason") or "lookup failed")
    return ", ".join(str(data[k]) for k in ("city", "region", "country_name") if data.get(k))


def visitor_location() -> str:
    """The visitor's City, State, Country ("Local" on a private or local address, "" when unknown); once per visit."""
    try:
        if "visitor_location" in st.session_state:
            return st.session_state["visitor_location"]
    except Exception:
        return ""
    ip = _visitor_ip()
    place = ""
    if ip:
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                place = "Local"
            else:
                place = _place_of(str(addr))
        except (ValueError, requests.RequestException):
            place = ""
    st.session_state["visitor_location"] = place              # kept for the visit, a failed lookup too (no wait on every rerun)
    return place


def device_of(agent: str) -> str:
    """A browser's User-Agent as "Browser on System" (e.g. Chrome on Windows); "" when there is none."""
    a = agent or ""
    if not a.strip():
        return ""
    browser = ("Edge" if "Edg/" in a else "Opera" if "OPR/" in a else "Samsung" if "SamsungBrowser/" in a
               else "Chrome" if ("Chrome/" in a or "CriOS/" in a) else "Firefox" if ("Firefox/" in a or "FxiOS/" in a)
               else "Safari" if "Safari/" in a else "Other")
    system = ("iPhone" if "iPhone" in a else "iPad" if "iPad" in a else "Android" if "Android" in a
              else "Windows" if "Windows" in a else "ChromeOS" if "CrOS" in a else "Mac" if "Mac OS X" in a
              else "Linux" if "Linux" in a else "Other")
    return f"{browser} on {system}"


def visitor_device() -> str:
    """The visitor's browser and system (Chrome on Windows ..), "" when not known; once per visit."""
    try:
        if "visitor_device" not in st.session_state:
            st.session_state["visitor_device"] = device_of(st.context.headers.get("User-Agent") or "")
        return st.session_state["visitor_device"]
    except Exception:                                         # (not in a page run)
        return ""


def visitor_timezone() -> str:
    """The time zone the visitor's browser is set to, with its offset (Asia/Kolkata (UTC+5:30)); "" when not known."""
    try:
        name, off = st.context.timezone, st.context.timezone_offset
    except Exception:
        return ""
    if not name:
        return ""
    if off is None:
        return name
    east = -int(off)                                          # (the browser gives minutes behind UTC)
    sign, east = ("+" if east >= 0 else "-"), abs(east)
    return f"{name} (UTC{sign}{east // 60}" + (f":{east % 60:02d})" if east % 60 else ")")
