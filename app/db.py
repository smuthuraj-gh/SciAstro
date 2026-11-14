"""The private store: customers, the planets and the orbs (Aspect Rules).

The database URL comes from the secret `db_url` (e.g. a Neon or Supabase Postgres URL on Streamlit Community Cloud,
whose own disk is wiped on every restart). Without it, a local SQLite file private/app.db is used.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from astro import core

from . import access
from .location import visitor_device, visitor_location, visitor_timezone

ROOT = Path(__file__).resolve().parent.parent
# the customer columns in table order; Email (login) first, as it is the key
ACCOUNT_FIELDS = ()                           # (none now: Group Owner Email, created_by, was dropped)
FIELDS = ["email", *ACCOUNT_FIELDS, "name", "last_name", "country", "state", "city", "other", "year", "mon", "day", "hr", "mn",
          "country_n", "state_n", "city_n", "other_n", "utc"]
LABELS = {"name": "First Name", "last_name": "Last Name", "email": "Email (login)",
          "access": "Access", "country": "Country", "state": "State",
          "other": "Other", "city": "City",
          "year": "Year", "mon": "Mon", "day": "Date", "hr": "Hr24", "mn": "Min", "country_n": "Country-N",
          "state_n": "State-N", "city_n": "City-N", "other_n": "Other-N", "utc": "UTC (blank = look up)"}

meta = sa.MetaData()
customers = sa.Table(
    "customers", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.String(120), nullable=False),       # not unique: the login email is the key
    sa.Column("last_name", sa.String(120)),
    sa.Column("email", sa.String(254)),
    sa.Column("access", sa.String(20)),                       # (earlier: each login's Access, now in the Customers table: see accounts)
    sa.Column("access_from", sa.DateTime),                    # (earlier: when it was set, now the Customers table's Start Date)
    sa.Column("country", sa.String(120)), sa.Column("state", sa.String(120)),
    sa.Column("other", sa.String(500)),                       # free text kept with the record (not used in the charts)
    sa.Column("city", sa.String(500)),
    sa.Column("year", sa.Integer), sa.Column("mon", sa.Integer), sa.Column("day", sa.Integer),
    sa.Column("hr", sa.Integer), sa.Column("mn", sa.Integer),
    sa.Column("country_n", sa.String(120)), sa.Column("state_n", sa.String(120)), sa.Column("city_n", sa.String(500)),
    sa.Column("other_n", sa.String(500)),                     # free text, like Other, for the place now
    sa.Column("utc", sa.Float),
    # when (UT): the record was added, last changed, and last opened by the customer themself (set by the app)
    sa.Column("added_at", sa.DateTime), sa.Column("updated_at", sa.DateTime), sa.Column("accessed_at", sa.DateTime),
)
# A login email (kept in lower case) is on its own customer (the one with an Access) and any number more (people added
# under it, a family). Blank emails are allowed for any number of customers.
# EMAIL_INDEX: the old rule, one per email.
EMAIL_INDEX = "ux_customers_email"
sa.Index("ix_customers_email", customers.c.email)
# The Customers table: a row per login email, with its Access (app/access.py), Start Date (UT; as set, or when Access or
# Days was saved) and End Date (UT; when DOB runs out: Start Date + the Days typed on the Customers page, not kept); seen by admins only (the Customers page). Each login's DOB records (above) share
# its email.
accounts = sa.Table(
    "accounts", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("email", sa.String(254), nullable=False),     # kept in lower case
    sa.Column("access", sa.String(20)),                     # Now, DOB, Admin
    sa.Column("start_date", sa.DateTime),
    sa.Column("end_date", sa.DateTime),                     # when DOB runs out (start_date + the days typed)
)
sa.Index("ux_accounts_email", accounts.c.email, unique=True)
settings = sa.Table("settings", meta, sa.Column("key", sa.String(64), primary_key=True), sa.Column("value", sa.Text))
# The Logins table: a row each time a signed-in person (Email) opens a customer (View; once per customer per visit),
# adds, changes or deletes one (Create, Update, Delete: a row per customer), or signs in with no birth details yet (Login;
# once per visit): the Activity, at Date_Time (UT), from Location (where the visitor was, by IP); seen by admins only
ACTIVITIES = ("View", "Create", "Update", "Delete", "Login")
logins = sa.Table(
    "logins", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("activity", sa.String(10), nullable=False),
    sa.Column("date_time", sa.DateTime, nullable=False),
    sa.Column("location", sa.String(200)),                   # City, State, Country of the visitor's IP ("Local", or blank when unknown)
    sa.Column("device", sa.String(60)),                      # their browser and system (Chrome on Windows ..)
    sa.Column("timezone", sa.String(64)),                    # the time zone their browser is set to (Asia/Kolkata (UTC+5:30))
    sa.Column("access", sa.String(20)),                      # their Access then (DOB .., "DOB ended"; blank: none, or no record)
    sa.CheckConstraint("activity IN ('View', 'Create', 'Update', 'Delete', 'Login')", name="ck_logins_activity"),
)
sa.Index("ix_logins_date_time", logins.c.date_time)
# The Defaults table: a row per page input (Page, Options) and what it starts as (Choices); seen by admins only (the
# Defaults page). Each page reads it as it is drawn; an input with no row starts as the app's own default.
defaults = sa.Table(
    "defaults", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("page", sa.String(60), nullable=False),
    sa.Column("options", sa.String(60), nullable=False),
    sa.Column("choices", sa.String(500)),
)
DEFAULTS_INDEX = "ux_defaults_page_options"                   # one row per Page and Options
sa.Index(DEFAULTS_INDEX, defaults.c.page, defaults.c.options, unique=True)
DEFAULT_ROWS = [                                              # the app's own defaults: the rows the table starts with
    ("AstroClock-2D", "Time", "Now"),
    ("AstroClock-2D", "Planets", "Su, Mo, Me, Ve, Ma, Ju, Sa, NN, SN"),
    ("AstroClock-2D", "Major Aspects", ""),
    ("AstroClock-2D", "Minor Aspects", ""),
    ("AstroClock-2D", "House", "On"),
    ("AstroClock-2D", "Rotate in 1s", ""),
    ("AstroClock-3D", "Time", "Now"),
    ("AstroClock-3D", "Planets", "Mo, Su, Me, Ve, Ma, Ju, Sa, NN, SN"),
    ("AstroClock-3D", "Planet Path", "Su"),
    ("AstroClock-3D", "Major Aspects", ""),
    ("AstroClock-3D", "Minor Aspects", ""),
    ("AstroClock-3D", "Coordinates", "Celes"),
    ("AstroClock-3D", "Rotate in 1s", "Manual"),
    ("Geo/Helio Model", "Centric Model", "Geo"),
    ("Geo/Helio Model", "Geo Time", "Now"),
    ("Geo/Helio Model", "Geo Planets", "Mo, Su, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Geo Planet Path", "Mo, Su, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Geo Coordinates", "Fit"),
    ("Geo/Helio Model", "Geo AU", "On"),
    ("Geo/Helio Model", "Geo Rotate in 1s", "Manual"),
    ("Geo/Helio Model", "Helio Time", "Now"),
    ("Geo/Helio Model", "Helio Planets", "Mo, Ea, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Helio Planet Path", "Mo, Ea, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Helio Coordinates", "Fit"),
    ("Geo/Helio Model", "Helio AU", "On"),
    ("Geo/Helio Model", "Helio Rotate in 1s", "Manual"),
    ("Aspects", "Start Date (UT)", "DOB"),
    ("Aspects", "End Date (UT)", "Start Date (UT) + 5 days"),
    ("Aspects", "Planets", "Ju, Sa"),
    ("Aspects", "Aspects", "Major Aspects, Minor Aspects"),
    ("Aspects", "Major Aspects", "0, 60, 90, 120, 180"),
    ("Aspects", "Minor Aspects", "30, 45, 72, 135, 144, 150"),
    ("Planets Cycles", "Start Date (UT)", "DOB"),
    ("Planets Cycles", "End Date (UT)", "Start Date (UT) + 30 years"),
    ("Planets Cycles", "Planets", "Ju, Sa"),
    ("Planets Cycles", "Major Aspects", "0, 180"),
    ("Planets Cycles", "Minor Aspects", ""),
    ("Planets Distance(%)", "Start Date (UT)", "DOB"),
    ("Planets Distance(%)", "End Date (UT)", "Start Date (UT) + 2 years"),
    ("Planets Distance(%)", "Planets", "Ju, Sa"),
]
DEFAULTS_VERSION = "5"                                        # 5: AstroClock-2D's aspects; 4: Aspects' angles; 3: AstroClock-2D's rows; 2: rows for every input; 1: the End Dates only
planets = sa.Table(                                           # seen by admins only (the Symbols page)
    "naming_conventions", meta,
    sa.Column("sn", sa.String(8), primary_key=True),
    sa.Column("symbol", sa.String(8)),                        # the conventional symbol, as text, for people; the charts draw their own
    sa.Column("name", sa.String(60)),
    sa.Column("color", sa.String(40)),
    sa.Column("color_name", sa.String(40)),                   # free text, for people; the charts use color
    sa.Column("size_clock_3d", sa.String(40)),                   # how the AstroClock-3D chart sizes it: Size_Clock-3D
    sa.Column("size", sa.String(40)),                         # how the GeoCentric chart sizes it: Size_Geo
    sa.Column("size_helio", sa.String(40)),                   # how the HelioCentric chart sizes it: Size_Helio
    sa.Column("size_clock_2d", sa.String(40)),                   # how the AstroClock-2D chart sizes it: Size_Clock-2D
)
# The Aspect Rules table: a row per aspect, with its RA orb and its Dec orb per planet (-RA, -De); pos keeps the order shown
ORB_COLUMNS = [c for c in core.default_orb_table().columns if c not in ("Aspect", "Angle")]
aspect_details = sa.Table(
    "aspect_details", meta,
    sa.Column("angle", sa.Float, primary_key=True),
    sa.Column("pos", sa.Integer, nullable=False),
    sa.Column("aspect", sa.String(60), nullable=False),
    *[sa.Column(c.lower().replace("-", "_"), sa.Float) for c in ORB_COLUMNS],
)
PLANET_NAMES = {"Su": "Sun", "Mo": "Moon", "Me": "Mercury", "Ve": "Venus", "Ma": "Mars", "Ju": "Jupiter", "Sa": "Saturn",
                "Ea": "Earth", "NN": "Moon's North Node", "SN": "Moon's South Node", "CN": "Place Now", "CB": "Birth Place"}
SYMBOLS = {"Su": "☉", "Mo": "☽", "Me": "☿", "Ve": "♀", "Ma": "♂", "Ju": "♃", "Sa": "♄", "Ea": "⊕",
           "NN": "☊", "SN": "☋", "CB": "👶", "CN": "🏠"}
POINT_ROWS = ("Ea", "NN", "SN", "CN", "CB")                         # the rows that are not bodies; always in the table
COLOUR_NAMES = {"rgb(255,0,0)": "Red", "rgb(112,48,160)": "Purple", "rgb(255,165,0)": "Orange", "rgb(0,176,80)": "Green",
                "rgb(146,208,80)": "Light Green", "rgb(0,112,192)": "Blue", "rgb(0,176,240)": "Light Blue",
                "rgb(90,140,200)": "Steel Blue", "rgb(0,0,0)": "Black",
                # the recommended ones
                "rgb(230,159,0)": "Gold", "rgb(140,140,150)": "Silver", "rgb(86,180,233)": "Sky Blue", "rgb(0,158,115)": "Green",
                "rgb(213,94,0)": "Vermilion Red", "rgb(120,60,160)": "Purple", "rgb(120,80,40)": "Brown", "rgb(0,114,178)": "Earth Blue",
                "rgb(204,121,167)": "Rose", "rgb(102,102,153)": "Slate", "rgb(0,60,140)": "Navy"}
RECOMMENDED_COLOURS = "colours_recommended_2026_11"   # the settings key that marks they were set once (later edits stay)


def _now():
    """Now, in UT, to the second (the time stamps are kept without a time zone, as UT)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _secret(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:          # no secrets file at all
        return default


@st.cache_resource
def engine() -> sa.Engine:
    url = _secret("db_url")
    if not url:
        (ROOT / "private").mkdir(exist_ok=True)
        url = f"sqlite:///{(ROOT / 'private' / 'app.db').as_posix()}"
    eng = sa.create_engine(url, pool_pre_ping=True)
    _rename_planets_table(eng)
    _rename_logins_operation(eng)
    _rename_defaults_options(eng)
    meta.create_all(eng)
    _allow_login_activity(eng)
    _add_logins_columns(eng)
    _add_missing_columns(eng)
    _drop_owner_column(eng)
    _add_account_end_date(eng)
    _seed_account_fields(eng)
    _new_access_names(eng)
    _seed_accounts(eng)
    _one_day_from_today(eng)
    _link_dob_emails(eng)
    _rename_planet_columns(eng)
    _rename_planet_size_columns(eng)
    _add_planet_color_name(eng)
    _add_planet_size(eng)
    _add_planet_size_helio(eng)
    _add_planet_size_globe(eng)
    _add_planet_size_clock(eng)
    _add_planet_symbol(eng)
    _update_earth_symbol(eng)
    _set_recommended_colours(eng)
    _seed_planets(eng)
    _add_orb_nn_ra(eng)
    _seed_aspect_details(eng)
    _add_orb_dec(eng)
    _rename_defaults_page(eng)
    _add_defaults_index(eng)
    _seed_defaults(eng)
    _set_time_now(eng)
    return eng


def _allow_login_activity(eng: sa.Engine):
    """A Logins table made before the Login activity gets its check widened to allow it (its rows kept)."""
    checks = [ck for ck in sa.inspect(eng).get_check_constraints("logins") if "'View'" in (ck.get("sqltext") or "")]
    if not checks or all("'Login'" in ck["sqltext"] for ck in checks):
        return
    rule = "activity IN ('View', 'Create', 'Update', 'Delete', 'Login')"
    with eng.begin() as c:
        if eng.dialect.name == "sqlite":                      # SQLite cannot change a check: the table is made again
            c.execute(sa.text("DROP INDEX IF EXISTS ix_logins_date_time"))
            c.execute(sa.text("ALTER TABLE logins RENAME TO logins_before_login"))
            logins.create(c)
            c.execute(sa.text("INSERT INTO logins (id, email, activity, date_time) "
                              "SELECT id, email, activity, date_time FROM logins_before_login"))
            c.execute(sa.text("DROP TABLE logins_before_login"))
        else:
            for ck in checks:
                c.execute(sa.text(f'ALTER TABLE logins DROP CONSTRAINT "{ck["name"]}"'))
            c.execute(sa.text(f"ALTER TABLE logins ADD CONSTRAINT ck_logins_activity CHECK ({rule})"))


def _add_logins_columns(eng: sa.Engine):
    """A Logins table made before the Location, Device, Time zone and Access columns gets them (its rows kept, blank in
    them)."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("logins")}
    with eng.begin() as c:
        for col in ("location", "device", "timezone", "access"):
            if col not in have:
                c.execute(sa.text(f"ALTER TABLE logins ADD COLUMN {col} {logins.c[col].type.compile(dialect=eng.dialect)}"))


def _rename_logins_operation(eng: sa.Engine):
    """A Logins table made with an operation column has it renamed activity (its rows and check kept)."""
    if not sa.inspect(eng).has_table("logins"):
        return
    if "operation" in {c["name"] for c in sa.inspect(eng).get_columns("logins")}:
        with eng.begin() as c:
            c.execute(sa.text("ALTER TABLE logins RENAME COLUMN operation TO activity"))


def _rename_defaults_options(eng: sa.Engine):
    """A Defaults table made with Page, Title, Options gets the names Page, Options, Choices: its options column is
    renamed choices, then its title column options (rows kept)."""
    if not sa.inspect(eng).has_table("defaults"):
        return
    have = {c["name"] for c in sa.inspect(eng).get_columns("defaults")}
    if "title" in have:
        with eng.begin() as c:
            if "options" in have:
                c.execute(sa.text("ALTER TABLE defaults RENAME COLUMN options TO choices"))
            c.execute(sa.text("ALTER TABLE defaults RENAME COLUMN title TO options"))


def _add_defaults_index(eng: sa.Engine):
    """A Defaults table made before the unique index on Page and Options gets it (it already had a rule allowing no two the same)."""
    with eng.begin() as c:
        c.execute(sa.text(f"CREATE UNIQUE INDEX IF NOT EXISTS {DEFAULTS_INDEX} ON defaults (page, options)"))


def _rename_defaults_page(eng: sa.Engine):
    """The Defaults rows of pages since renamed get the new names (their Choices kept)."""
    with eng.begin() as c:
        for old, new in (("astroglobe", "AstroClock-3D"), ("geo/helio", "Geo/Helio Model"), ("aspects", "Aspects"), ("aspects table", "Aspects")):
            if old != new.lower():                            # a row the new name already has wins (Page and Options are unique)
                taken = sa.select(sa.func.lower(defaults.c.options)).where(sa.func.lower(defaults.c.page) == new.lower())
                c.execute(defaults.delete().where(sa.func.lower(defaults.c.page) == old, sa.func.lower(defaults.c.options).in_(taken)))
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == old).values(page=new))
        c.execute(defaults.update().where(defaults.c.page == "Planets Cycles", defaults.c.options == "Major Aspects")   # its buttons have no degree sign now
                  .values(choices=sa.func.replace(defaults.c.choices, "\u00b0", "")))
        for old, new in (("maj aspects", "Major Aspects"), ("min aspects", "Minor Aspects")):   # and the inputs since renamed
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == "astroclock-3d", sa.func.lower(defaults.c.options) == old).values(options=new))
        c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == "astroclock-2d", sa.func.lower(defaults.c.options) == "rotate in 1s",
                                          sa.func.lower(defaults.c.choices) == "manual").values(choices=None))   # AstroClock-2D has no Manual now
        c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == "astroclock-2d", sa.func.lower(defaults.c.options) == "houses")
                  .values(options="House"))                   # its button is House now
        for old, new in (("geo scale", "Geo Coordinates"), ("helio scale", "Helio Coordinates")):
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == "geo/helio model", sa.func.lower(defaults.c.options) == old).values(options=new))


NEW_IN_4 = (("Aspects", "Major Aspects"), ("Aspects", "Minor Aspects"), ("Planets Cycles", "Minor Aspects"))
NEW_IN_5 = (("AstroClock-2D", "Major Aspects"), ("AstroClock-2D", "Minor Aspects"))


TIME_ROWS = (("astroclock-2d", "time"), ("astroclock-3d", "time"), ("geo/helio model", "geo time"), ("geo/helio model", "helio time"))


def _set_time_now(eng: sa.Engine):
    """Once (a note among the settings says it is done, so a Time changed since stays as it is): every page's Time row of
    the Defaults table starts as Now."""
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "time_now_set")).scalar():
            return
        for page, title in TIME_ROWS:
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == page, sa.func.lower(defaults.c.options) == title)
                      .values(choices="Now"))
        c.execute(settings.insert().values(key="time_now_set", value="1"))


def _seed_defaults(eng: sa.Engine):
    """The Defaults table gets the rows of DEFAULT_ROWS it lacks, once per DEFAULTS_VERSION (a note among the settings says
    which, so a row deleted since stays deleted); rows already there are left as they are."""
    with eng.begin() as c:
        done = c.execute(sa.select(settings.c.value).where(settings.c.key == "defaults_seeded")).scalar()
        if done == DEFAULTS_VERSION:
            return
        have = {(p.lower(), t.lower()) for p, t in c.execute(sa.select(defaults.c.page, defaults.c.options)).all()}
        added_since = {"2": lambda r: r[0] == "AstroClock-2D" or r[:2] in NEW_IN_4, "3": lambda r: r[:2] in NEW_IN_4 + NEW_IN_5, "4": lambda r: r[:2] in NEW_IN_5}
        wanted = [r for r in DEFAULT_ROWS if added_since[done](r)] if done in added_since else DEFAULT_ROWS   # (a row deleted before stays deleted)
        new = [dict(page=p, options=t, choices=o or None) for p, t, o in wanted if (p.lower(), t.lower()) not in have]
        if new:
            c.execute(defaults.insert(), new)
        if done is None:
            c.execute(settings.insert().values(key="defaults_seeded", value=DEFAULTS_VERSION))
        else:
            c.execute(settings.update().where(settings.c.key == "defaults_seeded").values(value=DEFAULTS_VERSION))


# ---------------------------------------------------------------- the Defaults table
def defaults_table() -> pd.DataFrame:
    """The Defaults table: Page, Options, Choices, sorted by Page, then Options, then Choices (case aside)."""
    with engine().connect() as c:
        rows = c.execute(sa.select(defaults).order_by(sa.func.lower(defaults.c.page), sa.func.lower(defaults.c.options),
                                                      sa.func.lower(sa.func.coalesce(defaults.c.choices, "")))).mappings().all()
    return pd.DataFrame([{"Page": r["page"], "Options": r["options"], "Choices": r["choices"]} for r in rows],
                        columns=["Page", "Options", "Choices"])


def defaults_map() -> dict[tuple[str, str], str]:
    """The Defaults table's Choices by its Page and Options, both in lower case."""
    with engine().connect() as c:
        rows = c.execute(sa.select(defaults.c.page, defaults.c.options, defaults.c.choices)).all()
    return {(p.strip().lower(), t.strip().lower()): o or "" for p, t, o in rows}


def defaults_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the Defaults rows: each needs a Page and Options (at most 60 characters), one row per Page and
    Options, and Choices of at most 500 characters. A wholly empty row does not count."""
    out, seen = [], set()
    for _, r in rows.iterrows():
        page, title, options = _cell(r["Page"]), _cell(r["Options"]), _cell(r["Choices"])
        if not (page or title or options):
            continue
        label = f"{page or 'New row'} / {title}" if title else (page or "New row")
        if not page:
            out.append(f"{label}: Page is empty")
        if not title:
            out.append(f"{label}: Options is empty")
        if len(page) > 60 or len(title) > 60:
            out.append(f"{label}: Page and Options can be at most 60 characters")
        if len(options) > 500:
            out.append(f"{label}: Choices can be at most 500 characters")
        if page and title:
            if (page.lower(), title.lower()) in seen:
                out.append(f"{label}: is in the table twice")
            seen.add((page.lower(), title.lower()))
    return out


def save_defaults(rows: pd.DataFrame) -> int:
    """Makes the Defaults table these rows (wholly empty ones left out); gives how many it has."""
    keep = [dict(page=_cell(r["Page"]), options=_cell(r["Options"]), choices=_cell(r["Choices"]) or None)
            for _, r in rows.iterrows() if _cell(r["Page"]) or _cell(r["Options"]) or _cell(r["Choices"])]
    with engine().begin() as c:
        c.execute(sa.delete(defaults))
        if keep:
            c.execute(defaults.insert(), keep)
    return len(keep)


def _add_orb_nn_ra(eng: sa.Engine):
    """An Aspect Rules table made before its NN-RA and SN-RA columns gets them, each row as its Ju-RA (as the defaults have them)."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("aspect_details")}
    with eng.begin() as c:
        for col, like in (("nn_ra", "ju_ra"), ("sn_ra", "ju_ra")):
            if col not in have:
                kind = aspect_details.c[col].type.compile(dialect=eng.dialect)
                c.execute(sa.text(f"ALTER TABLE aspect_details ADD COLUMN {col} {kind}"))
                c.execute(sa.text(f"UPDATE aspect_details SET {col} = {like}"))


def _add_orb_dec(eng: sa.Engine):
    """Once (a note among the settings says it is done): the Aspect Rules table gets its Dec orbs back (Mo-De .. SN-De),
    each as its RA orb, so that the aspects found stay as they were (old Dec orbs kept in the table are replaced)."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("aspect_details")}
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "dec_orbs_set")).scalar():
            return
        for col in [k.lower().replace("-", "_") for k in ORB_COLUMNS if k.endswith("-De")]:
            if col not in have:
                c.execute(sa.text(f"ALTER TABLE aspect_details ADD COLUMN {col} {aspect_details.c[col].type.compile(dialect=eng.dialect)}"))
            c.execute(sa.text(f"UPDATE aspect_details SET {col} = {col[:-3]}_ra"))
        c.execute(settings.insert().values(key="dec_orbs_set", value="1"))


def _seed_aspect_details(eng: sa.Engine):
    """The Aspect Rules table, when empty, starts from the orbs kept as text among the settings before it existed
    (that text stays until the table is next saved), or else from the defaults."""
    with eng.begin() as c:
        if c.execute(sa.select(sa.func.count()).select_from(aspect_details)).scalar():
            return
        kept = c.execute(sa.select(settings.c.value).where(settings.c.key == "orbs")).scalar()
        table = pd.read_csv(io.StringIO(kept)) if kept else core.default_orb_table()
        rows = _orb_rows(table.dropna(subset=["Angle"]).drop_duplicates("Angle"))
        if rows:
            c.execute(aspect_details.insert(), rows)


def _orb_rows(table: pd.DataFrame) -> list[dict]:
    rows = []
    for pos, (_, r) in enumerate(table.iterrows()):
        row = {"angle": float(r["Angle"]), "pos": pos, "aspect": str(r["Aspect"]).strip()}
        for c in ORB_COLUMNS:
            v = pd.to_numeric(r.get(c), errors="coerce")
            row[c.lower().replace("-", "_")] = None if pd.isna(v) else float(v)
        rows.append(row)
    return rows


def _rename_planets_table(eng: sa.Engine):
    """A store made when this table was called planets gets the new name; its rows stay."""
    have = set(sa.inspect(eng).get_table_names())
    if "planets" in have and "naming_conventions" not in have:
        with eng.begin() as c:
            c.execute(sa.text("ALTER TABLE planets RENAME TO naming_conventions"))


def _rename_planet_columns(eng: sa.Engine):
    """A table made with earlier column names gets the new ones; its rows stay."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}
    with eng.begin() as c:
        for old, new in (("planet", "sn"), ("desc", "name"), ("s_name", "sn"), ("l_name", "name")):
            if old in have:
                c.execute(sa.text(f'ALTER TABLE naming_conventions RENAME COLUMN "{old}" TO {new}'))


def _rename_planet_size_columns(eng: sa.Engine):
    """A table with the columns size_globe and size_clock has them renamed size_clock_3d and size_clock_2d (rows kept)."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}
    with eng.begin() as c:
        for old, new in (("size_clock", "size_clock_2d"), ("size_globe", "size_clock_3d")):
            if old in have:
                c.execute(sa.text(f"ALTER TABLE naming_conventions RENAME COLUMN {old} TO {new}"))


def _add_planet_color_name(eng: sa.Engine):
    """A table made before Color_Name gets it, named for the colours the charts start with; others stay blank."""
    if "color_name" in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        return
    with eng.begin() as c:
        c.execute(sa.text("ALTER TABLE naming_conventions ADD COLUMN color_name VARCHAR(40)"))
        for colour, name in COLOUR_NAMES.items():
            c.execute(planets.update().where(planets.c.color == colour).values(color_name=name))


def _add_planet_size(eng: sa.Engine):
    """A table made before Size gets it, blank. One where Size was a number has it as text, its values kept (5.0 as 5)."""
    kind = planets.c.size.type.compile(dialect=eng.dialect)
    have = {c["name"]: c["type"] for c in sa.inspect(eng).get_columns("naming_conventions")}
    if "size" not in have:
        with eng.begin() as c:
            c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN size {kind}"))
    elif not isinstance(have["size"], sa.String):
        with eng.begin() as c:
            c.execute(sa.text("ALTER TABLE naming_conventions RENAME COLUMN size TO size_number"))
            c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN size {kind}"))
            for sn, number in c.execute(sa.text("SELECT sn, size_number FROM naming_conventions WHERE size_number IS NOT NULL")).all():
                c.execute(planets.update().where(planets.c.sn == sn).values(size=f"{number:g}"))
            c.execute(sa.text("ALTER TABLE naming_conventions DROP COLUMN size_number"))


def _add_planet_size_helio(eng: sa.Engine):
    """A table made before Size_Helio gets it, each row as its Size_Geo, the Moon Tiny (as HelioCentric drew them then)."""
    if "size_helio" in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        return
    kind = planets.c.size_helio.type.compile(dialect=eng.dialect)
    with eng.begin() as c:
        c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN size_helio {kind}"))
        c.execute(sa.text("UPDATE naming_conventions SET size_helio = size"))
        c.execute(planets.update().where(planets.c.sn == "Mo").values(size_helio="Tiny"))


def _add_planet_size_globe(eng: sa.Engine):
    """A table made before Size_Clock-3D gets it, each row as its Size_Geo (as AstroClock-3D drew them then)."""
    if "size_clock_3d" in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        return
    kind = planets.c.size_clock_3d.type.compile(dialect=eng.dialect)
    with eng.begin() as c:
        c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN size_clock_3d {kind}"))
        c.execute(sa.text("UPDATE naming_conventions SET size_clock_3d = size"))


def _add_planet_size_clock(eng: sa.Engine):
    """A table made before Size_Clock-2D gets it, each row as its Size_Geo (as AstroClock-2D drew them then)."""
    if "size_clock_2d" in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        return
    kind = planets.c.size_clock_2d.type.compile(dialect=eng.dialect)
    with eng.begin() as c:
        c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN size_clock_2d {kind}"))
        c.execute(sa.text("UPDATE naming_conventions SET size_clock_2d = size"))


def _add_planet_symbol(eng: sa.Engine):
    """A table made before Symbol gets it, filled in for the rows that have a conventional one; others stay blank."""
    if "symbol" in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        return
    with eng.begin() as c:
        c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN symbol {planets.c.symbol.type.compile(dialect=eng.dialect)}"))
        for sn, symbol in SYMBOLS.items():
            c.execute(planets.update().where(planets.c.sn == sn).values(symbol=symbol))


def _set_recommended_colours(eng: sa.Engine):
    """Once (marked among the settings): every row the charts colour gets the recommended Color and its Color_Name. Any change an
    admin makes afterwards stays."""
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == RECOMMENDED_COLOURS)).scalar():
            return
        for sn, colour in core.COLOURS.items():
            c.execute(planets.update().where(planets.c.sn == sn).values(color=colour, color_name=COLOUR_NAMES[colour]))
        c.execute(sa.insert(settings).values(key=RECOMMENDED_COLOURS, value="done"))


def _update_earth_symbol(eng: sa.Engine):
    """The Earth's symbol is now the circled plus: a table still with the earlier one (U+2641) gets it; one an admin has changed keeps theirs."""
    with eng.begin() as c:
        c.execute(planets.update().where(planets.c.sn == "Ea", planets.c.symbol == chr(0x2641)).values(symbol=SYMBOLS["Ea"]))


def _seed_planets(eng: sa.Engine):
    """The table, when empty, starts with every row in the colours the charts use. A table made earlier gets the
    rows it lacks of Ea, NN, SN (in its Moon's colour, as they were drawn), CN and CB."""
    with eng.begin() as c:
        rows = dict(c.execute(sa.select(planets.c.sn, planets.c.color)).all())
        wanted = PLANET_NAMES if not rows else POINT_ROWS
        new = [{"sn": p, "name": PLANET_NAMES[p],
                "color": core.colour(p)}
               for p in wanted if p not in rows]
        for row in new:
            row["color_name"] = COLOUR_NAMES.get(row["color"])
            row["symbol"] = SYMBOLS.get(row["sn"])
            row["size"] = "Angular Size" if row["sn"] in core.PLANET_ID else None   # the Earth: as its Size says, none given
            row["size_helio"] = "Tiny" if row["sn"] == "Mo" else row["size"]         # the Moon round the Earth: a dot
            row["size_clock_3d"] = row["size"]
            row["size_clock_2d"] = row["size"]
        if new:
            c.execute(planets.insert(), new)


def all_planets() -> pd.DataFrame:
    """The Symbols table: SN, Symbol, Name, Color, Color_Name, Size_Clock-3D, Size (Size_Geo), Size_Helio, Size_Clock-2D, Sun first."""
    with engine().connect() as c:
        rows = c.execute(sa.select(planets)).mappings().all()
    order = {p: i for i, p in enumerate(PLANET_NAMES)}
    rows = sorted(rows, key=lambda r: order.get(r["sn"], len(order)))
    return pd.DataFrame([{"SN": r["sn"], "Symbol": r["symbol"], "Name": r["name"], "Color": r["color"], "Color_Name": r["color_name"], "Size_Clock-3D": r["size_clock_3d"],
                          "Size": r["size"], "Size_Helio": r["size_helio"], "Size_Clock-2D": r["size_clock_2d"]}
                         for r in rows], columns=["SN", "Symbol", "Name", "Color", "Color_Name", "Size_Clock-3D", "Size", "Size_Helio", "Size_Clock-2D"])


def planet_colours() -> dict[str, str]:
    """The Color of each row of the Symbols table, by its SN."""
    with engine().connect() as c:
        return {sn: color for sn, color in c.execute(sa.select(planets.c.sn, planets.c.color)) if color}


def planet_sizes() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """The Size (Size_Geo) of each row by its SN; its SN and Name, in lower case, to its SN (for "Bigger than Moon"); its
    Size_Helio by its SN; its Size_Clock-3D by its SN; and its Size_Clock-2D by its SN."""
    with engine().connect() as c:
        rows = c.execute(sa.select(planets.c.sn, planets.c.name, planets.c.size, planets.c.size_helio, planets.c.size_clock_3d,
                                   planets.c.size_clock_2d)).all()
    words = {w.strip().lower(): sn for sn, name, *_ in rows for w in (name, sn) if w}
    return ({sn: size or "" for sn, _, size, *_ in rows}, words, {sn: helio or "" for sn, _, _, helio, *_ in rows},
            {sn: globe or "" for sn, _, _, _, globe, _ in rows}, {sn: clock or "" for sn, *_, clock in rows})


def planet_symbols() -> dict[str, str]:
    """The Symbol of each row that has one, by its SN."""
    with engine().connect() as c:
        return {sn: symbol.strip() for sn, symbol in c.execute(sa.select(planets.c.sn, planets.c.symbol)) if symbol and symbol.strip()}


def _cell(value) -> str:
    return str(value).strip() if pd.notna(value) else ""


def planet_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the Symbols table's rows (_sn: the SN a row is kept under; blank on a new one, and a wholly empty
    new one does not count). Each needs a Name and a colour as rgb(r,g,b) or #rrggbb and an SN of up to 8 characters, unique;
    the SN of a row already in the table stays. Color_Name and Size may be blank, up to 40 characters each; Symbol may be blank, up to 8."""
    out, seen = [], set()
    words = {_cell(r[c]).lower() for _, r in rows.iterrows() for c in ("SN", "Name") if _cell(r[c])}   # what Bigger than may name
    for _, r in rows.iterrows():
        sn, name, colour, kept = _cell(r["SN"]), _cell(r["Name"]), _cell(r["Color"]), _cell(r["_sn"])
        colour_name = _cell(r["Color_Name"])
        if not (kept or sn or name or colour or colour_name or _cell(r["Size_Clock-3D"]) or _cell(r["Size"]) or _cell(r["Size_Helio"])
                or _cell(r["Size_Clock-2D"]) or _cell(r["Symbol"])):
            continue
        label = sn or kept or "New row"
        if kept and sn != kept:
            out.append(f"{kept}: the SAbr of a row already in the table cannot be changed")
        elif not sn:
            out.append("New row: SAbr is empty")
        elif len(sn) > 8:
            out.append(f"{sn}: SAbr can be at most 8 characters")
        elif sn.lower() in seen:
            out.append(f"{sn} is already in the table")
        seen.add(sn.lower())
        if not name:
            out.append(f"{label}: SDesc is empty")
        rgb = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", colour)
        if not (re.fullmatch(r"#[0-9a-fA-F]{6}", colour) or (rgb and all(int(v) <= 255 for v in rgb.groups()))):
            out.append(f"{label}: RGB must look like rgb(0,112,192) or #0070c0")
        if len(colour_name) > 40:
            out.append(f"{label}: Color can be at most 40 characters")
        for column, shown in (("Size_Clock-3D", "Size_Clock-3D"), ("Size", "Size_Geo"), ("Size_Helio", "Size_Helio"), ("Size_Clock-2D", "Size_Clock-2D")):
            if len(_cell(r[column])) > 40:
                out.append(f"{label}: {shown} can be at most 40 characters")
            elif not core.size_readable(_cell(r[column]), words):    # it would not change how anything is drawn
                out.append(f"{label}: {shown} '{_cell(r[column])}' is not one the app can use: Angular Size, Tiny, Small, a number of pixels, "
                           "or Bigger than, Smaller than or Same as another row's SAbr or SDesc")
        if len(_cell(r["Symbol"])) > 8:
            out.append(f"{label}: Symb can be at most 8 characters")
    return out


def save_planets(rows: pd.DataFrame) -> tuple[int, int, int]:
    """Makes the Symbols table these rows: (added, changed, deleted)."""
    old = {r["SN"]: (_cell(r["Name"]), _cell(r["Color"]), _cell(r["Color_Name"]), _cell(r["Size_Clock-3D"]), _cell(r["Size"]), _cell(r["Size_Helio"]),
               _cell(r["Size_Clock-2D"]), _cell(r["Symbol"])) for _, r in all_planets().iterrows()}
    added = changed = 0
    kept = {_cell(v) for v in rows["_sn"]} - {""}
    with engine().begin() as c:
        for sn in set(old) - kept:
            c.execute(planets.delete().where(planets.c.sn == sn))
        for _, r in rows.iterrows():
            sn, name, colour, was = _cell(r["SN"]), _cell(r["Name"]), _cell(r["Color"]), _cell(r["_sn"])
            colour_name = _cell(r["Color_Name"])
            size_clock_3d, size, size_helio, size_clock_2d, symbol = (_cell(r["Size_Clock-3D"]), _cell(r["Size"]), _cell(r["Size_Helio"]),
                                                                _cell(r["Size_Clock-2D"]), _cell(r["Symbol"]))
            values = dict(name=name, color=colour, color_name=colour_name or None, size_clock_3d=size_clock_3d or None, size=size or None,
                          size_helio=size_helio or None, size_clock_2d=size_clock_2d or None, symbol=symbol or None)
            if was:
                if old.get(was) != (name, colour, colour_name, size_clock_3d, size, size_helio, size_clock_2d, symbol):
                    c.execute(planets.update().where(planets.c.sn == was).values(**values))
                    changed += 1
            elif sn or name or colour or colour_name or size_clock_3d or size or size_helio or size_clock_2d or symbol:
                c.execute(planets.insert().values(sn=sn, **values))
                added += 1
    _seed_planets(engine())                                   # the rows that are always in the table come back if deleted
    return added, changed, len(set(old) - kept)


def aspect_angles() -> dict[str, float]:
    """The angle of each aspect by its name, in lower case (from the defaults): how a new row gets its Angle."""
    d = core.default_orb_table()
    return {str(a).strip().lower(): float(g) for a, g in zip(d["Aspect"], d["Angle"])}


def with_angles(rows: pd.DataFrame) -> pd.DataFrame:
    """These rows, a new one (no Angle yet) given the angle of its Aspect's name."""
    rows, angles = rows.copy(), aspect_angles()
    new = rows["Angle"].isna()
    # (a blank or unknown name stays blank: NaN, as None does not fit the number column on pandas 3)
    rows.loc[new, "Angle"] = rows.loc[new, "Aspect"].map(lambda a: angles.get(_cell(a).lower(), float("nan"))).astype(float)
    return rows


def orb_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the orb table's rows (_angle: the Angle a row is kept under; blank on a new one). Each needs an
    Aspect, a unique Angle (which stays on a row already there) and every orb a number of 0 or more."""
    out, seen = [], set()
    orbs = [c for c in rows.columns if c not in ("Aspect", "Angle", "_angle")]
    numbers = rows[orbs].apply(pd.to_numeric, errors="coerce")
    for i, r in rows.iterrows():
        aspect, kept = _cell(r["Aspect"]), r["_angle"]
        angle = pd.to_numeric(r["Angle"], errors="coerce")
        if pd.isna(kept) and not aspect and pd.isna(angle) and numbers.loc[i].isna().all():
            continue                                               # a wholly empty new row does not count
        label = aspect or "New row"
        if pd.notna(kept) and angle != kept:
            out.append(f"{label}: the Angle of a row already in the table cannot be changed")
        if not aspect:
            out.append(f"{label}: Aspect is empty")
        if aspect and pd.isna(angle):
            out.append(f"{label}: give an Angle (0 to 180), or an Aspect that is one of " + ", ".join(core.default_orb_table()["Aspect"]))
        elif pd.notna(angle) and not 0 <= angle <= 180:
            out.append(f"{label}: Angle must be a number from 0 to 180")
        elif pd.notna(angle) and angle in seen:
            out.append(f"{label}: {aspect} ({angle:g}) is already in the table")
        else:
            seen.add(angle)
        if numbers.loc[i].isna().any() or (numbers.loc[i] < 0).any():
            out.append(f"{label}: every orb must be a number of 0 or more")
    return out


def _add_missing_columns(eng: sa.Engine):
    """A store made before a column was added gets it; nothing else in it changes. The old rule of one customer per
    email (a unique index) goes: a Group's records share theirs (the DOB page checks the rest)."""
    _drop_name_unique(eng)
    have = {c["name"] for c in sa.inspect(eng).get_columns("customers")}
    with eng.begin() as c:
        for col in customers.columns:
            if col.name not in have:
                c.execute(sa.text(f"ALTER TABLE customers ADD COLUMN {col.name} "
                                  f"{col.type.compile(dialect=eng.dialect)}"))
        c.execute(sa.text("UPDATE customers SET email = NULL WHERE TRIM(email) = ''"))   # blank = none
        c.execute(sa.text(f"DROP INDEX IF EXISTS {EMAIL_INDEX}"))
        c.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email)"))


def _add_account_end_date(eng: sa.Engine):
    """A Customers table made before End Date gets it; one with the Days column (Days is only typed now, to work out
    End Date) loses that."""
    have = {col["name"] for col in sa.inspect(eng).get_columns("accounts")}
    with eng.begin() as c:
        if "end_date" not in have:
            c.execute(sa.text(f"ALTER TABLE accounts ADD COLUMN end_date {sa.DateTime().compile(dialect=eng.dialect)}"))
        if "days" in have:
            c.execute(sa.text("ALTER TABLE accounts DROP COLUMN days"))


def _new_access_names(eng: sa.Engine):
    """Access kept under an earlier name gets the new one (access.RENAMED: 1Day, DOBG, DOBT, DOBGT and the older names: DOB;
    Free ..: Now); Access_From stays. The Customers table's Access too, where a 1-day trial (access.TRIALS) gets End Date
    1 day after its Start Date (unless it has one)."""
    _drop_old_type_column(eng)
    with eng.begin() as c:
        if sa.inspect(c).has_table("accounts"):
            trials = c.execute(sa.select(accounts.c.id, accounts.c.start_date).where(
                sa.func.lower(accounts.c.access).in_([n.lower() for n in access.TRIALS]), accounts.c.end_date.is_(None))).all()
            for aid, start in trials:
                c.execute(accounts.update().where(accounts.c.id == aid).values(
                    end_date=(_stamp(start) or _now()) + timedelta(days=access.SIGNUP_DAYS)))
        for old, new in access.RENAMED.items():
            c.execute(customers.update().where(sa.func.lower(customers.c.access) == old.lower()).values(access=new))
            if sa.inspect(c).has_table("accounts"):
                c.execute(accounts.update().where(sa.func.lower(accounts.c.access) == old.lower()).values(access=new))


OLD_TYPE = "utype"                                            # the account-type column Access replaced


OLD_OWNER = "created_by"                                      # the Group Owner Email column, no longer used


def _drop_owner_column(eng: sa.Engine):
    """A store made with the Group Owner Email column (who added each record; never read) loses it."""
    with eng.begin() as c:
        if OLD_OWNER in {col["name"] for col in sa.inspect(c).get_columns("customers")}:
            c.execute(sa.text(f"ALTER TABLE customers DROP COLUMN {OLD_OWNER}"))


def _drop_old_type_column(eng: sa.Engine):
    """A store made with the account-type column Access replaced loses it; first (unless already done), a record that was
    an admin by it gets Access Admin, so that it stays an admin."""
    with eng.begin() as c:
        if OLD_TYPE not in {col["name"] for col in sa.inspect(c).get_columns("customers")}:
            return
        moved = c.execute(sa.select(settings.c.value).where(settings.c.key == f"{OLD_TYPE}_admin_moved")).scalar()
        if not moved:
            c.execute(sa.text(f"UPDATE customers SET access = 'Admin' WHERE LOWER(TRIM({OLD_TYPE})) = 'admin'"))
        c.execute(sa.text(f"ALTER TABLE customers DROP COLUMN {OLD_TYPE}"))


def _seed_account_fields(eng: sa.Engine):
    """Once (a note among the settings says it is done): the customers already here, who could see their DOB charts, get
    Access DOB, so that the Access rules take nothing from them."""
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "account_fields_set")).scalar():
            return
        c.execute(customers.update().where(customers.c.access.is_(None)).values(access="DOB"))
        c.execute(settings.insert().values(key="account_fields_set", value="1"))


def _drop_name_unique(eng: sa.Engine):
    """Stores made when First Name had to be unique lose that rule (the login email is the key); every customer and
    value is kept. SQLite cannot drop a table's rule, so its table is copied into a new one without it."""
    insp = sa.inspect(eng)
    uniq = [u for u in insp.get_unique_constraints("customers") if u["column_names"] == ["name"]]
    idx = [i for i in insp.get_indexes("customers") if i.get("unique") and i["column_names"] == ["name"]]
    if not uniq and not idx:
        return
    if eng.dialect.name == "sqlite":
        cols = [c["name"] for c in insp.get_columns("customers")]
        keep = ", ".join(c for c in cols if c in customers.c)        # columns this table has; others come later
        with eng.begin() as c:
            c.execute(sa.text(f"DROP INDEX IF EXISTS {EMAIL_INDEX}"))
            c.execute(sa.text("ALTER TABLE customers RENAME TO customers_old"))
            c.execute(sa.schema.CreateTable(customers))
            c.execute(sa.text(f"INSERT INTO customers ({keep}) SELECT {keep} FROM customers_old"))
            c.execute(sa.text("DROP TABLE customers_old"))
    else:
        with eng.begin() as c:
            for u in uniq:
                c.execute(sa.text(f'ALTER TABLE customers DROP CONSTRAINT "{u["name"]}"'))
            for i in idx:
                c.execute(sa.text(f'DROP INDEX IF EXISTS "{i["name"]}"'))


def _seed_accounts(eng: sa.Engine):
    """Once (a note among the settings says it is done): each login email of the DOB records gets a Customers row, with
    the Access and Access_From of its own (first) record, as Access and Start Date (blank Access: Now)."""
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "accounts_seeded")).scalar():
            return
        rows = c.execute(sa.text("SELECT id, email, access, access_from, added_at FROM customers WHERE email IS NOT NULL")).mappings().all()
        have = {e.lower() for (e,) in c.execute(sa.select(accounts.c.email)).all()}
        own = {}
        for r in sorted(rows, key=lambda r: int(r["id"])):    # each email's first record
            e = str(r["email"]).strip().lower()
            if e and e not in own:
                own[e] = r
        for e, r in own.items():
            if e in have:
                continue
            try:
                a = access.canonical(r["access"], access.ACCESS) or "Now"
            except ValueError:
                a = "Now"
            start = _stamp(r["access_from"]) or _stamp(r["added_at"])
            trial = str(r["access"] or "").strip().lower() in {n.lower() for n in access.TRIALS}
            c.execute(accounts.insert().values(email=e, access=a, start_date=start,
                                               end_date=(start or _now()) + timedelta(days=access.SIGNUP_DAYS) if trial else None))
        c.execute(settings.insert().values(key="accounts_seeded", value="1"))


def _one_day_from_today(eng: sa.Engine):
    """Once (a note among the settings says it is done), when DOB (then 1Day) came to end after 1 day: each DOB row with no
    End Date (made when it had no time limit) gets 1 day from now."""
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "one_day_from_today")).scalar():
            return
        c.execute(accounts.update().where(accounts.c.access == "DOB", accounts.c.end_date.is_(None))
                  .values(end_date=_now() + timedelta(days=access.SIGNUP_DAYS)))
        c.execute(settings.insert().values(key="one_day_from_today", value="1"))


def _ensure_accounts(c, emails, first=()) -> int:
    """The DOB records' Email refers to the Customers table: each of these emails without a Customers row gets one. A
    login's first DOB entry gives it DOB for 1 day from now: a new row, or one of first (emails with no DOB record before)
    whose Access is Now. Gives how many rows were added."""
    want = {str(e).strip().lower() for e in emails if isinstance(e, str) and e.strip()}
    have = {e.lower(): a for e, a in c.execute(sa.select(accounts.c.email, accounts.c.access)).all()}
    now = _now()
    one_day = dict(access="DOB", start_date=now, end_date=access.period_end("DOB", now))
    for e in sorted(want - set(have)):
        c.execute(accounts.insert().values(email=e, **one_day))
    for e in sorted({str(e).strip().lower() for e in first if isinstance(e, str)} & want & set(have)):
        try:
            now_only = (access.canonical(have[e], access.ACCESS) or "Now") == "Now"
        except ValueError:
            now_only = True
        if now_only:                                          # (signed in before, with no DOB record: Now)
            c.execute(accounts.update().where(accounts.c.email == e).values(**one_day))
    return len(want - set(have))


def _link_dob_emails(eng: sa.Engine):
    """Every start: a DOB record's Email with no Customers row (put there another way) gets one, with DOB for 1 day."""
    with eng.begin() as c:
        _ensure_accounts(c, [e for (e,) in c.execute(sa.select(customers.c.email)).all()])


def dob_emails_in_use(emails) -> dict[str, int]:
    """How many DOB records use each of these emails (those with none left out)."""
    want = {str(e).strip().lower() for e in emails if isinstance(e, str) and e.strip()}
    if not want:
        return {}
    with engine().connect() as c:
        rows = c.execute(sa.select(sa.func.lower(customers.c.email), sa.func.count()).where(sa.func.lower(customers.c.email).in_(want))
                         .group_by(sa.func.lower(customers.c.email))).all()
    return {e: n for e, n in rows}


def account_of(email: str) -> dict | None:
    """This login's Customers row (email, access, start_date, end_date), None when it has none."""
    if not email:
        return None
    with engine().connect() as c:
        r = c.execute(sa.select(accounts).where(accounts.c.email == email.lower())).mappings().first()
    return dict(r) if r else None


def ensure_account(email: str) -> dict:
    """This login's Customers row, made with Access Now and Start Date now when it has none (on their first sign-in)."""
    got = account_of(email)
    if got:
        return got
    try:
        with engine().begin() as c:
            c.execute(accounts.insert().values(email=email.lower(), access="Now", start_date=_now()))
    except sa.exc.IntegrityError:                             # (made meanwhile, in another of their tabs)
        pass
    return account_of(email) or {"email": email.lower(), "access": "Now", "start_date": None}


def _set_access(c, email: str, value: str):
    """This login's Customers row gets this Access, from now (DOB: for 1 day; the row made if it has none)."""
    now = _now()
    data = dict(access=value, start_date=now, end_date=access.period_end(value, now) if value in access.LASTS else None)
    if c.execute(sa.select(accounts.c.id).where(accounts.c.email == email.lower())).first():
        c.execute(accounts.update().where(accounts.c.email == email.lower()).values(**data))
    else:
        c.execute(accounts.insert().values(email=email.lower(), **data))


def accounts_table() -> pd.DataFrame:
    """The Customers table, by Email: id, email, access, start_date, end_date."""
    with engine().connect() as c:
        return pd.read_sql(sa.select(accounts).order_by(accounts.c.email), c)


def account_problems(rows: pd.DataFrame) -> list[str]:
    """What stops these Customers rows being saved: an Email missing, used twice or not an email, or an Access not one of
    the choices."""
    out = []
    emails = [str(v).strip().lower() if isinstance(v, str) else "" for v in rows.get("email", pd.Series(dtype=object))]
    if any(not e for e in emails):
        out.append("Every row needs an Email.")
    bad = sorted({e for e in emails if e and ("@" not in e or " " in e)})
    if bad:
        out.append("Not an email: " + ", ".join(bad) + ".")
    twice = sorted({e for e in emails if e and emails.count(e) > 1})
    if twice:
        out.append("An email can have one row only. Used more than once: " + ", ".join(twice) + ".")
    def not_a_choice(v) -> bool:
        try:
            access.canonical(v, access.ACCESS)
            return False
        except ValueError:
            return True
    wrong = sorted({str(v).strip() for v in rows.get("access", pd.Series(dtype=object)).dropna() if not_a_choice(v)})
    if wrong:
        out.append(f"Access must be one of {', '.join(access.ACCESS)} (not {', '.join(wrong)}).")
    bad_days = sorted({str(v) for v in rows.get("days", pd.Series(dtype=object))
                       if not (v is None or (not isinstance(v, str) and pd.isna(v)) or (isinstance(v, str) and not v.strip()))
                       and access.whole_days(v) is None})
    bad_days += sorted({str(v) for v in rows.get("days", pd.Series(dtype=object))
                        if access.whole_days(v) is not None and access.whole_days(v) not in access.DAY_PACKS})
    if bad_days:
        out.append(f"Days must be one of {', '.join(map(str, access.DAY_PACKS))} (not {', '.join(bad_days)}).")
    return out


def apply_days(rows: pd.DataFrame) -> pd.DataFrame:
    """The Customers table's Days box, applied (on Update, and again on Commit): each row with Days typed gets Access DOB
    and its End Date extended by that many days, from its End Date while that runs, else from now (Start Date then
    now). Days is then cleared (it is not kept). Admin rows are left alone."""
    out = rows.copy()
    if "days" not in out:
        return out
    now = _now()
    for i, r in out.iterrows():
        days = access.whole_days(r.get("days"))
        try:
            a = access.canonical(r.get("access"), access.ACCESS)
        except ValueError:
            a = None
        if not days or a == "Admin":
            continue
        start, end = access.extend(r.get("start_date"), r.get("end_date"), now, days)
        out.at[i, "access"], out.at[i, "start_date"], out.at[i, "end_date"] = "DOB", pd.Timestamp(start), pd.Timestamp(end)
    out["days"] = pd.Series([pd.NA] * len(out), index=out.index, dtype="Int64")
    return out


def save_accounts(edited: pd.DataFrame, original: pd.DataFrame, by: str | None = None) -> tuple[int, int, int]:
    """Apply an edited copy of the Customers table: (added, changed, deleted). A blank Access is Now. End Date is not
    typed in: Days typed extends it (apply_days: from End Date while it runs, else from now); a row newly DOB with no
    Days gets 1 day from now; Now and Admin have none. Start Date as typed when changed (a DOB keeps its length);
    blank on a new row: now. The DOB records refer to it by Email: a changed Email is changed on
    them too, and a row whose Email DOB records still use cannot be deleted. Raises ValueError, saving nothing, on
    account_problems or such a delete."""
    problems = account_problems(edited)
    kept_ids = set(edited["id"].dropna().astype(int)) if "id" in edited else set()
    still = {str(e).strip().lower() for e in edited.get("email", pd.Series(dtype=object)) if isinstance(e, str)}
    gone = [str(r["email"]).strip().lower() for _, r in original.iterrows()
            if pd.notna(r["id"]) and int(r["id"]) not in kept_ids and str(r["email"]).strip().lower() not in still]
    used = dob_emails_in_use(gone)
    if used:
        problems.append("Not deleted: DOB records still use " + ", ".join(f"{e} ({n} record{'s' if n != 1 else ''})" for e, n in sorted(used.items()))
                        + ". Delete those records on the DOB page, or give them another Email, first.")
    if problems:
        raise ValueError(" ".join(problems))
    edited = apply_days(edited)                               # (Days typed and Commit pressed without Update: the same)
    added = changed = deleted = 0
    keep = set(edited["id"].dropna().astype(int)) if "id" in edited else set()
    now = _now()
    with engine().begin() as c:
        for aid in set(original["id"].dropna().astype(int)) - keep:
            c.execute(sa.delete(accounts).where(accounts.c.id == aid)); deleted += 1
        new, updates = [], []
        for rec in edited.to_dict("records"):
            email = str(rec.get("email")).strip().lower()
            a = access.canonical(rec.get("access"), access.ACCESS) or "Now"
            typed_start, typed_end = _stamp(rec.get("start_date")), _stamp(rec.get("end_date"))

            def period(start):                                # from start: (start, end); DOB: 1 day
                return start, access.period_end(a, start) if a in access.LASTS else None

            aid = rec.get("id")
            if aid is None or pd.isna(aid):
                if a == "DOB" and typed_end:                  # (its Days applied)
                    start, end = typed_start or now, typed_end
                else:
                    start, end = period(typed_start or now)
                new.append(dict(email=email, access=a, start_date=start, end_date=end))
                continue
            old = original[original["id"] == int(aid)]
            if old.empty:
                continue
            was = old.iloc[0]
            was_access = access.canonical(was["access"], access.ACCESS) if isinstance(was["access"], str) else None
            was_start, was_end = _stamp(was.get("start_date")), _stamp(was.get("end_date"))
            moved = "start_date" in rec and typed_start is not None and typed_start != was_start
            extended = a == "DOB" and typed_end is not None and typed_end != was_end   # (Days applied)
            if extended:
                updates.append((int(aid), dict(email=email, access=a, start_date=typed_start or was_start or now, end_date=typed_end)))
            elif a != was_access:                             # a new Access: from now (DOB: 1 day)
                start, end = period(typed_start if moved else now)
                updates.append((int(aid), dict(email=email, access=a, start_date=start, end_date=end)))
            elif moved:                                       # a new Start Date alone: a DOB keeps its length
                if a == "DOB" and was_start and was_end:
                    start, end = typed_start, typed_start + (was_end - was_start)
                else:
                    start, end = period(typed_start)
                updates.append((int(aid), dict(email=email, access=a, start_date=start, end_date=end)))
            elif email != str(was["email"]).lower():
                updates.append((int(aid), dict(email=email)))
        old_email = {aid: str(original[original["id"] == aid].iloc[0]["email"]).strip().lower() for aid, _ in updates}
        for aid, data in updates:                             # (emails let go first, so that two can swap; the DOB records too)
            c.execute(accounts.update().where(accounts.c.id == aid).values(email=f"~{aid}"))
            if data["email"] != old_email[aid]:
                c.execute(customers.update().where(sa.func.lower(customers.c.email) == old_email[aid]).values(email=f"~{aid}"))
        for aid, data in updates:
            c.execute(accounts.update().where(accounts.c.id == aid).values(**data)); changed += 1
            if data["email"] != old_email[aid]:              # the DOB records follow their login's new Email
                c.execute(customers.update().where(customers.c.email == f"~{aid}").values(email=data["email"]))
        for data in new:
            c.execute(accounts.insert().values(**data)); added += 1
        _log(c, by, "Create", added)
        _log(c, by, "Update", changed)
        _log(c, by, "Delete", deleted)
    return added, changed, deleted


def add_days(email: str, days: int) -> datetime:
    """A customer adds days to their own DOB (DOB Details: Get more days; no payment yet): counted from their End Date
    while it runs, else from now (Start Date then now too). Access becomes DOB. Gives the new End Date. Raises
    ValueError for days not in access.DAY_PACKS, or for an admin."""
    if days not in access.DAY_PACKS:
        raise ValueError(f"Days must be one of {', '.join(map(str, access.DAY_PACKS))}.")
    now = _now()
    with engine().begin() as c:
        r = c.execute(sa.select(accounts).where(accounts.c.email == email.lower())).mappings().first()
        try:
            a = access.canonical(r["access"], access.ACCESS) if r else None
        except ValueError:
            a = None
        if a == "Admin":
            raise ValueError("An admin's access has no end.")
        running = a == "DOB" and not access.ended("DOB", r["start_date"], r["end_date"], now)
        start = _stamp(r["start_date"]) if running else now
        base = access.ends_at("DOB", r["start_date"], r["end_date"], now) if running else now
        end = base + timedelta(days=days)
        data = dict(access="DOB", start_date=start, end_date=end)
        if r:
            c.execute(accounts.update().where(accounts.c.email == email.lower()).values(**data))
        else:
            c.execute(accounts.insert().values(email=email.lower(), **data))
        _log(c, email, "Update")
    return end


def has_admin_rights(email: str) -> bool:
    """Whether this login's Customers row makes them an admin (Access Admin)."""
    got = account_of(email) if email else None
    return bool(got) and access.grant(got.get("access"), got.get("start_date"), _now(), got.get("end_date")).admin


def is_local_sqlite() -> bool:
    return engine().url.get_backend_name() == "sqlite"


# ---------------------------------------------------------------- customers
def all_customers() -> pd.DataFrame:
    with engine().connect() as c:
        df = pd.read_sql(sa.select(customers).order_by(customers.c.name), c)
    return df


def customers_for(email: str) -> pd.DataFrame:
    with engine().connect() as c:
        df = pd.read_sql(sa.select(customers).where(sa.func.lower(customers.c.email) == email.lower())
                         .order_by(customers.c.name), c)
    return df


def _clean(rec: dict) -> dict:
    out = {}
    for f in FIELDS:
        v = rec.get(f)
        if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()):
            out[f] = None
        elif f in ("year", "mon", "day", "hr", "mn"):
            out[f] = int(float(v))
        elif f == "utc":
            out[f] = float(v)
        else:
            out[f] = str(v).strip()
    if out.get("email"):
        out["email"] = out["email"].lower()
    return out


BIRTH_FIELDS = ("year", "mon", "day", "hr", "mn", "country", "state", "city")   # the UTC offset depends on these
BIRTH_YEARS = (1800, 2399)                                     # what the ephemeris files and the date boxes cover
REQUIRED = {"email": "Email (login)", "name": "First Name", "last_name": "Last Name", "country": "Country",
            "state": "State", "city": "City", "country_n": "Country-N", "state_n": "State-N", "city_n": "City-N"}
# (and the birth date and time: Year, Mon, Date, Hr24, Min; on the DOB page, one Date and one Time)


def missing_required(df: pd.DataFrame) -> list[str]:
    """What each customer row lacks of the required fields, as 'who: what' (rows left wholly empty are ignored)."""
    out = []
    for i, rec in enumerate(df.to_dict("records"), start=1):
        data = _clean(rec)
        if not any(v is not None for v in data.values()):     # a new row never filled in
            continue
        lacks = [label for f, label in REQUIRED.items() if not data.get(f)]
        try:
            from datetime import date
            if not BIRTH_YEARS[0] <= date(data["year"], data["mon"], data["day"]).year <= BIRTH_YEARS[1]:
                lacks.append(f"Birth date (the year must be from {BIRTH_YEARS[0]} to {BIRTH_YEARS[1]})")
        except (TypeError, ValueError, OverflowError):
            lacks.append("Birth date")
        if (data.get("hr") is None or not 0 <= data["hr"] <= 23      # the birth time: Hr24 0-23, Min 0-59
                or data.get("mn") is None or not 0 <= data["mn"] <= 59):
            lacks.append("Birth time")
        if lacks:
            who = " ".join(x for x in (data.get("name"), data.get("last_name")) if x) or f"row {i}"
            out.append(f"{who}: {', '.join(lacks)}")
    return out


def customer_problems(rows: pd.DataFrame) -> list[str]:
    """What stops these customer rows being saved: an Access not one of the choices, or a required field missing."""
    out = []
    missing = missing_required(rows)
    if missing:
        out.append("Required for every customer: Email (login), First Name, Last Name, Country, State, City, "
                   "the birth date and time (Date, Local-Time-24hr), and Country-N, State-N, City-N. " + "; ".join(missing))
    return out


def _log(c, email: str | None, activity: str, times: int = 1):
    """Rows in the Logins table: this person did this, times times (one row per customer), now, from where they are, on
    what device, in what time zone, with what Access."""
    if email and times > 0:
        assert activity in ACTIVITIES
        now = _now()
        row = dict(email=email.lower(), activity=activity, date_time=now, location=visitor_location() or None,
                   device=visitor_device() or None, timezone=visitor_timezone() or None, access=_access_now(c, email, now))
        c.execute(logins.insert(), [row] * times)


def _access_now(c, email: str, now) -> str | None:
    """This login's Access now, for the Logins table: Admin for one in the admins secret, else their Customers row's
    (with "ended" after its End Date); None with no row."""
    admins = _secret("admins", [])
    if isinstance(admins, str):
        admins = admins.replace(";", ",").split(",")
    if email.lower() in {a.strip().lower() for a in admins if a and a.strip()}:
        return "Admin"
    r = c.execute(sa.select(accounts).where(accounts.c.email == email.lower())).mappings().first()
    if not r:
        return None
    try:
        a = access.canonical(r["access"], access.ACCESS) or "Now"
    except ValueError:
        return None
    if a in access.LASTS and access.ended(a, r["start_date"], r["end_date"], now):
        return f"{a} ended"
    return a


def log_view(email: str | None):
    """A View row in the Logins table: this person opened a customer."""
    with engine().begin() as c:
        _log(c, email, "View")


def log_login(email: str | None):
    """A Login row in the Logins table: this person signed in with no birth details yet."""
    with engine().begin() as c:
        _log(c, email, "Login")


def logins_table(limit: int = 5000) -> pd.DataFrame:
    """The Logins table, newest first (at most limit rows): Id, Email, Activity, Date_Time (UT), Location, Device,
    Time zone, Access."""
    cols = ["Id", "Email", "Activity", "Date_Time", "Location", "Device", "Time zone", "Access"]
    with engine().connect() as c:
        rows = c.execute(sa.select(logins).order_by(logins.c.date_time.desc(), logins.c.id.desc()).limit(limit)).mappings().all()
    return pd.DataFrame([{"Id": r["id"], "Email": r["email"], "Activity": r["activity"], "Date_Time": r["date_time"],
                          "Location": r["location"] or "", "Device": r["device"] or "", "Time zone": r["timezone"] or "",
                          "Access": r["access"] or ""} for r in rows], columns=cols)


def delete_logins(ids: list[int] | None = None) -> int:
    """Deletes these rows of the Logins table (by Id), or every row when ids is None; gives how many went."""
    with engine().begin() as c:
        q = sa.delete(logins)
        if ids is not None:
            q = q.where(logins.c.id.in_([int(i) for i in ids]))
        return c.execute(q).rowcount


STAMP_FIELDS = ("added_at",)                                  # times the admin may set too: Created


def _stamp(v) -> datetime | None:
    """A time from the table (to the second), None when blank."""
    if v is None or v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        t = pd.Timestamp(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    return t.tz_localize(None).to_pydatetime().replace(microsecond=0) if t.tzinfo else t.to_pydatetime().replace(microsecond=0)


def save_customers(edited: pd.DataFrame, original: pd.DataFrame, by: str | None = None) -> tuple[int, int, int]:
    """Apply an edited copy of the customers table: (added, changed, deleted). original is what that copy started from,
    so a customer who joined or changed their details since is left alone. A new birth date, time or place clears the
    kept UTC offset, to be looked up again. Raises ValueError, saving nothing, when two customers would share a login email.
    by: who did it (their email), logged in the Logins table. Created as
    edited (added_at); a new record's, left blank, is now. (Access is on the Customers table: see save_accounts.)"""
    problems = customer_problems(edited)
    if problems:
        raise ValueError(" ".join(problems))
    added = changed = deleted = 0
    keep_ids = set(edited["id"].dropna().astype(int)) if "id" in edited else set()
    now = _now()
    with engine().begin() as c:
        had = {e.strip().lower() for (e,) in c.execute(sa.select(customers.c.email).where(customers.c.email.isnot(None))).all()}   # (emails with a DOB record before)
        for cid in set(original["id"].astype(int)) - keep_ids:
            c.execute(sa.delete(customers).where(customers.c.id == cid)); deleted += 1
        new, updates = [], []
        for rec in edited.to_dict("records"):
            data = _clean(rec)
            if not data.get("name"):
                continue
            times = {f: _stamp(rec.get(f)) for f in STAMP_FIELDS if f in rec}
            cid = rec.get("id")
            if cid is None or pd.isna(cid):
                new.append((data, times))
                continue
            old = original[original["id"] == int(cid)]
            if old.empty:
                continue
            was = _clean(old.iloc[0].to_dict())
            was_times = {f: _stamp(old.iloc[0].get(f)) for f in times}
            set_times = {f: t for f, t in times.items() if t != was_times[f]}   # the times the admin changed
            if was != data or set_times:
                if any(was[f] != data[f] for f in BIRTH_FIELDS):
                    data["utc"] = None
                data.update(set_times)
                updates.append((int(cid), data, was["email"] != data["email"]))
        # emails moving between customers (two swapped, say): each first let go, as an email can be on one customer only
        for cid, _, moved in updates:
            if moved:
                c.execute(sa.update(customers).where(customers.c.id == cid).values(email=None))
        for cid, data, _ in updates:
            c.execute(sa.update(customers).where(customers.c.id == cid).values(**data, updated_at=now))
            changed += 1
        for data, times in new:
            c.execute(sa.insert(customers).values(**data, added_at=times.get("added_at") or now, updated_at=now))
            added += 1
        _ensure_accounts(c, edited["email"] if "email" in edited else [], first=set(edited.get("email", pd.Series(dtype=object)).dropna().str.strip().str.lower()) - had)   # (each Email refers to a Customers row; a first DOB entry: DOB for 1 day)
        _log(c, by, "Create", added)
        _log(c, by, "Update", changed)
        _log(c, by, "Delete", deleted)
    return added, changed, deleted


def add_own_customer(rec: dict, email: str) -> bool:
    """A new member's own record, linked to their login email (the key: one record per email), with Access DOB for
    access.SIGNUP_DAYS (1 day) from now. Returns False, saving nothing, when that email already has one (they simply
    use it)."""
    data = _clean({**rec, "email": email})
    problems = missing_required(pd.DataFrame([data]))      # the same rule as the DOB page's table
    if problems:
        raise ValueError("Missing: " + problems[0].split(": ", 1)[-1])
    with engine().begin() as c:
        if c.execute(sa.select(customers.c.id).where(sa.func.lower(customers.c.email) == data["email"])).first():
            return False
        now = _now()
        c.execute(sa.insert(customers).values(**data, added_at=now, updated_at=now, accessed_at=now))
        _set_access(c, email, "DOB")                      # DOB: 1 day, from now
        _log(c, email, "Create")
    return True


def add_person(rec: dict, email: str) -> int:
    """A person a member with DOB adds under their login: their email, added by them, no
    Access of its own. Returns the new record's id. Raises ValueError, saving nothing, when a field is missing."""
    data = _clean({**rec, "email": email})
    problems = missing_required(pd.DataFrame([data]))
    if problems:
        raise ValueError("Missing: " + problems[0].split(": ", 1)[-1])
    now = _now()
    with engine().begin() as c:
        cid = c.execute(sa.insert(customers).values(**data, added_at=now, updated_at=now)).inserted_primary_key[0]
        _log(c, email, "Create")
    return int(cid)


def update_own_customer(rec: dict, email: str, cid: int) -> bool:
    """A member's changes to their own record cid, which must have their login email (which stays as it is; a Group's
    records share it). Returns False when it does not. The UTC offset is cleared, to be looked up again for the new birth
    time and place."""
    data = _clean({**rec, "email": email})
    problems = missing_required(pd.DataFrame([data]))      # the same rule as the DOB page's table
    if problems:
        raise ValueError("Missing: " + problems[0].split(": ", 1)[-1])
    data["utc"] = rec.get("utc")
    # only what the member's form has (and the UTC offset): columns it does not show are kept as they are; Updated is
    # set only when something they saved differs from what was there
    new = {k: v for k, v in data.items() if k in rec and k != "email"}
    with engine().begin() as c:
        where = (customers.c.id == int(cid)) & (sa.func.lower(customers.c.email) == data["email"])
        old = c.execute(sa.select(customers).where(where)).mappings().first()
        if old is None:
            return False
        before = _clean(dict(old))
        before["utc"] = old["utc"]
        if any(before.get(k) != v for k, v in new.items()):
            c.execute(sa.update(customers).where(where).values(**new, updated_at=_now()))
            _log(c, email, "Update")
    return True


def mark_accessed(email: str):
    """The customer with this login email opened their charts now (an admin looking at them does not count)."""
    if not email:
        return
    with engine().begin() as c:
        c.execute(sa.update(customers).where(sa.func.lower(customers.c.email) == email.lower())
                  .values(accessed_at=_now()))


def import_workbook_csv(raw: bytes, by: str | None = None) -> int:
    """Customers from a CSV saved from the workbook's Customers tab (Customer, Country, State, City, Other, ... City-N,
    Other-N; any column may be missing); new names only. by: who did it, logged as Create in the Logins table."""
    src = pd.read_csv(io.BytesIO(raw), dtype=str)
    back = {v.split(" (")[0].lower(): k for k, v in LABELS.items()}
    back["customer"] = "name"                                # the workbook's own heading for First Name
    back["others-n"] = "other_n"                             # the heading's earlier name
    src = src.rename(columns={c: back.get(str(c).strip().lower(), c) for c in src.columns})
    current = all_customers()
    have = set(current["name"].str.lower())
    used = set(current["email"].dropna().str.lower())
    had = set(used)
    n = 0
    with engine().begin() as c:
        for rec in src.to_dict("records"):
            data = _clean(rec)
            if data.get("email") in used:                    # an email already taken: imported without it
                data["email"] = None
            if data.get("name") and data["name"].lower() not in have and data["name"].lower() != "new":
                now = _now()
                c.execute(sa.insert(customers).values(**data, added_at=now, updated_at=now))
                have.add(data["name"].lower()); n += 1
                if data.get("email"):
                    used.add(data["email"])
        _ensure_accounts(c, list(used), first=used - had)  # (each Email refers to a Customers row; a first DOB entry: DOB for 1 day)
        _log(c, by, "Create", n)
    return n


# ---------------------------------------------------------------- the orb table
def orb_table() -> pd.DataFrame:
    """The Aspect Rules table, with the columns the charts read: Aspect, Angle, Mo-RA .. SN-RA."""
    with engine().connect() as c:
        rows = c.execute(sa.select(aspect_details).order_by(aspect_details.c.pos)).mappings().all()
    return pd.DataFrame([{"Aspect": r["aspect"], "Angle": r["angle"],
                          **{k: r[k.lower().replace("-", "_")] for k in ORB_COLUMNS}} for r in rows],
                        columns=["Aspect", "Angle"] + ORB_COLUMNS)


def save_orb_table(df: pd.DataFrame):
    with engine().begin() as c:
        c.execute(sa.delete(settings).where(settings.c.key == "orbs"))   # the old text, now out of date
        c.execute(sa.delete(aspect_details))
        rows = _orb_rows(df)
        if rows:
            c.execute(aspect_details.insert(), rows)
