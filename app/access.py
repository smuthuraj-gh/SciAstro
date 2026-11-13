"""What a signed-in person may use, from their row of the Customers table (one per login email): Access, Start Date and
End Date.

Access: Now (the Now charts only); 1Day (the DOB and Now charts of every DOB record under their login, and people they
add themselves) for 1 day; Admin (an admin, as those in the admins secret). 1Day is the paid option. End Date (UT): when
1Day runs out, 1 day after Start Date (set by the app; the admin may set a later one). Signing up with birth details
gives 1Day. Run out: the Now charts only. A login's
DOB records share its email: its own (the first) and any number more (people added under it, or a family an admin set
up).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

ACCESS = ("Now", "1Day", "Admin")
# earlier names, read as the new ones (the database is changed to the new ones; see db._new_access_names)
RENAMED = {"Free": "Now", "FreeInd": "Now", "FreeGrp": "Now",
           "DOBG": "1Day", "DOB": "1Day", "Individual": "1Day", "Ind": "1Day", "Group": "1Day", "1wu": "1Day", "1mu": "1Day", "1yu": "1Day",
           "DOBT": "1Day", "Trial-Ind": "1Day", "TrInd": "1Day", "TrDOB": "1Day", "Trial DOB": "1Day",
           "DOBGT": "1Day", "Trial-Grp": "1Day", "TrGrp": "1Day", "TrGroup": "1Day", "Trial Group": "1Day"}
# earlier 1-day trials: as 1Day, with End Date 1 day after Start Date (see db._new_access_names)
TRIALS = ("DOBT", "Trial-Ind", "TrInd", "TrDOB", "Trial DOB", "DOBGT", "Trial-Grp", "TrGrp", "TrGroup", "Trial Group")
SIGNUP_DAYS = 1                    # 1Day lasts this many days from Start Date (signing up gives it)
PAID_NOTE = "DOB charts are a paid option (1Day): ask the admin."
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


def ends_at(since, until, now: datetime) -> datetime:
    """When a 1Day runs out: its End Date (until), else 1 day after its Start Date (since; blank: now)."""
    return as_time(until) or (as_time(since) or now) + timedelta(days=SIGNUP_DAYS)


def ended(since, until, now: datetime) -> bool:
    """Whether a 1Day with this Start Date and End Date has run out."""
    return ends_at(since, until, now) <= now


def grant(value, since: datetime | None, now: datetime, until=None) -> Grant:
    """What a person may use now (UT), by their Customers row's Access (value; blank or unknown: Now), Start Date (since)
    and End Date (until: when 1Day runs out; blank: 1 day after Start Date)."""
    try:
        a = canonical(value, ACCESS) or "Now"
    except ValueError:
        a = "Now"
    if a == "Admin":
        return Grant(admin=True, dob=True, many=True)
    if a == "1Day":
        end = ends_at(since, until, now)
        if end > now:
            return Grant(admin=False, dob=True, many=True, note=f"1Day until {end:%Y-%m-%d %H:%M} UT.")
        return Grant(admin=False, dob=False, note=f"Your 1Day ended on {end:%Y-%m-%d}. " + PAID_NOTE)
    return Grant(admin=False, dob=False, note="Now charts only. " + PAID_NOTE)


def own_record_id(records: list[dict]) -> int | None:
    """A login's own DOB record: its first (the others are the people added under it)."""
    if not records:
        return None
    return int(min(int(r["id"]) for r in records))
