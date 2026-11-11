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
