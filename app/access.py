"""What a signed-in person may use, from their row of the Customers table (one per login email): Access, Start Date, Days
and End Date.

Access: Now (the Now charts only); DOB (the DOB and Now charts of every DOB record under their login, and people they add
themselves) for Days days; Admin (an admin, as those in the admins secret). DOB is the paid option. End Date (UT): when it
runs out, set by the app: Start Date + Days; Start Date
is as the admin sets it, else when Access or Days was saved. Signing up with birth details gives DOB for 1 day. Run out: the Now charts only. A login's
DOB records share its email: its own (the first) and any number more (people added under it, or a family an admin set
up).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

ACCESS = ("Now", "DOB", "Admin")
# earlier names, read as the new ones (the database is changed to the new ones; see db._new_access_names)
RENAMED = {"Free": "Now", "FreeInd": "Now", "FreeGrp": "Now",
           "1Day": "DOB", "1Year": "DOB", "DOBG": "DOB", "Individual": "DOB", "Ind": "DOB", "Group": "DOB", "1wu": "DOB", "1mu": "DOB", "1yu": "DOB",
           "DOBT": "DOB", "Trial-Ind": "DOB", "TrInd": "DOB", "TrDOB": "DOB", "Trial DOB": "DOB",
           "DOBGT": "DOB", "Trial-Grp": "DOB", "TrGrp": "DOB", "TrGroup": "DOB", "Trial Group": "DOB"}
# earlier 1-day trials: as DOB, with End Date 1 day after Start Date (see db._new_access_names)
TRIALS = ("DOBT", "Trial-Ind", "TrInd", "TrDOB", "Trial DOB", "DOBGT", "Trial-Grp", "TrGrp", "TrGroup", "Trial Group")
SIGNUP_DAYS = 1                    # DOB with Days left blank lasts this many days (signing up gives it)
LASTS = ("DOB",)                   # the Access that run out: DOB after Days days (see period_end)
PAID_NOTE = "DOB charts are a paid option (DOB): ask the admin."
DAY_PACKS = (1, 7, 30, 90, 180, 365)  # the days a customer may add themselves (DOB Details: Get more days)
QUICK = -1                         # the sidebar's Quick birth (not saved), in place of a record's id


@dataclass(frozen=True)
class Grant:
    admin: bool                    # an admin
    dob: bool                      # may see the DOB charts (otherwise the Now charts only)
    many: bool = False             # of every record under their login and people they add (else their own only)
    note: str = ""                 # what to tell them (an end date, or why DOB is not open)


def canonical(value, choices: tuple[str, ...]) -> str | None:
    """An Access as it is kept (any case, spaces trimmed), None when blank; raises ValueError when not a choice."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or not str(value).strip():
        return None
    low = {c.lower(): c for c in choices}
    low.update({old.lower(): new for old, new in RENAMED.items() if new in choices or new is None})   # (an earlier name: as the new one)
    try:
        return low[str(value).strip().lower()]                # (one now blank: None)
    except KeyError:
        raise ValueError(f"'{value}' is not one of {', '.join(choices)}") from None


def as_time(v) -> datetime | None:
    """A date or time as a datetime (UT); None when blank."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()):
        return None
    t = pd.Timestamp(v)
    return None if pd.isna(t) else t.to_pydatetime().replace(tzinfo=None)


def period_end(value: str, start: datetime, days=None) -> datetime:
    """When a DOB from start runs out: days days on (blank: SIGNUP_DAYS)."""
    return start + timedelta(days=whole_days(days) or SIGNUP_DAYS)


def whole_days(v) -> int | None:
    """Days as a whole number of 1 or more; None when blank or not one."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == f and f >= 1 and f.is_integer() else None


def ends_at(value: str, since, until, now: datetime) -> datetime:
    """When a DOB runs out: its End Date (until), else its period after its Start Date (since; blank: now)."""
    return as_time(until) or period_end(value, as_time(since) or now)


def ended(value: str, since, until, now: datetime) -> bool:
    """Whether a DOB with this Start Date and End Date has run out."""
    return ends_at(value, since, until, now) <= now


def grant(value, since: datetime | None, now: datetime, until=None) -> Grant:
    """What a person may use now (UT), by their Customers row's Access (value; blank or unknown: Now), Start Date (since)
    and End Date (until: when DOB runs out; blank: 1 day after Start Date)."""
    try:
        a = canonical(value, ACCESS) or "Now"
    except ValueError:
        a = "Now"
    if a == "Admin":
        return Grant(admin=True, dob=True, many=True)
    if a in LASTS:
        end = ends_at(a, since, until, now)
        if end > now:
            return Grant(admin=False, dob=True, many=True, note=f"{a} until {end:%Y-%m-%d %H:%M} UT.")
        return Grant(admin=False, dob=False, note=f"Your {a} ended on {end:%Y-%m-%d}. " + PAID_NOTE)
    return Grant(admin=False, dob=False, note="Now charts only. " + PAID_NOTE)


def own_record_id(records: list[dict]) -> int | None:
    """A login's own DOB record: its first (the others are the people added under it)."""
    if not records:
        return None
    return int(min(int(r["id"]) for r in records))
