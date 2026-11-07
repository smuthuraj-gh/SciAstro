"""The private store: customers and the orb table.

The database URL comes from the secret `db_url` (e.g. a Neon or Supabase Postgres URL on Streamlit Community Cloud,
whose own disk is wiped on every restart). Without it, a local SQLite file private/app.db is used.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from astro import core

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["name", "last_name", "email", "country", "state", "city", "year", "mon", "day", "hr", "mn",
          "country_n", "state_n", "city_n", "utc"]
LABELS = {"name": "First Name", "last_name": "Last Name", "email": "Email (login)", "country": "Country", "state": "State", "city": "City",
          "year": "Year", "mon": "Mon", "day": "Date", "hr": "Hr24", "mn": "Min", "country_n": "Country-N",
          "state_n": "State-N", "city_n": "City-N", "utc": "UTC (blank = look up)"}

meta = sa.MetaData()
customers = sa.Table(
    "customers", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.String(120), nullable=False),       # not unique: the login email is the key
    sa.Column("last_name", sa.String(120)),
    sa.Column("email", sa.String(254)),
    sa.Column("country", sa.String(120)), sa.Column("state", sa.String(120)), sa.Column("city", sa.String(500)),
    sa.Column("year", sa.Integer), sa.Column("mon", sa.Integer), sa.Column("day", sa.Integer),
    sa.Column("hr", sa.Integer), sa.Column("mn", sa.Integer),
    sa.Column("country_n", sa.String(120)), sa.Column("state_n", sa.String(120)), sa.Column("city_n", sa.String(500)),
    sa.Column("utc", sa.Float),
)
# One customer per login email (kept in lower case); blank emails are allowed for any number of customers
EMAIL_INDEX = "ux_customers_email"
sa.Index(EMAIL_INDEX, customers.c.email, unique=True)
settings = sa.Table("settings", meta, sa.Column("key", sa.String(64), primary_key=True), sa.Column("value", sa.Text))


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
    meta.create_all(eng)
    _add_missing_columns(eng)
    return eng


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


def customer(cid: int) -> dict | None:
    with engine().connect() as c:
        row = c.execute(sa.select(customers).where(customers.c.id == cid)).mappings().first()
    return dict(row) if row else None


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


def save_customers(edited: pd.DataFrame, original: pd.DataFrame) -> tuple[int, int, int]:
    """Apply an edited copy of the customers table: (added, changed, deleted). Raises ValueError, saving nothing,
    when two customers would share a login email."""
    dup = shared_emails(edited)
    if dup:
        raise ValueError("Each login email can belong to one customer only. Used more than once: " + ", ".join(dup))
    added = changed = deleted = 0
    keep_ids = set(edited["id"].dropna().astype(int)) if "id" in edited else set()
    with engine().begin() as c:
        for cid in set(original["id"].astype(int)) - keep_ids:
            c.execute(sa.delete(customers).where(customers.c.id == cid)); deleted += 1
        for rec in edited.to_dict("records"):
            data = _clean(rec)
            if not data.get("name"):
                continue
            cid = rec.get("id")
            if cid is None or pd.isna(cid):
                c.execute(sa.insert(customers).values(**data)); added += 1
            else:
                old = original[original["id"] == int(cid)]
                if not old.empty and _clean(old.iloc[0].to_dict()) != data:
                    c.execute(sa.update(customers).where(customers.c.id == int(cid)).values(**data)); changed += 1
    return added, changed, deleted


def add_own_customer(rec: dict, email: str) -> bool:
    """A new member's own record, linked to their login email (the key: one record per email). Returns False, saving
    nothing, when that email already has one (they simply use it)."""
    data = _clean({**rec, "email": email})
    if not data.get("name") or not data.get("email"):
        raise ValueError("First Name and a login email are needed.")
    with engine().begin() as c:
        if c.execute(sa.select(customers.c.id).where(sa.func.lower(customers.c.email) == data["email"])).first():
            return False
        c.execute(sa.insert(customers).values(**data))
    return True


def import_workbook_csv(raw: bytes) -> int:
    """Customers from a CSV saved from the workbook's Customers tab (Customer, Country, ... City-N); new names only."""
    src = pd.read_csv(io.BytesIO(raw), dtype=str)
    back = {v.split(" (")[0].lower(): k for k, v in LABELS.items()}
    back["customer"] = "name"                                # the workbook's own heading for First Name
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
                c.execute(sa.insert(customers).values(**data)); have.add(data["name"].lower()); n += 1
                if data.get("email"):
                    used.add(data["email"])
    return n


# ---------------------------------------------------------------- the orb table
def orb_table() -> pd.DataFrame:
    with engine().connect() as c:
        v = c.execute(sa.select(settings.c.value).where(settings.c.key == "orbs")).scalar()
    return pd.read_csv(io.StringIO(v)) if v else core.default_orb_table()


def save_orb_table(df: pd.DataFrame):
    text = df.to_csv(index=False)
    with engine().begin() as c:
        c.execute(sa.delete(settings).where(settings.c.key == "orbs"))
        c.execute(sa.insert(settings).values(key="orbs", value=text))
