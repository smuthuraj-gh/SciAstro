"""What a signed-in person may use, from their row of the Customers table (one per login email): Access and Start Date.

Access: Now (the Now charts only); DOB (the DOB and Now charts of their own DOB record, no time limit); DOBG (unlimited:
the DOB and Now charts of every DOB record under their login, people they add themselves and quick births not saved, no
time limit); DOBT and DOBGT (free trials of DOB and DOBG for 1 day from Start Date: given on signing up with birth
details, as they pick, or by the admin); Admin (an admin, as those in the admins secret). DOB and DOBG are the paid
options. A trial run out: the Now charts only. A login's DOB records share its email: its own (the first) and any
number more (people added under it, or a family an admin set up).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

ACCESS = ("Now", "DOBT", "DOBGT", "DOB", "DOBG", "Admin")
# earlier names, read as the new ones (the database is changed to the new ones; see db._new_access_names)
RENAMED = {"Free": "Now", "FreeInd": "Now", "FreeGrp": "Now",
           "Individual": "DOB", "Ind": "DOB", "Group": "DOBG", "1wu": "DOBG", "1mu": "DOBG", "1yu": "DOBG",
           "Trial-Ind": "DOBT", "TrInd": "DOBT", "TrDOB": "DOBT", "Trial DOB": "DOBT",
           "Trial-Grp": "DOBGT", "TrGrp": "DOBGT", "TrGroup": "DOBGT", "Trial Group": "DOBGT"}
# the Access that run for a while from Start Date: months, days, unlimited (else their own DOB only), in words
PERIODS = {"DOBT": (0, 1, False, "free 1-day trial (your own DOB)"), "DOBGT": (0, 1, True, "free 1-day trial (unlimited)")}
PAID_NOTE = "DOB charts are a paid option (DOB or DOBG): ask the admin."
QUICK = -1                         # the sidebar's Quick birth (not saved), in place of a record's id


@dataclass(frozen=True)
class Grant:
    admin: bool                    # an admin
    dob: bool                      # may see the DOB charts (otherwise the Now charts only)
    many: bool = False             # of every record under their login, people they add and quick births (else their own only)
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


def _add_months(when: datetime, months: int) -> datetime:
    y, m = divmod(when.month - 1 + months, 12)
    year, month = when.year + y, m + 1
    last = (datetime(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return when.replace(year=year, month=month, day=min(when.day, last))


def ends(access: str, since: datetime) -> datetime:
    """When an Access of PERIODS (DOBT, DOBGT) set at since runs out."""
    months, days, _, _ = PERIODS[access]
    return _add_months(since, months) + timedelta(days=days)


def grant(value, since: datetime | None, now: datetime) -> Grant:
    """What a person may use now (UT), by their Customers row's Access (value; blank or unknown: Now) and Start Date."""
    try:
        a = canonical(value, ACCESS) or "Now"
    except ValueError:
        a = "Now"
    if a == "Admin":
        return Grant(admin=True, dob=True, many=True)
    if a == "DOBG":                                           # unlimited, no time limit
        return Grant(admin=False, dob=True, many=True)
    if a == "DOB":
        return Grant(admin=False, dob=True)
    if a in PERIODS:
        end, words = ends(a, since or now), PERIODS[a][3]
        if end > now:
            return Grant(admin=False, dob=True, many=PERIODS[a][2], note=f"{words[0].upper()}{words[1:]}, until {end:%Y-%m-%d %H:%M} UT.")
        return Grant(admin=False, dob=False, note=f"Your {words} ended on {end:%Y-%m-%d}. " + PAID_NOTE)
    return Grant(admin=False, dob=False, note="Now charts only. " + PAID_NOTE)


def own_record_id(records: list[dict]) -> int | None:
    """A login's own DOB record: its first (the others are the people added under it)."""
    if not records:
        return None
    return int(min(int(r["id"]) for r in records))
