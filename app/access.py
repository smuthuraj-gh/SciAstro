"""What a signed-in person may use, from their customer record(s): UType (Individual, Group, Admin) and Access.

Access: Admin (an admin, as those in the admins secret); DOB (the DOB and Now charts of their own record, no time limit);
1wu, 1mu, 1yu (unlimited: the DOB and Now charts of every record under their login, people they add themselves and quick
births not saved, for 1 week, 1 month or 1 year from Access From, when the Access was set). DOB, 1wu, 1mu and 1yu are the
paid options. Free, given by the admin for 1 week from Access From: TrDOB (as DOB) or TrGroup (unlimited, as 1wu). Now,
none, or a period run out: the Now charts only. UType Admin makes an admin too. A login's records share its
email: its own (Individual or Admin) and any number of Group ones (people added under it, or a family an admin set up).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

UTYPES = ("Individual", "Group", "Admin")
ACCESS = ("Admin", "DOB", "1wu", "1mu", "1yu", "TrDOB", "TrGroup", "Now")
RENAMED = {"Trial DOB": "TrDOB", "Trial Group": "TrGroup"}   # their earlier names, kept in the database for a while
# the Access that run for a while from Access From: months, days, unlimited (else their own DOB only), in words
PERIODS = {"1wu": (0, 7, True, "1 week unlimited access"), "1mu": (1, 0, True, "1 month unlimited access"),
           "1yu": (12, 0, True, "1 year unlimited access"),
           "TrDOB": (0, 7, False, "free 1-week trial (your own DOB)"), "TrGroup": (0, 7, True, "free 1-week trial (unlimited)")}
PAID_NOTE = "DOB charts are a paid option (DOB, 1 week, 1 month or 1 year): ask the admin."
QUICK = -1                         # the sidebar's Quick birth (not saved), in place of a record's id


@dataclass(frozen=True)
class Grant:
    admin: bool                    # an admin
    dob: bool                      # may see the DOB charts (otherwise the Now charts only)
    many: bool = False             # of every record under their login, people they add and quick births (else their own only)
    note: str = ""                 # what to tell them (an end date, or why DOB is not open)


def canonical(value, choices: tuple[str, ...]) -> str | None:
    """A UType or Access as it is kept (any case, spaces trimmed), None when blank; raises ValueError when not a choice."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or not str(value).strip():
        return None
    low = {c.lower(): c for c in choices}
    low.update({old.lower(): new for old, new in RENAMED.items() if new in choices})   # (an earlier name: as the new one)
    try:
        return low[str(value).strip().lower()]
    except KeyError:
        raise ValueError(f"'{value}' is not one of {', '.join(choices)}") from None


def _add_months(when: datetime, months: int) -> datetime:
    y, m = divmod(when.month - 1 + months, 12)
    year, month = when.year + y, m + 1
    last = (datetime(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return when.replace(year=year, month=month, day=min(when.day, last))


def ends(access: str, since: datetime) -> datetime:
    """When an Access of PERIODS (1wu, 1mu, 1yu, TrDOB, TrGroup) set at since runs out."""
    months, days, _, _ = PERIODS[access]
    return _add_months(since, months) + timedelta(days=days)


def _when(v) -> datetime | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return None
    return pd.Timestamp(v).to_pydatetime()


def grant(records: list[dict], now: datetime) -> Grant:
    """What the person whose customer records these are (all with their login email) may use, now (UT)."""
    def val(r, k, choices):
        try:
            return canonical(r.get(k), choices)
        except ValueError:
            return None
    if any(val(r, "utype", UTYPES) == "Admin" or val(r, "access", ACCESS) == "Admin" for r in records):
        return Grant(admin=True, dob=True, many=True)
    own_dob = any(val(r, "access", ACCESS) == "DOB" for r in records)
    many, own, lapsed = None, None, None                     # (the latest end of each: running unlimited, running own, run out)
    for r in records:
        a = val(r, "access", ACCESS)
        if a in PERIODS:
            since = _when(r.get("access_from")) or _when(r.get("added_at")) or now
            end, words = ends(a, since), PERIODS[a][3]
            if end <= now:
                lapsed = max(lapsed or (end, words), (end, words))
            elif PERIODS[a][2]:
                many = max(many or (end, words), (end, words))
            else:
                own = max(own or (end, words), (end, words))
    if many:
        return Grant(admin=False, dob=True, many=True, note=f"{many[1][0].upper()}{many[1][1:]}, until {many[0]:%Y-%m-%d %H:%M} UT.")
    if own_dob:
        return Grant(admin=False, dob=True, note=(f"Your {lapsed[1]} ended on {lapsed[0]:%Y-%m-%d}: "
                                                  "your own DOB charts only." if lapsed else ""))
    if own:
        return Grant(admin=False, dob=True, note=f"{own[1][0].upper()}{own[1][1:]}, until {own[0]:%Y-%m-%d %H:%M} UT.")
    if lapsed:
        return Grant(admin=False, dob=False, note=f"Your {lapsed[1]} ended on {lapsed[0]:%Y-%m-%d}. " + PAID_NOTE)
    return Grant(admin=False, dob=False, note="Now charts only. " + PAID_NOTE)


def own_record_id(records: list[dict]) -> int | None:
    """A login's own record: the one that is not UType Group (the first, if there are more), else its first."""
    if not records:
        return None
    def is_group(r):
        try:
            return canonical(r.get("utype"), UTYPES) == "Group"
        except ValueError:
            return False
    own = [r for r in records if not is_group(r)] or records
    return int(min(own, key=lambda r: int(r["id"]))["id"])
