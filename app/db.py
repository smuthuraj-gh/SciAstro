"""The private store: customers, the planets and the orbs (Aspect Rules).

The database URL comes from the secret `db_url` (e.g. a Neon or Supabase Postgres URL on Streamlit Community Cloud,
whose own disk is wiped on every restart). Without it, a local SQLite file private/app.db is used.
"""
from __future__ import annotations

import functools
import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from astro import core

from . import access
from .location import visitor_device, visitor_timezone

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
# once per visit): the Activity, at Date_Time (UT), on which Device; seen by admins only (rows of earlier tables keep the
# Location and Came from they were written with, no longer shown or written)
ACTIVITIES = ("View", "Create", "Update", "Delete", "Login")
logins = sa.Table(
    "logins", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("activity", sa.String(10), nullable=False),
    sa.Column("date_time", sa.DateTime, nullable=False),
    sa.Column("device", sa.String(60)),                      # their browser and system (Chrome on Windows ..)
    sa.Column("timezone", sa.String(64)),                    # the time zone their browser is set to (Asia/Kolkata (UTC+5:30))
    sa.Column("access", sa.String(20)),                      # their Access then (DOB .., "DOB ended"; blank: none, or no record)
    sa.Column("page", sa.String(60)),                        # the page they were on (Equatorial-2D, DOB Details ..)
    sa.Column("details", sa.String(300)),                    # what was done (Get more days of access: 7 days, coupon Free ..)
    sa.CheckConstraint("activity IN ('View', 'Create', 'Update', 'Delete', 'Login')", name="ck_logins_activity"),
)
sa.Index("ix_logins_date_time", logins.c.date_time)
# The Defaults table: a row per page input and what it starts as; seen by admins only (the Defaults page), where its columns
# are shown as Page, Choice (options: the input's name) and Choice Values (choices: what
# it starts as), with Allowed Values. Each page reads it as it is drawn; an input with no row starts as the app's own default.
defaults = sa.Table(
    "defaults", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("page", sa.String(60), nullable=False),
    sa.Column("options", sa.String(60), nullable=False),
    sa.Column("choices", sa.String(500)),
    sa.Column("allowed_values", sa.String(500)),             # the values its Choice Values may be set to (blank: all the app has)
)
# The Help table: a row per abbreviation the pages use (Abbreviation) and what it means (Description); kept by admins (the Help
# page), filled once with the app's own (HELP_ROWS).
HELP_ABBR_MOST = 60                                           # an Abbreviation's most characters (20 once: see _widen_help_abbreviation)
help_table = sa.Table(
    "help", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("abbreviation", sa.String(HELP_ABBR_MOST), nullable=False, unique=True),
    sa.Column("description", sa.String(500)),
)
HELP_ROWS_3 = [                                               # added later still: the Defaults table's columns, DOB Details' and Logins' names
    ("Choice", "Page Defaults column: the input, by its name on the page (e.g. Days); one row per Page and Choice"),
    ("Choice Values", "Page Defaults column: what the input starts as (e.g. 7; Ju, Sa; On); blank: the app's own default"),
    ("Allowed Values", "Page Defaults column: the values Choice Values may be set to, and all the page offers (e.g. 1, 7, 30; for a text box, words such as Pay, Free); blank: all"),
    ("Get more days of access", "DOB Details box: add days of DOB access with Days and Pay / Coupon"),
    ("Pay / Coupon", "DOB Details: the coupon (Free, for now) or, later, the payment for the days added"),
    ("Add days", "DOB Details button: adds the Days picked to your End Date (from now when it has passed)"),
    ("Add a DOB", "DOB Details box: a person to add under your login, with Search Only or Save and Search"),
    ("Edit a DOB", "DOB Details box: change your own birth details"),
    ("Search Only", "Add a DOB button: that person's DOB charts, not saved (a Search choice in the sidebar)"),
    ("Save and Search", "Add a DOB button: the person saved under your login, then their DOB charts"),
    ("Select all", "Logins button: ticks every row (pressed again, Unselect all: none)"),
]
HELP_OUT_OF_DATE = {
    "Ecliptic latitude": ("Systems graph right of the clock: each planet's latitude north (+) or south (-) of the ecliptic, -10 to +10 degrees, moving as time moves",),   # (its scale since -7 to +7)
    "Ho": ("House lines: twelve, 30 degrees apart from the RA of CB and of CN", "Houses, under Coordinates: on Equatorial-2D and Equatorial-3D, the house lines, twelve, 30 degrees apart from the RA of CB and of CN; on Systems, each place's Ascendant (As) and the houses H01 to H12 of each System shown: Eq, those house lines; Ec, equal houses of 30 degrees from As; Tr, Si and Op, whole signs (H01 the sign As is in); KP, the Placidus cusps", "Houses, under Coordinates: on Equatorial-2D and Equatorial-3D, the house lines, twelve, 30 degrees apart from the RA of CB and of CN; on Systems, each place's Ascendant (As) and twelve equal houses from it, H01 to H12, 30 degrees of ecliptic longitude each"),   # (Systems' Ho, the Ascendant's houses, added)
    "As": ("Ascendant: a Systems button after the Planets (on or off): each place's Ascendant (the ecliptic rising in the east there, the first house's start), a red arrow from Ea out past the rings (dashed for the DOB) with its value on each: Ec its longitude; Tr, Si and Op its sign and degree; Na its star and quarter; KP star lord / sub lord", "Ascendant: a Systems button under System (on or off): each place's Ascendant, the ecliptic rising in the east there (the first house's start), a line across the rings with its value on each: Ec its longitude, Tr, Si and Op its sign and degree, Na its star and quarter", "Ascendant: a System button on Systems (on or off): each place's Ascendant (the ecliptic rising in the east there, the first house's start), a red arrow from Ea out past the rings (dashed for the DOB) with its value on each: Ec its longitude; Tr, Si and Op its sign and degree; Na its star and quarter; KP star lord / sub lord"),   # (Systems' Help, brought up to date)
    "Eq": ("Equator: a System button on Systems (on or off; once Ho, under Coordinates): the house lines of CB and CN", "Systems button under System (on or off; once Ho, under Coordinates): the house lines of CB and CN",),   # (Systems' Help, brought up to date)
    "Ec": ("Ecliptic: a Systems button beside Tr and Si (on or off): a ring of ecliptic longitude, 0 to 360 (Tropical), round the circle, each degree at the RA it falls at",),   # (Systems' Help, brought up to date)
    "Si": ("Sidereal: System on Systems: the signs further on by the Lahiri ayanamsa at the time shown (about 24 degrees now)",),   # (Systems' Help, brought up to date)
    "Tr": ("Tropical: System on Systems: the signs from the March equinox (Aries at 0 degrees of the ecliptic)",),   # (Systems' Help, brought up to date)                                          # the Help rows' Descriptions the app once wrote, out of date since
    "Systems": ("Page: a copy of Equatorial-2D (the Geo drawing seen from above the north celestial pole, with the De and Distance(%) graphs), with its own choices and Page Defaults rows", "Page: a copy of Equatorial-2D (the Geo drawing seen from above the north celestial pole, with the De graph) without its Distance(%) graph, with its own choices and Page Defaults rows",),   # (Systems has no Distance(%) graph now)
    "System": ("Systems button, before Time: Tropical or Sidereal, one at a time", "Systems button, before Time: Tropical or Sidereal, one at a time; Tropical: a ring of the Tropical signs round the circle, each over its RA span", "Systems button, before Time: Tr (Tropical) or Si (Sidereal), one at a time: a ring of the twelve signs round the circle, each over its RA span", "Systems button, before Time: Tr (Tropical) or Si (Sidereal), one at a time: a ring of the twelve signs round the circle, each over its RA span; beside them, Ei (Ecliptic, on or off): a ring of ecliptic longitude, between the circle and the signs", "Systems button, before Time: Tr (Tropical) or Si (Sidereal), one at a time: a ring of the twelve signs round the circle, each over its RA span; beside them, Ei (Ecliptic, on or off): a ring of ecliptic longitude, between the circle and the signs; below them, Eq (on or off): the house lines of CB and CN", "Systems button, before Time: Tr (Tropical) or Si (Sidereal), one at a time: a ring of the twelve signs round the circle, each over its RA span; beside them, Ec (Ecliptic, on or off): a ring of ecliptic longitude, between the circle and the signs; below them, Eq (on or off): the house lines of CB and CN", "Systems button, before Time: Tr (Tropical) or Si (Sidereal), one at a time: a ring of the twelve signs round the circle, each over its RA span; after them, Ec (Ecliptic, on or off): a ring of ecliptic longitude, between the circle and the signs; before them, Eq (on or off): the house lines of CB and CN", "Systems buttons, before Time: Eq, Tr, Si and Ec, each on or off, their rings one on another: Eq, the house lines of CB and CN; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs", "Systems buttons, before Time: Eq, Ec, Tr and Si, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's)", "Systems buttons, before Time: Eq, Ec, Tr, Si and Vd, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Vd (Vedic), a ring of the 27 stars (nakshatras) outside them", "Systems buttons, before Time: Eq, Ec, Tr, Si and Na, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters", "Systems buttons, before Time: Eq, Ec, Tr, Si, Na and 13, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); 13, a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters", "Systems buttons, before Time: Eq, Ec, Tr, Si, 13 and Na, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); 13, a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters", "Systems buttons, before Time: Eq, Ec, Tr, Si, 13, Op and Na, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); 13, a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Op, a ring of thirteen equal signs (Ophiuchus among them) from the March equinox; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters", "Systems buttons, before Time: Eq, Ec, Tr, Si, Op and Na, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Op (Ophiuchus), a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters", "Systems buttons, before Time: Eq, Ec, Tr, Si, Op, Na and As, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Op (Ophiuchus), a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters; As, each place's Ascendant (the first house's start), a line across the rings with its value on each", "Systems buttons, before Time: Eq, Ec, As, Tr, Si, Op and Na, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Op (Ophiuchus), a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters; As, each place's Ascendant (the first house's start), a line across the rings with its value on each", "Systems buttons, before Time: Eq, Ec, As, Tr, Si, Op, Na and KP, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Op (Ophiuchus), a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters; As, each place's Ascendant (the first house's start), a line across the rings with its value on each; KP (Krishnamurti), a ring of the 27 stars with their star lords and their 243 subs by sub lord, outside all the others", "Systems buttons, after Time: Eq, Ec, As, Tr, Si, Op, Na and KP, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Op (Ophiuchus), a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters; As, each place's Ascendant (the first house's start), a line across the rings with its value on each; KP (Krishnamurti), a ring of the 27 stars with their star lords and their 243 subs by sub lord, outside all the others", "Systems buttons, after Time: Eq, Ec, As, Tr, Si, Op, Na and KP, each on or off, their rings one on another: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude, between the circle and the signs; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs round the circle, each over its RA span (Si's outside Tr's); Op (Ophiuchus), a ring of the 13 constellations on the ecliptic (Ophiuchus among them) at their IAU boundaries; Na (Nakshatra, Vedic), a ring of the 27 stars (nakshatras) outside them, each in four quarters; As, each place's Ascendant (the first house's start), a line across the rings with its value on each; KP (Krishnamurti), a ring of the 27 stars' 243 subs by sub lord, outside all the others", "Systems buttons, after Time, each on or off, their rings one on another round the circle, inner first: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude; As, each place's Ascendant, a red arrow from Ea across the rings with its value on each; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs with their lords; Op (Ophiuchus), the 13 constellations at their IAU boundaries, with their lords; Na (Nakshatra), the 27 stars, named, with their star lords and four quarters; KP (Krishnamurti), the 27 stars' 243 subs, each in its sub lord's colour with its symbol", "Systems buttons, after Time, each on or off, their rings one on another round the circle, inner first: Eq, the house lines of CB and CN; Ec (Ecliptic), a ring of ecliptic longitude; Tr (Tropical) and Si (Sidereal), each a ring of the twelve signs with their lords; Op (Ophiuchus), the 13 constellations at their IAU boundaries, with their lords; Na (Nakshatra), the 27 stars, named, with their star lords and four quarters; KP (Krishnamurti), the 27 stars' 243 subs, each in its sub lord's colour with its symbol"),   # (Tropical, then Tr, draws the signs; Sidereal, then Si, too)
    "Na": ("Vedic: a Systems button under System (on or off): a ring of the 27 stars (nakshatras), each 13 degrees 20 minutes of the Sidereal ecliptic (Lahiri ayanamsa) from Ashwini, named", "Nakshatra (Vedic): a Systems button under System (on or off; once Vd): a ring of the 27 stars (nakshatras), each 13 degrees 20 minutes of the Sidereal ecliptic (Lahiri ayanamsa) from Ashwini, named, with a tick at each of its four quarters",),   # (once Vd, then Na)
    "Op": ("Systems button under System (on or off): a ring of thirteen equal signs, about 27.69 degrees of the ecliptic each, Ophiuchus between Scorpio and Sagittarius, Aries from the March equinox (Tropical)", "Ophiuchus: Systems button under System (on or off; once 13): a ring of the 13 constellations the ecliptic passes through, Ophiuchus among them, at their IAU boundaries (so not all the same width), moved on by the precession to the time shown",),   # (Op was thirteen equal signs; then 13 was renamed Op)
    "KP": ("Krishnamurti Paddhati: a Systems button under System (on or off): a ring of the 27 stars (nakshatras) by the KP ayanamsa, each with its star lord, and inside them their 243 subs, each in its sub lord's colour, its share of the star as its lord's Vimshottari years of 120", "Krishnamurti Paddhati: a Systems button under System (on or off): a ring of the 27 stars' (nakshatras') 243 subs by the KP ayanamsa, each in its sub lord's colour (a line at each star's start), its share of the star as its lord's Vimshottari years of 120",),   # (KP's ring has its subs alone now)
    "Distance(%)": ("A planet's distance from the Earth between its nearest (0) and farthest (100)",),   # (the Distance(%) page, once Planets Distance(%), has its Help here now)
    "TABP": ("Transit Aspects Now from Birth Points: Prediction Rules' Chart (once Transit, TfSaB, PTfBP, then TfBP) and its Predictions table: a planet now coming to an angle with a point of the birth chart",),   # (its table was Transit Aspects Now from Birth Points for a while)
    "Mundane": ("Transit Aspects (Mundane): Prediction Rules' Chart (once Sky, PT, then TEON) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)", "Transit Aspects to Each Others Now: Prediction Rules' Chart (once Sky, PT, then TEON) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)",),   # (its table is Transit Aspects (Mundane))
    "HT": ("Houses at Now: Prediction Rules' Chart and its Predictions table: the house of the birth chart each planet is in at this moment, with its reading", "Houses Now: Prediction Rules' Chart and its Predictions table: the house of the birth chart each planet is in at this moment, with its reading", "Houses Now: Prediction Rules' Chart and its Predictions table: each planet now passing through a house of the birth chart, when it comes in and goes out",),   # (Houses Now taken off Predictions)
    "TfBP": ("Transits from Birth Points: Prediction Rules' Chart (once Transit, TfSaB, then PTfBP) and its Predictions table: a planet now coming to an angle with a point of the birth chart", "Transits from Birth Points: Prediction Rules' Chart (once Transit, TfSaB, then PTfBP) and its Predictions table, Planets Transits from Birth Points: a planet now coming to an angle with a point of the birth chart",),   # (its table is Transits from Birth Points)
    "TEON": ("Transits to Each Other Now: Prediction Rules' Chart (once Sky, then PT) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)", "Planets Transits Now: Prediction Rules' Chart (once Sky, then PT) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)",),   # (its table is Transits to Each Other Now)
    "PTfBP": ("Planets Transit from Birth Points: Prediction Rules' Chart (once Transit, then TfSaB) and its Predictions table: a planet now coming to an angle with a point of the birth chart", "Prediction Rules' Chart (once Transit, then TfSaB) and its Predictions table, Transit from Sun at Birth: a planet now coming to an angle with a point of the birth chart",),   # (PTfBP is Planets Transit from Birth Points)
    "Prediction Rules": ("Page (admins): the Predictions table: a row per Chart (Birth or TABP), Planet1/Now, P2/Bth/Ho, Kind (RA or De) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or TABP), Planet1/Now, Planet2/Birth, Kind (RA or De) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or TfBP), Planet1/Now, Planet2/Birth, Kind (RA or De) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or TfBP), Planet1-Now, Planet2-Birth, Kind (RA or De) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or PTfBP), Planet1-Now, Planet2-Birth, Kind (RA or De) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or PTfBP), Planet1-Now, Planet2-Birth, Kind (RA or De) and Angle, with its Event", "Page (admins): the Predictions table: a row per Chart (Birth or PTfBP), Moving, Birth, Kind (RA or De) and Angle, with its Event", "Page (admins): the Predictions table: a row per Chart (Birth or TfSaB), Moving, Birth, Kind (RA or De) and Angle, with its Event", "Page (admins): the Predictions table: a row per Chart (Birth or Transit), Moving, Birth, Kind (RA or De) and Angle, with its Event", "Page (admins): the Predictions table: a row per Moving planet, Birth point, Kind (RA or Dec) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or Transit), Moving, Birth, Kind (RA or Dec) and Angle, with its Prediction", "Page (admins): the Predictions table: a row per Chart (Birth or Transit), Moving, Birth, Kind (RA or Dec) and Angle, with its Events",),
    "P1/Now": ("Prediction Rules column (once Moving, then Planet1-Now): TABP: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Prediction Rules column (once Moving, then Planet1-Now): TfBP: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Prediction Rules column (once Moving): TfBP: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Prediction Rules column (once Moving): PTfBP: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Predictions column: PTfBP: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Predictions column: TfSaB: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Predictions column: Transit: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart", "Predictions column: the planet now (Mo .. Sa, NN, SN)",),
    "PT": ("Planets Transits: Prediction Rules' Chart (once Sky) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)", "Prediction Rules' Chart (once Sky): two planets now at an angle with each other, the same for everyone; shown in Predictions' Sky table",),
    "RA+De": ("Predictions Kind (Birth, TABP, TAEON): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, TfBP, TAEON): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, TfBP, TEON): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, TfBP, PT): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, PTfBP, PT): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, TfSaB, PT): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, TfSaB, Sky): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions Kind (Birth, Transit, Sky): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored", "Predictions (Chart Aspect): two planets in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored",),
    "Chart": ("Predictions column: Birth (two points at the angle in the birth chart), TABP (a planet now coming to the angle with a birth point), TAEON (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the place now, CN)", "Predictions column: Birth (two points at the angle in the birth chart), TABP (a planet now coming to the angle with a birth point), TAEON (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the birth chart)", "Predictions column: Birth (two points at the angle in the birth chart), TABP (a planet now coming to the angle with a birth point), TAEON (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth) or HB (a planet in a house at birth)", "Predictions column: Birth (two points at the angle in the birth chart), TABP (a planet now coming to the angle with a birth point), TAEON (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the birth chart)", "Predictions column: Birth (two points at the angle in the birth chart), TfBP (a planet now coming to the angle with a birth point), TAEON (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the birth chart)", "Predictions column: Birth (two points at the angle in the birth chart), TfBP (a planet now coming to the angle with a birth point), TEON (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the birth chart)", "Predictions column: Birth (two points at the angle in the birth chart), TfBP (a planet now coming to the angle with a birth point), TEON (two planets now at the angle with each other) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), TfBP (a planet now coming to the angle with a birth point), PT (two planets now at the angle with each other) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), PTfBP (a planet now coming to the angle with a birth point), PT (two planets now at the angle with each other) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), TfSaB (a planet now coming to the angle with a birth point), PT (two planets now at the angle with each other) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), TfSaB (a planet now coming to the angle with a birth point), Sky (two planets now at the angle with each other) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), Transit (a planet now coming to the angle with a birth point), Sky (two planets now at the angle with each other) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), Transit (a planet now coming to the angle with a birth point), Sky (two planets now at the angle with each other in RA or in De), Aspect (two planets now in aspect by Aspect Rules: RA and De together) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (two points at the angle in the birth chart), Transit (a planet now coming to the angle with a birth point), Sky (two planets now at the angle with each other, the same for everyone) or Distance (a planet at its closest to, or farthest from, the Earth)", "Predictions column: Birth (the two points at the angle in the birth chart) or Transit (the planet now coming to the angle with the birth point)",),
    "Kind": ("Predictions column: RA (the two's RA apart is the RA column's degrees), De (RA column 0: parallel, the same De; 180: contra-parallel, mirrored), RA+De (in aspect by Aspect Rules: RA within the RA orb of those degrees and De within the De orb, equal or mirrored), or for Distance rows Near (closest to the Earth) or Far (farthest)", "Predictions column: RA (the RA between the two is the Angle), De (Angle 0: parallel, the same De; 180: contra-parallel, mirrored), RA+De (in aspect by Aspect Rules: RA within the RA orb of the Angle and De within the De orb, equal or mirrored), or for Distance rows Near (closest to the Earth) or Far (farthest)", "Predictions column: RA (the RA between the two is the Angle), De (Angle 0: parallel, the same De; 180: contra-parallel, mirrored), RA+De (Aspect rows: RA within the RA orb of the Angle and De within the De orb, equal or mirrored), or for Distance rows Near (closest to the Earth) or Far (farthest)", "Predictions column: RA (the RA between the two is the Angle) or De (Angle 0: parallel, the same De; 180: contra-parallel, mirrored)", "Predictions column: RA (the RA between the two is the Angle), De (Angle 0: parallel, the same De; 180: contra-parallel, mirrored), or for Distance rows Near (closest to the Earth) or Far (farthest)",),
    "De": ("Each planet's Dec line on the sphere", "De: Declination, a planet's angle north (+) or south (-) of the celestial equator; on AstroClock-3D, the Coordinates button for each planet's De line on the sphere",),
    "Predictions": ("Page: when the planets now come to the angles with the birth chart that the Prediction Rules table names, with its Prediction for each",),
    "Prediction": ("Prediction Rules column: the prediction for the row (optional, at most 500 characters); Event: what happens", "Prediction Rules column: the prediction for the row (optional, at most 500 characters); Events: what happens",),
    "P2/Bth/Ho": ("Prediction Rules column (once Birth, Planet2-Birth, then Planet2/Birth): the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB); HB: the house, H01 .. H12", "Prediction Rules column (once Birth, Planet2-Birth, then Planet2/Birth): the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB); HB, HT: the house, H01 .. H12", "Prediction Rules column (once Birth, then Planet2-Birth): the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB); HB, HT: the house, H01 .. H12", "Prediction Rules column (once Birth, then Planet2-Birth): the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB)", "Prediction Rules column (once Birth): the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB)", "Predictions column: the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB)", "Predictions column: the point of the birth chart it comes to (Mo .. Sa, NN, SN, CB)",),
    "Page Defaults": ("Page (admins): what each page's inputs start as (Page, Box Title, Choice, Choice Values, Allowed Values)", "Page (admins): what each page's buttons start as (Page, Options, Choices)", "Page (admins): what each page's inputs start as (Page, Box Title, Choice, Choice Values, Allowed_Values)",),
    "Customers": ("Page (admins): a row per login: Email, Access, Start Date, Days, End Date",),
    "Access": ("Customers column: Now (the Now charts), DOB (the DOB charts, for Days days) or Admin",),
    "Coordinates": ("Title button: which lines and tags to show (Ho, Ce, AU, 3D, Sp, SpC, RA, De, La, Lg, 1C, DA)", "Title button: which lines and tags to show (Ho, Ce, AU, 3D, Sp, SpC, PP, RA, De, La, Lg, 1C, DA)", "Title button: which lines and tags to show (Ho, CM, AU, 3D, Sp, SpC, PP, RA, De, La, Lg, 1C, DA); Re beside it: the Timer back at the DOB or Now",),
    "Rotate in 1s": ("Title button: how much time passes each second (Manual, 1s to 1y)", "Title button: how much time passes each second (1s to 1y); none picked: time stands still, and dragging the drawing turns it",),
    "App Conditions": ("Page (admins): the Conditions table: a row per Condition (unique) and its Values", "Page (admins): the Conditions table: a row per Condition (unique), its Table Name and its Values", "Page (admins): the App Conditions table: a row per Condition (unique), its Table Name and its Values", "Page (admins): the App Conditions table: a row per Condition (unique), its Object and its Values", "Page (admins): the App Conditions table: a row per Object, Condition (unique) and its Desc",),
    "Choice": ("Defaults column: the input, by its name on the page (e.g. Days); one row per Page and Choice",),
    "Choice Values": ("Defaults column: what the input starts as (e.g. 7; Ju, Sa; On); blank: the app's own default",),
    "Allowed Values": ("Defaults column: the values Choice Values may be set to, and all the page offers (e.g. 1, 7, 30; for a text box, words such as Pay, Free); blank: all",),
    "Get more days of access": ("DOB Details box (its title as the Defaults table's Box Title says): add days of DOB access with Days and Pay / Coupon", "DOB Details box (its title as the Page Defaults table's Box Title says): add days of DOB access with Days and Pay / Coupon",),
    "Days": ("Customers column: days of DOB access to add (1, 7, 30, 90, 180, 365); End Date is extended by them",),
}
HELP_RENAMED = {"CM": ("Ce",), "Page Defaults": ("Defaults", "Page_Defaults"), "App Conditions": ("Conditions",),
                "P1/Now": ("Planet1/Now", "Planet1-Now", "Moving"), "P2/Bth/Ho": ("Planet2/Birth", "Planet2-Birth", "Birth"),
                "Equatorial-2D": ("AstroClock-2D",), "Equatorial-3D": ("AstroClock-3D",), "Cycles": ("Planets Cycles",), "Geo/Helio": ("Geo/Helio Model",), "Ec": ("Ei",), "Na": ("Vd",)}   # pages' Help rows renamed
HELP_GONE_TOO = {"Sky": ("Predictions (Chart Sky): two planets now at an angle with each other, the same for everyone (with New and Full Moon)", "Predictions table Sky (Chart PT): two planets now at an angle with each other, the same for everyone (with New and Full Moon)"),   # (the Sky table and Chart are Planets Transits, PT, now)
                 "Box Title": ("Defaults column: the title of the box the input is in on its page (e.g. Get more days of access); None: no box",
                              "Page Defaults column: the title of the box the input is in on its page (e.g. Get more days of access); None: no box")}   # (the Page Defaults table has no Box Title now)
HELP_GONE = {"13": "Systems button under System (on or off): a ring of the 13 constellations the ecliptic passes through, Ophiuchus among them, at their IAU boundaries (so not all the same width), moved on by the precession to the time shown",   # (Systems' 13 is Op)
             "Planets Distance(%)": "Page: each planet's Distance(%) from the Earth over time",   # (the page is Distance(%) now: its Help is that row's)
             "TAEON": "Transit Aspects to Each Others Now: Prediction Rules' Chart (once Sky, PT, then TEON) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)",   # (the Chart is Mundane now)
             "HT": "Houses Now: Prediction Rules' Chart, a planet now in a house of the birth chart (its Predictions table, Houses Now, taken off; the rules kept)",   # (its rules deleted)
             "TfBP": "Transit Aspects from Birth Points: Prediction Rules' Chart (once Transit, TfSaB, then PTfBP) and its Predictions table: a planet now coming to an angle with a point of the birth chart",   # (the Chart is TABP now)
             "TEON": "Transit Aspects to Each Others Now: Prediction Rules' Chart (once Sky, then PT) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)",   # (the Chart is TAEON now)
             "PT": "Planets Transits Now: Prediction Rules' Chart (once Sky) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)",   # (the Chart is TEON now)
             "PTfBP": "Planets Transits from Birth Points: Prediction Rules' Chart (once Transit, then TfSaB) and its Predictions table: a planet now coming to an angle with a point of the birth chart",   # (the Chart is TfBP now)
             "TfSaB": "Transit from Sun at Birth: Prediction Rules' Chart (once Transit) and its Predictions table: a planet now coming to an angle with a point of the birth chart",   # (the Chart is PTfBP now)
             "Kind": "Predictions column: RA (the two's RA apart, at the RA column's degrees), De (the De column: 0 parallel, the same De; 180 contra-parallel, mirrored), RA+De (in aspect by Aspect Rules: RA within the RA orb of the RA column's degrees and De within the De orb, equal or mirrored), or for Distance rows Near (closest to the Earth) or Far (farthest)",   # (Prediction Rules no longer shows it)
             "Off": "Predictions column: how far from the Angle it is at Exact (degrees; 0: exact)",   # (RAO and DeO took its place)
             "AR": "Aspect Rules: Predictions column (Birth), the pair's orb in the Aspect Rules table",   # (the Predictions column is gone)
             "Aspects": "Page: when the planets are in aspect, between a start and an end date",   # (the page is gone)
             "Came from": "Logins column: the site that brought the visitor (its name only); blank: none known",
             "Manual": "Time stands still; drag the drawing to turn it", "Planet Path": "Title button: the path of each planet picked"}   # the Help rows for buttons since gone, as the app wrote them
HELP_ROWS_4 = [                                               # added later again
    ("PP", "Planet Path: a button under Coordinates (Equatorial-2D, Equatorial-3D, Geo/Helio): the path of each planet shown"),
]
HELP_ROWS_5 = [                                               # and again
    ("App Conditions", "Page (admins): the App Conditions table: a row per Object, its Values and Condition (unique)"),
]
HELP_ROWS_6 = [                                               # and again: Predictions
    ("Predictions", "Page: the Prediction Rules readings for the birth chart (its points at those angles at birth) and for transits (when the planets now come to those angles with it)"),
    ("Prediction Rules", "Page (admins): the Predictions table: a row per Chart (Birth or TABP), P1/Now, P2/Bth/Ho, Kind (RA or De) and Angle, with its Prediction"),
    ("P1/Now", "Prediction Rules column (once Moving, Planet1-Now, then Planet1/Now): TABP: the planet now (Mo .. Sa, NN, SN); Birth: the first point of the birth chart"),
    ("P2/Bth/Ho", "Prediction Rules column (once Birth, Planet2-Birth, then Planet2/Birth): the point of the birth chart it comes to, or is at the angle with (Mo .. Sa, NN, SN, CB); HB, HT: the house, H01 .. H12"),
    ("Chart", "Predictions column: Birth (two points at the angle in the birth chart), TABP (a planet now coming to the angle with a birth point), Mundane (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the place now, CN)"),
    ("Begins", "Predictions column: when the moving planet comes within the orb (before Start: within it already)"),
    ("Exact", "Predictions column: when it is closest to the Angle"),
    ("Ends", "Predictions column: when it leaves the orb (after End: still within it)"),
]
HELP_ROWS_7 = [("Chart", "Predictions column: Birth (two points at the angle in the birth chart), TABP (a planet now coming to the angle with a birth point), Mundane (two planets now at the angle with each other), Distance (a planet at its closest to, or farthest from, the Earth), HB (a planet in a house at birth) or HT (a planet now in a house of the place now, CN)")]   # (for a table given set 6 before Chart came in)
HELP_ROWS_8 = [("Prediction", "Prediction Rules column: the prediction for the row (optional, at most 500 characters)")]
HELP_ROWS_9 = []                                              # (was AR, a column since gone: see HELP_GONE)
HELP_ROWS_10 = [
    ("Near", "Predictions (Chart Distance, Kind Near): a planet at its closest to the Earth"),
    ("Far", "Predictions (Chart Distance, Kind Far): a planet at its farthest from the Earth"),
]
HELP_ROWS_11 = [
    ("RA+De", "Predictions Kind (Birth, TABP, Mundane): in aspect by Aspect Rules: RA within the RA orb of the angle and De within the De orb, equal or mirrored"),
]
HELP_ROWS_12 = [
    ("RAO", "Predictions column: RA off, how far the two's RA is from the angle at Exact (degrees; 0: exact; blank for De rows)"),
    ("DeO", "Predictions column: De off; De rows, how far from parallel or contra-parallel; RA and RA+De rows, how far apart the two's De values are (equal or mirrored, whichever is closer)"),
]
HELP_ROWS_13 = []                                             # (was TfSaB, since PTfBP: see HELP_GONE and HELP_ROWS_15)
HELP_ROWS_14 = []                                             # (was PT, since TEON: see HELP_GONE and HELP_ROWS_17)
HELP_ROWS_15 = []                                             # (was PTfBP, since TfBP: see HELP_GONE and HELP_ROWS_16)
HELP_ROWS_16 = []                                             # (was TfBP, since TABP: see HELP_GONE and HELP_ROWS_20)
HELP_ROWS_17 = []                                             # (was TEON, since TAEON: see HELP_GONE and HELP_ROWS_19)
HELP_ROWS_18 = [("HB", "Houses at Birth: Prediction Rules' Chart and its Predictions table: the house (H01 .. H12) each planet was in at birth, with its reading")]   # (HT: deleted with its rules; see HELP_GONE)
HELP_ROWS_19 = []                                             # (was TAEON, since Mundane: see HELP_GONE and HELP_ROWS_22)
HELP_ROWS_20 = [("TABP", "Transit Aspects from Birth Points: Prediction Rules' Chart (once Transit, TfSaB, PTfBP, then TfBP) and its Predictions table: a planet now coming to an angle with a point of the birth chart")]
HELP_ROWS_21 = [("HT", "Houses at Now: Prediction Rules' Chart and its Predictions table: the house each planet is in at this moment, the houses from CN, the place now (or Greenwich when none is known), with its reading")]   # (HT back)
HELP_ROWS_22 = [("Mundane", "Transit Aspects Now (Mundane): Prediction Rules' Chart (once Sky, PT, then TEON) and its Predictions table: two planets now at an angle with each other, the same for everyone (with New and Full Moon)")]
HELP_ROWS_23 = [("Systems", "Page: like Equatorial-2D (the Geo drawing seen from above the north celestial pole, every planet on one circle at its RA), with rings of the zodiacs round it (System: Eq, Ec, As, Tr, Si, Op, Na, KP), the De graph left of it and an Ecliptic latitude graph right of it; no aspects and no Rotate in 1s (time dragged sideways)")]
HELP_ROWS_24 = [("System", "Systems buttons, after Time, each on or off, their rings stacked round the circle, inner first: Eq, the house lines of CB and CN; Ec (Ecliptic), ecliptic longitude; Tr (Tropical) and Si (Sidereal), the twelve signs with their lords; Op (Ophiuchus), the 13 constellations at their IAU boundaries, with their lords; Na (Nakshatra), the 27 stars with their star lords and quarters; KP (Krishnamurti), the 27 stars' 243 subs by sub lord, coloured and marked")]
HELP_ROWS_25 = [("Tr", "Tropical: a System button on Systems (on or off): a ring of the twelve signs from the March equinox (Aries at 0 degrees of the ecliptic), each with its lord (Ma, Ve, Me, Mo, Su, Me, Ve, Ma, Ju, Sa, Sa, Ju), Tr at Aries' start"),
                ("Si", "Sidereal: a System button on Systems (on or off): a ring of the twelve signs, each further on by the Lahiri ayanamsa at the time shown (about 24 degrees now), each with its lord, Si at Aries' start")]
HELP_ROWS_26 = [("Ec", "Ecliptic: a System button on Systems (on or off): a ring of ecliptic longitude, 0 to 360 (Tropical), just outside the circle, each degree at the RA it falls at; Ec above its 0, Lg below")]
HELP_ROWS_27 = [("Eq", "Equator: a System button on Systems (on or off): the RA scale's numbers; with Ho (under Coordinates) on, the house lines of CB and CN")]
HELP_ROWS_28 = [("Na", "Nakshatra (Vedic): a System button on Systems (on or off; once Vd): a ring of the 27 stars, each 13 degrees 20 minutes of the Sidereal ecliptic (Lahiri ayanamsa) from Ashwini, named (at most 9 letters) with its star lord's symbol, a tick at each of its four quarters")]
HELP_ROWS_29 = [("Op", "Ophiuchus: a System button on Systems (on or off; once 13): a ring of the 13 constellations the ecliptic passes through, Ophiuchus among them, at their IAU boundaries (so not all the same width), moved on by the precession to the time shown, each with its lord (Ophiuchus: none)")]
HELP_ROWS_30 = []                                             # (was Op, thirteen equal signs, since gone: Op is the 13 constellations)
HELP_ROWS_31 = [("As", "Ascendant: on Systems, with Ho (under Coordinates) on: each place's Ascendant (the ecliptic rising in the east there, the first house's start), a red arrow from Ea out past the rings (dashed for the DOB); point at it for where it falls in each system shown")]
HELP_ROWS_32 = [("KP", "Krishnamurti Paddhati: a System button on Systems (on or off): a ring of the 27 stars' 243 subs (KP ayanamsa), each its share of the star as its lord's Vimshottari years of 120, from the star's lord on: inside, each in its sub lord's colour; outside, its sub lord's symbol; a line at each star's start")]
HELP_ROWS_33 = [("Ecliptic latitude", "Systems graph right of the clock: each planet's latitude north (+) or south (-) of the ecliptic, -7 to +7 degrees (beyond: at the end), moving as time moves")]
HELP_VERSION = "33"                                            # the sets of rows the Help table has been given
HELP_ROWS_2 = [                                               # added later: the app's own names (pages, titles, tags, columns ..)
    # the pages
    ("Equatorial-2D", "Page: the Geo drawing seen from above the north celestial pole, each planet at its RA and distance, with the De and Distance(%) graphs"),
    ("Equatorial-3D", "Page: the Earth turning inside the celestial sphere, the planets on it at their RA and De (3D: a true 3D view)"),
    ("Geo/Helio", "Page: the planets' paths at their real distances round the Earth (Geo) or the Sun (Helio)"),
    ("Cycles", "Page: each planet's RA and De over time, between a start and an end date"),
    ("DOB Details", "Page (members): their birth details, and people added under their login"),
    ("Help", "Page: this table of the app's names and what they mean (admins change it)"),
    ("Aspect Rules", "Page (admins): the orbs, RA and De, a pair of planets must be within to be in aspect"),
    ("Customers", "Page (admins): a row per login: Email, Access, Start Date, End Date"),
    ("Page Defaults", "Page (admins): what each page's inputs start as (Page, Choice, Choice Values, Allowed Values)"),
    ("Logins", "Page (admins): who opened, added, changed or deleted what, when and from where"),
    ("Readme", "Page (admins): the app's README file"),
    ("Symbols", "Page (admins): each planet's symbol, short name, colour and size"),
    # the title buttons
    ("Time", "Title button: which moment the charts show, Now or DOB (one at a time)"),
    ("Planets", "Title button: which planets (and NN, SN) to show"),
    ("Major Aspects", "Title button: the major aspect angles to draw: 0, 60, 90, 120, 180"),
    ("Minor Aspects", "Title button: the minor aspect angles to draw: 30, 45, 72, 135, 144, 150"),
    ("Coordinates", "Title button: which lines and tags to show (Ho, CM, AU, 3D, Sp, SpC, PP, RA, De, La, Lg, 1C, DA)"),
    ("Rotate in 1s", "Title button: how much time passes each second (1s to 1y); none picked: time stands still, and dragging the drawing turns it. R beside it: time runs backwards; RS: the Timer back at the DOB or Now"),
    ("Centric Model", "Title button: Geo (the Earth at the centre) or Helio (the Sun at the centre)"),
    ("Start Date (UT)", "When a chart over time starts: DOB or Now"),
    ("End Date (UT)", "When a chart over time ends: Now, or the start plus a time (e.g. 5 days, 2 years)"),
    # the aspect angles
    ("0", "Conjunction: two planets together (major aspect)"), ("60", "Sextile (major aspect)"),
    ("90", "Square (major aspect)"), ("120", "Trine (major aspect)"), ("180", "Opposition (major aspect)"),
    ("30", "Semi-sextile (minor aspect)"), ("45", "Semi-square (minor aspect)"), ("72", "Quintile (minor aspect)"),
    ("135", "Sesquiquadrate (minor aspect)"), ("144", "Biquintile (minor aspect)"), ("150", "Quincunx (minor aspect)"),
    ("0-Ma-Ju", "An aspect line's tag: the angle, then the two planets (here Mars and Jupiter in conjunction)"),
    ("Orb", "How far from the exact angle two planets may be and still count as in aspect (Aspect Rules)"),
    # the drawings' tags
    ("H01 to H12", "House tags: the twelve house lines, 30 degrees apart from the RA of CB and of CN"),
    ("UT", "Universal Time"), ("UTC", "Universal Time, Coordinated: UTC+5.50 is 5 h 30 min ahead of it"),
    ("Fit", "The scale of distance used: each tenfold distance takes the same room"),
    # the tables' buttons and columns
    ("Insert", "Table button: adds a blank row at the bottom to fill in (saving any edits first)"),
    ("Update", "Table button: saves the rows as they stand"),
    ("Delete", "Table button: deletes the rows ticked in Del"),
    ("Ignore", "Table button: drops the changes not saved yet"),
    ("Reset to Previous", "Table button: puts the table back as it was before its last save"),
    ("Del", "Table column: tick a row, then press Delete"),
    ("Access", "Customers column: Now (the Now charts), DOB (the DOB charts, until End Date) or Admin"),
    ("Days", "DOB Details (Get more days of access): days of DOB access to add (1, 7, 30, 90, 180, 365); End Date is extended by them"),
    ("SAbr", "Symbols column: a planet's short name (Su, Mo ..)"), ("Symb", "Symbols column: a planet's symbol"),
    ("SDesc", "Symbols column: a planet's name"), ("RGB", "Symbols column: a planet's colour, rgb(r,g,b)"),
    ("Size_Clock-2D", "Symbols column: a planet's mark size on Equatorial-2D"),
    ("Size_Clock-3D", "Symbols column: a planet's mark size on Equatorial-3D"),
    ("Size_Geo", "Symbols column: a planet's mark size on Geo"), ("Size_Helio", "Symbols column: a planet's mark size on Helio"),
]
# The Predictions table (the Prediction Rules page): a row per rule, kept by admins. Chart Transit: when the Moving planet
# (now) comes to the Angle with the Birth point, in RA or in De (Kind), the Predictions page shows its Prediction; Chart
# Birth: when the two (Moving: the first point, Birth: the second) are at that Angle in the birth chart itself
TRANSIT = "TABP"                                           # Transit Aspects from Birth Points: a planet now coming to a birth point (Transit, TfSaB, then PTfBP once)
SKY = "Mundane"                                              # Transit Aspects (Mundane): two planets now with each other (Chart Sky, PT, TEON, then TAEON, once)
HOUSE_BIRTH, HOUSE_NOW = "HB", "HT"                         # Houses at Birth: a planet in a house at birth; Houses at Now: a planet now in a house of the place now (CN)
HOUSE_CHARTS = (HOUSE_BIRTH, HOUSE_NOW)
PRED_CHARTS = ["Birth", HOUSE_BIRTH, TRANSIT, HOUSE_NOW, SKY, "Distance"]   # Mundane: two planets now; Distance: a planet's closest and farthest
# A row's Kind (not shown; see row_kind): RA, De, RA+De (in aspect by Aspect Rules, RA and De together), Near, Far (Distance
# rows only) or House (HB and HT rows)
HOUSES = core.HOUSE_NAMES                                     # H01 .. H12: an HB or HT row's P2/Bth/Ho
DIST_POINTS = ["Mo", "Su", "Me", "Ve", "Ma", "Ju", "Sa"]     # the planets a Distance row may name (their Birth: Ea, the Earth)
PRED_MOVING = ["Mo", "Su", "Me", "Ve", "Ma", "Ju", "Sa", "NN", "SN"]   # the planets now
PRED_BIRTH = PRED_MOVING + ["CB"]                             # the points of the birth chart (CB: house 10 at birth)
PRED_TEXT_MOST = 500                                          # a Prediction's most characters
predictions = sa.Table(
    "predictions", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("chart", sa.String(8), nullable=False, server_default=TRANSIT),   # Chart: Birth, TABP (Transit, TfSaB, PTfBP, TfBP once), Mundane (Sky, PT, TEON, TAEON once) or Distance
    sa.Column("moving", sa.String(8), nullable=False),       # Moving
    sa.Column("birth", sa.String(8), nullable=False),        # Birth
    sa.Column("kind", sa.String(8), nullable=False),         # Kind: RA or De
    sa.Column("angle", sa.Integer, nullable=False),          # Angle (De: 0 parallel, 180 contra-parallel)
    sa.Column("prediction", sa.String(PRED_TEXT_MOST)),      # Event (named prediction before)
    sa.Column("forecast", sa.String(PRED_TEXT_MOST)),        # Prediction (optional)
    sa.UniqueConstraint("chart", "moving", "birth", "kind", "angle", name="ux_predictions_chart_rule"),
)
PREDICTIONS_COLUMNS = ["id", "Chart", "Moving", "Birth", "Kind", "RA", "De", "Event", "Prediction"]   # (RA or De: the column angle, by Kind;
                                                             # Event: prediction; Prediction: forecast)
PREDICTION_ROWS = [                                           # the Transit rows the table starts with, once (samples, to be replaced)
    ("Sa", "Su", "RA", 0, "Sample: Saturn at your birth Sun's RA"),
    ("Sa", "Sa", "RA", 0, "Sample: Saturn back at its birth RA (Saturn return)"),
    ("Ju", "Su", "RA", 0, "Sample: Jupiter at your birth Sun's RA"),
    ("Sa", "Su", "RA", 180, "Sample: Saturn and your birth Sun 180° apart in RA"),
    ("Ma", "Mo", "De", 0, "Sample: Mars parallel your birth Moon in De"),
]
PREDICTION_BIRTH_ROWS = [                                     # and the Birth rows, once (added later)
    ("Su", "Mo", "RA", 0, "Sample: Sun with Moon in RA at birth"),
    ("Su", "Sa", "RA", 90, "Sample: Sun and Saturn 90° apart in RA at birth"),
    ("Ve", "Ma", "De", 0, "Sample: Venus parallel Mars in De at birth"),
]


# The Conditions table: a row per Condition (unique, whatever its case), its Object and its Values; kept by admins (the
# Conditions page)
COND_NAME_MOST, COND_VALUES_MOST = 60, 500                    # a Condition's and its Values' most characters
conditions = sa.Table(
    "conditions", meta,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.String(COND_NAME_MOST), nullable=False, unique=True),   # Condition
    sa.Column("value_list", sa.String(COND_VALUES_MOST)),     # Values
    sa.Column("table_name", sa.String(COND_NAME_MOST)),       # Object
)
sa.Index("ux_conditions_name", sa.func.lower(conditions.c.name), unique=True)   # (Abc and abc are one)
HELP_INDEX = "ux_help_abbre"                                   # one row per Abbreviation, whatever its case (Su and su are one)
sa.Index(HELP_INDEX, sa.func.lower(help_table.c.abbreviation), unique=True)
HELP_ROWS = [                                                 # the abbreviations the pages use, as the table starts
    ("Su", "Sun"), ("Mo", "Moon"), ("Me", "Mercury"), ("Ve", "Venus"), ("Ma", "Mars"), ("Ju", "Jupiter"), ("Sa", "Saturn"),
    ("Ea", "Earth"), ("NN", "The Moon's north node: where its path crosses the Sun's going north"),
    ("SN", "The Moon's south node: where its path crosses the Sun's going south"),
    ("CB", "The place of birth, on the Earth"), ("CN", "The place now, on the Earth"),
    ("DOB", "Date of birth: as a Time, the planets at birth; also the admins' page of every customer's birth details"), ("Now", "The planets now"),
    ("Ave", "Average: each planet's Distance(%) halfway between DOB and Now"),
    ("RA", "Right Ascension: a planet's position along the celestial equator, 0 to 360 degrees"),
    ("AU", "Astronomical unit: the Earth's average distance from the Sun, about 150 million km"),
    ("Distance(%)", "Page, and its measure: a planet's distance from the Earth between its nearest (0) and farthest (100), each chosen planet's over time"),
    ("Ho", "Houses, under Coordinates: on Equatorial-2D and Equatorial-3D, the house lines, twelve, 30 degrees apart from the RA of CB and of CN; on Systems, each place's Ascendant (As) and the houses H01 to H12 of each System shown: Eq, those house lines; Ec, Tr, Si, Op, Na or KP, equal houses of 30 degrees from As; on the rings, Tr, Si and Op whole signs (H01 the sign As is in), KP the Placidus cusps"),
    ("CM", "Celestial coordinates: the axis with NCP and SCP, and the celestial equator"),
    ("NCP", "North celestial pole"), ("SCP", "South celestial pole"),
    ("WCE", "West end of the celestial equator, as drawn"), ("ECE", "East end of the celestial equator, as drawn"),
    ("Sp", "Spokes: a line from the Earth's centre through each planet to the sphere (in 3D, to the edge of the view)"),
    ("SpC", "Lines from CB (DOB) or CN (Now) on the Earth to each planet"),
    ("De", "Declination, a planet's angle north (+) or south (-) of the celestial equator; on Equatorial-3D, the Coordinates button for each planet's De line on the sphere"), ("La", "The Earth's lines of latitude, every 30 degrees"),
    ("Lg", "The Earth's lines of longitude, every 30 degrees"),
    ("3D", "A true 3D view round the Earth, to turn and zoom with the mouse"),
    ("1C", "One circle: every planet on one circle at its RA, whatever its distance, to see conjunctions"),
    ("DA", "Shows or hides the Ave planets on the Distance(%) graph"),
    ("Geo", "GeoCentric: the Earth at the centre"), ("Helio", "HelioCentric: the Sun at the centre"),
    ("1s to 1y", "Rotate in 1s: 1s, 1m, 1h, 1d, 1w, 1mo, 1y: that much time passes each second (a second, minute, hour, day, week, month, year)"),
]
DEFAULTS_INDEX = "ux_defaults_page_options"                   # one row per Page and Options
sa.Index(DEFAULTS_INDEX, defaults.c.page, defaults.c.options, unique=True)


planets = sa.Table(                                           # seen by admins only (the Symbols page)
    "naming_conventions", meta,
    sa.Column("sn", sa.String(8), primary_key=True),
    sa.Column("id", sa.Integer),                              # the row's number (ID), set by the app
    sa.Column("symbol", sa.String(8)),                        # the conventional symbol, as text, for people; the charts draw their own
    sa.Column("name", sa.String(60)),
    sa.Column("color", sa.String(40)),
    sa.Column("color_name", sa.String(40)),                   # free text, for people; the charts use color
    sa.Column("size_clock_3d", sa.String(40)),                   # how the Equatorial-3D chart sizes it: Size_Clock-3D
    sa.Column("size", sa.String(40)),                         # how the GeoCentric chart sizes it: Size_Geo
    sa.Column("size_helio", sa.String(40)),                   # how the HelioCentric chart sizes it: Size_Helio
    sa.Column("size_clock_2d", sa.String(40)),                   # how the Equatorial-2D chart sizes it: Size_Clock-2D
)
# The Aspect Rules table: one row, ALL_ASPECTS, with an RA orb and a De orb per planet (-RA, -De), for every angle (kept
# under angle 0; pos 0)
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
    _number_planets(eng)
    _add_orb_nn_ra(eng)
    _add_orb_points(eng)
    _seed_aspect_details(eng)
    _add_orb_dec(eng)
    _one_orb_row(eng)
    _add_defaults_index(eng)
    _add_defaults_allowed(eng)
    # (the Page Defaults and App Conditions tables: only their columns and index are brought up to date here; their rows
    # are the admins' alone, never added to or changed at startup)
    _rename_help_abbre(eng)
    _add_help_index(eng)
    _rename_help_rows(eng)
    _widen_help_abbreviation(eng)
    _add_conditions_table_name(eng)
    _seed_help(eng)
    _add_prediction_chart(eng)
    _add_prediction_forecast(eng)
    _dec_is_de(eng)                                           # (before new rows come in: they are De already)
    _transit_is_tfsab(eng)                                    # (and TABP: Transit, TfSaB, PTfBP, then TfBP, once)
    _sky_is_pt(eng)                                           # (and Mundane: Sky, PT, TEON, then TAEON, once)
    _seed_predictions(eng)
    _trim_prediction_texts(eng)
    _drop_prediction_dots(eng)
    _fill_prediction_readings(eng)
    _plain_ra_events(eng)
    _keep_rade_only(eng)
    _drop_starts(eng)                                         # (no "In RA and De both" / "At its farthest" / "At its closest" start)
    _seed_houses(eng)                                         # (HB rows: each planet in each house)
    _drop_ht_rows(eng)                                        # (HT rows: Houses Now taken off, its rules deleted once)
    _seed_houses_now(eng)                                     # (HT rows again: Houses Now back, at this moment)
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
    """A Logins table made before the Device, Time zone, Access, Page and Details columns gets them (its rows kept, blank
    in them)."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("logins")}
    with eng.begin() as c:
        for col in ("device", "timezone", "access", "page", "details"):
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


def _add_defaults_allowed(eng: sa.Engine):
    """A Defaults table made before its Allowed Values column gets it (its rows kept, blank: all the app has)."""
    if "allowed_values" not in {c["name"] for c in sa.inspect(eng).get_columns("defaults")}:
        with eng.begin() as c:
            c.execute(sa.text(f"ALTER TABLE defaults ADD COLUMN allowed_values {defaults.c.allowed_values.type.compile(dialect=eng.dialect)}"))


def _add_defaults_index(eng: sa.Engine):
    """A Defaults table made before the unique index on Page and Options gets it (it already had a rule allowing no two the same)."""
    with eng.begin() as c:
        c.execute(sa.text(f"CREATE UNIQUE INDEX IF NOT EXISTS {DEFAULTS_INDEX} ON defaults (page, options)"))


# below Coordinates, once a row each, and whether each starts on with no row


def _path_to_pp(eng: sa.Engine, page: str):
    with eng.begin() as c:
        row = c.execute(sa.select(defaults.c.id, defaults.c.choices).where(sa.func.lower(defaults.c.page) == page,
                                                                            sa.func.lower(defaults.c.options) == "planet path")).first()
        if row is None:
            return
        coords = c.execute(sa.select(defaults.c.id, defaults.c.choices).where(sa.func.lower(defaults.c.page) == page,
                                                                               sa.func.lower(defaults.c.options) == "coordinates")).first()
        on = [p.strip() for p in ((coords.choices if coords else "") or "").split(",") if p.strip()]
        if (row.choices or "").strip() and coords is not None and "pp" not in [p.lower() for p in on]:
            c.execute(defaults.update().where(defaults.c.id == coords.id).values(choices=", ".join(on + ["PP"])))
        c.execute(defaults.delete().where(defaults.c.id == row.id))


def _rename_help_abbre(eng: sa.Engine):
    """A Help table made with the column abbre has it renamed abbreviation (its rows kept); its index goes, to be made again on it."""
    if "help" not in sa.inspect(eng).get_table_names():
        return
    if "abbre" in {c["name"] for c in sa.inspect(eng).get_columns("help")}:
        with eng.begin() as c:
            c.execute(sa.text(f"DROP INDEX IF EXISTS {HELP_INDEX}"))
            c.execute(sa.text("ALTER TABLE help RENAME COLUMN abbre TO abbreviation"))


def _rename_help_rows(eng: sa.Engine):
    """Help rows for pages since renamed get the new name (their Description kept; HELP_RENAMED: Defaults, once
    Page_Defaults, is Page Defaults, and Conditions is App Conditions); rows the app wrote that are out of date since (HELP_OUT_OF_DATE) are brought up to date."""
    if "help" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        for new, olds in HELP_RENAMED.items():               # (the first old name there, when the new one is not)
            if c.execute(sa.select(help_table.c.id).where(sa.func.lower(help_table.c.abbreviation) == new.lower())).first():
                continue
            for old in olds:
                if c.execute(help_table.update().where(sa.func.lower(help_table.c.abbreviation) == old.lower())
                             .values(abbreviation=new)).rowcount:
                    break
        # (a row still as the app first wrote it, since out of date, gets the one the app has now; one an admin has changed stays)
        now = dict(HELP_ROWS + HELP_ROWS_2 + HELP_ROWS_3 + HELP_ROWS_4 + HELP_ROWS_5 + HELP_ROWS_6 + HELP_ROWS_7 + HELP_ROWS_8 + HELP_ROWS_9 + HELP_ROWS_10 + HELP_ROWS_11 + HELP_ROWS_12 + HELP_ROWS_13 + HELP_ROWS_14 + HELP_ROWS_15 + HELP_ROWS_16 + HELP_ROWS_17 + HELP_ROWS_18 + HELP_ROWS_19 + HELP_ROWS_20 + HELP_ROWS_21 + HELP_ROWS_22 + HELP_ROWS_23 + HELP_ROWS_24 + HELP_ROWS_25 + HELP_ROWS_26 + HELP_ROWS_27 + HELP_ROWS_28 + HELP_ROWS_29 + HELP_ROWS_30 + HELP_ROWS_31 + HELP_ROWS_32 + HELP_ROWS_33)
        for abbreviation, text in now.items():               # (pages renamed, AstroClock-2D, -3D and Geo/Helio Model: a row as the app wrote it with the old names gets the new)
            old = text.replace("Equatorial-2D", "AstroClock-2D").replace("Equatorial-3D", "AstroClock-3D").replace("Geo/Helio", "Geo/Helio Model")
            if old != text:
                c.execute(help_table.update().where(sa.func.lower(help_table.c.abbreviation) == abbreviation.lower(),
                                                    help_table.c.description == old).values(description=text))
        for abbreviation, olds in HELP_OUT_OF_DATE.items():
            where = (sa.func.lower(help_table.c.abbreviation) == abbreviation.lower(), help_table.c.description.in_(olds))
            if abbreviation in now:
                c.execute(help_table.update().where(*where).values(description=now[abbreviation]))
            else:                                             # (a row the app no longer has, e.g. Kind: its old texts go too)
                c.execute(help_table.delete().where(*where))
        # (a row for a button since gone, still as the app wrote it, goes)
        for abbreviation, old in [*HELP_GONE.items(), *((a, o) for a, olds in HELP_GONE_TOO.items() for o in olds)]:
            c.execute(help_table.delete().where(sa.func.lower(help_table.c.abbreviation) == abbreviation.lower(),
                                                help_table.c.description == old))


def _add_help_index(eng: sa.Engine):
    """A Help table made before its index gets it: one row per Abbreviation, whatever its case."""
    try:
        with eng.begin() as c:
            c.execute(sa.text(f"CREATE UNIQUE INDEX IF NOT EXISTS {HELP_INDEX} ON help (lower(abbreviation))"))
    except sa.exc.SQLAlchemyError:                             # (two rows already differ only in case: the page's check still holds)
        pass


def _widen_help_abbreviation(eng: sa.Engine):
    """A Help table made when an Abbreviation was at most 20 characters takes HELP_ABBR_MOST (Postgres holds to the
    length; SQLite does not, so there is nothing to change)."""
    if eng.dialect.name != "postgresql" or "help" not in sa.inspect(eng).get_table_names():
        return
    size = next((c["type"].length for c in sa.inspect(eng).get_columns("help") if c["name"] == "abbreviation"), None)
    if size is not None and size < HELP_ABBR_MOST:
        with eng.begin() as c:
            c.execute(sa.text(f"ALTER TABLE help ALTER COLUMN abbreviation TYPE VARCHAR({HELP_ABBR_MOST})"))


def _seed_help(eng: sa.Engine):
    """Once per set (a note among the settings says which, so a row deleted since stays deleted): the Help table gets the
    rows of HELP_ROWS, then of HELP_ROWS_2, then of HELP_ROWS_3, it lacks (rows already there, the admins' own, are left as
    they are)."""
    with eng.begin() as c:
        done = c.execute(sa.select(settings.c.value).where(settings.c.key == "help_seeded")).scalar()
        if done == HELP_VERSION:
            return
        later = [HELP_ROWS_2, HELP_ROWS_3, HELP_ROWS_4, HELP_ROWS_5, HELP_ROWS_6, HELP_ROWS_7, HELP_ROWS_8, HELP_ROWS_9, HELP_ROWS_10, HELP_ROWS_11, HELP_ROWS_12, HELP_ROWS_13, HELP_ROWS_14, HELP_ROWS_15, HELP_ROWS_16, HELP_ROWS_17, HELP_ROWS_18, HELP_ROWS_19, HELP_ROWS_20, HELP_ROWS_21, HELP_ROWS_22, HELP_ROWS_23, HELP_ROWS_24, HELP_ROWS_25, HELP_ROWS_26, HELP_ROWS_27, HELP_ROWS_28, HELP_ROWS_29, HELP_ROWS_30, HELP_ROWS_31, HELP_ROWS_32, HELP_ROWS_33]   # (the sets added since each note: 1 has had HELP_ROWS ..)
        wanted = sum(later[int(done) - 1:], []) if done and done.isdigit() else HELP_ROWS + sum(later, [])
        have = {a.lower() for (a,) in c.execute(sa.select(help_table.c.abbreviation)).all()}
        new = []
        for a, d in wanted:                                   # (each once: a later set may name one again)
            if a.lower() not in have:
                new.append(dict(abbreviation=a, description=d))
                have.add(a.lower())
        if new:
            c.execute(help_table.insert(), new)
        if done is None:
            c.execute(settings.insert().values(key="help_seeded", value=HELP_VERSION))
        else:
            c.execute(settings.update().where(settings.c.key == "help_seeded").values(value=HELP_VERSION))


# ---------------------------------------------------------------- the Help table
def by_id(rows: pd.DataFrame) -> pd.DataFrame:
    """A table's rows by their ID (column id), lowest first, as every table is shown; a new row (no ID yet) at the bottom,
    in the order it was added."""
    ids = pd.to_numeric(rows["id"], errors="coerce") if "id" in rows.columns else pd.Series([float("nan")] * len(rows))
    order = sorted(range(len(rows)), key=lambda i: (pd.isna(ids.iloc[i]), 0 if pd.isna(ids.iloc[i]) else ids.iloc[i], i))
    return rows.iloc[order].reset_index(drop=True)


def help_sorted(rows: pd.DataFrame) -> pd.DataFrame:
    """The Help rows by ID, as the page shows them (a new row at the bottom)."""
    return by_id(rows)


def help_rows() -> pd.DataFrame:
    """The Help table: id, Abbreviation, Description, by ID."""
    with engine().connect() as c:
        rows = c.execute(sa.select(help_table).order_by(help_table.c.id)).mappings().all()
    return pd.DataFrame([{"id": r["id"], "Abbreviation": r["abbreviation"], "Description": r["description"]} for r in rows],
                        columns=["id", "Abbreviation", "Description"])


def help_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the Help rows: each needs an Abbreviation (at most HELP_ABBR_MOST characters, once in the table) and a Description of
    at most 500 characters. A wholly empty row does not count."""
    out, seen = [], set()
    for _, r in rows.iterrows():
        abbreviation, text = _cell(r["Abbreviation"]), _cell(r["Description"])
        if not (abbreviation or text):
            continue
        label = abbreviation or "New row"
        if not abbreviation:
            out.append(f"{label}: Abbreviation is empty")
        if len(abbreviation) > HELP_ABBR_MOST:
            out.append(f"{label}: Abbreviation can be at most {HELP_ABBR_MOST} characters")
        if len(text) > 500:
            out.append(f"{label}: Description can be at most 500 characters")
        if abbreviation:
            if abbreviation.lower() in seen:
                out.append(f"{label}: is in the table twice")
            seen.add(abbreviation.lower())
    return out


def _row_id(value) -> int | None:
    """A row's id as the page sent it (blank on a new row)."""
    try:
        return int(value) if pd.notna(value) and str(value).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _save_by_id(table: sa.Table, keep: list[tuple[int | None, dict]]) -> int:
    """Makes the table these rows, each kept under its id (so a row keeps its ID across saves): rows not among them go,
    rows with an id are changed in place (only those that differ: a long table saves quickly), new ones (no id, or one no
    longer there) are added with a new id."""
    with engine().begin() as c:
        there = {r["id"]: r for r in c.execute(sa.select(table)).mappings().all()}
        ids = {i for i, _ in keep if i in there}
        gone = set(there) - ids
        if gone:
            c.execute(table.delete().where(table.c.id.in_(gone)))
        added = []
        for i, values in keep:
            if i in ids:
                if any(there[i][k] != v for k, v in values.items()):
                    c.execute(table.update().where(table.c.id == i).values(**values))
            else:
                added.append(values)
        if added:
            c.execute(table.insert(), added)
    return len(keep)


def save_help(rows: pd.DataFrame) -> int:
    """Makes the Help table these rows (wholly empty ones left out), each keeping its ID; gives how many it has."""
    return _save_by_id(help_table, [(_row_id(r.get("id")), dict(abbreviation=_cell(r["Abbreviation"]), description=_cell(r["Description"]) or None))
                                    for _, r in rows.iterrows() if _cell(r["Abbreviation"]) or _cell(r["Description"])])


# ---------------------------------------------------------------- the Conditions table
CONDITIONS_COLUMNS = ["id", "Object", "Values", "Condition"]
# The conditions the app follows while their row is in the table (an admin deletes the row and the app stops following it):
# Table, Login, "Do not track login details for Admin access": no Logins rows for an admin's activity
NO_ADMIN_LOGINS = re.compile(r"(?i)\b(do\s*n[o']?t|no)\s+track\b.*\badmin")   # its Condition, however worded (Do not track login
                                                                               # details for / who have Admin access ..)


def _no_admin_logins(c) -> bool:
    """The App Conditions table has a row Object Table, Values Login (or Logins), Condition "Do not track .. Admin ..":
    while it is there, an admin's activity is not written to the Logins table."""
    if "conditions" not in sa.inspect(c).get_table_names():
        return False
    for obj, values, name in c.execute(sa.select(conditions.c.table_name, conditions.c.value_list, conditions.c.name)).all():
        if ((obj or "").strip().lower() == "table" and NO_ADMIN_LOGINS.search(name or "")
                and any(v.strip().lower() in ("login", "logins") for v in (values or "").split(","))):
            return True
    return False


SEARCHES_A_DAY = re.compile(r"(?i)\bsearch(es)?\b.*\bday\b")   # its Condition: Searches a day for those without DOB access ..


def searches_a_day() -> int | None:
    """The App Conditions table's row Object Search, Condition "Searches a day ..", Values a whole number: while it is
    there, how many unsaved searches a day (UT) one without DOB access may make on DOB Details; None (no limit) without it."""
    with engine().connect() as c:
        for obj, values, name in c.execute(sa.select(conditions.c.table_name, conditions.c.value_list, conditions.c.name)).all():
            if (obj or "").strip().lower() in ("search", "searches") and SEARCHES_A_DAY.search(name or ""):
                try:
                    return max(0, int(str(values or "").strip()))
                except ValueError:
                    return None
    return None


def _search_key(email: str) -> str:
    """The settings row counting a login's unsaved searches today (by a hash of the email: no email kept there)."""
    import hashlib
    return "searches:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]


def searches_today(email: str) -> int:
    """How many unsaved searches this login has made today (UT)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with engine().connect() as c:
        kept = c.execute(sa.select(settings.c.value).where(settings.c.key == _search_key(email))).scalar() or ""
    day, _, n = kept.partition(" ")
    return int(n) if day == today and n.isdigit() else 0


def count_search(email: str) -> None:
    """One more unsaved search for this login today (UT)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    value = f"{today} {searches_today(email) + 1}"
    with engine().begin() as c:
        if c.execute(sa.update(settings).where(settings.c.key == _search_key(email)).values(value=value)).rowcount == 0:
            c.execute(settings.insert().values(key=_search_key(email), value=value))


NO_TRACK = re.compile(r"(?i)\b(do\s*n[o']?t|no)\s+track\b")   # Do not track login details ..
NO_ADMIN_DELETE = re.compile(r"(?i)\b(do\s*n[o']?t|no)\s+delete\b.*\badmin")   # Do not delete customers who have Admin access
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _condition_rows(c) -> list[tuple[str, list[str], str]]:
    """The App Conditions table's rows as (Object, Values, Condition), Object and Values in lower case (read each time: a
    row changed applies at once)."""
    if "conditions" not in sa.inspect(c).get_table_names():
        return []
    return [((o or "").strip().lower(), [v.strip().lower() for v in (vs or "").split(",") if v.strip()], n or "")
            for o, vs, n in c.execute(sa.select(conditions.c.table_name, conditions.c.value_list, conditions.c.name)).all()]


def _no_track_emails(c) -> set[str]:
    """The logins named in an App Conditions row Object Table, Values Login, Condition "Do not track .. for <email> ..":
    their activity is not written to the Logins table."""
    return {e.lower() for o, vs, n in _condition_rows(c) if o == "table" and {"login", "logins"} & set(vs) and NO_TRACK.search(n)
            for e in EMAIL.findall(n)}


def no_admin_delete() -> bool:
    """The App Conditions table has a row Object Table, Values Customers, Condition "Do not delete customers who have Admin
    access": while it is there, a Customers row with Access Admin cannot be deleted."""
    with engine().connect() as c:
        return any(o == "table" and {"customer", "customers"} & set(vs) and NO_ADMIN_DELETE.search(n) for o, vs, n in _condition_rows(c))


def _add_conditions_table_name(eng: sa.Engine):
    """A Conditions table made before its Object column gets it (its rows kept, blank in it)."""
    if "table_name" not in {c["name"] for c in sa.inspect(eng).get_columns("conditions")}:
        with eng.begin() as c:
            c.execute(sa.text(f"ALTER TABLE conditions ADD COLUMN table_name {conditions.c.table_name.type.compile(dialect=eng.dialect)}"))


def conditions_sorted(rows: pd.DataFrame) -> pd.DataFrame:
    """The Conditions rows by ID, as the page shows them (a new row at the bottom)."""
    return by_id(rows)


def conditions_rows() -> pd.DataFrame:
    """The Conditions table: Object, Values, Condition, in the order of Condition (case aside)."""
    with engine().connect() as c:
        rows = c.execute(sa.select(conditions).order_by(conditions.c.id)).mappings().all()
    return pd.DataFrame([{"id": r["id"], "Condition": r["name"], "Object": r["table_name"], "Values": r["value_list"]} for r in rows],
                        columns=CONDITIONS_COLUMNS)


def conditions_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the Conditions rows: each needs a Condition (at most COND_NAME_MOST characters, once in the table,
    whatever its case), an Object of at most COND_NAME_MOST and Values of at most COND_VALUES_MOST. A wholly empty row
    does not count."""
    out, seen = [], set()
    for _, r in rows.iterrows():
        name, table, values = _cell(r["Condition"]), _cell(r.get("Object")), _cell(r["Values"])
        if not (name or table or values):
            continue
        label = name or "New row"
        if not name:
            out.append(f"{label}: Condition is empty")
        if len(name) > COND_NAME_MOST:
            out.append(f"{label}: Condition can be at most {COND_NAME_MOST} characters")
        if len(table) > COND_NAME_MOST:
            out.append(f"{label}: Object can be at most {COND_NAME_MOST} characters")
        if len(values) > COND_VALUES_MOST:
            out.append(f"{label}: Values can be at most {COND_VALUES_MOST} characters")
        if table.lower() in ("search", "searches") and SEARCHES_A_DAY.search(name) and not values.isdigit():
            out.append(f"{label}: Values is how many searches a day, a whole number (e.g. 1)")
        if name:
            if name.lower() in seen:
                out.append(f"{label}: is in the table twice (a Condition is unique)")
            seen.add(name.lower())
    return out


def save_conditions(rows: pd.DataFrame) -> int:
    """Makes the Conditions table these rows (wholly empty ones left out), each keeping its ID; gives how many it has."""
    return _save_by_id(conditions, [(_row_id(r.get("id")), dict(name=_cell(r["Condition"]), table_name=_cell(r.get("Object")) or None,
                                                              value_list=_cell(r["Values"]) or None))
                                    for _, r in rows.iterrows() if _cell(r["Condition"]) or _cell(r.get("Object")) or _cell(r["Values"])])


# ---------------------------------------------------------------- the Predictions table
def _add_prediction_chart(eng: sa.Engine):
    """A Predictions table made before its Chart column is made again with it (its rows kept, as Transit rows), so that
    Chart is unique with Moving, Birth, Kind and Angle."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    if "chart" in {c["name"] for c in sa.inspect(eng).get_columns("predictions")}:
        return
    with eng.begin() as c:
        old = [dict(r) for r in c.execute(sa.text("SELECT id, moving, birth, kind, angle, prediction FROM predictions")).mappings()]
        c.execute(sa.text("DROP TABLE predictions"))
    predictions.create(eng)
    if old:
        with eng.begin() as c:
            c.execute(predictions.insert(), [{**r, "chart": "Transit"} for r in old])
            if eng.dialect.name == "postgresql":              # (the ids go on from the highest)
                c.execute(sa.text("SELECT setval(pg_get_serial_sequence('predictions', 'id'), (SELECT MAX(id) FROM predictions))"))


PRED_ANGLES = [("RA", 0, "conjunct"), ("RA", 60, "sextile"), ("RA", 90, "square"), ("RA", 120, "trine"), ("RA", 180, "opposite"),
               ("RA", 30, "semi-sextile"), ("RA", 45, "semi-square"), ("RA", 72, "quintile"), ("RA", 135, "sesquiquadrate"),
               ("RA", 144, "bi-quintile"), ("RA", 150, "quincunx"),
               ("De", 0, "parallel"), ("De", 180, "contra-parallel")]   # every combination gets each (major and minor angles; De both)


PRED_KIND_ANGLES = PRED_ANGLES + [("RA+De", a, w) for k, a, w in PRED_ANGLES if k == "RA"]   # (RA+De: each aspect of Aspect Rules)


def kind_words(kind: str) -> str:
    """A Kind in an Event's words: RA, De, or RA and De."""
    return "RA and De" if kind == "RA+De" else kind


def prediction_combinations(named_ra: bool = False) -> list[tuple[str, str, str, str, int, str]]:
    """Every combination, as (chart, moving, birth, kind, angle, event): Transit, each planet now (PRED_MOVING) with each
    point of the birth chart (PRED_BIRTH); Birth, each two points of the birth chart once (not NN with SN, always opposite);
    Sky, each two planets now once (not NN with SN; the Sun with the Moon at RA 0 and 180 named New and Full Moon); each at
    PRED_KIND_ANGLES (RA, De, and RA+De: in aspect by Aspect Rules, RA and De together); and Distance, each of DIST_POINTS
    at its closest (Near) and farthest (Far) from the Earth (Ea). The aspects' names (conjunct, square ..) only for RA+De:
    an RA row in plain words, e.g. Saturn and your birth Sun 90° apart in RA (named_ra: as they once were, by name)."""
    def name(p):
        return "house 10 (CB)" if p == "CB" else PLANET_NAMES.get(p, p)

    def plain(kind):                                          # (an RA row's Event in plain words)
        return kind == "RA" and not named_ra
    out = []
    for m in PRED_MOVING:
        for b in PRED_BIRTH:
            for kind, angle, word in PRED_KIND_ANGLES:
                out.append((TRANSIT, m, b, kind, angle, f"{name(m)} and your birth {name(b)} {angle}° apart in RA" if plain(kind) else
                            f"{name(m)} {word} your birth {name(b)} in {kind_words(kind)} ({angle}°)"))
    for i, a in enumerate(PRED_BIRTH):
        for b in PRED_BIRTH[i + 1:]:
            if {a, b} == {"NN", "SN"}:
                continue
            for kind, angle, word in PRED_KIND_ANGLES:
                out.append(("Birth", a, b, kind, angle, f"{name(a)} and {name(b)} {angle}° apart in RA at birth" if plain(kind) else
                            f"{name(a)} {word} {name(b)} in {kind_words(kind)} ({angle}°) at birth"))
    for i, a in enumerate(PRED_MOVING):
        for b in PRED_MOVING[i + 1:]:
            if {a, b} == {"NN", "SN"}:
                continue
            for kind, angle, word in PRED_KIND_ANGLES:
                moon = {a, b} == {"Mo", "Su"} and kind == "RA" and angle in (0, 180)
                lead = ("New Moon: " if angle == 0 else "Full Moon: ") if moon else ""
                out.append((SKY, a, b, kind, angle, f"{lead}{name(a)} and {name(b)} {angle}° apart in RA in the sky" if plain(kind) else
                            f"{lead}{name(a)} {word} {name(b)} in {kind_words(kind)} ({angle}°) in the sky"))
    for p in DIST_POINTS:
        out.append(("Distance", p, "Ea", "Near", 0, f"{name(p)} at its closest to the Earth"))
        out.append(("Distance", p, "Ea", "Far", 0, f"{name(p)} at its farthest from the Earth"))
    return out


PRED_TEXT_ENDS = (" Add your reading.", " Replace this with your own reading.")   # once at the end of the texts the app wrote


def _trim_prediction_texts(eng: sa.Engine):
    """Once (a note among the settings says it is done): the Predictions texts the app wrote lose PRED_TEXT_ENDS at their
    end (the rest of each kept; texts without it are left as they are)."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "predictions_trimmed")).scalar():
            return
        changed = {}
        for i, text in c.execute(sa.select(predictions.c.id, predictions.c.prediction)).all():
            for end in PRED_TEXT_ENDS:
                if text and text.endswith(end):
                    changed[i] = text[: -len(end)]
                    break
        if changed:
            _update_by_id(c, predictions.c.prediction, changed)
        c.execute(settings.insert().values(key="predictions_trimmed", value="1"))


# The Prediction column's readings, made from each planet's and angle's usual meanings (a draft to edit): a Transit
# row, a period the moving planet brings to that part of the birth chart; a Birth row, a lasting trait
TRANSIT_BRINGS = {   # what the planet now brings, and for how long
    "Mo": ("moods, needs and passing feelings", "for a day or two"),
    "Su": ("attention, vitality and visibility", "for a few days"),
    "Me": ("news, talks, errands and ideas", "for a few days"),
    "Ve": ("affection, ease, pleasure and money matters", "for a few days"),
    "Ma": ("energy, drive, haste and friction", "for a week or two"),
    "Ju": ("growth, opportunity and confidence", "over several weeks"),
    "Sa": ("duty, limits, tests and hard work", "over some months"),
    "NN": ("new directions and meetings that point the way", "over some months"),
    "SN": ("endings, release and old patterns coming back", "over some months"),
}
BIRTH_PART = {   # the part of the birth chart (as a Transit's object), and the quality it is at birth
    "Mo": ("your feelings, home and family", "feelings"),
    "Su": ("your sense of self and vitality", "will"),
    "Me": ("your thinking, learning and dealings", "mind"),
    "Ve": ("your relationships, tastes and finances", "affections"),
    "Ma": ("your drive, courage and ambitions", "drive"),
    "Ju": ("your hopes, beliefs and good fortune", "optimism"),
    "Sa": ("your duties, structures and long-term plans", "discipline"),
    "NN": ("your life direction and growth", "life direction"),
    "SN": ("your inborn gifts and past habits", "inborn gifts"),
    "CB": ("your career and public standing", "public aims"),
}
TRANSIT_ANGLE = {   # (kind, angle): how the planet now meets the birth point
    ("RA", 0): "{brings} merge with {part} {span}: a strong, focused influence",
    ("RA", 60): "{brings} open a door for {part} {span}: a chance worth taking",
    ("RA", 90): "{brings} press on {part} {span}: tension that asks for effort and patience",
    ("RA", 120): "{brings} flow easily into {part} {span}: a smooth, supportive time",
    ("RA", 180): "{brings} pull against {part} {span}: others or outside events ask for balance",
    ("RA", 30): "{brings} brush {part} {span}: a light touch, small adjustments",
    ("RA", 45): "{brings} rub against {part} {span}: minor friction to work through",
    ("RA", 72): "{brings} spark {part} {span}: a creative, inventive opening",
    ("RA", 135): "{brings} grate on {part} {span}: niggling strain that asks for care",
    ("RA", 144): "{brings} lend a talent to {part} {span}: a quietly productive time",
    ("RA", 150): "{brings} sit awkwardly with {part} {span}: adjustments are needed",
    ("De", 0): "{brings} quietly charge {part} {span}, like a soft conjunction",
    ("De", 180): "{brings} stand across from {part} {span}, like a soft opposition asking for balance",
}
TRANSIT_ADVICE = {   # the moving planet's advice: (with an easy angle, with a hard one, otherwise)
    "Mo": ("a good moment to rest and connect", "let reactions settle before acting", "notice what you need"),
    "Su": ("a good time to be seen and to lead", "avoid clashes of pride", "put yourself into it"),
    "Me": ("a good time to talk, write, sign or plan", "check details and messages twice", "keep your thoughts clear"),
    "Ve": ("enjoy, mend ties and make peace", "beware overspending and easy indulgence", "let warmth guide you"),
    "Ma": ("act with confidence", "avoid rash moves and quarrels", "channel the energy into action"),
    "Ju": ("a good time to grow, travel or ask for support", "beware promising or taking on too much", "aim high but stay grounded"),
    "Sa": ("patient work builds something lasting", "steady effort pays off, shortcuts do not", "take it seriously and pace yourself"),
    "NN": ("follow the people and chances that appear", "growth comes from the harder path", "a turning point worth heeding"),
    "SN": ("old skills come in useful", "let go of what no longer fits", "review the past to move on"),
}
BIRTH_ANGLE = {   # (kind, angle): how two points of the birth chart meet
    ("RA", 0): "{a} and {b} act as one: a strong, concentrated trait",
    ("RA", 60): "{a} and {b} help each other: talents that grow with use",
    ("RA", 90): "{a} and {b} pull at each other: an inner tension that becomes strength through effort",
    ("RA", 120): "{a} and {b} work in easy harmony: a natural gift",
    ("RA", 180): "{a} and {b} face each other: a lifelong balancing act, often lived out through others",
    ("RA", 30): "{a} and {b} sit side by side: a subtle link that grows with attention",
    ("RA", 45): "{a} and {b} chafe: a small inner friction that drives effort",
    ("RA", 72): "{a} and {b} spark each other: a creative gift",
    ("RA", 135): "{a} and {b} grate: a lasting strain that asks for patience",
    ("RA", 144): "{a} and {b} combine: a quiet talent",
    ("RA", 150): "{a} and {b} need adjusting: two sides of you that learn to cooperate",
    ("De", 0): "{a} and {b} are quietly linked and color each other, like a soft conjunction",
    ("De", 180): "{a} and {b} quietly mirror each other, like a soft opposition seeking balance",
}
SKY_ANGLE = {   # (kind, angle): two planets now, for everyone
    ("RA", 0): "{a} and {b} merge {span}: a strong, shared theme for everyone",
    ("RA", 60): "{a} and {b} support each other {span}: openings for everyone",
    ("RA", 90): "{a} and {b} clash {span}: tension felt widely, asking for effort",
    ("RA", 120): "{a} and {b} flow together {span}: an easy, helpful time for everyone",
    ("RA", 180): "{a} and {b} pull apart {span}: a time of balance and choices",
    ("RA", 30): "{a} and {b} touch lightly {span}: small adjustments in the air",
    ("RA", 45): "{a} and {b} rub {span}: minor friction around",
    ("RA", 72): "{a} and {b} spark {span}: a creative moment",
    ("RA", 135): "{a} and {b} grate {span}: niggling strain around",
    ("RA", 144): "{a} and {b} combine {span}: a quietly productive moment",
    ("RA", 150): "{a} and {b} sit awkwardly {span}: adjustments needed all round",
    ("De", 0): "{a} and {b} share their De {span}, like a soft conjunction for everyone",
    ("De", 180): "{a} and {b} mirror each other's De {span}, like a soft opposition for everyone",
}
MOON_PHASES = {0: "New Moon: a fresh start; a good time for beginnings and intentions",
               180: "Full Moon: things come to light; a time of completion, release and feelings running high"}
SPEED_ORDER = ["Mo", "Su", "Me", "Ve", "Ma", "Ju", "Sa", "NN", "SN"]   # fastest first (a Sky pair lasts as its faster passes)
EASY = {("RA", 60), ("RA", 120), ("RA", 30), ("RA", 72), ("RA", 144)}
HARD = {("RA", 90), ("RA", 180), ("RA", 45), ("RA", 135), ("RA", 150), ("De", 180)}


HOUSE_THEMES = {   # house: (its matters, a lasting trait with a planet there at birth, a passing time with a planet now there)
    1: ("your self, body and the way you come across", "it shows plainly in how you meet the world", "a time to put yourself forward"),
    2: ("your money, belongings and sense of worth", "it shapes what you value and how you earn", "a time to look after what you have and earn"),
    3: ("your talks, studies, short trips and siblings", "it colours how you think, speak and learn", "a busy time of messages, errands and learning"),
    4: ("your home, family and roots", "it runs deep in your home and private life", "a time to tend home and family"),
    5: ("your creativity, pleasure, romance and children", "it comes out in play, love and what you create", "a time to enjoy, create and take a chance"),
    6: ("your daily work, routines and health", "it shows in how you work and look after yourself", "a time to sort out work, habits and health"),
    7: ("your partners, contracts and open dealings", "it is met through partners and the people close to you", "a time when others and agreements take the lead"),
    8: ("shared money, debts, change and what lies hidden", "it works through deep bonds and shared resources", "a time for joint finances and letting go"),
    9: ("your beliefs, higher learning, travel and law", "it reaches out through study, faith and far places", "a time to learn, travel or widen your view"),
    10: ("your career, reputation and public standing", "it is seen in your career and the way the world knows you", "a time when work and standing are in view"),
    11: ("your friends, groups, hopes and plans", "it works through friends and the causes you join", "a time for friends, networks and future plans"),
    12: ("your inner life, rest and what is behind the scenes", "it works quietly, out of sight, in solitude and care", "a time to rest, reflect and finish things"),
}


def prediction_reading(chart: str, moving: str, birth: str, kind: str, angle: int) -> str:
    """The Prediction column's reading for a row (no full stop at the end, as Event), or '' for one it has none for."""
    if kind == "RA+De":                                       # in aspect by Aspect Rules: as the RA one, by RA and De both
        return prediction_reading(chart, moving, birth, "RA", angle)
    key = (kind, int(angle))
    if chart == TRANSIT and moving in TRANSIT_BRINGS and birth in BIRTH_PART and key in TRANSIT_ANGLE:
        brings, span = TRANSIT_BRINGS[moving]
        easy, hard, other = TRANSIT_ADVICE[moving]
        text = TRANSIT_ANGLE[key].format(brings=brings, part=BIRTH_PART[birth][0], span=span)
        return text[0].upper() + text[1:] + "; " + (easy if key in EASY else hard if key in HARD else other)
    if chart == "Birth" and moving in BIRTH_PART and birth in BIRTH_PART and key in BIRTH_ANGLE:
        text = BIRTH_ANGLE[key].format(a="your " + BIRTH_PART[moving][1], b="your " + BIRTH_PART[birth][1])
        return text[0].upper() + text[1:]
    if chart == SKY and moving in TRANSIT_BRINGS and birth in TRANSIT_BRINGS and key in SKY_ANGLE:
        if {moving, birth} == {"Mo", "Su"} and kind == "RA" and int(angle) in MOON_PHASES:
            return MOON_PHASES[int(angle)]
        faster, slower = sorted((moving, birth), key=SPEED_ORDER.index)   # (it lasts as the faster passes; the slower sets the tone)
        text = SKY_ANGLE[key].format(a=PLANET_NAMES[moving], b=PLANET_NAMES[birth], span=TRANSIT_BRINGS[faster][1])
        easy, hard, other = TRANSIT_ADVICE[slower]
        return text[0].upper() + text[1:] + "; " + (easy if key in EASY else hard if key in HARD else other)
    if chart in HOUSE_CHARTS and moving in TRANSIT_BRINGS and birth in HOUSES:
        n = int(birth[1:])
        theme, lasting, passing = HOUSE_THEMES[n]
        if chart == HOUSE_BIRTH:
            return f"Your {BIRTH_PART[moving][1]} works through {theme}: {lasting}"
        brings, span = TRANSIT_BRINGS[moving]
        return f"{brings[0].upper() + brings[1:]} move through {theme} {span}: {passing}"
    if chart == "Distance" and moving in TRANSIT_BRINGS and kind in ("Near", "Far"):
        brings = TRANSIT_BRINGS[moving][0]
        return (f"Its {brings} are felt more strongly and nearer to hand" if kind == "Near" else
                f"Its {brings} feel quieter and more distant")
    return ""


def _update_by_id(c, column: sa.Column, values: dict[int, str]) -> None:
    """Sets column to values[id] in each of those rows, a few hundred rows a statement (one round trip each, quick on a
    distant database too)."""
    items = list(values.items())
    for k in range(0, len(items), 200):
        part = items[k:k + 200]
        c.execute(column.table.update().where(column.table.c.id.in_([i for i, _ in part]))
                  .values({column.name: sa.case({i: sa.cast(sa.literal(v), column.type) for i, v in part}, value=column.table.c.id)}))   # (typed: Postgres needs it)


DEC_WORD = re.compile(r"\bDecs\b|\bDec\b")                   # Dec, as it was called before De (uniform naming)


def _dec_text(text):
    """text with Dec called De (Decs: De values)."""
    return DEC_WORD.sub(lambda m: "De values" if m.group(0) == "Decs" else "De", text) if text else text


def _dec_is_de(eng: sa.Engine):
    """Once (a note among the settings says it is done): Dec is called De everywhere in the data: the Predictions table's
    Kind, Event and Prediction; the Help table's descriptions, its Dec row joining its De row (or becoming it)."""
    tables = sa.inspect(eng).get_table_names()
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "dec_is_de")).scalar():
            return
        if "predictions" in tables:
            c.execute(predictions.update().where(predictions.c.kind == "Dec").values(kind="De"))
            for col in (predictions.c.prediction, predictions.c.forecast):
                rows = c.execute(sa.select(predictions.c.id, col)).all()
                changed = {i: _dec_text(v) for i, v in rows if v and _dec_text(v) != v}
                if changed:
                    _update_by_id(c, col, changed)
        if "help" in tables:
            ids = {a.lower(): i for i, a in c.execute(sa.select(help_table.c.id, help_table.c.abbreviation)).all()}
            if "dec" in ids:
                if "de" in ids:
                    c.execute(help_table.delete().where(help_table.c.id == ids["dec"]))
                else:
                    c.execute(help_table.update().where(help_table.c.id == ids["dec"]).values(abbreviation="De"))
            rows = c.execute(sa.select(help_table.c.id, help_table.c.description)).all()
            changed = {i: _dec_text(v) for i, v in rows if v and _dec_text(v) != v}
            if changed:
                _update_by_id(c, help_table.c.description, changed)
        c.execute(settings.insert().values(key="dec_is_de", value="1"))


def _plain_ra_events(eng: sa.Engine):
    """Once (a note among the settings says it is done): the RA rows' Events still as the app wrote them, by an aspect's
    name (Saturn square your birth Sun in RA (90°)), in plain words (Saturn and your birth Sun 90° apart in RA): the names
    are for RA+De only. An Event changed since is left as it is."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "ra_plain_words2")).scalar():
            return
        old = {r[:5]: r[5] for r in prediction_combinations(named_ra=True) if r[3] == "RA"}
        new = {r[:5]: r[5] for r in prediction_combinations() if r[3] == "RA"}
        samples = {(TRANSIT, "Sa", "Su", "RA", 180): ("Saturn opposite your birth Sun in RA", "Saturn and your birth Sun 180° apart in RA"),
                   ("Birth", "Su", "Sa", "RA", 90): ("Sun square Saturn in RA at birth", "Sun and Saturn 90° apart in RA at birth")}
        rows = c.execute(sa.select(predictions.c.id, predictions.c.chart, predictions.c.moving, predictions.c.birth,
                                   predictions.c.kind, predictions.c.angle, predictions.c.prediction)
                         .where(predictions.c.kind == "RA")).all()
        changed = {}
        for i, ch, m, b, k, a, text in rows:
            key = next((x for x in ((ch, m, b, k, a), (ch, b, m, k, a)) if x in old), None)   # (Birth, Sky: either way round)
            if key and text == old[key]:
                changed[i] = new[key]
            elif (ch, m, b, k, a) in samples:                 # the app's sample rows, with or without "Sample: "
                was, now = samples[(ch, m, b, k, a)]
                if text in (was, "Sample: " + was):
                    changed[i] = text.replace(was, now)
        if changed:
            _update_by_id(c, predictions.c.prediction, changed)
        c.execute(settings.insert().values(key="ra_plain_words2", value="1"))


def _fill_prediction_readings(eng: sa.Engine):
    """Once (a note among the settings says it is done): every Predictions row with an empty Prediction gets its reading
    (prediction_reading); a Prediction already written is left as it is."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "predictions_readings")).scalar():
            return
        rows = c.execute(sa.select(predictions.c.id, predictions.c.chart, predictions.c.moving, predictions.c.birth,
                                   predictions.c.kind, predictions.c.angle, predictions.c.forecast)).all()
        fill = {i: text for i, ch, m, b, k, a, f in rows if not (f or "").strip() and (text := prediction_reading(ch, m, b, k, a))}
        if fill:
            _update_by_id(c, predictions.c.forecast, fill)
        c.execute(settings.insert().values(key="predictions_readings", value="1"))


DROPPED_STARTS = (("In RA and De both, so stronger:", "no_stronger"),     # (once at the start of RA+De rows' Predictions)
                  ("At its farthest from the Earth:", "no_farthest"),    # (and of Distance Far rows')
                  ("At its closest to the Earth:", "no_closest"))        # (and Near rows')


def _drop_starts(eng: sa.Engine):
    """Once each (a note among the settings says it is done): a Prediction starting with one of DROPPED_STARTS loses it
    (and the space after it; its first letter made capital); the rest of the text is left as it is."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        for start, note in DROPPED_STARTS:
            if c.execute(sa.select(settings.c.value).where(settings.c.key == note)).scalar():
                continue
            rows = c.execute(sa.select(predictions.c.id, predictions.c.forecast).where(predictions.c.forecast.startswith(start))).all()
            fix = {i: (rest[:1].upper() + rest[1:]) for i, f in rows if (rest := f[len(start):].lstrip())}
            if fix:
                _update_by_id(c, predictions.c.forecast, fix)
            c.execute(settings.insert().values(key=note, value="1"))


def _add_prediction_forecast(eng: sa.Engine):
    """A Predictions table made before the Prediction column gets it (column forecast, empty in the rows there)."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    if "forecast" not in {c["name"] for c in sa.inspect(eng).get_columns("predictions")}:
        with eng.begin() as c:
            c.execute(sa.text(f"ALTER TABLE predictions ADD COLUMN forecast {predictions.c.forecast.type.compile(dialect=eng.dialect)}"))


def _drop_prediction_dots(eng: sa.Engine):
    """Once (a note among the settings says it is done): every Predictions text loses the full stop at its end."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "predictions_no_dot")).scalar():
            return
        changed = {i: text.rstrip().rstrip(".").rstrip() for i, text in c.execute(sa.select(predictions.c.id, predictions.c.prediction)).all()
                   if text and text.rstrip().endswith(".")}
        if changed:
            _update_by_id(c, predictions.c.prediction, changed)
        c.execute(settings.insert().values(key="predictions_no_dot", value="1"))


PRED_SEEDED_KINDS = ("RA+De", "Near", "Far", "House")       # the rows the app adds: RA+De, Distance's and the houses' (2026-11-19: RA and De deleted)


def _transit_is_tfsab(eng: sa.Engine):
    """The Predictions table's Chart Transit (and, for a while, TfSaB, PTfBP, then TfBP) is called TABP (TRANSIT): each once (a
    note among the settings says it is done)."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        for old, note in (("Transit", "transit_is_tfsab"), ("TfSaB", "tfsab_is_ptfbp"), ("PTfBP", "ptfbp_is_tfbp"), ("TfBP", "tfbp_is_tabp")):
            if c.execute(sa.select(settings.c.value).where(settings.c.key == note)).scalar():
                continue
            c.execute(predictions.update().where(predictions.c.chart == old).values(chart=TRANSIT))
            c.execute(settings.insert().values(key=note, value="1"))


def _sky_is_pt(eng: sa.Engine):
    """The Predictions table's Chart Sky (and, for a while, PT, TEON, then TAEON) is called Mundane (SKY): each once (a note among the
    settings says it is done)."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        for old, note in (("Sky", "sky_is_pt"), ("PT", "pt_is_teon"), ("TEON", "teon_is_taeon"), ("TAEON", "taeon_is_mundane")):
            if c.execute(sa.select(settings.c.value).where(settings.c.key == note)).scalar():
                continue
            c.execute(predictions.update().where(predictions.c.chart == old).values(chart=SKY))
            c.execute(settings.insert().values(key=note, value="1"))


def _keep_rade_only(eng: sa.Engine):
    """Once (a note among the settings says it is done): the Predictions table keeps only its RA+De rows (in aspect by
    Aspect Rules) and its Distance rows (Near, Far); its RA and De rows are deleted, and the app adds none again
    (PRED_SEEDED_KINDS). Rows of those kinds an admin adds later stay."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "predictions_rade_only")).scalar():
            return
        c.execute(predictions.delete().where(predictions.c.kind.notin_(PRED_SEEDED_KINDS)))
        c.execute(settings.insert().values(key="predictions_rade_only", value="1"))


def _seed_houses(eng: sa.Engine):
    """Once (a note among the settings says it is done; a row deleted since stays deleted): the Predictions table gets an
    HB row (Houses at Birth) for each planet of PRED_MOVING in each house H01 .. H12, with its reading (prediction_reading),
    where it lacks one."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "houses_seeded")).scalar():
            return
        have = {(ch, m, b) for ch, m, b in c.execute(sa.select(predictions.c.chart, predictions.c.moving, predictions.c.birth)
                                                     .where(predictions.c.chart == HOUSE_BIRTH)).all()}
        new = [dict(chart=ch, moving=m, birth=h, kind="House", angle=0,
                    prediction=f"{PLANET_NAMES[m]} in {h} at birth",
                    forecast=prediction_reading(ch, m, h, "House", 0) or None)
               for ch in (HOUSE_BIRTH,) for m in PRED_MOVING for h in HOUSES if (ch, m, h) not in have]
        if new:
            c.execute(predictions.insert(), new)
        c.execute(settings.insert().values(key="houses_seeded", value="1"))


def _drop_ht_rows(eng: sa.Engine):
    """Once (a note among the settings says it is done): the Predictions table's HT rows (Houses Now, taken off the
    Predictions page) are deleted."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "ht_rows_dropped")).scalar():
            return
        c.execute(predictions.delete().where(predictions.c.chart == "HT"))
        c.execute(settings.insert().values(key="ht_rows_dropped", value="1"))


def _seed_houses_now(eng: sa.Engine):
    """Once (a note among the settings says it is done; a row deleted since stays deleted), after _drop_ht_rows: the
    Predictions table gets an HT row (Houses at Now, once Houses Now, back on the Predictions page) for each planet of PRED_MOVING in each house
    H01 .. H12, with its reading (prediction_reading), where it lacks one."""
    if "predictions" not in sa.inspect(eng).get_table_names():
        return
    with eng.begin() as c:
        if c.execute(sa.select(settings.c.value).where(settings.c.key == "ht_rows_seeded")).scalar():
            return
        have = {(m, b) for m, b in c.execute(sa.select(predictions.c.moving, predictions.c.birth)
                                             .where(predictions.c.chart == HOUSE_NOW)).all()}
        new = [dict(chart=HOUSE_NOW, moving=m, birth=h, kind="House", angle=0, prediction=f"{PLANET_NAMES[m]} in {h}, your birth house, now",
                    forecast=prediction_reading(HOUSE_NOW, m, h, "House", 0) or None)
               for m in PRED_MOVING for h in HOUSES if (m, h) not in have]
        if new:
            c.execute(predictions.insert(), new)
        c.execute(settings.insert().values(key="ht_rows_seeded", value="1"))


def _seed_predictions(eng: sa.Engine):
    """Once per set (a note among the settings says which; a row deleted since stays deleted): the Predictions table gets
    the Transit sample rows of PREDICTION_ROWS (when it is empty), then the Birth ones of PREDICTION_BIRTH_ROWS, then
    every combination (prediction_combinations) it lacks (a Birth pair already there either way round counts; rows
    already there keep their Prediction)."""
    with eng.begin() as c:
        done = c.execute(sa.select(settings.c.value).where(settings.c.key == "predictions_seeded")).scalar()
        if done == "6":
            return
        c.execute(predictions.update().where(predictions.c.chart == "Aspect").values(chart=SKY))   # (Chart Aspect: Sky's, now TAEON's, RA+De)
        new = []
        if done is None and not c.execute(sa.select(predictions.c.id).limit(1)).first():
            new += [dict(chart=TRANSIT, moving=m, birth=b, kind=k, angle=a, prediction=p) for m, b, k, a, p in PREDICTION_ROWS
                    if k in PRED_SEEDED_KINDS]
        if done in (None, "1"):
            have = {(m, b, k, a) for m, b, k, a in c.execute(sa.select(predictions.c.moving, predictions.c.birth, predictions.c.kind,
                                                                       predictions.c.angle).where(predictions.c.chart == "Birth")).all()}
            new += [dict(chart="Birth", moving=m, birth=b, kind=k, angle=a, prediction=p) for m, b, k, a, p in PREDICTION_BIRTH_ROWS
                    if (m, b, k, a) not in have and k in PRED_SEEDED_KINDS]
        have = {(ch, m, b, k, a) for ch, m, b, k, a in c.execute(sa.select(predictions.c.chart, predictions.c.moving, predictions.c.birth,
                                                                         predictions.c.kind, predictions.c.angle)).all()}
        have |= {(r["chart"], r["moving"], r["birth"], r["kind"], r["angle"]) for r in new}
        later = done is not None and done.isdigit() and int(done) >= 3   # (set 3 had the major angles: the new ones get their readings now)
        for ch, m, b, k, a, p in prediction_combinations():
            if k not in PRED_SEEDED_KINDS:                    # (the rows the app adds: RA+De and Distance's; RA and De deleted for good)
                continue
            if (ch, m, b, k, a) in have or (ch in ("Birth", SKY) and (ch, b, m, k, a) in have):
                continue
            new.append(dict(chart=ch, moving=m, birth=b, kind=k, angle=a, prediction=p,
                            forecast=prediction_reading(ch, m, b, k, a) or None if later else None))
        for row in new:                                       # (every row the same fields: one insert for them all)
            row.setdefault("forecast", None)
        if new:
            c.execute(predictions.insert(), new)
        if done is None:
            c.execute(settings.insert().values(key="predictions_seeded", value="6"))
        else:
            c.execute(settings.update().where(settings.c.key == "predictions_seeded").values(value="6"))


def prediction_aspects() -> list[str]:
    """What a Prediction Rules row's Aspect may be: the aspects' names (as Aspect Rules names them), Closest and Farthest
    (Distance rows), Parallel and Contra-parallel (De rows)."""
    return list(_aspect_names().values()) + ["Closest", "Farthest", "In house", "Parallel", "Contra-parallel"]


def row_kind(r) -> str:
    """A Predictions row's kind (its Kind column is not shown): a Distance row's from its Aspect, Closest (Near) or Farthest
    (Far); any other row's as kept (RA, De or RA+De), a new one's RA+De ('' for a Distance row with neither)."""
    kept = _cell(r.get("Kind"))
    if _pick(PRED_CHARTS, r.get("Chart")) in HOUSE_CHARTS:
        return "House"
    if _pick(PRED_CHARTS, r.get("Chart")) == "Distance":
        aspect = _cell(r.get("Aspect"))
        return {"Closest": "Near", "Farthest": "Far"}.get(aspect, kept if kept in ("Near", "Far") else "")
    return kept if kept in ("RA", "De", "RA+De") else "RA+De"


def row_angle(r):
    """A Predictions row's angle, as the page shows it: in its De column for a De row, else its RA column (RA blank on an
    RA+De row: its Aspect's angle, by name; a Distance row: 0); NaN when not a number."""
    kind = row_kind(r)
    value = pd.to_numeric(r.get("De" if kind == "De" else "RA"), errors="coerce")
    if pd.isna(value) and kind == "RA+De":
        value = next((a for a, n in _aspect_names().items() if n == _cell(r.get("Aspect"))), value)
    return 0 if kind in ("Near", "Far", "House") or _pick(PRED_CHARTS, r.get("Chart")) == "Distance" and pd.isna(value) else value


def aspect_name(kind, angle) -> str:
    """A rule's aspect by name: RA+De, the name of its Angle among the aspects (Conjunction 0 .. Quincunx 150, as Aspect Rules
    names them: those names only for RA+De); De, Parallel (0) or Contra-parallel (180); Near, Closest; Far, Farthest ('' for
    RA, and for none of those)."""
    kind, a = _cell(kind), pd.to_numeric(angle, errors="coerce")
    if kind in ("Near", "Far"):
        return "Closest" if kind == "Near" else "Farthest"
    if kind == "House":
        return "In house"
    if pd.isna(a):
        return ""
    if kind == "De":
        return {0: "Parallel", 180: "Contra-parallel"}.get(int(a), "")
    if kind == "RA+De":
        return _aspect_names().get(float(a), "")
    return ""


@functools.lru_cache(maxsize=1)
def _aspect_names() -> dict[float, str]:
    """The aspects' names by angle, as Aspect Rules names them (read once)."""
    names = core.default_orb_table()
    return {float(x): str(n) for n, x in zip(names["Aspect"], names["Angle"]) if pd.notna(x)}


def predictions_sorted(rows: pd.DataFrame) -> pd.DataFrame:
    """The Predictions rows by ID, as the page shows them (a new row at the bottom), with each one's Kind (not shown) and Aspect by
    name (after De): an RA+De row's from its RA; a Distance row's Closest or Farthest, as picked."""
    rows = by_id(rows)                                        # (by ID; a new row at the bottom)
    kinds = [row_kind(r) for _, r in rows.iterrows()]
    angles = [row_angle(r) for _, r in rows.iterrows()]
    rows["Kind"] = kinds                                      # (not shown: from Chart and Aspect)
    for i, (kind, angle) in enumerate(zip(kinds, angles)):   # (an RA+De row's RA from its Aspect when left blank)
        if kind == "RA+De" and pd.isna(pd.to_numeric(rows.at[i, "RA"], errors="coerce")) and pd.notna(angle):
            rows.at[i, "RA"] = angle
    aspects = [aspect_name(k, a) if k else _cell(r.get("Aspect")) for k, a, (_, r) in zip(kinds, angles, rows.iterrows())]
    rows = rows.drop(columns="Aspect", errors="ignore")
    rows.insert(rows.columns.get_loc("De") + 1, "Aspect", aspects)
    return rows


def predictions_rows() -> pd.DataFrame:
    """The Predictions table: id, Chart, Moving, Birth, Kind, Angle, Aspect (its name), Event (its prediction), Prediction
    (its forecast), as the page shows it."""
    with engine().connect() as c:
        rows = c.execute(sa.select(predictions)).mappings().all()
    df = pd.DataFrame([{"id": r["id"], "Chart": r["chart"], "Moving": r["moving"], "Birth": r["birth"], "Kind": r["kind"],
                        "RA": r["angle"] if r["kind"] in ("RA", "RA+De") else None, "De": r["angle"] if r["kind"] == "De" else None,
                        "Event": r["prediction"], "Prediction": r["forecast"]} for r in rows], columns=PREDICTIONS_COLUMNS)
    return predictions_sorted(df)


def prediction_rules() -> list[tuple[str, str, str, str, int, str, str]]:
    """The Predictions rows as (chart, moving, birth, kind, angle, events, prediction), for the Predictions page."""
    with engine().connect() as c:
        rows = c.execute(sa.select(predictions.c.chart, predictions.c.moving, predictions.c.birth, predictions.c.kind,
                                   predictions.c.angle, predictions.c.prediction, predictions.c.forecast)).all()
    return [(ch, m, b, k, int(a), p or "", f or "") for ch, m, b, k, a, p, f in rows]


def _pick(names: list[str], value) -> str:
    """value as one of names, whatever its case ('' when it is none of them)."""
    v = _cell(value).lower()
    return next((n for n in names if n.lower() == v), "")


def predictions_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the Predictions rows: each needs a Chart (PRED_CHARTS), and by its Chart: Transit, a Moving planet
    (PRED_MOVING) and a Birth point (PRED_BIRTH); Birth, two different points of PRED_BIRTH; Sky, two different planets of
    PRED_MOVING (not NN with SN); each of those a Kind, RA or De, and an Angle (a whole number, 0 to 180; De: 0 or 180);
    Distance, a planet of DIST_POINTS, Birth Ea (the Earth), Kind Near or Far and Angle 0. Every row an Event, and a
    Prediction of at most PRED_TEXT_MOST characters; Chart, Moving, Birth, Kind and Angle together once in the table (a
    Birth or Sky row's two points either way round: Su-Mo and Mo-Su are one pair). A wholly empty row does not count."""
    out, seen = [], set()
    for _, r in rows.iterrows():
        cells = [_cell(r.get(c)) for c in PREDICTIONS_COLUMNS[1:]]
        if not any(cells):
            continue
        chart = _pick(PRED_CHARTS, r.get("Chart"))
        movers = {"Birth": PRED_BIRTH, "Distance": DIST_POINTS}.get(chart, PRED_MOVING)
        others = {TRANSIT: PRED_BIRTH, "Birth": PRED_BIRTH, SKY: PRED_MOVING, "Distance": ["Ea"],
                  HOUSE_BIRTH: HOUSES, HOUSE_NOW: HOUSES}.get(chart, PRED_BIRTH)
        moving, birth, kind = _pick(movers, r.get("Moving")), _pick(others, r.get("Birth")), row_kind(r)
        angle = row_angle(r)
        other = pd.to_numeric(r.get("RA" if kind == "De" else "De"), errors="coerce")   # (the column a row of its Kind leaves blank)
        text = _cell(r.get("Event"))
        label = " ".join(c for c in cells[:5] if c) or "New row"
        if not chart:
            out.append(f"{label}: Chart must be one of {', '.join(PRED_CHARTS)}")
        if not moving:
            out.append(f"{label}: P1/Now must be one of {', '.join(movers)}")
        elif chart in ("Birth", SKY) and moving == birth:
            out.append(f"{label}: a {chart} row needs two different points (P1/Now and P2/Bth/Ho)")
        elif chart == SKY and {moving, birth} == {"NN", "SN"}:
            out.append(f"{label}: NN and SN are always opposite (no {chart} row for them)")
        if not birth:
            out.append(f"{label}: P2/Bth/Ho must be " + ("Ea (the Earth)" if chart == "Distance" else f"one of {', '.join(others)}"))
        if not kind:
            out.append(f"{label}: a Distance row's Event must be Closest or Farthest")
        elif kind == "RA+De" and _cell(r.get("Aspect")) and pd.notna(angle) and _cell(r.get("Aspect")) != aspect_name(kind, angle):
            out.append(f"{label}: Event {_cell(r.get('Aspect'))} and Angle {int(angle)} disagree (clear one, and the other sets it)")
        column = "De" if kind == "De" else "Angle"                # (the RA column, headed Angle)
        if chart == "Distance" or chart in HOUSE_CHARTS:
            ra = pd.to_numeric(r.get("RA"), errors="coerce")
            if pd.notna(ra) and int(ra) != 0 or pd.notna(pd.to_numeric(r.get("De"), errors="coerce")):
                out.append(f"{label}: {'an' if chart[:1] in 'AEIOUH' else 'a'} {chart} row leaves Angle blank")   # (an HB, an HT)
        elif pd.isna(angle) or float(angle) != int(angle) or not 0 <= angle <= 180:
            out.append(f"{label}: {column} must be a whole number from 0 to 180" + (" (0 parallel, 180 contra-parallel)" if kind == "De" else ""))
        elif kind == "De" and int(angle) not in (0, 180):
            out.append(f"{label}: De is 0 (parallel) or 180 (contra-parallel)")
        elif kind and pd.notna(other):
            out.append(f"{label}: {'an' if kind.startswith('RA') else 'a'} {kind} row leaves {'Angle' if kind == 'De' else 'De'} blank")
        if len(text) > PRED_TEXT_MOST:                         # (Event: not shown, nor needed)
            out.append(f"{label}: Event can be at most {PRED_TEXT_MOST} characters")
        if len(_cell(r.get("Prediction"))) > PRED_TEXT_MOST:
            out.append(f"{label}: Prediction can be at most {PRED_TEXT_MOST} characters")
        if chart and moving and birth and kind and pd.notna(angle):
            pair = tuple(sorted((moving, birth))) if chart in ("Birth", SKY) else (moving, birth)   # (Su-Mo and Mo-Su are one pair)
            key = (chart, *pair, kind, int(angle))
            if key in seen:
                out.append(f"{label}: is in the table twice (Chart, P1/Now, P2/Bth/Ho and Angle, De or Event are unique together"
                           + (f"; a {chart} row's two points count either way round)" if chart in ("Birth", SKY) else ")"))
            seen.add(key)
    return out


def save_predictions(rows: pd.DataFrame) -> int:
    """Makes the Predictions table these rows (wholly empty ones left out), each keeping its ID; gives how many it has."""
    return _save_by_id(predictions, [
        (_row_id(r.get("id")), dict(chart=_pick(PRED_CHARTS, r.get("Chart")), moving=_pick(PRED_BIRTH, r.get("Moving")),
                                    birth=_pick(PRED_BIRTH + ["Ea"] + HOUSES, r.get("Birth")),
                                    kind=row_kind(r), angle=int(row_angle(r)),
                                    prediction=_cell(r.get("Event")) or None, forecast=_cell(r.get("Prediction")) or None))
        for _, r in rows.iterrows() if any(_cell(r.get(c)) for c in PREDICTIONS_COLUMNS[1:])])


# ---------------------------------------------------------------- the Defaults table
DEFAULTS_COLUMNS = ["id", "Page", "Choice", "Choice Values", "Allowed Values"]


def defaults_table() -> pd.DataFrame:
    """The Defaults table as its page shows it: Page, Choice (the input), Choice Values (what it starts as) and
    Allowed Values, sorted by Page, then Options, then Choice (case aside)."""
    with engine().connect() as c:
        rows = c.execute(sa.select(defaults).order_by(defaults.c.id)).mappings().all()   # (by ID)
    return pd.DataFrame([{"id": r["id"], "Page": r["page"], "Choice": r["options"], "Choice Values": r["choices"],
                          "Allowed Values": r["allowed_values"]} for r in rows], columns=DEFAULTS_COLUMNS)


def defaults_allowed_map() -> dict[tuple[str, str], str]:
    """The Defaults table's Allowed Values ("" when blank) by its Page and Choice, both in lower case."""
    with engine().connect() as c:
        rows = c.execute(sa.select(defaults.c.page, defaults.c.options, defaults.c.allowed_values)).all()
    return {(p.strip().lower(), t.strip().lower()): (a or "").strip() for p, t, a in rows}


def defaults_map() -> dict[tuple[str, str], str]:
    """The Defaults table's Choice by its Page and Options, both in lower case."""
    with engine().connect() as c:
        rows = c.execute(sa.select(defaults.c.page, defaults.c.options, defaults.c.choices)).all()
    return {(p.strip().lower(), t.strip().lower()): o or "" for p, t, o in rows}


def defaults_problems(rows: pd.DataFrame) -> list[str]:
    """What is wrong with the Defaults rows: each needs a Page and Choice (the input; Page and Choice at most 60
    characters), one row per Page and Choice, and Choice Values of at most 500 characters. A wholly empty row does not count."""
    out, seen = [], set()
    for _, r in rows.iterrows():
        page, title, value = _cell(r["Page"]), _cell(r["Choice"]), _cell(r["Choice Values"])
        if not (page or title or value):
            continue
        label = f"{page or 'New row'} / {title}" if title else (page or "New row")
        if not page:
            out.append(f"{label}: Page is empty")
        if not title:
            out.append(f"{label}: Choice is empty")
        if len(page) > 60 or len(title) > 60:
            out.append(f"{label}: Page and Choice can be at most 60 characters")
        if len(value) > 500:
            out.append(f"{label}: Choice Values can be at most 500 characters")
        if page and title:
            if (page.lower(), title.lower()) in seen:
                out.append(f"{label}: is in the table twice")
            seen.add((page.lower(), title.lower()))
    return out


def save_defaults(rows: pd.DataFrame) -> int:
    """Makes the Defaults table these rows, as its page shows them (wholly empty ones left out), each keeping its ID; gives
    how many it has."""
    return _save_by_id(defaults, [(_row_id(r.get("id")), dict(page=_cell(r["Page"]), options=_cell(r["Choice"]),
                                                           choices=_cell(r["Choice Values"]) or None,
                                                           allowed_values=_cell(r.get("Allowed Values")) or None))
                                  for _, r in rows.iterrows() if _cell(r["Page"]) or _cell(r["Choice"]) or _cell(r["Choice Values"])])


def _add_orb_nn_ra(eng: sa.Engine):
    """An Aspect Rules table made before its NN-RA and SN-RA columns gets them, each row as its Ju-RA (as the defaults have them)."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("aspect_details")}
    with eng.begin() as c:
        for col, like in (("nn_ra", "ju_ra"), ("sn_ra", "ju_ra")):
            if col not in have:
                kind = aspect_details.c[col].type.compile(dialect=eng.dialect)
                c.execute(sa.text(f"ALTER TABLE aspect_details ADD COLUMN {col} {kind}"))
                c.execute(sa.text(f"UPDATE aspect_details SET {col} = {like}"))


POINT_ORB_COLUMNS = ["CB-RA", "CN-RA", "CB-De", "CN-De"]     # the house points' orbs (0 to start: a pair then takes the planet's)


def _add_orb_points(eng: sa.Engine):
    """An Aspect Rules table made before CB's and CN's orb columns (CB-RA, CN-RA, CB-De, CN-De) gets them, each 0, so that
    a pair with CB or CN keeps the planet's orb alone, as before, until an admin sets them."""
    have = {c["name"] for c in sa.inspect(eng).get_columns("aspect_details")}
    with eng.begin() as c:
        for col in [k.lower().replace("-", "_") for k in POINT_ORB_COLUMNS]:
            if col not in have:
                c.execute(sa.text(f"ALTER TABLE aspect_details ADD COLUMN {col} {aspect_details.c[col].type.compile(dialect=eng.dialect)}"))
                c.execute(sa.text(f"UPDATE aspect_details SET {col} = 0"))


def _add_orb_dec(eng: sa.Engine):
    """Once (a note among the settings says it is done): the Aspect Rules table gets its De orbs back (Mo-De .. SN-De),
    each as its RA orb, so that the aspects found stay as they were (old De orbs kept in the table are replaced)."""
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
        rows = _orb_rows(table.dropna(subset=["Angle"]).head(1))   # (one row: for every angle)
        if rows:
            c.execute(aspect_details.insert(), rows)


ALL_ASPECTS = "All aspects"                                   # the Aspect Rules table's one row


def _one_orb_row(eng: sa.Engine):
    """An Aspect Rules table with a row per aspect keeps only its first (by pos), as the one row for every angle."""
    with eng.begin() as c:
        rows = c.execute(sa.select(aspect_details.c.angle).order_by(aspect_details.c.pos)).all()
        if not rows or (len(rows) == 1 and rows[0][0] == 0.0):
            return
        keep = rows[0][0]
        c.execute(sa.delete(aspect_details).where(aspect_details.c.angle != keep))
        c.execute(aspect_details.update().values(angle=0.0, pos=0, aspect=ALL_ASPECTS))


def _orb_rows(table: pd.DataFrame) -> list[dict]:
    """The one row to keep: the table's first, for every angle."""
    rows = []
    for pos, (_, r) in enumerate(table.head(1).iterrows()):
        row = {"angle": 0.0, "pos": pos, "aspect": ALL_ASPECTS}
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
    """A table made before Size_Clock-3D gets it, each row as its Size_Geo (as Equatorial-3D drew them then)."""
    if "size_clock_3d" in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        return
    kind = planets.c.size_clock_3d.type.compile(dialect=eng.dialect)
    with eng.begin() as c:
        c.execute(sa.text(f"ALTER TABLE naming_conventions ADD COLUMN size_clock_3d {kind}"))
        c.execute(sa.text("UPDATE naming_conventions SET size_clock_3d = size"))


def _add_planet_size_clock(eng: sa.Engine):
    """A table made before Size_Clock-2D gets it, each row as its Size_Geo (as Equatorial-2D drew them then)."""
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


def _number_planets(eng: sa.Engine):
    """Every Symbols row gets an ID (a table made before has its id column added): rows with none are numbered after the
    highest, in the app's order of the planets."""
    if "id" not in {c["name"] for c in sa.inspect(eng).get_columns("naming_conventions")}:
        with eng.begin() as c:
            c.execute(sa.text("ALTER TABLE naming_conventions ADD COLUMN id INTEGER"))
    with eng.begin() as c:
        rows = c.execute(sa.select(planets.c.sn, planets.c.id)).all()
        top = max([i for _, i in rows if i is not None], default=0)
        order = {p: n for n, p in enumerate(PLANET_NAMES)}
        for sn in sorted((s for s, i in rows if i is None), key=lambda s: (order.get(s, len(order)), s)):
            top += 1
            c.execute(planets.update().where(planets.c.sn == sn).values(id=top))


def all_planets() -> pd.DataFrame:
    """The Symbols table: SN, Symbol, Name, Color, Color_Name, Size_Clock-3D, Size (Size_Geo), Size_Helio, Size_Clock-2D, Sun first."""
    with engine().connect() as c:
        rows = c.execute(sa.select(planets).order_by(planets.c.id)).mappings().all()   # (by ID)
    return pd.DataFrame([{"id": r["id"], "SN": r["sn"], "Symbol": r["symbol"], "Name": r["name"], "Color": r["color"], "Color_Name": r["color_name"], "Size_Clock-3D": r["size_clock_3d"],
                          "Size": r["size"], "Size_Helio": r["size_helio"], "Size_Clock-2D": r["size_clock_2d"]}
                         for r in rows], columns=["id", "SN", "Symbol", "Name", "Color", "Color_Name", "Size_Clock-3D", "Size", "Size_Helio", "Size_Clock-2D"])


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
    _number_planets(engine())                                 # (and new rows get their IDs)
    return added, changed, len(set(old) - kept)


def orb_problems(row: pd.DataFrame) -> list[str]:
    """What is wrong with the Aspect Rules table's one row: every orb must be a number of 0 or more."""
    numbers = row[[c for c in ORB_COLUMNS if c in row]].apply(pd.to_numeric, errors="coerce")
    bad = [c for c in numbers.columns if numbers[c].isna().any() or (numbers[c] < 0).any()]
    return [f"Every orb must be a number of 0 or more (not {', '.join(bad)})."] if bad else []


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
    one_day = dict(access="DOB", start_date=now, end_date=access.period_end(now))
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
    data = dict(access=value, start_date=now, end_date=access.period_end(now) if value in access.LASTS else None)
    if c.execute(sa.select(accounts.c.id).where(accounts.c.email == email.lower())).first():
        c.execute(accounts.update().where(accounts.c.email == email.lower()).values(**data))
    else:
        c.execute(accounts.insert().values(email=email.lower(), **data))


def accounts_table() -> pd.DataFrame:
    """The Customers table, by Email: id, email, access, start_date, end_date."""
    with engine().connect() as c:
        return pd.read_sql(sa.select(accounts).order_by(accounts.c.id), c)   # (by ID)


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
    return out


def save_accounts(edited: pd.DataFrame, original: pd.DataFrame, by: str | None = None) -> tuple[int, int, int]:
    """Apply an edited copy of the Customers table: (added, changed, deleted). A blank Access is Now. A typed End Date
    lengthens or shortens DOB (the row becoming DOB); a row newly DOB with no End Date typed gets 1 day from now; Now
    and Admin have none. Start Date as typed when changed (a DOB keeps its length);
    blank on a new row: now. The DOB records refer to it by Email: a changed Email is changed on
    them too, and a row whose Email DOB records still use cannot be deleted. Raises ValueError, saving nothing, on
    account_problems or such a delete."""
    problems = account_problems(edited)
    kept_ids = set(edited["id"].dropna().astype(int)) if "id" in edited else set()
    still = {str(e).strip().lower() for e in edited.get("email", pd.Series(dtype=object)) if isinstance(e, str)}
    gone = [str(r["email"]).strip().lower() for _, r in original.iterrows()
            if pd.notna(r["id"]) and int(r["id"]) not in kept_ids and str(r["email"]).strip().lower() not in still]
    admins_gone = [str(r["email"]).strip() for _, r in original.iterrows() if pd.notna(r["id"]) and int(r["id"]) not in kept_ids
                   and str(r.get("access") or "").strip().lower() == "admin"]
    if admins_gone and no_admin_delete():                     # (App Conditions: Do not delete customers who have Admin access)
        problems.append("Not deleted: " + ", ".join(admins_gone) + " (Access Admin; App Conditions: Do not delete customers who "
                        "have Admin access).")
    used = dob_emails_in_use(gone)
    if used:
        problems.append("Not deleted: DOB records still use " + ", ".join(f"{e} ({n} record{'s' if n != 1 else ''})" for e, n in sorted(used.items()))
                        + ". Delete those records on the DOB page, or give them another Email, first.")
    if problems:
        raise ValueError(" ".join(problems))
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
                return start, access.period_end(start) if a in access.LASTS else None

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
        _log(c, by, "Create", added, details="Customers table")
        _log(c, by, "Update", changed, details="Customers table")
        _log(c, by, "Delete", deleted, details="Customers table")
    return added, changed, deleted


def add_days(email: str, days: int, coupon: str | None = None) -> datetime:
    """A customer adds days to their own DOB (DOB Details: Get more days of access; no payment yet): counted from their End Date
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
        running = a == "DOB" and not access.ended(r["start_date"], r["end_date"], now)
        start = _stamp(r["start_date"]) if running else now
        base = access.ends_at(r["start_date"], r["end_date"], now) if running else now
        end = base + timedelta(days=days)
        data = dict(access="DOB", start_date=start, end_date=end)
        if r:
            c.execute(accounts.update().where(accounts.c.email == email.lower()).values(**data))
        else:
            c.execute(accounts.insert().values(email=email.lower(), **data))
        _log(c, email, "Update", details=f"Get more days of access: {days} day{'s' if days != 1 else ''}"
                                         + (f", coupon {coupon}" if coupon else "") + f"; DOB until {end:%Y-%m-%d %H:%M} UT")
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
        df = pd.read_sql(sa.select(customers).order_by(customers.c.id), c)   # (by ID)
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


def _visit(name: str) -> str | None:
    """This visit's page (_page), as the app keeps it; None outside a visit."""
    try:
        return st.session_state.get(name) or None
    except Exception:                                         # (no Streamlit session: a script, a test)
        return None


def _log(c, email: str | None, activity: str, times: int = 1, details: str | None = None):
    """Rows in the Logins table: this person did this (details: what), times times (one row per customer), now, on which
    page, on what device, in what time zone, with what Access. None for an admin while the App Conditions table has the
    row Table, Login, Do not track login details for Admin access."""
    if email and times > 0:
        assert activity in ACTIVITIES
        now = _now()
        access_then = _access_now(c, email, now)
        if access_then == "Admin" and _no_admin_logins(c) or email.lower() in _no_track_emails(c):
            return                                            # (App Conditions: not tracked)
        row = dict(email=email.lower(), activity=activity, date_time=now, device=visitor_device() or None, timezone=visitor_timezone() or None, access=access_then,
                   page=(_visit("_page") or "")[:60] or None, details=(details or "")[:300] or None)
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
    if a in access.LASTS and access.ended(r["start_date"], r["end_date"], now):
        return f"{a} ended"
    return a


def log_view(email: str | None, details: str | None = None):
    """A View row in the Logins table: this person opened a customer (details: which)."""
    with engine().begin() as c:
        _log(c, email, "View", details=details)


def log_login(email: str | None):
    """A Login row in the Logins table: this person signed in with no birth details yet."""
    with engine().begin() as c:
        _log(c, email, "Login", details="Signed in, no birth details yet")


def logins_table(limit: int = 5000) -> pd.DataFrame:
    """The Logins table, its newest limit rows, by Id (oldest first): Id, Email, Activity, Access, Date_Time (UT), Page,
    Details, Device, Time zone."""
    cols = ["Id", "Email", "Activity", "Access", "Date_Time", "Page", "Details", "Device", "Time zone"]
    with engine().connect() as c:
        rows = c.execute(sa.select(logins).order_by(logins.c.id.desc()).limit(limit)).mappings().all()[::-1]   # (the newest, by Id)
    return pd.DataFrame([{"Id": r["id"], "Email": r["email"], "Activity": r["activity"], "Date_Time": r["date_time"],
                          "Device": r["device"] or "", "Time zone": r["timezone"] or "",
                          "Access": r["access"] or "", "Page": r["page"] or "", "Details": r["details"] or ""} for r in rows],
                        columns=cols)


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
        _log(c, by, "Create", added, details="DOB table")
        _log(c, by, "Update", changed, details="DOB table")
        _log(c, by, "Delete", deleted, details="DOB table")
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
        _log(c, email, "Create", details="Their own birth details (signing up)")
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
        _log(c, email, "Create", details="Add a DOB: a person under their login")
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
            _log(c, email, "Update", details="Edit a DOB: their own birth details")
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
        _log(c, by, "Create", n, details="DOB table: workbook import")
    return n


# ---------------------------------------------------------------- the orb table
def orb_table() -> pd.DataFrame:
    """The Aspect Rules table, with the columns the charts read: Aspect, Angle, Mo-RA .. SN-DE (one row, for every angle)."""
    with engine().connect() as c:
        rows = c.execute(sa.select(aspect_details).order_by(aspect_details.c.pos)).mappings().all()
    return pd.DataFrame([{"Aspect": r["aspect"], "Angle": r["angle"],
                          **{k: r[k.lower().replace("-", "_")] for k in ORB_COLUMNS}} for r in rows],
                        columns=["Aspect", "Angle"] + ORB_COLUMNS)


def keep_previous(name: str, rows: pd.DataFrame) -> None:
    """Keeps a table's rows as they were before a save (a note among the settings), for its Reset to Previous."""
    import base64, pickle
    text = base64.b64encode(pickle.dumps(rows.reset_index(drop=True))).decode("ascii")
    with engine().begin() as c:
        c.execute(sa.delete(settings).where(settings.c.key == f"previous:{name}"))
        c.execute(settings.insert().values(key=f"previous:{name}", value=text))


def previous_rows(name: str) -> pd.DataFrame | None:
    """A table's rows as they were before its last save (keep_previous); None when none was kept."""
    import base64, pickle
    with engine().connect() as c:
        text = c.execute(sa.select(settings.c.value).where(settings.c.key == f"previous:{name}")).scalar()
    return pickle.loads(base64.b64decode(text)) if text else None   # (written by the app itself, above)


PREVIOUS_ORBS = "orbs_previous"                               # (a note among the settings: the orbs before the last save)


def previous_orbs() -> pd.DataFrame | None:
    """The orbs as they were before the last save (one row, ORB_COLUMNS); None when none was kept."""
    with engine().connect() as c:
        text = c.execute(sa.select(settings.c.value).where(settings.c.key == PREVIOUS_ORBS)).scalar()
    if not text:
        return None
    kept = pd.read_json(io.StringIO(text), orient="records").reindex(columns=ORB_COLUMNS)
    return kept.fillna({c: 0.0 for c in POINT_ORB_COLUMNS})   # (kept before CB's and CN's orbs: 0, as they started)


def save_orb_table(df: pd.DataFrame):
    """Saves the orbs; the ones they replace are kept (previous_orbs), for Reset to Previous."""
    before = orb_table()[ORB_COLUMNS].head(1).to_json(orient="records")
    with engine().begin() as c:
        c.execute(sa.delete(settings).where(settings.c.key.in_(["orbs", PREVIOUS_ORBS])))   # (orbs: the old text, now out of date)
        c.execute(settings.insert().values(key=PREVIOUS_ORBS, value=before))
        c.execute(sa.delete(aspect_details))
        rows = _orb_rows(df)
        if rows:
            c.execute(aspect_details.insert(), rows)
