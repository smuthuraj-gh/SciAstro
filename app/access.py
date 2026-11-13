"""What a signed-in person may use, from their row of the Customers table (one per login email): Access, Start Date and
End Date.

Access: Now (the Now charts only); DOBG (the DOB and Now charts of every DOB record under their login, and people they
add themselves); Admin (an admin, as those in the admins secret). DOBG is the paid option. End Date (UT): when DOBG runs
out (blank: no time limit); signing up with birth details gives DOBG for 1 day. Run out: the Now charts only. A login's
DOB records share its email: its own (the first) and any number more (people added under it, or a family an admin set
up).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

ACCESS = ("Now", "DOBG", "Admin")
# earlier names, read as the new ones (the database is changed to the new ones; see db._new_access_names)
RENAMED = {"Free": "Now", "FreeInd": "Now", "FreeGrp": "Now",
           "DOB": "DOBG", "Individual": "DOBG", "Ind": "DOBG", "Group": "DOBG", "1wu": "DOBG", "1mu": "DOBG", "1yu": "DOBG",
           "DOBT": "DOBG", "Trial-Ind": "DOBG", "TrInd": "DOBG", "TrDOB": "DOBG", "Trial DOB": "DOBG",
           "DOBGT": "DOBG", "Trial-Grp": "DOBG", "TrGrp": "DOBG", "TrGroup": "DOBG", "Trial Group": "DOBG"}
# earlier 1-day trials: as DOBG, with End Date 1 day after Start Date (see db._new_access_names)
TRIALS = ("DOBT", "Trial-Ind", "TrInd", "TrDOB", "Trial DOB", "DOBGT", "Trial-Grp", "TrGrp", "TrGroup", "Trial Group")
SIGNUP_DAYS = 1                    # signing up with birth details: DOBG for this many days
PAID_NOTE = "DOB charts are a paid option (DOBG): ask the admin."
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


def ended(value, until, now: datetime) -> bool:
    """Whether a DOBG with this End Date (until; blank: no time limit) has run out."""
    end = as_time(until)
    return end is not None and end <= now


def grant(value, since: datetime | None, now: datetime, until=None) -> Grant:
    """What a person may use now (UT), by their Customers row's Access (value; blank or unknown: Now) and End Date
    (until: when DOBG runs out; blank: no time limit)."""
    try:
        a = canonical(value, ACCESS) or "Now"
    except ValueError:
        a = "Now"
    if a == "Admin":
        return Grant(admin=True, dob=True, many=True)
    if a == "DOBG":
        end = as_time(until)
        if end is None:                                       # no time limit
            return Grant(admin=False, dob=True, many=True)
        if end > now:
            return Grant(admin=False, dob=True, many=True, note=f"DOBG until {end:%Y-%m-%d %H:%M} UT.")
        return Grant(admin=False, dob=False, note=f"Your DOBG ended on {end:%Y-%m-%d}. " + PAID_NOTE)
    return Grant(admin=False, dob=False, note="Now charts only. " + PAID_NOTE)


def own_record_id(records: list[dict]) -> int | None:
    """A login's own DOB record: its first (the others are the people added under it)."""
    if not records:
        return None
    return int(min(int(r["id"]) for r in records))
