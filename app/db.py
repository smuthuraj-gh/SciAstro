"""The private store: customers, the planets and the orbs (Aspect Rules).

The database URL comes from the secret `db_url` (e.g. a Neon or Supabase Postgres URL on Streamlit Community Cloud,
whose own disk is wiped on every restart). Without it, a local SQLite file private/app.db is used.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from astro import core

ROOT = Path(__file__).resolve().parent.parent
# the customer columns in table order; Email (login) first, as it is the key
FIELDS = ["email", "name", "last_name", "country", "state", "city", "other", "year", "mon", "day", "hr", "mn",
          "country_n", "state_n", "city_n", "other_n", "utc"]
LABELS = {"name": "First Name", "last_name": "Last Name", "email": "Email (login)", "country": "Country", "state": "State",
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
# One customer per login email (kept in lower case); blank emails are allowed for any number of customers
EMAIL_INDEX = "ux_customers_email"
sa.Index(EMAIL_INDEX, customers.c.email, unique=True)
settings = sa.Table("settings", meta, sa.Column("key", sa.String(64), primary_key=True), sa.Column("value", sa.Text))
# The Logins table: a row each time a signed-in person (Email) opens a customer (View; once per customer per visit) or
# adds, changes or deletes one (Create, Update, Delete: a row per customer): the Activity, at Date_Time (UT); seen by
# admins only
ACTIVITIES = ("View", "Create", "Update", "Delete")
logins = sa.Table(
    "logins", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("activity", sa.String(10), nullable=False),
    sa.Column("date_time", sa.DateTime, nullable=False),
    sa.CheckConstraint("activity IN ('View', 'Create', 'Update', 'Delete')", name="ck_logins_activity"),
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
    ("AstroClock-2D", "Time", "DOB"),
    ("AstroClock-2D", "Planets", "Su, Mo, Me, Ve, Ma, Ju, Sa, NN, SN"),
    ("AstroClock-2D", "Major Aspects", ""),
    ("AstroClock-2D", "Minor Aspects", ""),
    ("AstroClock-2D", "Houses", "On"),
    ("AstroClock-2D", "Rotate in 1s", "Manual"),
    ("AstroClock-3D", "Time", "DOB"),
    ("AstroClock-3D", "Planets", "Mo, Su, Me, Ve, Ma, Ju, Sa, NN, SN"),
    ("AstroClock-3D", "Planet Path", "Su"),
    ("AstroClock-3D", "Major Aspects", ""),
    ("AstroClock-3D", "Minor Aspects", ""),
    ("AstroClock-3D", "Coordinates", "Celes"),
    ("AstroClock-3D", "Rotate in 1s", "Manual"),
    ("Geo/Helio Model", "Centric Model", "Geo"),
    ("Geo/Helio Model", "Geo Time", "DOB"),
    ("Geo/Helio Model", "Geo Planets", "Mo, Su, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Geo Planet Path", "Mo, Su, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Geo Coordinates", "Fit"),
    ("Geo/Helio Model", "Geo AU", "On"),
    ("Geo/Helio Model", "Geo Rotate in 1s", "Manual"),
    ("Geo/Helio Model", "Helio Time", "DOB"),
    ("Geo/Helio Model", "Helio Planets", "Mo, Ea, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Helio Planet Path", "Mo, Ea, Me, Ve, Ma, Ju, Sa"),
    ("Geo/Helio Model", "Helio Coordinates", "Fit"),
    ("Geo/Helio Model", "Helio AU", "On"),
    ("Geo/Helio Model", "Helio Rotate in 1s", "Manual"),
    ("Aspects Table", "Start Date (UT)", "DOB"),
    ("Aspects Table", "End Date (UT)", "Start Date (UT) + 5 days"),
    ("Aspects Table", "Planets", "Ju, Sa"),
    ("Aspects Table", "Aspects", "Major Aspects, Minor Aspects"),
    ("Aspects Table", "Major Aspects", "0, 60, 90, 120, 180"),
    ("Aspects Table", "Minor Aspects", "30, 45, 72, 135, 144, 150"),
    ("Planets Cycles", "Start Date (UT)", "DOB"),
    ("Planets Cycles", "End Date (UT)", "Start Date (UT) + 30 years"),
    ("Planets Cycles", "Planets", "Ju, Sa"),
    ("Planets Cycles", "Major Aspects", "0, 180"),
    ("Planets Cycles", "Minor Aspects", ""),
    ("Planets Distance(%)", "Start Date (UT)", "DOB"),
    ("Planets Distance(%)", "End Date (UT)", "Start Date (UT) + 2 years"),
    ("Planets Distance(%)", "Planets", "Ju, Sa"),
]
DEFAULTS_VERSION = "5"                                        # 5: AstroClock-2D's aspects; 4: Aspects Table's angles; 3: AstroClock-2D's rows; 2: rows for every input; 1: the End Dates only
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
# The Aspect Rules table: a row per aspect, with its orb per planet (for RA and Dec alike); pos keeps the order shown
# (a store made when it had -De columns keeps them, unused)
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
    _add_missing_columns(eng)
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
    _rename_defaults_page(eng)
    _add_defaults_index(eng)
    _seed_defaults(eng)
    return eng


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
        for old, new in (("astroglobe", "AstroClock-3D"), ("geo/helio", "Geo/Helio Model"), ("aspects", "Aspects Table")):
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == old).values(page=new))
        c.execute(defaults.update().where(defaults.c.page == "Planets Cycles", defaults.c.options == "Major Aspects")   # its buttons have no degree sign now
                  .values(choices=sa.func.replace(defaults.c.choices, "\u00b0", "")))
        for old, new in (("maj aspects", "Major Aspects"), ("min aspects", "Minor Aspects")):   # and the inputs since renamed
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == "astroclock-3d", sa.func.lower(defaults.c.options) == old).values(options=new))
        for old, new in (("geo scale", "Geo Coordinates"), ("helio scale", "Helio Coordinates")):
            c.execute(defaults.update().where(sa.func.lower(defaults.c.page) == "geo/helio model", sa.func.lower(defaults.c.options) == old).values(options=new))


NEW_IN_4 = (("Aspects Table", "Major Aspects"), ("Aspects Table", "Minor Aspects"), ("Planets Cycles", "Minor Aspects"))
NEW_IN_5 = (("AstroClock-2D", "Major Aspects"), ("AstroClock-2D", "Minor Aspects"))


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
    rows.loc[new, "Angle"] = rows.loc[new, "Aspect"].map(lambda a: angles.get(_cell(a).lower()))
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
    """A store made before a column (or the unique email rule) was added gets it; nothing else in it changes.
    The email rule is added only if no two customers already share an email (the Customers page checks too)."""
    _drop_name_unique(eng)
    have = {c["name"] for c in sa.inspect(eng).get_columns("customers")}
    with eng.begin() as c:
        for col in customers.columns:
            if col.name not in have:
                c.execute(sa.text(f"ALTER TABLE customers ADD COLUMN {col.name} "
                                  f"{col.type.compile(dialect=eng.dialect)}"))
        c.execute(sa.text("UPDATE customers SET email = NULL WHERE TRIM(email) = ''"))   # blank = none
        shared = c.execute(sa.text("SELECT COUNT(*) FROM (SELECT LOWER(email) FROM customers WHERE email IS NOT NULL "
                                   "GROUP BY LOWER(email) HAVING COUNT(*) > 1) d")).scalar()
        if not shared:
            c.execute(sa.text(f"CREATE UNIQUE INDEX IF NOT EXISTS {EMAIL_INDEX} ON customers (email)"))


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


def shared_emails(df: pd.DataFrame) -> list[str]:
    """Login emails given to more than one customer in a table (ignoring case and blanks)."""
    e = df["email"].dropna().astype(str).str.strip().str.lower()
    e = e[e != ""]
    return sorted(e[e.duplicated()].unique())


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
# (and the birth date and time: Year, Mon, Date, Hr24, Min)


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
        if data.get("hr") is None or not 0 <= data["hr"] <= 23:     # the birth time: Hr24 0-23, Min 0-59
            lacks.append("Hr24")
        if data.get("mn") is None or not 0 <= data["mn"] <= 59:
            lacks.append("Min")
        if lacks:
            who = " ".join(x for x in (data.get("name"), data.get("last_name")) if x) or f"row {i}"
            out.append(f"{who}: {', '.join(lacks)}")
    return out


def customer_problems(rows: pd.DataFrame) -> list[str]:
    """What stops these customer rows being saved: a login email used twice, or a required field missing."""
    out = []
    dup = shared_emails(rows)
    if dup:
        out.append("Each login email can belong to one customer only. Used more than once: " + ", ".join(dup))
    missing = missing_required(rows)
    if missing:
        out.append("Required for every customer: Email (login), First Name, Last Name, Country, State, City, "
                   "the birth date and time (Year, Mon, Date, Hr24, Min), and Country-N, State-N, City-N. " + "; ".join(missing))
    return out


def _log(c, email: str | None, activity: str, times: int = 1):
    """Rows in the Logins table: this person did this, times times (one row per customer), now."""
    if email and times > 0:
        assert activity in ACTIVITIES
        now = _now()
        c.execute(logins.insert(), [dict(email=email.lower(), activity=activity, date_time=now)] * times)


def log_view(email: str | None):
    """A View row in the Logins table: this person opened a customer."""
    with engine().begin() as c:
        _log(c, email, "View")


def logins_table(limit: int = 5000) -> pd.DataFrame:
    """The Logins table, newest first (at most limit rows): Id, Email, Activity, Date_Time (UT)."""
    with engine().connect() as c:
        rows = c.execute(sa.select(logins).order_by(logins.c.date_time.desc(), logins.c.id.desc()).limit(limit)).mappings().all()
    return pd.DataFrame([{"Id": r["id"], "Email": r["email"], "Activity": r["activity"], "Date_Time": r["date_time"]} for r in rows],
                        columns=["Id", "Email", "Activity", "Date_Time"])


def delete_logins(ids: list[int] | None = None) -> int:
    """Deletes these rows of the Logins table (by Id), or every row when ids is None; gives how many went."""
    with engine().begin() as c:
        q = sa.delete(logins)
        if ids is not None:
            q = q.where(logins.c.id.in_([int(i) for i in ids]))
        return c.execute(q).rowcount


def save_customers(edited: pd.DataFrame, original: pd.DataFrame, by: str | None = None) -> tuple[int, int, int]:
    """Apply an edited copy of the customers table: (added, changed, deleted). original is what that copy started from,
    so a customer who joined or changed their details since is left alone. A new birth date, time or place clears the
    kept UTC offset, to be looked up again. Raises ValueError, saving nothing, when two customers would share a login email.
    by: who did it (their email), logged in the Logins table."""
    problems = customer_problems(edited)
    if problems:
        raise ValueError(" ".join(problems))
    added = changed = deleted = 0
    keep_ids = set(edited["id"].dropna().astype(int)) if "id" in edited else set()
    now = _now()
    with engine().begin() as c:
        for cid in set(original["id"].astype(int)) - keep_ids:
            c.execute(sa.delete(customers).where(customers.c.id == cid)); deleted += 1
        new, updates = [], []
        for rec in edited.to_dict("records"):
            data = _clean(rec)
            if not data.get("name"):
                continue
            cid = rec.get("id")
            if cid is None or pd.isna(cid):
                new.append(data)
                continue
            old = original[original["id"] == int(cid)]
            if old.empty:
                continue
            was = _clean(old.iloc[0].to_dict())
            if was != data:
                if any(was[f] != data[f] for f in BIRTH_FIELDS):
                    data["utc"] = None
                updates.append((int(cid), data, was["email"] != data["email"]))
        # emails moving between customers (two swapped, say): each first let go, as an email can be on one customer only
        for cid, _, moved in updates:
            if moved:
                c.execute(sa.update(customers).where(customers.c.id == cid).values(email=None))
        for cid, data, _ in updates:
            c.execute(sa.update(customers).where(customers.c.id == cid).values(**data, updated_at=now))
            changed += 1
        for data in new:
            c.execute(sa.insert(customers).values(**data, added_at=now, updated_at=now))
            added += 1
        _log(c, by, "Create", added)
        _log(c, by, "Update", changed)
        _log(c, by, "Delete", deleted)
    return added, changed, deleted


def add_own_customer(rec: dict, email: str) -> bool:
    """A new member's own record, linked to their login email (the key: one record per email). Returns False, saving
    nothing, when that email already has one (they simply use it)."""
    data = _clean({**rec, "email": email})
    problems = missing_required(pd.DataFrame([data]))      # the same rule as the Customers table
    if problems:
        raise ValueError("Missing: " + problems[0].split(": ", 1)[-1])
    with engine().begin() as c:
        if c.execute(sa.select(customers.c.id).where(sa.func.lower(customers.c.email) == data["email"])).first():
            return False
        now = _now()
        c.execute(sa.insert(customers).values(**data, added_at=now, updated_at=now, accessed_at=now))
        _log(c, email, "Create")
    return True


def update_own_customer(rec: dict, email: str) -> bool:
    """A member's changes to their own record, found by their login email (which stays as it is). Returns False when
    no record has that email. The UTC offset is cleared, to be looked up again for the new birth time and place."""
    data = _clean({**rec, "email": email})
    problems = missing_required(pd.DataFrame([data]))      # the same rule as the Customers table
    if problems:
        raise ValueError("Missing: " + problems[0].split(": ", 1)[-1])
    data["utc"] = rec.get("utc")
    # only what the member's form has (and the UTC offset): columns it does not show are kept as they are; Updated is
    # set only when something they saved differs from what was there
    new = {k: v for k, v in data.items() if k in rec and k != "email"}
    with engine().begin() as c:
        where = sa.func.lower(customers.c.email) == data["email"]
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
