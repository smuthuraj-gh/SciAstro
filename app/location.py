"""Who the visitor is using: their browser and system, and their browser's time zone (for the Logins table's Device and
Time zone columns). (Where they are, by IP address, is not looked up.)
"""
from __future__ import annotations

import streamlit as st


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
