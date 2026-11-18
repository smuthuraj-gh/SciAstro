"""Equatorial (RA / De) charts with Swiss Ephemeris - the web version of the Excel workbook.

Pages: AstroClock-2D, AstroClock-3D, Geo/Helio Model, Planets Distance(%), Planets Cycles, Aspects (its aspects as tables) for everyone (their own customers only);
Aspect Rules, Customers (each login's Access), DOB (the birth details), Symbols, Page Defaults, App Conditions and Logins for admins; DOB Details for users. Run locally:  .venv\\Scripts\\streamlit run streamlit_app.py
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import os
import sys

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

# The app's own modules, each after those it imports. Streamlit runs this file again when it changes (as after a push, on
# Streamlit Cloud), but keeps the modules it imported as they were: a module whose file has changed since is loaded again
# here, with those after it in this list (they may use it), so the app never runs a new page with old modules.
OWN_MODULES = ["astro.se", "astro.core", "astro.mapchart", "astro.places", "astro.rangechart", "astro.distancechart",
               "astro.globechart", "astro.space3d", "astro.space3dview",
               "app.access", "app.location", "app.db", "app.auth", "app.chartdata"]


STAMP = "_loaded_file_time"                                    # kept on each own module: its file's time when it was loaded


def _reload_changed_modules(record_only: bool = False) -> None:
    """Has each own module changed since it was loaded (or loaded before this check came in, with no time kept on it, so
    its age is not known), with those after it, loaded afresh by the imports below: they are taken out of the loaded
    modules (and off their package), not reloaded in place, which fails when the package itself has been unloaded
    (Streamlit may do that when files change). record_only: keeps the times of those just imported only."""
    first = None
    for i, name in enumerate(OWN_MODULES):
        mod = sys.modules.get(name)
        if mod is None or not getattr(mod, "__file__", None):
            continue
        stamp = os.path.getmtime(mod.__file__)
        if record_only:
            if not hasattr(mod, STAMP):
                setattr(mod, STAMP, stamp)
        elif getattr(mod, STAMP, None) != stamp and first is None:
            first = i
    if first is None or record_only:
        return
    for name in OWN_MODULES[first:]:
        sys.modules.pop(name, None)
        package, _, leaf = name.rpartition(".")
        if package in sys.modules and hasattr(sys.modules[package], leaf):
            delattr(sys.modules[package], leaf)             # (else "from package import leaf" would give the old one)


_reload_changed_modules()
from app import access, auth, db
from app.chartdata import NOW_ONLY, Prepared, locate_cached, now_values, prepare
from astro import core, distancechart, globechart, mapchart, places, rangechart, se, space3d, space3dview
_reload_changed_modules(record_only=True)                     # (their file times, as first imported)

# wide pages, the sidebar (menu, customer) starting closed so the charts get the whole window; » opens it
st.set_page_config(page_title="Equatorial charts", page_icon=":material/public:", layout="wide",
                   initial_sidebar_state="collapsed")
# all text on all pages is 12 px (the most allowed; the least is 10): the theme (.streamlit/config.toml) sets body text and
# headings; this also brings Streamlit's other text (captions, buttons, labels, menus, tooltips) to 12 px. Icons keep their own size.
st.html("""<style>
.stApp :is(p, span, div, label, small, a, li, input, textarea, button, td, th, code, h1, h2, h3, h4, h5, h6):not([data-testid="stIconMaterial"]),
[data-baseweb="popover"] :is(p, span, div, li):not([data-testid="stIconMaterial"]),
[role="dialog"] :is(p, span, div, li, h1, h2, h3, button):not([data-testid="stIconMaterial"]),
[data-testid="stTooltipContent"] * { font-size: 12px !important; }
/* an editable table's cell editor opens outside the table: it undoes the page's zoom, as the table does, to open on its cell */
#portal { zoom: calc(1 / var(--app-zoom, 1)); }
#portal :is(input, textarea, div, span) { font-size: 10px !important; }
/* a pulldown list is placed by screen position outside the page, so the page's zoom would move it again and off its box:
   its holder undoes the zoom, and its text is sized to match the page's */
body > div:has(> [data-testid="stSelectboxVirtualDropdown"]) { zoom: calc(1 / var(--app-zoom, 1)); }
[data-testid="stSelectboxVirtualDropdown"] * { font-size: calc(12px * var(--app-zoom, 1)) !important; }
/* one set of shapes on every page, all 24px high: a word is a small pill; a planet, an angle or a speed is a small circle */
[data-testid="stButtonGroup"] button { padding: 0 7px !important; height: 24px !important; min-height: 24px !important; border-radius: 12px !important; }
/* AstroClock-3D's lists: two a line, the last alone not stretched across */
.st-key-globe_bodies button, .st-key-globe_coords button, .st-key-globe_speed button,
.st-key-globe_major button, .st-key-globe_minor button, .st-key-space_speed button, .st-key-globe_time button
  { flex: 0 0 auto !important; width: auto !important; }
/* the circles: every planet, every angle, every speed */
:is(.st-key-sci_bodies, .st-key-globe_bodies, .st-key-space_bodies, .st-key-helio_bodies,
    [class*="dec_on_v2"], .st-key-dist_on_v2) button,
:is(.st-key-globe_major, .st-key-globe_minor, .st-key-asp_major, .st-key-asp_minor, .st-key-sci_major, .st-key-sci_minor, [class*="ea_on_v5"], [class*="minor_on_v1"]) button,
:is(.st-key-helio_speed, .st-key-space_speed, .st-key-globe_speed) button, .st-key-sci_speed button
  { border-radius: 50% !important; width: 24px !important; min-width: 24px !important; height: 24px !important; min-height: 24px !important;
    padding: 0 !important; justify-content: center !important; flex: 0 0 auto !important; }
/* angles and speeds in a smaller type, so that 120 and 1mo fit the same circle as 0 and 1s */
.stApp :is(.st-key-globe_major, .st-key-globe_minor, .st-key-asp_major, .st-key-asp_minor, .st-key-sci_major, .st-key-sci_minor, [class*="ea_on_v5"], [class*="minor_on_v1"]) button :is(p, span, div),
.stApp :is(.st-key-helio_speed, .st-key-space_speed, .st-key-globe_speed) button:not(:first-child) :is(p, span, div), .stApp .st-key-sci_speed button :is(p, span, div)
  { font-size: 10px !important; }
/* every action button (Insert, Update, Delete, Ignore, Yes, Sign out ..): the same small pill */
:is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primaryFormSubmit"], [data-testid="stBaseButton-secondaryFormSubmit"])
  { padding: 0 7px !important; height: 24px !important; min-height: 24px !important; border-radius: 12px !important; }
/* the button that opens the sidebar (pages, customer) is titled Menu, so it is clear what it opens */
[data-testid="stExpandSidebarButton"] { width: auto !important; padding: 0 6px !important; gap: 4px;
  display: inline-flex !important; align-items: center; }
[data-testid="stExpandSidebarButton"]::after { content: "Menu"; font-size: 12px; font-weight: 600;
  color: rgba(47, 45, 43, 0.8); white-space: nowrap; }
</style>""")
# Everything (text, buttons, tables, charts, map) resizes with the window, as one picture: the whole app is zoomed so
# that the page's content column is always WIDTH (1100) px before zooming, the width the charts are laid out at. So the
# charts are never scaled on their own and all text, chart text too, is always the same size (12 px x the zoom).
st.html("""<script>
(() => {
  if (window.__appZoom) { window.__appZoom(); return; }
  // tables are drawn on a canvas in 0.875 of the theme's 12 px, and no setting changes that: they are drawn in 10 px instead
  const canvasFont = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, "font");
  Object.defineProperty(CanvasRenderingContext2D.prototype, "font", {configurable: true, get() { return canvasFont.get.call(this); },
    set(v) { canvasFont.set.call(this, String(v).replace("10.5px", "10px")); }});
  const WIDTH = """ + str(mapchart.WIDTH - mapchart.INSET_L - mapchart.INSET_R) + """;   // the text column
  const MIN_ZOOM = 10 / 12;
  function zoom() {
    if (window.__appZooming) return;                         // (the resize sent below comes back here)
    const root = document.documentElement, main = document.querySelector('[data-testid="stMain"]');
    const block = document.querySelector('[data-testid="stMainBlockContainer"]');
    if (!main || !block) return;
    const z = parseFloat(root.style.zoom) || 1;
    const cs = getComputedStyle(block);
    const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    // the main area's width inside its scrollbar (beside any open sidebar), on screen, made WIDTH + padding wide;
    // with the sidebar open its width on screen changes with the zoom, so each check comes a step closer
    // but never below MIN_ZOOM, so that 12 px text stays at least 10 px on screen: on a phone the column is then narrower
    // than WIDTH, the page's rows wrap, and each chart is scaled down as a picture to the column (two fingers enlarge it)
    const want = Math.max(MIN_ZOOM, z * main.clientWidth / (WIDTH + pad));
    if (Math.abs(want - z) > 0.001) {
      root.style.zoom = want;
      root.style.setProperty("--app-zoom", want);
      window.__appZooming = true;
      window.dispatchEvent(new Event("resize"));             // the charts fit themselves again (mapchart.fit_html)
      window.__appZooming = false;
      // Plotly measures text in its own hidden element, and the editable tables (drawn on a canvas) size themselves
      // from the zoomed width: keep those unzoomed, so charts lay out as at 1:1 and the tables fit the page
      let st = document.getElementById("app-zoom-style");
      if (!st) { st = document.createElement("style"); st.id = "app-zoom-style"; document.head.appendChild(st); }
      // (the column keeps its width when only the zoom changes, so a table's width comes from CSS, not a measurement)
      st.textContent = '#js-plotly-tester, [data-testid="stDataFrame"] { zoom: ' + (1 / want) + '; }' +
                       '[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] ' +
                       '{ width: 100% !important; max-width: 100% !important; }' +
                       // the areas as tall as the window (100vh, which the zoom does not change) would be zoomed
                       // past the window's bottom, cutting the page off: make them the window's height once zoomed
                       '[data-testid="stAppViewContainer"] > *, [data-testid="stMain"], [data-testid="stSidebar"] ' +
                       '{ height: calc(100dvh / var(--app-zoom, 1)) !important; ' +
                       'max-height: calc(100dvh / var(--app-zoom, 1)) !important; }';
    }
    // a table undoes the page's zoom, so it is drawn taller or shorter than the room the page keeps for it: the room is set
    // to what is drawn, so that nothing below it is covered
    const now = parseFloat(root.style.zoom) || 1;
    document.querySelectorAll('[data-testid="stDataFrame"]').forEach((table) => {
      const room = table.closest('[data-testid="stElementContainer"]');
      const drawn = Math.max(0, ...[...table.querySelectorAll("canvas")].map((c) => c.getBoundingClientRect().height));
      if (room && Math.abs((parseFloat(room.style.minHeight) || 0) - drawn / now) > 1) room.style.minHeight = (drawn / now) + "px";
    });
  }
  window.__appZoom = zoom;
  window.addEventListener("resize", zoom);
  const watch = () => {
    const main = document.querySelector('[data-testid="stMain"]');
    if (!main) return setTimeout(watch, 100);
    new ResizeObserver(zoom).observe(main);                  // the sidebar opening or closing
    setInterval(zoom, 500);                                  // and a check in case an event is missed
    zoom();
  };
  watch();
})();
</script>""", unsafe_allow_javascript=True)

user = auth.current_user()
# what they may use, by their row of the Customers table (made, with Access Now, on their first sign-in; an admin: everything)
_MINE = [] if user.is_admin else db.customers_for(user.email).to_dict("records")   # their DOB records (all share their email)
_ACCOUNT = None if user.is_admin else db.ensure_account(user.email)
GRANT = (access.Grant(admin=True, dob=True, many=True) if user.is_admin
         else access.grant(_ACCOUNT.get("access"), _ACCOUNT.get("start_date"), datetime.now(timezone.utc).replace(tzinfo=None),
                           _ACCOUNT.get("end_date")))
OWN_ID = access.own_record_id(_MINE)                          # their own record (the others: people added under their login)


def _access_is_dob() -> bool:
    """Their Access is one with DOB charts: DOB."""
    try:
        return access.canonical((_ACCOUNT or {}).get("access"), access.ACCESS) in access.LASTS
    except ValueError:
        return False


# the Time buttons: DOB first for one whose Access is DOB; Now first for anyone else, with DOB still
# there (a new member picks it to reach the form for their birth details)
TIMES = ("DOB", "Now") if _access_is_dob() else ("Now", "DOB")


# ---------------------------------------------------------------- who can see which customers
def visible_customers() -> pd.DataFrame:
    """An admin: every customer. A member: with DOB (before its End Date), every record under their login; else their own."""
    if user.is_admin:
        return db.all_customers()
    df = db.customers_for(user.email)
    return df if GRANT.many else df[df["id"] == OWN_ID]


def record_items(row: pd.Series) -> tuple:
    out = []
    for f in db.FIELDS:
        if f in db.ACCOUNT_FIELDS:                            # (not the charts': kept out of prepare's cache key)
            continue
        v = row.get(f)
        if v is not None and isinstance(v, float) and pd.isna(v):
            v = None
        out.append((f, v))
    return tuple(out)


_chosen: tuple[pd.Series | None, Prepared | None] = (None, None)


def pick_customer() -> tuple[pd.Series | None, Prepared | None]:
    """The customer chosen in the sidebar (chosen once per run, before the page; see the end of this file)."""
    return _chosen


PAGE_HELP = {   # shown on pointing at the (?) beside each page's name
    "Predictions": "The Prediction Rules table's readings, in four tables (each with its RA, De and RA+De rows: RA+De, in aspect by Aspect Rules, RA and De together): Birth and Transits for the birth chart of the customer picked, then Sky (the planets now with each other in RA or De, the same for everyone, New and Full Moon among them) and Distance (each planet at its closest to and farthest from the Earth, with its AU and Distance(%)), over the Start and End dates. Birth: its Birth rows whose two points are at their angle at birth (within the pair's orb in Aspect Rules, by Aspect Rules), closest first: Planet, With, Aspect, Off (degrees from the angle), Event and Prediction (its reading, from Prediction Rules). "
                   "Transits: its Transit rows, when the planets now come to those angles with the birth chart, between the Start and End dates (dates only, UT: from the start of the Start Date to the end of the End Date), soonest first. "
                   "Every planet (and the Moon's nodes, NN and SN) is looked at: there are no Planets buttons. Each row: Exact (when it is closest to the angle), Moving, Birth (the point of the birth chart; CB: house 10 at birth), "
                   "Aspect (RA and its angle, or De parallel / contra-parallel), Begins and Ends (when it comes within the orb and leaves it: the total of the two's orbs in Aspect Rules, by Aspect Rules; before Start / after End: within it already, or still), "
                   "Off (degrees from the angle at Exact), Event and Prediction. Only passes that come within 1 degree of the angle count; a planet that turns back may come to it more than once. Needs DOB access and birth details: a member without them is taken to DOB Details, told so, and comes back here once their details are saved.",
    "Prediction Rules": "The Predictions table: a row per Chart (Birth: the two points at the angle in the birth chart, Moving the first, Birth the second; Transit: the planet now coming to the angle with the birth point; Sky: two planets now at the angle with each other, either way round; Distance: a planet, Birth Ea, Kind Near or Far, Angle 0), Moving planet (Transit: Mo .. Sa, NN, SN; Birth: CB too), Birth point (the same, and CB), Kind (RA: the RA between the two is the Angle; De: Angle 0 parallel, 180 contra-parallel) and Angle (0 to 180), "
                        "unique together (a Birth row's two points either way round: Su-Mo and Mo-Su are one pair), with its Event (required, at most 500 characters: its reading, shown in the Predictions page's Event column) and, last, its Prediction (optional, at most 500 characters; filled once, where empty, with a draft reading from the planets' and angles' usual meanings: a Transit row a period, a Birth row a lasting trait). It starts with every combination: Transit, each planet now (Mo .. Sa, NN, SN) with each birth point (and CB); Birth, each two birth points once (not NN with SN); each at RA 0, 60, 90, 120, 180 and De 0, 180, with a plain Prediction naming it to replace with your reading (938 rows; a row deleted stays deleted). "
                        "Insert, Update, Delete, each saved at once; Ignore; Reset to Previous.",
    "AstroClock-3D": "Time, with Now and DOB below it: which moments to show. The Earth inside the celestial sphere, its axis tilted 23.44 degrees and joining the North and South Celestial Poles (NCP, SCP); ECE and WCE are East and West on the Celestial Equator. "
                  "Rotate in 1s: the Earth turns about that fixed axis, west to east, while the sphere stands still, and time "
                  "runs from each moment, until it is turned off: the clock beside the name gives the date and time, and the Sun, "
                  "Moon and planets move over the sphere as they really did (time starts again after 72 years; refresh the page to go back "
                  "to the start). Below it, with no speed picked (as to start): the Earth, the celestial sphere, Ho, RA, De, La and Lg are frozen together; drag the chart sideways to turn them as one unit and see the other side of the AstroClock-3D. Or pick a speed to start, how much time passes each second: 1s a second, 1m a minute, 1h an hour, 1d a day, 1w a week, 1mo a month, 1y a year; with none picked it holds still. The Earth starts as it was at that "
                  "moment, so a planet is straight above the place it was overhead. Each planet is on the sphere at its RA and Declination, with its symbol inside its marker (☉ Su, ☽ Mo, ☿ Me, ♀ Ve, ♂ Ma, ♃ Ju, ♄ Sa), sized as the Size_Clock-3D column of Symbols says, usually by how big it looks from the Earth then (a "
                  "logarithmic scale, as to true scale the planets would not show; point at one for its De/Lati, RA, Angular Size, Distance from earth and the others approaching and leaving it in De/Lati; at CB or CN for its Long, De/Lati, RA and the planets approaching and leaving its De/Lati). The far side of the sphere is "
                  "fainter, and hidden behind the Earth. Planets, picking from the list below it: which of the Sun, Moon and planets to show, with their RA and De lines, and the Moon's north and south nodes (NN, SN), where its path crosses the Sun's, drawn with their symbols (☊ and ☋; point at one for its details). Major Aspects (0, 60, 90, 120, 180; black) and Minor Aspects (30, 45, 72, 135, 144, 150; grey): pick the angles to draw a line between any two planets or nodes shown (not NN with SN) that are in that aspect, by the orbs in Aspect Rules, as time runs; dotted for DOB, each with its tag, as 0-Ma-Ju, along it where there is room, or beside it when the two are too close (point at a line for its name). Coordinates, with Ho, Ce, AU, 3D, Sp, SpC, RA, De, La and Lg below it: which lines to show. 3D: in place of the sphere, a true 3D view, to drag to turn and scroll to zoom: the Earth in the middle as a globe (as on the sphere: land and sea, coastlines, borders, lines of latitude and longitude every 30 degrees, turned as it was then and turning with time, with CB and CN on it), the planets picked at their real directions and distances on the Fit scale (at the time picked: Now, or DOB, hollow), sized as the Symbols table's Size_Geo says, each with its symbol inside, with PP their Planet Paths over one trip from then; with Ce the celestial coordinates (the axis with NCP and SCP, the equator and its RA names, its plane), with AU the rings of distance in AU on that plane, with Sp a dashed spoke from the Earth through each planet out to the edge of the view, with SpC a line from CB or CN to each planet; Rotate in 1s: time runs from each moment at the speed picked (none: it stands still, and dragging turns it); point at a planet for its RA, De and distance and its distance to the others. AU: each planet drawn inside the sphere, along its RA and De, at a radius by its distance from the Earth, from the Earth out to the sphere (past Saturn), to scale (the Moon on the Earth, the inner planets close to it, Saturn near the sphere; NN and SN, on the Moon's path, at the Moon's distance), and with Sp a dashed line (spoke) out to its place on the sphere, where its RA, De and aspect lines are; off, all are on the sphere. Point at a planet for its distance in AU. SpC: a thin line to every planet from CB (DOB planets) or CN (Now planets) on the Earth, fainter where it runs to or from the far side (to the planet inside the sphere with AU on, on the sphere with it off). Ce: the axis with the names NCP and SCP and the dots at the poles, and the celestial equator with the names WCE and ECE. Ho: the house lines, twelve on the sphere, 30 degrees apart from the RA of CB (dashed) and of CN (solid), named H01 to H12, turning with the Earth, with each line's RA at its lower right (on the near side, where there is room). RA, De: the RA lines and the De lines of each planet, and of NN and SN, on the sphere, and "
                  "of CB and CN on the Earth. La, Lg: the Earth's lines of latitude and of longitude, every 30 degrees, turning with it. PP (Planet Path): a trail behind each planet shown, "
                  "drawn only while time runs, where it has really been since time started running (none while it stands still; each start begins new ones; up to 72 years). "
                  "DOB: at birth, hollow, dashed lines, with CB, a baby, at the birth place. Now: the planets "
                  "now, solid lines, with CN, a house, at the place now.",
    "Geo/Helio Model": "Centric Model: Geo, GeoCentric, the Earth at the centre, or Helio, HelioCentric, the Sun at the centre; each keeps its own choices on the other buttons. "
                  "GeoCentric: the paths of the Sun, Moon and planets around the Earth (Ea), each at its own distance from the Earth (on AstroClock-3D all are on one sphere). "
                  "Point at a planet for its distance from the centre and, under Distance to the others, how far it is from each other body shown at that moment, in AU (straight across space). "
                  "Each point is placed by its RA, De and distance. North is up, the axis from NCP to SCP tilted 23.44 degrees on the page, with everything else leaning with it. Buttons under Coordinates: Ce, the celestial coordinates: the axis with NCP and SCP and the RA lines with their names (on to start); AU, the rings on the plane of the Earth's equator with their distances in AU, out to 20 AU (1 AU is about the Sun's distance); "
                  "Rotate in 1s: with no speed picked (as to start), time stands still, and dragging the drawing turns it, what is behind being fainter. Or pick a speed, how much time passes each second: 1s a second, 1m a minute, 1h an hour, 1d a day, 1w a week, 1mo a month, 1y a year: the clock beside the name gives the date and time, and the Sun, Moon and planets move as they really did, nearer and farther, the Moon's path going with it (time starts again after 72 years; refresh the page to go back to the start). With none picked it holds still. Each has its symbol inside its marker (☉ Su, ☽ Mo, ☿ Me, ♀ Ve, ♂ Ma, ♃ Ju, ♄ Sa, ⊕ Ea). Sizes follow the Size_Geo column of Symbols: usually a planet by how big it looks from the Earth at that moment (a logarithmic scale, as to true scale the planets would not show), so it grows as it comes nearer, and the Earth as its Size says (Tiny, a dot, when it says nothing readable; to true scale it would be far smaller still). Point at a planet for its De/Lati, RA, Angular Size and distance, or at a path for its span and distances. "
                  "Time: DOB is hollow with dashed paths, Now solid. PP, under Coordinates: the Planet Path of each planet shown, a trail behind it, drawn only while time runs: where it has really been since time started running, kept for up to 72 years, when time starts again (a trail over many years is drawn with fewer points). With time standing still there are no trails, and each start begins new ones. "
                  "Coordinates: Ce, AU and PP below it. Distances are on the Fit scale: each tenfold distance takes the same room, so the Moon's path and Saturn's can be seen together, and the empty space between the Moon's path and the planets' is taken out (it alone is not to scale). A label with no room is left off: point at its mark. "
                    "HelioCentric: as GeoCentric, with the Sun (Su) at the centre: the paths of the planets and the Earth (Ea) around the Sun, each at its own distance from the Sun, "
                    "placed by its RA, De and distance as seen from the Sun, on the same frame as from the Earth (the plane of the Earth's equator, north up). The Moon (Mo) goes round the Earth: seen from the Sun it is where the Earth is, so it is drawn close round the Earth's mark (a dot when its Size_Helio is Tiny, as it starts), farther out than to scale, in its real direction from the Earth and nearer and farther with its real distance (its path loops round the Earth's). "
                    "AU: all the tags, NCP, SCP and the RA names, and rings on the plane of the Earth's equator, each with its distance from the Sun in AU (1 AU is about the Earth's distance; on Fit 0.5, 1, 2.5, 5, 10 and 20 AU, on True 1, 2.5, 5, 10 and 20 AU, nearer ones being inside the Sun's mark there); off, the drawing has no tags. "
                    "Rotate in 1s: with no speed picked (as to start), time stands still, and dragging the drawing turns it, what is behind being fainter. Or pick a speed, how much time passes each second (1s, 1m, 1h, 1d, 1w, 1mo, 1y): the clock beside the name gives the date and time, and the planets and the Earth move round the Sun as they really did (time starts again after 72 years; refresh the page to go back to the start). With none picked it holds still. "
                    "Each has its symbol inside its marker (☿ Me, ♀ Ve, ⊕ Ea, ☽ Mo, ♂ Ma, ♃ Ju, ♄ Sa, ☉ Su). Sizes follow the Size_Helio column of Symbols: usually a planet by how big it looks from the Earth at that moment (a logarithmic scale), the Sun and the Earth as their Sizes say. Point at a planet for its De/Lati, RA, Angular Size and distance from the Sun, or at a path for its span and distances. "
                    "Time: DOB is hollow with dashed paths, Now solid. PP, under Coordinates: the Planet Path of each planet shown, a trail behind it, drawn only while time runs, kept for up to 72 years (with time standing still there are no trails, and each start begins new ones). "
                    "Coordinates: Ce, AU and PP below it. Distances are on the Fit scale: each tenfold distance takes the same room, so Mercury's path and Saturn's can be seen together. A label with no room is left off: point at its mark.",
    "Planets Cycles": "Each chosen planet's Declination (-M lines) over the period, with dots and tags where two of "
                      "them are in a chosen major or minor aspect. A tag with no room is left off: point at "
                      "its dot to see it. Dates and times are UT.",
    "AstroClock-2D": "Coordinates: Ho (the house lines of CB and CN), 1C (every planet on one circle at its RA, whatever its distance, so that planets in conjunction sit together) DA (the Ave planets on the Distance(%) graph, on to start) and PP (the Planet Path of each planet shown: a trail behind it while time runs). Left of the clock, De: each planet's Declination on a scale from +30 to -30 degrees, moving as time runs, all on lines of one length, so that planets at the same Declination overlap (point at one for its value). Right of the clock, a Distance(%) graph the same way, from 0 (nearest) to 100 (farthest): the planets at DOB and at Now to the left of its line, and at Ave (the average of the two, moving as time runs) to the right. Major Aspects and Minor Aspects: the angles to draw; two planets at the same time in one of them, by the orbs in Aspect Rules, are joined by a line tagged as 0-Ma-Ju. Rotate in 1s: pick a speed for time to run; with none picked it stands still, and dragging the drawing moves it by hand: right is later, left is back, as far as where it started, 6 hours a pixel.",
    "Planets Distance(%)": "Each chosen planet's distance from the Earth (-D lines) over the period, as D: the % "
                           "between its nearest (0) and farthest (100) over 1800 to 2400. Dates and times are UT.",
    "App Conditions": "The App Conditions table: a row per Object, its Values and its Condition. The app follows a row while it is there (delete it and the app stops following it): Table, Login, Do not track login details for Admin access: an admin's activity is not written to the Logins table. Condition is required and unique (Abc and abc "
                  "are the same), at most 60 characters; Object at most 60; Values at most 500. Rows are in Condition order. Seen by admins only, "
                  "who can Insert, Update and Delete rows (each saved at once), Ignore changes not saved yet, and Reset to "
                  "Previous; click a column name to sort.",
    "Logins": "The Logins table, newest first: who (Email, the signed-in login) did what (Activity) and when (Date_Time, "
              "UT). View: opened a customer's charts (once per customer per visit). Create, Update, Delete: added, changed or "
              "deleted a customer (on DOB, by import, or their own DOB Details), a row per customer. Login: signed in with "
              "no birth details yet, seeing the Now charts only (once per visit). Device, Time zone: their "
              "browser and system, and their browser's time zone. Access: theirs then. Seen by admins only; "
              "click a column name to sort. To delete rows, tick them in the Del column and press Delete, or press Delete all; "
              "either asks first, and a deleted row cannot be brought back.",
    "Page Defaults": "The Page Defaults table: what each page's inputs start as. A row per input, each column its own: Page (e.g. DOB Details), Choice (the input, e.g. Days), Choice Values (what it starts as, e.g. 1) and Allowed Values (the values Choice Values may be set to, e.g. 1, 7, 30, 90, 180, 365: all the input's values, or those typed there, comma-separated; the page offers only those; clear it for all again; a text box, the words allowed, e.g. Pay, Free, blank for any text; dates and single on / off buttons cannot be narrowed). "
                "Choice Values: buttons, the ones on, comma-separated, by name, SAbr or symbol (e.g. Ju, Sa; 0, 180; 1d), "
                "blank for none; Coordinates: the buttons below it that start on (e.g. Ho, DA; Ce, AU). Start Date (UT): DOB or Now. End Date (UT): Now, or "
                "Start Date (UT) + a time, e.g. 5 days, 2 years 6 months (years, months, weeks, days), which moves with the "
                "Start. Update checks each row against the page's input. An input with no row starts as the app's own default. "
                "Rows are sorted by Page, Choice; Choice Values blank: the app's own default; click a column name to sort by it. Changes apply when a page is next opened (a button already changed this visit keeps its choice). Seen by admins "
                "only, who can Insert, Update and Delete rows (each saved at once).",
    "Symbols": "The Symbols table: the short name (SAbr), symbol (Symb), long name (SDesc) and colour (RGB, and its name, Color) of each planet, the Earth (Ea), the Moon's nodes (NN, SN), the place now (CN) and the birth place (CB). Seen by admins only, who can "
               "use Insert for a new row, type changes in the table and press Update, tick Del and press Delete: each is saved at once; Ignore drops changes not saved yet. Click a column name to sort. SAbr is unique, and stays once a row is in the table. Symb is what the pages show in place of its SAbr, the SAbr itself when blank. On AstroClock-2D, AstroClock-3D and Geo/Helio Model the conventional symbols are drawn, in the row's RGB colour; anything else is shown as typed, an emoji such as the baby in its own colours. RGB is rgb(r,g,b) or #rrggbb; Color is its name in words, for reference, and may be blank. Size_Clock-3D says how AstroClock-3D draws the Sun, Moon, planets, Ea, the nodes NN and SN and the places CB and CN: Angular Size, by how big it looks from the Earth; Tiny, a dot with no symbol; Small, 9 pixels; a number, its radius in pixels; Bigger than, Smaller than or Same as another, by its SAbr or SDesc (Bigger than Moon); blank, as usual (a planet by its angular size, Ea a dot, the nodes and places 9 pixels). Size_Clock-2D says the same for AstroClock-2D, its De and Distance(%) graphs (it starts as Size_Geo), Size_Geo for Geo/Helio Model's Geo, and Size_Helio for its Helio (it starts as Size_Geo, with the Moon Tiny). The charts take the colours from here: a planet's marker, RA and De lines and path; Ea's mark and name on Geo/Helio Model's Geo; NN's and SN's symbol; CN's and CB's mark, name, RA and De lines. The Ea, NN, SN, CN and CB rows come back if deleted.",
    "Aspect Rules": "The orbs: one row, for every aspect (Conjunction 0, Opposition 180, Square 90, Trine 120, Sextile 60, "
                       "Semi-sextile 30, Semi-square 45, Quintile 72, Sesquiquadrate 135, Bi-quintile 144, Quincunx 150): for each "
                       "planet, an RA orb and a De orb, how far from exact still counts as the aspect. A pair of planets uses the "
                       "total of their two orbs (RA and De each). 👶 RA, 🏠 RA, 👶 De, 🏠 De: the orbs of CB (house 10 at birth) and CN (house 10 now), "
                       "0 to start (a pair with one then takes the planet's orb alone). Type the changes and press Update; they apply to every chart. Ignore drops changes not updated; Reset to Previous puts back the orbs before the last Update.",
    "Customers": "One row per login: its Email, its Access, Start Date (UT) and End Date (UT; when DOB runs out). "
                 "Now: the Now charts only. DOB, the paid option: the DOB and Now charts of every DOB record "
                 "under their login, and people they add, or search for without saving, on DOB Details, until End Date. "
                 "Type a new End Date and press Update to lengthen or shorten DOB (the row becomes DOB); members add days "
                 "themselves on DOB Details. "
                 "Change Start Date to count from another day (it keeps the length); a new DOB with no End Date typed "
                 "lasts 1 day. "
                 "Signing up with birth details gives DOB for 1 day. Admin: an admin. After End Date: the Now charts only. A row is made, with Now, when someone signs in for the first "
                 "time. A login's first DOB record (signing up, or saved on the DOB page) gives it DOB for 1 day. The DOB records refer to this table by "
                 "Email: changing an Email here changes it on them too, and a row whose Email DOB records still use cannot "
                 "be deleted. Insert, Update, Delete, "
                 "Ignore as on DOB.",
    "DOB": "The customers' birth details. Insert for a new customer, type changes and press Update, tick Del and press Delete: each is saved at once; Ignore drops changes not saved yet. Click a column name to sort. ID is the record's number, and Created and Last_Updated (UT) when it was added and last changed, all set by the app. Required (*): Email (login), First Name, "
                 "Last Name, Country, State, City, the birth date and time (Date, Local-Time-24hr), and where they "
                 "live now (Country-N, State-N, City-N). "
                 "Email (login) is the Google account each customer signs in with (one customer per email; they see "
                 "only their own). Other and Other-N: anything else to keep about the birth place and the place now "
                 "(not used in the charts). The UTC offset is looked up from the birth place and date. Import adds customers from the workbook's Customers CSV.",
    "DOB Details": "Get more days of access (every member): pick 1, 7, 30, 90, 180 or 365 days, apply the coupon Free (for now, free) and press Add days (Days and Pay / Coupon start as the Page Defaults table says); they are added to your End Date while it runs, else from now, and open the DOB charts. With DOB access, Add a DOB (at the top): a person to add under your login, with Search Only (their DOB charts, not saved, as a Search choice in the sidebar) or Save and Search (saved, then their charts). Your own birth details, used for the DOB charts (without them, the Now charts only). Edit a DOB to change them; your login "
                  "email stays the same.",
}


def birth_label(row: pd.Series | None, prep: Prepared | None) -> str:
    """The chosen customer's birth as DOB yyyy-mm-dd hh:mm (no time when it is not known); blank when there is none, or
    the DOB charts are not open to them (as the sidebar)."""
    if row is None or prep is None or not prep.ok or prep.now_only:
        return ""
    def num(f):
        v = row.get(f)
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else int(v)
    y, m, d, hr, mn = (num(f) for f in ("year", "mon", "day", "hr", "mn"))
    if None in (y, m, d):
        return ""
    return f"DOB {y}-{m:02d}-{d:02d}" + (f" {hr:02d}:{mn or 0:02d}" if hr is not None else "")


def top_line(title: str, row: pd.Series | None, prep: Prepared | None = None):
    """Every page's top line: its title (with its help), then the chosen customer's First and Last Name, their DOB when
    there is one, and the Now clock (UT, to the second)."""
    TABLES_DRAWN["n"] = 0                                      # (each run: the same keys for the same tables)
    # one row drawn here (not Streamlit's row, which can wrap the name onto a line of its own): both on one baseline
    name = ""
    if row is not None:                                       # First Name and Last Name (blank parts left out)
        parts = [row.get(f) for f in ("name", "last_name")]
        name = " ".join(str(p).strip() for p in parts if p is not None and not (isinstance(p, float) and pd.isna(p))
                        and str(p).strip())
    help_text = PAGE_HELP.get(title)
    help_mark = (f'<span title="{html.escape(help_text)}" aria-label="Help: {html.escape(help_text)}" '
                 f'style="cursor:help; display:inline-flex; align-items:center; justify-content:center; '
                 f'width:1.15em; height:1.15em; margin-left:6px; border:1px solid currentColor; border-radius:50%; '
                 f'opacity:0.55; font-weight:600; font-size:0.85em; line-height:1; vertical-align:middle">?</span>'
                 ) if help_text else ""
    # the First Name right after the title (and its help), on the same line; then a slot (TITLE_SLOT) where a page may
    # put more on this line
    global TITLE_SLOT
    line = st.container(horizontal=True, vertical_alignment="top", gap="large")
    line.container(width="content").html(
        f'<div style="display:flex; align-items:baseline; justify-content:flex-start; gap:24px; '
        f'flex-wrap:nowrap; font-weight:600">'
        f'<span style="white-space:nowrap">{html.escape(title)}{help_mark}</span>'
        f'<span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{html.escape(name)}'
        + ('<span class="globe-clock" style="white-space:pre; font-weight:400; margin-left:12px"></span>'   # the chart's Timer, next to the name (its script writes it)
           if title in ("AstroClock-2D", "AstroClock-3D", "Geo/Helio Model") else "")
        + (f'<span class="dob-label" style="font-weight:400; margin-left:12px">{html.escape(dob)}</span>' if (dob := birth_label(row, prep)) else "") +
        '<span class="now-clock" style="font-weight:400; margin-left:12px"></span>'   # (NOW_CLOCK_JS writes it)
        '</span>'
        f'</div>' + NOW_CLOCK_JS, unsafe_allow_javascript=True)
    # the slot fills the rest of the line
    TITLE_SLOT = line.container(width="stretch", horizontal=True, gap="small")


# the Now clock beside the name on every page's top line: the time now, UT, to the second (one timer for the page, kept
# across reruns; built from no user input, so safe to run)
NOW_CLOCK_JS = """<script>
(() => {
  const tick = () => {
    const text = "Now " + new Date().toISOString().slice(0, 19).replace("T", " ") + " UT";
    document.querySelectorAll(".now-clock").forEach((e) => { if (e.textContent !== text) e.textContent = text; });
  };
  tick();
  if (!window._nowClockTimer) window._nowClockTimer = setInterval(tick, 1000);
})();
</script>"""


TITLE_SLOT = None                                             # set by top_line for the page being shown


PLACE_SEARCH_DOWN = "The place search is not answering just now. Please try again in a few minutes."


def _pick_customer() -> tuple[pd.Series | None, Prepared | None]:
    """The sidebar, right after the page list: the Customer box (and what goes with it), then who is signed in."""
    try:
        return _pick_customer_box()
    finally:                                                  # (also after a page switch or rerun: harmless)
        st.sidebar.markdown(f"**{user.name}**" + ("  \n:blue-badge[admin]" if user.is_admin else ""))
        auth.sign_out_button(user)


def _pick_customer_box() -> tuple[pd.Series | None, Prepared | None]:
    df = visible_customers()
    if nav.url_path != "me":                                  # (the chart page Add a DOB's buttons go back to)
        st.session_state["_last_chart_page"] = nav.url_path
    saved_note = st.session_state.pop("_quick_saved", None)   # a quick birth just saved
    if saved_note:
        st.toast(saved_note)
    # they picked DOB, which is not open to them (none, or run out): where to get more days, on the page (not a toast, which
    # fades); on DOB Details, below its boxes (page_notes)
    locked_note = st.session_state.pop("_dob_locked", None) if nav.url_path != "me" else None
    if locked_note:
        st.warning(locked_note if isinstance(locked_note, str) else access.PAID_NOTE)
    if df.empty:
        if user.is_admin:                                     # (anyone signed in sees the Now charts)
            st.sidebar.info("No customers yet.")
            return None, Prepared(True, "Add a customer on the DOB page for the DOB charts.", now_only=True, locked=True)
        # a new member: no form to fill in, a Login row (once per visit), and the Now charts (birth details can be added in
        # DOB Details, for the DOB ones)
        if not st.session_state.get("login_logged"):
            db.log_login(user.email)
            st.session_state["login_logged"] = True
        st.sidebar.caption("Now charts only: pick DOB to add your birth details. " + access.PAID_NOTE)
        return None, NOW_ONLY
    # chosen by record (names need not be unique: the login email is the key), shown as First and Last Name, with the
    # email added where two customers share both
    full = (df["name"].fillna("") + " " + df["last_name"].fillna("")).str.strip()
    label = {int(i): (f"{f} ({e})" if (full == f).sum() > 1 and e else f)
             for i, f, e in zip(df["id"], full, df["email"].fillna(""))}
    searched = st.session_state.get("_searched")              # a member's birth from DOB Details' Search Only (not saved)
    if GRANT.dob and GRANT.many and searched and not user.is_admin:   # (admins add births on the DOB page)
        label[access.QUICK] = searched
    ids = list(label)
    if "_select_customer" in st.session_state:                # (a person just added: shown at once)
        st.session_state["customer_id"] = st.session_state.pop("_select_customer")
    prev = st.session_state.get("customer_id")
    idx = ids.index(prev) if prev in ids else ids.index(OWN_ID) if OWN_ID in ids else 0   # (a member: their own, to start)
    cid = st.sidebar.selectbox("Customer", ids, index=idx, format_func=label.get, key="customer_id")
    if cid == access.QUICK:
        base = df[df["id"] == OWN_ID] if (df["id"] == OWN_ID).any() else df
        row, prep = quick_birth(base.iloc[0])
        mark_accessed()
        return row, prep
    row = df[df["id"] == cid].iloc[0]
    try:
        prep = prepare(record_items(row))
    except places.LookupDown:
        prep = Prepared(False, PLACE_SEARCH_DOWN)
    if not GRANT.dob:                                         # none, or a paid period or trial run out: the Now charts only,
        prep = Prepared(True, access.EXPIRED_NOTE if GRANT.expired else access.PAID_NOTE,   # (shown when they pick DOB)
                        now_only=True, locked=True,   # at the place they live now
                        cn=prep.cn if prep.ok else None, cn_tz=prep.cn_tz if prep.ok else None)
        st.sidebar.caption(GRANT.note)
    elif not prep.ok:                                         # birth details that cannot be worked out: the Now charts still
        st.sidebar.error(prep.message)
        prep = Prepared(True, prep.message + (" Fix it on the DOB page." if user.is_admin else " Fix it in DOB Details."),
                        now_only=True, locked=True)
    else:
        hr, mn = row.get("hr"), row.get("mn")
        if hr is None or pd.isna(hr):
            at = "time unknown, 12:00 used"
        else:
            at = f"{int(hr):02d}:{0 if mn is None or pd.isna(mn) else int(mn):02d}"
        st.sidebar.caption(f"{int(row['year'])}-{int(row['mon']):02d}-{int(row['day']):02d} {prep.weekday} "
                           f"{at}, UTC {prep.utc:+.2f}  \n"
                           + ", ".join(str(row[f]) for f in ("city", "state", "country") if pd.notna(row[f]))
                           + f" ({prep.birth_lat}, {prep.birth_lon})"
                           + (f"  \n{GRANT.note}" if GRANT.note else ""))
    mark_accessed()
    viewed = st.session_state.setdefault("viewed_customers", set())   # a View in the Logins table: once per customer per visit
    if cid not in viewed:
        db.log_view(user.email, f"Customer #{cid}")
        viewed.add(cid)
    return row, prep


def birth_time(text: str):
    """hh:mm in 24 hours as a time; None when blank; raises ValueError when not a time."""
    if not (text or "").strip():
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*", text)
    if not (m and int(m[1]) < 24 and int(m[2]) < 60):
        raise ValueError(text)
    return time(int(m[1]), int(m[2]))


def quick_birth(base: pd.Series) -> tuple[pd.Series, Prepared]:
    """A birth typed in the sidebar, not saved: its DOB charts, with the place now of base (their own record). A member
    with DOB may save it, with a First and Last Name, as a person under their login."""
    if st.session_state.pop("_quick_clear", False):           # (just saved: the boxes empty again)
        for k in ("quick_date", "quick_time", "quick_city", "quick_state", "quick_country", "quick_first", "quick_last"):
            st.session_state.pop(k, None)
    st.session_state.update(st.session_state.pop("_quick_fill", {}))   # (DOB Details' Search Only: its birth, typed in)
    box = st.sidebar.container(border=True)
    born = box.date_input("Birth date", value=None, min_value=datetime(1800, 1, 1).date(), max_value=datetime(2399, 12, 31).date(),
                          format="YYYY-MM-DD", key="quick_date")
    at_txt = box.text_input("Birth time (local, 24 h)", placeholder="hh:mm", max_chars=5, key="quick_time")
    city = box.text_input("City", key="quick_city")
    state = box.text_input("State/Region", key="quick_state")
    country = box.text_input("Country", key="quick_country")
    row = pd.Series({**base.to_dict(), "id": access.QUICK, "name": "Search", "last_name": "", "other": None,
                     "utc": None, "city": city.strip(), "state": state.strip(), "country": country.strip()})
    try:
        at = birth_time(at_txt)
    except ValueError:
        return row, Prepared(False, "Search: type the birth time as hh:mm in 24 hours, e.g. 14:30.")
    if born is None or at is None or not all(v.strip() for v in (city, state, country)):
        box.caption("Type a birth date, time and place to see its DOB charts. Nothing is saved.")
        return row, Prepared(False, "Search: type a birth date, time and place in the sidebar.")
    row = pd.Series({**row.to_dict(), "year": born.year, "mon": born.month, "day": born.day, "hr": at.hour, "mn": at.minute})
    try:
        prep = prepare(record_items(row))
    except places.LookupDown:
        return row, Prepared(False, PLACE_SEARCH_DOWN)
    if prep.ok:
        box.caption(f"{born} {prep.weekday} {at:%H:%M}, UTC {prep.utc:+.2f} ({prep.birth_lat}, {prep.birth_lon}). Not saved.")
        if not user.is_admin and GRANT.many:                  # DOB: it may be kept, under their login
            first = box.text_input("First Name", max_chars=120, key="quick_first")
            last = box.text_input("Last Name", max_chars=120, key="quick_last")
            if box.button("Save this birth", key="quick_save"):
                if not (first.strip() and last.strip()):
                    box.error("Type a First Name and a Last Name to save it.")
                else:
                    rec = {"name": first, "last_name": last, "country": country, "state": state, "city": city, "other": None,
                           "year": born.year, "mon": born.month, "day": born.day, "hr": at.hour, "mn": at.minute,
                           **{f: base.get(f) for f in ("country_n", "state_n", "city_n", "other_n")}}   # their place now, as theirs
                    try:
                        cid = db.add_person(rec, user.email)
                    except ValueError as exc:
                        box.error(str(exc))
                    else:
                        st.session_state["_select_customer"] = cid   # chosen in the sidebar at once
                        st.session_state["_quick_clear"] = True
                        st.session_state.pop("_searched", None)   # (saved: the search choice goes)
                        st.session_state["_quick_saved"] = f"{first.strip()} {last.strip()} is saved under your login."
                        st.rerun()
    return row, prep


def mark_accessed():
    """The Accessed column: the last time this member used the site. Set when they open it and again while they go
    on using it (at most every 5 minutes, not on every click); an admin looking at customers does not count."""
    import time as _t
    if user.is_admin:
        return
    last = st.session_state.get("accessed_marked_at", 0.0)
    if _t.time() - last >= 300:
        db.mark_accessed(user.email)
        st.session_state["accessed_marked_at"] = _t.time()


def orbs() -> core.Orbs:
    return core.Orbs(db.orb_table())


def dob_asked(picked: bool, *keys_reset) -> None:
    """A member with no birth details picked DOB: their Time is set back (keys_reset: (key, value) pairs, set before the
    buttons are drawn) and the form opens on DOB Details; once saved, they come back to this page. One whose Access does
    not open the DOB charts is told so, and taken to DOB Details with Get more days of access open (an admin, who has no
    DOB Details page, is told so where they are)."""
    if not picked:
        return
    for k, v in keys_reset:
        st.session_state[k] = v
    if _chosen[1] is not None and _chosen[1].locked:
        st.session_state["_dob_locked"] = _chosen[1].message or access.PAID_NOTE   # (shown on the page it goes to)
        if user.is_admin or "me" not in PAGE_BY_PATH:
            st.rerun()
        st.session_state["_open_more_days"] = True             # Get more days of access, open, on DOB Details
        st.switch_page(PAGE_BY_PATH["me"])
    st.session_state["_back_to"] = nav.url_path
    st.switch_page(PAGE_BY_PATH["me"])


def new_member_form():
    """A member signing in for the first time (no record has their email yet) enters their own birth details; the
    record is saved with their login email, so they see their charts at once. One record per email."""
    st.write("Welcome! Enter your birth details to see your DOB charts. They are kept private: only you (and the admin) "
             "can see them.")
    details_form(None)


def details_form(row: pd.Series | None, person: bool = False):
    """A member's own birth details: empty for a new member, or their record to change (row). Saved with their
    login email, which stays the same (it is the key). person: a new person to add under their login (unlimited access),
    row giving only the place now to start from."""
    k = "person_" if person else ""                           # (both forms may be on the page)
    def val(f):
        v = row.get(f) if row is not None else None
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else v

    def txt(f):
        return str(val(f) or "")

    born0, at0 = None, ""
    if row is not None and all(val(f) is not None for f in ("year", "mon", "day")):
        try:
            born0 = datetime(int(val("year")), int(val("mon")), int(val("day"))).date()
        except ValueError:
            pass
        if born0 and not datetime(1800, 1, 1).date() <= born0 <= datetime.now().date():
            born0 = None                                      # outside what the date box allows: to be typed again
    if row is not None and val("hr") is not None:
        at0 = f"{int(val('hr')):02d}:{int(val('mn') or 0):02d}"
    with st.form("add_person" if person else "member_details" if row is None else "edit_details"):
        c1, c2 = st.columns(2)
        first = c1.text_input("First Name *", value=txt("name"), max_chars=120)
        last = c2.text_input("Last Name *", value=txt("last_name"), max_chars=120)
        c1, c2 = st.columns(2)
        born = c1.date_input("Birth date *", value=born0, min_value=datetime(1800, 1, 1).date(),
                             max_value=datetime.now().date(), format="YYYY-MM-DD")
        # a text box (Streamlit's time box shows its own "HH:mm"): hh:mm, 24 h
        at_txt = c2.text_input("Birth time (local, 24 h) *", value=at0, placeholder="hh:mm", max_chars=5,
                               help="Hours and minutes, 24 h, e.g. 14:30 or 09:05.")
        st.markdown("**Birth place**")
        c1, c2, c3, c4 = st.columns(4)
        city = c1.text_input("City *", value=txt("city"), max_chars=500)
        state = c2.text_input("State/Region *", value=txt("state"), max_chars=120)
        country = c3.text_input("Country *", value=txt("country"), max_chars=120)
        other = c4.text_input("District/Others", value=txt("other"), max_chars=500,
                              help="The district, or anything else about the birth place (optional; not used in the "
                                   "charts).")
        st.markdown("**Where you live now** (for the Now charts)")
        c1, c2, c3, c4 = st.columns(4)
        city_n = c1.text_input("City *", value=txt("city_n"), max_chars=500, key=f"{k}city_n")
        state_n = c2.text_input("State/Region *", value=txt("state_n"), max_chars=120, key=f"{k}state_n")
        country_n = c3.text_input("Country *", value=txt("country_n"), max_chars=120, key=f"{k}country_n")
        other_n = c4.text_input("District/Other", value=txt("other_n"), max_chars=500, key=f"{k}other_n",
                                help="The district, or anything else about where you live now (optional; not used "
                                     "in the charts).")
        if row is None and not person:                        # signing up: DOB for 1 day
            st.caption("Signing up gives you DOB access for 1 day: your DOB and Now charts, and people you add or search for. "
                       "After it, the admin can keep it for you.")
        search = False
        if person:                                            # Search Only: its DOB charts, not saved;
            c1, c2, _ = st.columns([1, 1, 4])                 # Save and Search: saved, then its DOB charts
            search = c1.form_submit_button("Search Only")
            sent = c2.form_submit_button("Save and Search", type="primary")
        else:
            sent = st.form_submit_button("Save my details" if row is None else "Save changes", type="primary")
    if not (sent or search):
        return
    try:
        at = birth_time(at_txt)
    except ValueError:
        st.error("Birth time: type it as hh:mm in 24 hours, e.g. 14:30 or 09:05.")
        return
    missing = [n for n, v in (("First Name", first), ("Last Name", last), ("Birth date", born), ("Birth time", at),
                              ("City", city), ("State/Region", state), ("Country", country),
                              ("City (now)", city_n), ("State/Region (now)", state_n), ("Country (now)", country_n))
               if not (v.strip() if isinstance(v, str) else v)
               and not (search and n in ("First Name", "Last Name", "City (now)", "State/Region (now)", "Country (now)"))]
    if missing:
        st.error("Please fill in: " + ", ".join(missing) + ".")
        return
    try:
        born_at = locate_cached(city.strip(), state.strip(), country.strip())
        lives_at = True if search else locate_cached(city_n.strip(), state_n.strip(), country_n.strip())
    except places.LookupDown:
        st.error(PLACE_SEARCH_DOWN)
        return
    if born_at is None:                                       # caught here, before saving
        st.error(f"The birth place '{city}, {state}, {country}' was not found. Check the spelling, or try a larger "
                 "city nearby.")
        return
    if lives_at is None:
        st.error(f"The place where you live now, '{city_n}, {state_n}, {country_n}', was not found. Check the "
                 "spelling, or try a larger city nearby.")
        return
    rec = {"name": first, "last_name": last, "country": country, "state": state, "city": city, "other": other,
           "other_n": other_n,
           "year": born.year, "mon": born.month, "day": born.day,
           "hr": at.hour if at else None, "mn": at.minute if at else None,     # blank time: none kept (12:00 used)
           "country_n": country_n, "state_n": state_n, "city_n": city_n}
    if search:                                                # Search Only: this birth, not saved, on the chart page
        st.session_state["_quick_fill"] = {"quick_date": born, "quick_time": f"{at:%H:%M}", "quick_city": city.strip(),
                                           "quick_state": state.strip(), "quick_country": country.strip(),
                                           "quick_first": first.strip(), "quick_last": last.strip()}
        st.session_state["_select_customer"] = access.QUICK
        st.session_state["_searched"] = "Search: " + (f"{first.strip()} {last.strip()}".strip() or f"{born} {at:%H:%M}") + " (not saved)"
        st.switch_page(PAGE_BY_PATH[back_page()])
    if person:                                                # Save and Search: saved, chosen, on the chart page
        st.session_state["_select_customer"] = db.add_person(rec, user.email)
        st.session_state["_quick_saved"] = f"{first.strip()} {last.strip()} is saved under your login."
        st.switch_page(PAGE_BY_PATH[back_page()])
    elif row is None:
        db.add_own_customer(rec, user.email)                 # (DOB for 1 day) an email that already has a record keeps it (nothing is changed)
        back = st.session_state.pop("_back_to", None)
        if back in PAGE_BY_PATH:                              # they came from a chart's DOB: back to it
            st.switch_page(PAGE_BY_PATH[back])
    else:
        def num(v):
            return None if v is None else int(float(v))
        same_birth = (all(num(val(f)) == rec[f] for f in ("year", "mon", "day", "hr", "mn"))
                      and all(rec[f].strip() == txt(f).strip() for f in ("city", "state", "country")))
        rec["utc"] = val("utc") if same_birth else None   # a new birth time or place: its UTC offset is looked up
        db.update_own_customer(rec, user.email, int(row["id"]))
        st.session_state["details_saved"] = True
    st.rerun()


def back_page() -> str:
    """The chart page Add a DOB (or DOB Details) was opened from (else AstroClock-2D)."""
    back = st.session_state.pop("_back_to", None) or st.session_state.get("_last_chart_page")
    return back if back in PAGE_BY_PATH and back != "me" else "astroclock-2d"


def need_chart(prep: Prepared | None) -> bool:
    if prep is None:
        if user.is_admin:
            st.info("Choose a customer in the sidebar.")
        else:
            new_member_form()
        return False
    if not prep.ok:
        st.warning(prep.message)
        return False
    return True


# ---------------------------------------------------------------- the Defaults table: what each page's inputs start as
SPEED_CHOICES = list(globechart.SPEEDS)                       # Rotate in 1s: none picked, time stands still and the drawing is dragged round
GLOBE_MAJOR = [str(a) for a in sorted(core.MAJOR)]
GLOBE_MINOR = [str(a) for a in core.MINOR]
START, END = "start", "end"                                   # the two date inputs (not buttons)
TEXT = "text"                                                 # a box to type in (its Choice Values: what is typed in to start)
TEXT_MOST = 30                                                # (at most this long, as the box takes)


def default_inputs() -> dict[tuple[str, str], tuple]:
    """Every page input the Defaults table can set, by (Page, Options): (its choices, or START / END; more than one may be
    picked; the app's own default, used when the table has no row for it)."""
    globe = list(globechart.BODY_CHOICES) + list(globechart.NODE_CHOICES)
    out = {("AstroClock-2D", "Time"): (["Now", "DOB"], False, "Now"),   # (Time: Now or DOB, one at a time)
           ("AstroClock-2D", "Planets"): (globe, True, globe),
           ("AstroClock-2D", "Major Aspects"): (GLOBE_MAJOR, True, []),
           ("AstroClock-2D", "Minor Aspects"): (GLOBE_MINOR, True, []),
           ("AstroClock-2D", "Coordinates"): (["Ho", "PP", "1C", "DA"], True, ["Ho", "DA"]),   # (the buttons below it that start on)
           ("AstroClock-2D", "Rotate in 1s"): (SPEED_CHOICES, False, None),
           ("AstroClock-3D", "Time"): (["Now", "DOB"], False, "Now"),
           ("AstroClock-3D", "Planets"): (globe, True, globe),
           ("AstroClock-3D", "Major Aspects"): (GLOBE_MAJOR, True, []),
           ("AstroClock-3D", "Minor Aspects"): (GLOBE_MINOR, True, []),
           ("AstroClock-3D", "Coordinates"): (["Ho", "Ce", "AU", "Sp", "SpC", "PP", "3D", "RA", "De", "La", "Lg"], True, ["Ce"]),
           ("AstroClock-3D", "Rotate in 1s"): (SPEED_CHOICES, False, None),
           ("Geo/Helio Model", "Centric Model"): (["Geo", "Helio"], False, "Geo")}
    # Geo/Helio Model: one row per input for both models; its planets are both models' (each takes those it has: Su for
    # Geo, Ea for Helio)
    bodies = list(globechart.BODY_CHOICES) + [b for b in space3d.HELIO_BODIES if b not in globechart.BODY_CHOICES]
    out |= {("Geo/Helio Model", "Time"): (["Now", "DOB"], False, "Now"),
            ("Geo/Helio Model", "Planets"): (bodies, True, bodies),
            ("Geo/Helio Model", "Coordinates"): (["Ce", "AU", "PP"], True, ["Ce", "AU"]),
            ("Geo/Helio Model", "Rotate in 1s"): (SPEED_CHOICES, False, None)}
    for page, end, planets in (("Planets Cycles", (360, 0), core.BUTTON_ORDER),
                               ("Planets Distance(%)", (24, 0), core.BUTTON_ORDER)):
        out |= {(page, "Start Date (UT)"): (START, False, "DOB"), (page, "End Date (UT)"): (END, False, end),
                (page, "Planets"): (list(planets), True, ["Sa", "Ju"])}
    out[("DOB Details", "Days")] = ([str(d) for d in access.DAY_PACKS], False, "7")   # Get more days of access
    out[("DOB Details", "Pay / Coupon")] = (TEXT, False, None)
    out[("Planets Cycles", "Major Aspects")] = ([str(a) for a in rangechart.EA_NAME], True, ["0", "180"])
    out[("Planets Cycles", "Minor Aspects")] = (GLOBE_MINOR, True, [])
    out |= {("Predictions", "Start Date (UT)"): (START, False, "Now"), ("Predictions", "End Date (UT)"): (END, False, (12, 0))}
    return out


def _word(text: str) -> str:
    """A choice as typed, to compare: lower case, without spaces, degree signs or the text-style mark of a symbol."""
    return "".join(ch for ch in str(text).lower() if ch not in " °\ufe0e\ufe0f")


def read_options(choices, multi: bool, text: str):
    """The Defaults table's Choice Values text as the input's start: (value, what was not understood). Buttons: the choices named
    (by name, SAbr, symbol or planet name, any case, comma-separated; for one on / off button On or Off). Start: DOB or Now.
    End: Now, or Start Date (UT) + a time such as 5 days, 2 years 6 months, 30 years (years, months, weeks, days)."""
    text = (text or "").strip()
    if choices == TEXT:                                       # a box to type in: as written (blank: empty)
        return (text or None), ([] if len(text) <= TEXT_MOST else [text])
    if choices == START:
        w = _word(text)
        return ("Now", []) if w == "now" else ("DOB", [] if w in ("dob", "") else [text])
    if choices == END:
        if _word(text) == "now":
            return "Now", []
        m = re.fullmatch(r"(?is)\s*(?:start(?:\s*date)?(?:\s*\(ut\))?)?\s*\+?\s*(.*?)\s*", text)
        months = days = 0
        parts = re.findall(r"(?i)(\d+)\s*(years?|yrs?|y|months?|mons?|mo|weeks?|wks?|w|days?|d)\b", m[1])
        if not parts or re.sub(r"(?i)(\d+)\s*(years?|yrs?|y|months?|mons?|mo|weeks?|wks?|w|days?|d)\b|,|and", "", m[1]).strip():
            return None, [text]
        for n, unit in parts:
            n, u = int(n), unit.lower()
            if u.startswith("y"):
                months += 12 * n
            elif u.startswith("mo"):
                months += n
            elif u.startswith("w"):
                days += 7 * n
            else:
                days += n
        return (months, days), []
    names = {}
    for c in choices:
        for alias in (c, core.symbol_of(c), db.PLANET_NAMES.get(c, "")):
            if alias:
                names[_word(alias)] = c
    picked, wrong = [], []
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        w = _word(part)
        if len(choices) == 1 and w in ("on", "off", "yes", "no"):
            if w in ("on", "yes"):
                picked.append(choices[0])
        elif w in names:
            if names[w] not in picked:
                picked.append(names[w])
        else:
            wrong.append(part)
    if multi:
        return picked, wrong
    if len(picked) > 1:
        wrong.append("only one can be picked")
    return (picked[0] if picked else None), wrong


def default_choice(page: str, title: str):
    """What this input starts as: the Defaults table's Choice Values for it, read as read_options says; with no row, or Choice Values it
    cannot read, the app's own default."""
    choices, multi, own = default_inputs()[(page, title)]
    text = DEFAULT_TEXTS.get((page.lower(), title.lower()))
    if text is None:
        value = own
    else:
        value, wrong = read_options(choices, multi, text)
        value = own if wrong else value
    if isinstance(choices, list) and len(choices) > 1:        # (kept within what the input offers: Allowed Values)
        allowed = [str(o) for o in offered(page, title, choices)]
        if multi:
            value = [v for v in (value or []) if str(v) in allowed]
        elif value is not None and str(value) not in allowed:
            value = allowed[0] if allowed else None
    return value


def offered(page: str, title: str, options: list) -> list:
    """The options an input offers: those its Defaults row's Allowed Values names (in the app's order), else all of them
    (and all of them too when Allowed Values names none of them: an input is never left with nothing)."""
    text = DEFAULT_ALLOWED.get((page.lower(), title.lower()), "")
    if not text:
        return list(options)
    spec = default_inputs().get((page, title))
    names = spec[0] if spec and isinstance(spec[0], list) else [str(o) for o in options]
    picked, _ = read_options(names, True, text)
    keep = [o for o in options if str(o) in {str(x) for x in picked}]
    return keep or list(options)


def allowed_words(page: str, title: str) -> list[str]:
    """A text box's Allowed Values: the words it takes (none: any text)."""
    text = DEFAULT_ALLOWED.get((page.lower(), title.lower()), "")
    return [w.strip() for w in text.split(",") if w.strip()]




def options_problems(rows: pd.DataFrame) -> list[str]:
    """The Defaults rows whose Page and Choice are no input of the app, or whose Choice Values it cannot read."""
    inputs = {(p.lower(), t.lower()): (p, t, spec) for (p, t), spec in default_inputs().items()}
    out = []
    for _, r in rows.iterrows():
        page, title = db._cell(r["Page"]), db._cell(r["Choice"])
        if not (page and title):
            continue                                          # (said by db.defaults_problems)
        known = inputs.get((page.lower(), title.lower()))
        if known is None:
            names = ", ".join(t for p, t in default_inputs() if p.lower() == page.lower())
            out.append(f"{page} / {title}: no input of that name on the page (Choice names one of its inputs"
                       + (f": {names})" if names else "; no page has that name)"))
            continue
        choices, multi, _ = known[2]
        _, wrong = read_options(choices, multi, db._cell(r["Choice Values"]))
        if wrong:
            if choices == START:
                hint = "DOB or Now"
            elif choices == END:
                hint = "Now, or Start Date (UT) + a time such as 5 days or 2 years 6 months"
            elif choices == TEXT:
                hint = f"any text of at most {TEXT_MOST} characters"
            else:
                hint = ("one of " if not multi else "any of ") + ", ".join(choices) + (" (or On / Off)" if len(choices) == 1 else "")
            one = "only one can be picked"
            said = ", ".join(w for w in wrong if w != one)
            out.append(f"{page} / {title}: " + (f"Choice Values '{said}' not understood: {hint}" if said else f"pick {hint}"))
    return out


# ---------------------------------------------------------------- pages
def add_months(when: datetime, months: int) -> datetime:
    """That many calendar months later, on the same day of the month (or the month's last day, if it has fewer days)."""
    y, m = divmod(when.month - 1 + months, 12)
    year, month = when.year + y, m + 1
    last = (datetime(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return when.replace(year=year, month=month, day=min(when.day, last))


def period(prep: Prepared, row=None, page: str = "") -> tuple[float, float] | None:
    """The Start Date / End Date inputs (UT, dates only, no times) as Julian days, from the start of the Start Date to the
    end of the End Date, or None (with a warning) if unusable. They start as the Defaults table says for this page
    (Start: DOB or Now; End: Now, or Start Date (UT) + a time, which moves with the Start). With row (a horizontal
    container) they go into it, each just wide enough; otherwise in two columns."""
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    birth_dt = core.jd_to_datetime(prep.jd_birth) if prep.jd_birth is not None else now_dt   # (Now charts only: from now)
    c = [row] * 2 if row is not None else st.columns(2)
    dw = 125 if row is not None else "stretch"
    start0 = now_dt if default_choice(page, "Start Date (UT)") == "Now" else birth_dt
    start0 = min(max(start0, datetime(1800, 1, 1)), datetime(2399, 12, 31))   # (the dates allowed)
    d0 = c[0].date_input("Start Date (UT)", value=start0.date(), min_value=datetime(1800, 1, 1),
                         max_value=datetime(2399, 12, 31), width=dw, key=f"start_date_{page}_{prep.jd_birth}_{start0.date()}")
    after = default_choice(page, "End Date (UT)")             # (months, days) after the Start, or "Now"
    if after != "Now":                                        # the End follows the Start: a changed Start sets it again
        end0 = min(add_months(datetime.combine(d0, time(0, 0)), after[0]) + timedelta(days=after[1]), datetime(2399, 12, 31))
        d1 = c[1].date_input("End Date (UT)", value=end0.date(), min_value=datetime(1800, 1, 1),
                             max_value=datetime(2399, 12, 31), width=dw, key=f"end_date_{page}_{d0}_{after}")
    else:
        d1 = c[1].date_input("End Date (UT)", value=now_dt.date(), min_value=datetime(1800, 1, 1),
                             max_value=datetime(2399, 12, 31), width=dw)
    start, end = datetime.combine(d0, time(0, 0)), datetime.combine(d1, time(0, 0)) + timedelta(days=1)   # (to the End Date's end)
    if end <= start:
        st.warning("The end must be after the start.")
        return None
    if (end - start).days > 100 * 366:
        st.warning("That period is too long - choose about 100 years at most.")
        return None
    return core.jd_of_datetime(start), core.jd_of_datetime(end)


def cycles_inputs(keys: str, page: str = "Planets Cycles"):
    """The inputs of Planets Cycles (keys: its buttons' keys): (period as Julian days, planets, major angles, minor angles),
    or None when there is nothing to show yet; a button per major and per minor angle."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return None
    jds = period(prep, head, page)
    # on / off buttons, as on Distance: every choice always in view
    choices = offered(page, "Planets", core.BUTTON_ORDER)
    dec_on = core.in_order(titled(head, "Planets", f"{keys}t_planets", core.shown_order(choices), f"{keys}dec_on_v2", default_choice(page, "Planets"),
                                  selection_mode="multi", format_func=core.symbol_of), choices)
    ea_names = {str(a): a for a in rangechart.EA_NAME}         # the buttons 0, 60, 90, 120, 180 -> their angles
    major_names = offered(page, "Major Aspects", list(ea_names))
    minor_names = offered(page, "Minor Aspects", GLOBE_MINOR)
    ea = core.in_order(titled(head, "Major Aspects", f"{keys}t_major", major_names, f"{keys}ea_on_v5", default_choice(page, "Major Aspects"),
                              selection_mode="multi"), major_names)
    minor = [int(a) for a in core.in_order(titled(head, "Minor Aspects", f"{keys}t_minor", minor_names, f"{keys}minor_on_v1",
                                                  default_choice(page, "Minor Aspects"), selection_mode="multi"), minor_names)]
    if jds is None:
        return None
    return jds, dec_on, [ea_names[e] for e in ea], minor


def page_astroclock():
    """AstroClock-2D: the top page of the menu, for everyone: the Geo drawing in 2D, seen from above the north celestial
    pole, with only the 12 AU circle and an RA scale round it, 1 to 360, always on the Fit scale, an arrow from the Earth through each body out to the circle, and the twelve house lines of CB and CN (the Ho button under Coordinates, on to start). Its buttons, Time, Planets
    (with NN, SN: on the Moon's path, at the Moon's distance, joined by a line, 180 degrees apart) and Rotate in 1s (how fast time runs; none picked: it stands still, and dragging the drawing sideways moves it),
    are its own, and start as the Defaults table says."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="small")
    if not need_chart(prep):
        return
    space_page(head, prep, "sci", "Ea", globechart.BODY_CHOICES + globechart.NODE_CHOICES, model="Geo", flat=True)


def page_globe():
    """The Earth turning inside the celestial sphere: the planets and their RA and De lines on the sphere, CB, CN on it."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="small")
    if not need_chart(prep):
        return

    def one_time(default) -> list:
        """Time, with Now or DOB below it, one at a time (DOB above Now for one whose Access is DOB): [the one picked]."""
        box = head.container(width="content", gap="xxsmall")
        if not box.pills("Time", ["Time"], default="Time", key="globe_Time_on", label_visibility="collapsed"):
            return []
        got = box.pills("Which Time", offered("AstroClock-3D", "Time", list(TIMES)), default=default, key="globe_time",
                        label_visibility="collapsed", width=48)
        return [got] if got else []

    def options_under(title: str, key: str, names: list, default: list, width: int = 84) -> tuple:
        """A button with options listed below it, two a line (width: room for two), to pick from; those picked, none with
        the button off."""
        box = head.container(width="content", gap="xxsmall")
        if not box.pills(title, [title], default=title, key=f"globe_{key}_on", label_visibility="collapsed"):
            return ()
        return tuple(core.in_order(box.pills(f"Which {title}", core.shown_order(names), selection_mode="multi", default=default,
                                             key=f"globe_{key}", format_func=core.symbol_of, label_visibility="collapsed", width=width),
                                   names))

    if prep.now_only:                                         # no birth details: DOB opens the form for them
        dob_asked(st.session_state.get("globe_time") == "DOB", ("globe_time", "Now"))
        shown = one_time("Now")
    else:
        shown = one_time(default_choice("AstroClock-3D", "Time"))
    time_on_top_line(shown[0] if shown else None)
    all_bodies = list(globechart.BODY_CHOICES)
    with_nodes = all_bodies + list(globechart.NODE_CHOICES)   # shown in two rows: Mo Su Me Ve Ma, Ju Sa NN SN
    bodies = options_under("Planets", "bodies", offered("AstroClock-3D", "Planets", with_nodes), default_choice("AstroClock-3D", "Planets"), width=140)
    major = options_under("Major Aspects", "major", offered("AstroClock-3D", "Major Aspects", GLOBE_MAJOR), default_choice("AstroClock-3D", "Major Aspects"), width=90)
    minor = options_under("Minor Aspects", "minor", offered("AstroClock-3D", "Minor Aspects", GLOBE_MINOR), default_choice("AstroClock-3D", "Minor Aspects"), width=90)
    coords_on = default_choice("AstroClock-3D", "Coordinates")
    coords = head.container(width="content", gap="xxsmall")   # Coordinates, with its options below it in fixed rows
    if coords.pills("Coordinates", ["Coordinates"], default="Coordinates", key="globe_coords_on", label_visibility="collapsed"):
        coords_ok = set(offered("AstroClock-3D", "Coordinates", ["Ho", "Ce", "AU", "Sp", "SpC", "PP", "3D", "RA", "De", "La", "Lg"]))
        for row_of in ([n for n in r if n in coords_ok] for r in (["Ho", "Ce", "AU", "Sp", "SpC"], ["PP", "3D", "RA", "De", "La", "Lg"])):   # (two rows)
            if not row_of:
                continue
            shown += coords.pills(f"Coordinates {row_of[0]}", row_of, selection_mode="multi", default=[n for n in row_of if n in coords_on],
                                  key=f"globe_coords_{row_of[0]}", label_visibility="collapsed")
    paths = list(bodies) if "PP" in shown else []             # PP (Planet Path): the paths of the planets shown
    spin = head.container(width="content", gap="xxsmall")     # Rotate, with how fast below it
    day_seconds = None
    if spin.pills("Rotate in 1s", ["Rotate in 1s"], default="Rotate in 1s", key="globe_rotate", label_visibility="collapsed"):
        speed = spin.pills("Rotate speed", offered("AstroClock-3D", "Rotate in 1s", SPEED_CHOICES), default=default_choice("AstroClock-3D", "Rotate in 1s"), key="globe_speed",
                           label_visibility="collapsed", width=124)   # (two rows: 1s, 1m, 1h, 1d; then 1w, 1mo, 1y)
        day_seconds = globechart.SPEEDS.get(speed)
    manual = day_seconds is None                              # no speed: time stands still, and the Earth is dragged round by hand
    jd_now = core.now_jd()
    now_pts, _ = now_values(jd_now)
    utc_now = datetime.now(ZoneInfo(prep.cn_tz)).utcoffset().total_seconds() / 3600.0 if prep.cn_tz else None
    if "3D" in shown:                                         # 3D: in place of the sphere, a true 3D view round the Earth, to turn
        moments = [m for m in (("Now", jd_now, utc_now), ("DOB", prep.jd_birth, prep.utc)) if m[0] in shown]   # and zoom with the mouse
        if not moments or not bodies:
            st.info("Choose a time and at least one planet.")
            return
        spots = {**({"DOB": ("CB", prep.birth_lat, prep.birth_lon)} if not prep.now_only and prep.birth_lon is not None else {}),
                  **({"Now": ("CN", prep.cn[0], prep.cn[1])} if prep.cn else {})}
        moving = bool(day_seconds) and not manual            # Rotate in 1s: time runs at the speed picked
        at = [(m[0], m[1]) for m in moments]
        fig = space3dview.space_figure("Ea", bodies, paths, at, spots, moving=moving, show_au="AU" in shown,
                                       show_links="SpC" in shown, show_celes="Ce" in shown, show_spokes="Sp" in shown)
        # (the HTML is built only from the chart and the tables, never from what a user typed: safe to run) the script draws
        # the Earth as a globe, and with a speed picked moves the planets and turns the Earth
        st.html(mapchart.fit_html(fig, after_js=space3dview.space_js("Ea", bodies, at, day_seconds if moving else None, spots,
                                                                     {m[0]: m[2] for m in moments}, "SpC" in shown)),
                unsafe_allow_javascript=True)
        return
    g = globechart.GlobeInput(
        birth=prep.birth, now=now_pts, jd_birth=prep.jd_birth, jd_now=jd_now,
        cb=None if prep.now_only else (prep.birth_lat, prep.birth_lon), cn=prep.cn, show_birth="DOB" in shown, show_now="Now" in shown,
        show_ra="RA" in shown, show_dec="De" in shown, show_latitude="La" in shown,
        show_longitude="Lg" in shown, show_celes="Ce" in shown, show_houses="Ho" in shown, bodies=bodies, paths=paths,
        show_distance="AU" in shown, show_links="SpC" in shown, show_spokes="Sp" in shown, aspects=tuple(int(a) for a in major + minor), orbs=orbs(),
        utc_birth=prep.utc, utc_now=utc_now)
    # (the HTML is built only from the chart, never from what a user typed, so its script is safe to run)
    st.html(mapchart.fit_html(globechart.globe_figure(g),
                              after_js=globechart.globe_js(g, day_seconds, manual)),
            unsafe_allow_javascript=True)


CENTRIC_MODELS = {"Geo": ("space", "Ea", globechart.BODY_CHOICES),        # GeoCentric, HelioCentric: its buttons' keys, the body at the
                  "Helio": ("helio", "Su", space3d.HELIO_BODIES)}           # centre, the planets


def page_centric():
    """The paths at their real distances, in 3D, around the Earth (GeoCentric) or the Sun (HelioCentric)."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="small")
    if not need_chart(prep):
        return
    model = (titled(head, "Centric Model", "t_centric", offered("Geo/Helio Model", "Centric Model", list(CENTRIC_MODELS)), "centric_model", default_choice("Geo/Helio Model", "Centric Model"))
             or st.session_state.get("_kept_centric_model") or "Geo")   # (with the title off, the model last picked)
    space_page(head, prep, *CENTRIC_MODELS[model], model=model)


def kept_pills(box, label: str, options, key: str, default=None, **kw):
    """Buttons whose choice is kept while they are not on the page (Streamlit forgets a widget's choice on a run that does not
    show it): when they come back they start from the choice they had."""
    store = f"_kept_{key}"
    start = st.session_state.get(store, default)
    start = [v for v in start if v in options] if isinstance(start, list) else start if start in options else None   # (a choice since removed: none)
    value = box.pills(label, options, default=start, key=key, **kw)
    st.session_state[store] = value
    return value


def titled(head, title: str, title_key: str, options, key: str, default=None, **kw):
    """As AstroClock-3D's: a title button with its choices below it. The choices picked; nothing while the title is off (they
    come back as they were when it is turned on again)."""
    box = head.container(width="content", gap="xxsmall")
    if not kept_pills(box, title, [title], title_key, title, label_visibility="collapsed"):
        return None
    return kept_pills(box, f"Which {title}", options, key, default, label_visibility="collapsed", **kw)


def coords_below(coords, keys: dict, names: list, on: list, title_key: str) -> list:
    """The Coordinates title button and, below it, an on / off button for each of names (keys: each one's key): those on
    (none while the title is off). Each starts on when on (the Defaults row Coordinates) names it."""
    if not kept_pills(coords, "Coordinates", ["Coordinates"], title_key, "Coordinates", label_visibility="collapsed"):
        return []
    below = coords.container(horizontal=True, width="content", gap="xxsmall")
    return [n for n in names if kept_pills(below, n, [n], keys[n], n if n in (on or []) else None, label_visibility="collapsed")]


def time_on_top_line(when: str | None) -> None:
    """A page with DOB and Now buttons shows on its top line only the one picked: DOB (the birth) or Now (the clock); neither
    with Time off."""
    hide = {"DOB": [".now-clock"], "Now": [".dob-label"]}.get(when, [".now-clock", ".dob-label"])
    st.html(f"<style>{', '.join(hide)} {{ display: none; }}</style>")


def space_page(head, prep, key: str, centre: str, choices: tuple, model: str = "Geo", flat: bool = False):
    """GeoCentric (centre Ea) or HelioCentric (centre Su): its buttons each keep their own choice (key), also while the other
    model is shown; they start as the Defaults table says (Geo/Helio Model's rows, Time .. Rotate in 1s, for both models)."""
    def start(title: str):
        if flat:
            return default_choice("AstroClock-2D", title)
        value = default_choice("Geo/Helio Model", title)      # (the planets: those this model has)
        return [v for v in value if v in choices] if title == "Planets" else value

    def may(title: str, options: list) -> list:
        """What this input offers (its Defaults row's Allowed Values)."""
        return offered("AstroClock-2D", title, options) if flat else offered("Geo/Helio Model", title, options)
    if prep.now_only:                                         # no birth details: Now, and DOB opens the form for them
        dob_asked(st.session_state.get(f"{key}_when") == "DOB", (f"{key}_when", "Now"), (f"_kept_{key}_when", "Now"))
        when = titled(head, "Time", f"{key}_t_time", list(TIMES), f"{key}_when", "Now")
    else:
        when = titled(head, "Time", f"{key}_t_time", may("Time", list(TIMES)), f"{key}_when", start("Time"))
    shown = [when] if when else []                            # Now or DOB, one at a time
    time_on_top_line(when)
    choices = tuple(may("Planets", list(choices)))
    bodies = core.in_order(titled(head, "Planets", f"{key}_t_bodies", core.shown_order(choices), f"{key}_bodies", start("Planets"), selection_mode="multi",
                                  format_func=core.symbol_of), choices)
    aspects, one_circle = (), False
    with_paths = []                                           # (PP, under Coordinates: the paths of the planets shown)
    if flat:      # always Fit
        major_names, minor_names = may("Major Aspects", GLOBE_MAJOR), may("Minor Aspects", GLOBE_MINOR)
        major = core.in_order(titled(head, "Major Aspects", f"{key}_t_major", major_names, f"{key}_major", start("Major Aspects"), selection_mode="multi"), major_names)
        minor = core.in_order(titled(head, "Minor Aspects", f"{key}_t_minor", minor_names, f"{key}_minor", start("Minor Aspects"), selection_mode="multi"), minor_names)
        aspects = tuple(int(a) for a in major + minor)
        show_au, show_celes = True, True
        coords = head.container(width="content", gap="xxsmall")   # Coordinates, with Ho, PP, 1C and DA below it (the title off: none)
        # (DA: the Ave planets on the Distance(%) graph; which start on, and which are there: the Defaults row Coordinates)
        on = coords_below(coords, {"Ho": f"{key}_houses", "PP": f"{key}_pp", "1C": f"{key}_one_circle", "DA": f"{key}_dav"},
                          may("Coordinates", ["Ho", "PP", "1C", "DA"]), start("Coordinates"), f"{key}_t_coords")
        show_houses, one_circle, show_ave = "Ho" in on, "1C" in on, "DA" in on
        with_paths = list(bodies) if "PP" in on else []
    else:
        coords = head.container(width="content", gap="xxsmall")   # Coordinates, with Ce, AU and PP below it (always the Fit scale)
        # (Ce, first: the celestial coordinates; then AU; then PP, the Planet Path of each planet shown; the title off: none)
        on = coords_below(coords, {"Ce": f"{key}_ce", "AU": f"{key}_au", "PP": f"{key}_pp"}, may("Coordinates", ["Ce", "AU", "PP"]),
                          start("Coordinates"), f"{key}_t_scale")
        show_celes, show_au = "Ce" in on, "AU" in on
        with_paths = list(bodies) if "PP" in on else []
    speed = titled(head, "Rotate in 1s", f"{key}_t_speed", may("Rotate in 1s", SPEED_CHOICES), f"{key}_speed", start("Rotate in 1s"))
    day_seconds = globechart.SPEEDS.get(speed)
    manual = day_seconds is None and not flat                 # no speed: time stands still, and the drawing is dragged round (the flat
                                                              # page: dragging it sideways moves time)
    jd_now = core.now_jd()
    ave_jds = None
    if flat and show_ave and not prep.now_only:               # AstroClock-2D: the Ave planets on its Distance(%) graph, moving as time runs
        ave_jds = {"DOB": prep.jd_birth, "Now": jd_now}
    if not shown or not bodies:
        st.info("Choose a time and at least one planet.")
        # nothing drawn: no clock beside the name either (the last drawing's would stay there)
        st.html("<script>document.querySelectorAll('.globe-clock').forEach((e) => { e.textContent = ''; });</script>",
                unsafe_allow_javascript=True)
        return
    utc_now = datetime.now(ZoneInfo(prep.cn_tz)).utcoffset().total_seconds() / 3600.0 if prep.cn_tz else None
    moments = [m for m in (("Now", jd_now, utc_now), ("DOB", prep.jd_birth, prep.utc)) if m[0] in shown]
    st.html(space3d.space_html(bodies, moments, space3d.FIT, str(prep.jd_birth), day_seconds, manual, show_au, tuple(with_paths), centre, flat,
                               {**({"DOB": ("CB", prep.birth_lon)} if prep.birth_lon is not None else {}),
                                **({"Now": ("CN", prep.cn[1])} if prep.cn else {})} if flat and show_houses else None, ave_jds,
                               aspects, orbs() if aspects else None, one_circle, show_celes=show_celes),
            unsafe_allow_javascript=True)


def page_range():
    got = cycles_inputs("", page="Planets Cycles")
    if got is None:
        return
    jds, dec_on, angles, minor = got
    with st.spinner("Drawing..."):
        fig, note = _range_cached(tuple(dec_on), tuple(angles + minor), *jds, db.orb_table().to_csv(index=False))
    # fixed size, scaled down whole to fit (its tags are placed for that size)
    st.html(mapchart.fit_html(fig), unsafe_allow_javascript=True)
    if note:
        st.caption(note)


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _range_cached(dec_on, ea, jd_from, jd_to, orb_csv):
    import io
    return rangechart.range_figure(list(dec_on), list(ea), jd_from, jd_to, core.Orbs(pd.read_csv(io.StringIO(orb_csv))))


def page_distance():
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return
    jds = period(prep, head, "Planets Distance(%)")
    # on / off buttons: all seven planets always in view (a selection box would hide some, or not fit on the line)
    dist_names = offered("Planets Distance(%)", "Planets", core.BUTTON_ORDER)
    dist_on = core.in_order(titled(head, "Planets", "t_dist", core.shown_order(dist_names), "dist_on_v2", default_choice("Planets Distance(%)", "Planets"),
                                   selection_mode="multi", format_func=core.symbol_of), dist_names)
    if jds is None:
        return
    with st.spinner("Drawing..."):
        fig = _distance_cached(tuple(dist_on), *jds)
    st.html(mapchart.fit_html(fig), unsafe_allow_javascript=True)   # a fixed size, zoomed with the page
    st.caption("D = % between the planet's least and greatest distance from the Earth (1800-2400): 0 nearest, "
               "100 farthest.")


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _distance_cached(dist_on, jd_from, jd_to):
    return distancechart.distance_figure(list(dist_on), jd_from, jd_to)



# Customers, DOB, Defaults, Help and Symbols: Insert, Update, Delete and Ignore on the title line. Editable tables sort by their
# column headers only while they cannot add or delete rows themselves, so these buttons do that. Each saves at once (Update
# checks what has been typed; Delete takes the rows ticked in the first column); Ignore drops what has not been saved.
# each character's width in Source Sans at 14 px (measured in the browser); the tables draw their text at TABLE_FONT_PX
# (the app's 12 px type), so a width is these times TABLE_FONT_PX / 14; a character not here (a planet's symbol ..) taken
# as OTHER_CHAR_PX
CHAR_PX = dict(zip(" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~°…",
                   [2.8, 4.05, 5.96, 6.96, 6.96, 11.54, 8.53, 3.49, 4.24, 4.24, 5.85, 6.96, 3.49, 4.35, 3.49, 4.9] + [6.96] * 10 +
                   [3.49, 3.49, 6.96, 6.96, 6.96, 5.95, 11.86, 7.6, 8.23, 7.99, 8.61, 7.38, 6.92, 8.64, 9.13, 3.68, 6.71, 8.11, 6.8,
                    10.18, 9.06, 9.3, 7.92, 9.3, 7.97, 7.48, 7.5, 9.03, 7.21, 11, 7.18, 6.66, 7.55, 4.24, 4.9, 4.24, 6.96, 7, 7.59,
                    7.06, 7.74, 6.38, 7.77, 6.94, 4.09, 7.06, 7.62, 3.46, 3.46, 6.93, 3.57, 11.61, 7.66, 7.59, 7.77, 7.77, 4.86, 5.87,
                    4.73, 7.62, 6.54, 10.07, 6.24, 6.54, 5.95, 4.24, 3.37, 4.24, 6.96, 4.63, 13.27]))
OTHER_CHAR_PX = 14.0
TABLE_FONT_PX = 10.0                                          # the tables' text (the page's script draws their canvas text in 10 px)
CELL_PAD_PX = 14                                              # a cell's space, both sides together (6 px each, and 2 to spare)
HEAD_ICON_PX = 18                                             # an editable table's heading: the small icon before its name


def text_px(text: str) -> float:
    """How wide the text is in a table (px)."""
    return sum(CHAR_PX.get(ch, OTHER_CHAR_PX) for ch in text) * TABLE_FONT_PX / 14.0


def fitted(df: pd.DataFrame, column_config: dict | None = None, icons: bool = False) -> dict:
    """column_config with a width for each column of df that has none: just wide enough for the longest text the column
    has, or its heading (icons: with its icon, as an editable table shows it), so the columns stand close together with no
    space to spare (the data itself is not changed)."""
    out = dict(column_config or {})
    for col in df.columns:
        cfg = out.get(col)
        if cfg is None and col in out:                        # (a column hidden)
            continue
        cfg = dict(cfg or {})
        if cfg.get("width"):
            out[col] = cfg
            continue
        head = text_px(str(cfg.get("label") or col)) + (HEAD_ICON_PX if icons else 0)
        values = [] if df[col].dtype == bool else df[col].dropna()   # (a tick box: its heading's width)
        shown = (f"{v:.2f}" if isinstance(v, float) else v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, (datetime, pd.Timestamp))
                 else str(v) for v in values)                 # (numbers and times as the tables show them)
        cfg["width"] = int(max([head] + [text_px(s) for s in shown]) + CELL_PAD_PX)
        out[col] = cfg
    return out


ROW_PX = 26                                                   # a table's row (and heading) height, as the tables draw it


def rows_px(n: int) -> int:
    """A table's height with all its n rows in view, and its heading (no empty rows below them)."""
    return ROW_PX * (n + 1) + 3


TABLES_DRAWN = {"n": 0}                                       # the tables drawn on this run (a key each: see table_fit)


def table_fit(df: pd.DataFrame, config: dict, kw: dict, name: str | None = None) -> tuple[dict, str, str]:
    """For a table: kw (width "content"), the key of a box to draw it in (from name, else a new one), and the style that
    makes the table in that box just as wide as its columns (Streamlit's own content width leaves space after the last):
    set in the table's own pixels, which the page's zoom does not change, so it holds at any window size; with room for a
    scroll bar when its rows do not all fit; never wider than the page."""
    if name is None:
        TABLES_DRAWN["n"] += 1
        name = str(TABLES_DRAWN["n"])
    box = "fit_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(name))
    kw = {**kw, "width": "content"} if kw.get("width", "content") == "content" else kw
    total = sum(c["width"] for col, c in config.items() if col in df.columns and c is not None and c.get("width"))
    h = kw.get("height", "auto")
    scrolls = len(df) > 10 if h in (None, "auto") else isinstance(h, int) and h < rows_px(len(df))
    px = int(total) + 2 + (14 if scrolls else 0)
    style = (f'<style>.st-key-{box} [data-testid="stDataFrame"], .st-key-{box} [data-testid="stDataFrameResizable"] '
             f'{{ width: min({px}px, 100%) !important; max-width: 100% !important; }}</style>')
    return kw, box, style


def show_table(df: pd.DataFrame, column_config: dict | None = None, **kw):
    """st.dataframe with its columns close together (fitted), and no space after the last."""
    config = fitted(df, column_config)
    kw, box, style = table_fit(df, config, kw)
    got = st.container(key=box).dataframe(df, column_config=config, **kw)
    st.html(style)
    return got


def edit_table(df: pd.DataFrame, column_config: dict | None = None, **kw):
    """st.data_editor with its columns close together (fitted), and no space after the last."""
    config = fitted(df, column_config, icons=True)
    kw, box, style = table_fit(df, config, kw, name=kw.get("key"))
    got = st.container(key=box).data_editor(df, column_config=config, **kw)
    st.html(style)
    return got


def crud_table(key: str, show: pd.DataFrame, problems, commit, column_config: dict | None = None, width: str = "content",
               height: int | None = None, on_update=None) -> None:
    """Insert, Update, Delete, Ignore and Reset to Previous, each saving at once (no Commit): Insert saves the edits made,
    then adds a blank row at the bottom to fill in; Update saves the rows as they stand (the new row too, once filled in);
    Delete saves the table without the rows ticked; Ignore drops every change not saved yet; Reset to Previous puts the
    table back as it was before its last save (kept in the database at each save; pressed again, it comes back).
    problems(rows) gives what is wrong with the rows as they stand; commit(rows) saves them and gives what to report;
    on_update(rows), when given, gives the rows as they are saved (e.g. worked-out columns filled in)."""
    pressed = next((name for name in ("Insert", "Update", "Delete", "Ignore", "Reset to Previous")
                    if TITLE_SLOT.button(name, key=f"{key}_{name}")), None)   # (all alike: none marked as the main one)
    if pressed == "Reset to Previous":
        st.session_state[f"{key}_reset_ask"] = True
    def fresh() -> None:
        """The table on the screen starts again from the rows given it: the typing it still held is dropped (popping the
        widget's state is not enough, as the browser sends its edits back; a new key starts it empty)."""
        st.session_state[f"{key}_ver"] = st.session_state.get(f"{key}_ver", 0) + 1

    if pressed == "Ignore":                                    # every change not saved is dropped: the table as saved
        for name in (f"{key}_working", f"{key}_base"):
            st.session_state.pop(name, None)
        fresh()
        st.session_state[f"{key}_said"] = "Changes ignored: the table is as saved."
        st.rerun()
    if st.session_state.pop(f"{key}_add_row", False):          # Insert: a blank row at the bottom, to fill in
        if isinstance(height, int):                            # (the page sized the table before the row was added)
            height += ROW_PX
        start = st.session_state.get(f"{key}_working", show)
        st.session_state.setdefault(f"{key}_base", show)       # what the rows started from (see page_customers)
        st.session_state[f"{key}_working"] = start.reindex(range(len(start) + 1)).reset_index(drop=True)
        fresh()
        st.session_state[f"{key}_said"] = ((st.session_state.get(f"{key}_said") or "") +
                                           " A new row is at the bottom of the table: fill it in and press Update to save it.").strip()
    view = st.session_state.get(f"{key}_working", show).copy()
    view.insert(0, "Del", False)
    editor_key = f"{key}_v{st.session_state.get(f'{key}_ver', 0)}"   # (a new one after each save: see fresh)
    edited = edit_table(view, hide_index=True, width=width, num_rows="fixed", key=editor_key, height=height or "auto",
                            column_config={"Del": st.column_config.CheckboxColumn("Del",
                                                                                  help="Tick, then press Delete."),
                                           **(column_config or {})}).reset_index(drop=True)
    rows, ticked = edited.drop(columns="Del"), edited["Del"].fillna(False).astype(bool)
    said = st.session_state.pop(f"{key}_said", None)           # below the table, so that it does not move
    if said:
        st.success(said)
    elif f"{key}_working" in st.session_state:
        st.caption("Fill in the new row, then press Update to save it (Ignore drops it).")

    def save(new_rows: pd.DataFrame, verb: str) -> bool:
        """Saves the rows at once (as on_update gives them); False, with what is wrong shown, when they cannot be saved.
        A row left wholly blank (Insert's, not filled in) is not saved, and is not a problem on any table."""
        new_rows = new_rows[[any(_filled(v) for v in r) for r in new_rows.itertuples(index=False)]].reset_index(drop=True)
        new_rows = on_update(new_rows) if on_update else new_rows
        wrong = problems(new_rows)
        if wrong:
            st.error(f"Not {verb}. " + "; ".join(wrong))
            return False
        try:
            report = commit(new_rows)
        except SQLAlchemyError as exc:                         # nothing is saved: the table stays as it is on the screen
            st.error(f"Not {verb}. The database refused it: {getattr(exc, 'orig', exc)}")
            return False
        st.cache_data.clear()                                  # charts kept with the old values
        db.keep_previous(key, show)                            # the table as it was before, for Reset to Previous
        for name in (f"{key}_working", f"{key}_base"):
            st.session_state.pop(name, None)
        fresh()
        st.session_state[f"{key}_said"] = report
        return True

    if st.session_state.get(f"{key}_reset_ask"):              # Reset to Previous: the table as it was before its last save
        previous = db.previous_rows(key)
        if previous is not None and list(previous.columns) != list(show.columns):   # kept before the table's columns changed
            st.info("Nothing to go back to: the copy kept was made before the table's columns changed. Save the table once "
                    "to keep a new one.")
            st.session_state.pop(f"{key}_reset_ask", None)
            return
        if previous is None:
            st.info("Nothing to go back to: the table has not been saved since this was added.")
            st.session_state.pop(f"{key}_reset_ask", None)
            return
        st.warning("Put the table back as it was before its last save? (Pressed again, it comes back to this.)")
        yes, no = st.columns(2, width=220)
        if yes.button("Yes, reset", type="primary", key=f"{key}_reset_yes"):
            st.session_state.pop(f"{key}_reset_ask", None)
            back = previous.copy()
            if "id" in back.columns and "id" in show.columns:  # a row deleted since comes back as a new one (a new ID)
                gone = ~back["id"].isin(show["id"].dropna())
                back["id"] = back["id"].astype("Float64").mask(gone)
            st.session_state[f"{key}_base"] = show                 # (saved against the table as it is now)
            if save(back, "reset"):
                st.session_state[f"{key}_said"] = "Reset: the table is as it was before its last save. " + st.session_state[f"{key}_said"]
                st.rerun()
        if no.button("No", key=f"{key}_reset_no"):
            st.session_state.pop(f"{key}_reset_ask", None)
            st.rerun()

    if pressed == "Insert":
        # the edits made (other than ticks) are saved first, a row left blank not counting; then a blank row is added
        # to the table as it stands, to fill in (on the next run, so that it follows a save)
        typed = (st.session_state.get(editor_key) or {}).get("edited_rows", {})
        if any(set(cells) - {"Del"} for cells in typed.values()):
            if not save(rows, "inserted"):                       # (a row left blank is dropped by save)
                return
        st.session_state[f"{key}_add_row"] = True
        st.rerun()
    elif pressed == "Delete":
        if not ticked.any():
            st.warning("Tick the rows to delete in the Del column first.")
        elif save(rows[~ticked].reset_index(drop=True), "deleted"):
            st.rerun()
    elif pressed == "Update":
        if save(rows, "saved"):
            st.rerun()


def _filled(v) -> bool:
    """A cell with something in it (not blank, None or NaN)."""
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return str(v).strip() != ""


def page_logins():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    all_on = st.session_state.get("logins_all", False)        # Select all: every row ticked (pressed again: none)
    pick = "Unselect all" if all_on else "Select all"
    pressed = next((name for name in (pick, "Delete", "Delete all")
                    if TITLE_SLOT.button(name, key="logins_select" if name == pick else f"logins_{name}")), None)
    if pressed == pick:
        st.session_state["logins_all"] = not all_on
        st.session_state.pop("logins_ask", None)
        st.rerun()
    table = db.logins_table()
    view = table.copy()
    view.insert(0, "Del", all_on)
    # (ticks are kept by row position: a new key when the rows move, so that a tick cannot land on another row)
    edited = edit_table(view, hide_index=True, width="content", num_rows="fixed",
                            key=f"logins_table_{len(table)}_{table['Id'].iloc[0] if len(table) else 0}_{int(all_on)}",
                            height="auto" if len(table) <= 18 else 700, disabled=["Id", "Email", "Activity", "Date_Time", "Page", "Details", "Device", "Time zone", "Access"],
                            column_config={"Del": st.column_config.CheckboxColumn("Del", help="Tick, then press Delete."),
                                           "Id": st.column_config.NumberColumn("ID", format="%d",
                                                                               help="The row's number, set by the app."),
                                           "Date_Time": st.column_config.DatetimeColumn("Date_Time (UT)", format="YYYY-MM-DD HH:mm:ss"),
                                           "Device": st.column_config.TextColumn(help="Their browser and system, e.g. "
                                                                                 "Chrome on Windows; blank when not known."),
                                           "Time zone": st.column_config.TextColumn(help="The time zone their browser "
                                                                                    "is set to; blank when not known."),
                                           "Page": st.column_config.TextColumn(help="The page they were on."),
                                           "Details": st.column_config.TextColumn(help="What was done: which customer "
                                                                                  "was opened (by record number), which table was "
                                                                                  "saved, days added with which coupon .."),
                                           "Access": st.column_config.TextColumn(help="Their Access then (Now, DOB, Admin; "
                                                                                 "'DOB ended' after its End Date); blank "
                                                                                 "with none, or no customer record.")})
    ticked = edited.loc[edited["Del"].fillna(False).astype(bool), "Id"].tolist()
    said = st.session_state.pop("logins_said", None)
    if said:
        st.success(said)
    else:
        st.caption(f"{len(table)} row(s), newest first" + (" (the latest 5000)" if len(table) >= 5000 else "") + ".")
    if pressed == "Delete":
        if ticked:
            st.session_state["logins_ask"] = ticked
        else:
            st.warning("Tick the rows to delete in the Del column first.")
    elif pressed == "Delete all":
        st.session_state["logins_ask"] = "all"
    ask = st.session_state.get("logins_ask")
    if ask and ask != "all" and ask != ticked:                # the ticks changed since: the question no longer fits them
        st.session_state.pop("logins_ask", None)
        ask = None
    if ask:
        what = "every row of the Logins table" if ask == "all" else f"{len(ask)} row(s)"
        st.warning(f"Delete {what} for good? This cannot be undone.")
        yes, no = st.columns(2, width=220)
        if yes.button("Yes, delete", type="primary", key="logins_yes"):
            n = db.delete_logins(None if ask == "all" else ask)
            st.session_state.pop("logins_ask", None)
            st.session_state.pop("logins_all", None)          # (the rows left start unticked)
            st.session_state["logins_said"] = f"Deleted {n} row(s)."
            st.rerun()
        if no.button("No", key="logins_no"):
            st.session_state.pop("logins_ask", None)
            st.rerun()


def input_spec(page, options):
    """A Defaults row's input: (its choices, more than one may be picked, the app's own default); None when no page has it."""
    return {(p.lower(), o.lower()): s for (p, o), s in default_inputs().items()}.get(
        (str(page or "").strip().lower(), str(options or "").strip().lower()))


def is_list_input(spec) -> bool:
    """An input of buttons to pick from (not a date, a text box or one on / off button)."""
    return spec is not None and isinstance(spec[0], list) and len(spec[0]) > 1


def can_limit(spec) -> bool:
    """An input whose Allowed Values can limit its Choice Values: buttons to pick from, or a text box (to the words typed there)."""
    return is_list_input(spec) or (spec is not None and spec[0] == TEXT)


def allowed_values(page, options, stored=None) -> str:
    """A Defaults row's Allowed Values as shown: those kept (stored), else every value its input takes; for a date, a text
    box or one on / off button, what Choice Values may hold (those cannot be narrowed)."""
    spec = input_spec(page, options)
    if spec is None:
        return "" if not (page and options) else "(no page has that input)"
    choices = spec[0]
    if choices == START:
        return "DOB or Now"
    if choices == END:
        return "Now, or Start Date (UT) + a time (e.g. 5 days, 2 years 6 months)"
    if choices == TEXT:
        return db._cell(stored) or f"any text, at most {TEXT_MOST} characters (blank: empty)"
    if len(choices) == 1:
        return f"On or Off ({choices[0]})"
    kept = db._cell(stored)
    return kept if kept else ", ".join(map(str, choices))


def allowed_to_keep(page, options, text) -> tuple[str | None, list[str]]:
    """Allowed Values as typed, as it is kept: (the values named, in the app's order, or None for all of them / an input
    that cannot be narrowed; what was not understood)."""
    spec = input_spec(page, options)
    if spec is not None and spec[0] == TEXT:                  # a text box: the words typed, comma-separated (blank, or its
        text = db._cell(text)                                 # description: any text)
        if not text or text == allowed_values(page, options):
            return None, []
        words = list(dict.fromkeys(w.strip() for w in text.split(",") if w.strip()))
        long = [w for w in words if len(w) > TEXT_MOST]
        return ", ".join(words) or None, [f"{w} (more than {TEXT_MOST} characters)" for w in long]
    if not is_list_input(spec):
        return None, []
    text = re.sub(r"(?i)^\s*(one|any)\s+of\s*:\s*", "", db._cell(text))
    if not text:
        return None, []
    picked, wrong = read_options(spec[0], True, text)
    if wrong:
        return text, wrong
    if not picked:
        return None, ["none named"]
    names = [str(c) for c in spec[0] if str(c) in {str(x) for x in picked}]
    return (None if len(names) == len(spec[0]) else ", ".join(names)), []


def page_defaults():
    """The Defaults table, each column its own: Page, Choice (the input), Choice Values (what it starts as) and Allowed
    Values (the values Choice Values may be set to, and all the page offers)."""
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()

    def shown(rows: pd.DataFrame) -> pd.DataFrame:
        """The rows as the page shows (and keeps) them: Allowed Values as kept, all the input's values when blank; one
        typed for a date or one on / off button is left as typed (refused by problems)."""
        out = rows.copy()
        for i, r in out.iterrows():
            spec, typed = input_spec(r["Page"], r["Choice"]), db._cell(r.get("Allowed Values"))
            if spec is not None and not can_limit(spec) and typed and typed != allowed_values(r["Page"], r["Choice"]):
                continue
            kept, wrong = allowed_to_keep(r["Page"], r["Choice"], typed)
            if not wrong:
                out.at[i, "Allowed Values"] = allowed_values(r["Page"], r["Choice"], kept)
        return out[db.DEFAULTS_COLUMNS]

    def problems(rows: pd.DataFrame) -> list[str]:
        out = db.defaults_problems(rows) + options_problems(rows)
        for _, r in rows.iterrows():
            page, title = db._cell(r["Page"]), db._cell(r["Choice"])
            spec = input_spec(page, title)
            if not (page and title) or spec is None:
                continue
            typed = db._cell(r.get("Allowed Values"))
            if not can_limit(spec):
                if typed and typed != allowed_values(page, title):
                    out.append(f"{page} / {title}: Allowed Values cannot be changed for this input "
                               f"({allowed_values(page, title)}); change Choice Values instead")
                continue
            kept, wrong = allowed_to_keep(page, title, typed)
            if wrong:
                out.append(f"{page} / {title}: Allowed Values '{', '.join(wrong)}' not understood")
            elif kept and spec[0] == TEXT:                    # a text box's Choice Values: one of its words (or blank: empty)
                value = db._cell(r["Choice Values"])
                if value and value.lower() not in [w.lower() for w in kept.split(", ")]:
                    out.append(f"{page} / {title}: Choice Values {value} not in its Allowed Values ({kept}); "
                               "add it to Allowed Values too, or clear Allowed Values for any text")
            elif kept:                                        # Choice Values must be among its Allowed Values
                value, bad = read_options(spec[0], spec[1], db._cell(r["Choice Values"]))
                start = value if isinstance(value, list) else ([value] if value else [])
                outside = [str(v) for v in start if str(v) not in kept.split(", ")]
                if not bad and outside:
                    out.append(f"{page} / {title}: Choice Values {', '.join(outside)} not in its Allowed Values ({kept}); "
                               "add it to Allowed Values too, or clear Allowed Values for all")
        return out

    def commit(rows: pd.DataFrame) -> str:
        keep = rows.copy()
        keep["Allowed Values"] = [allowed_to_keep(p, o, a)[0] for p, o, a in zip(rows["Page"], rows["Choice"], rows["Allowed Values"])]
        return f"Saved: {db.save_defaults(keep)} row(s)."

    table = shown(db.defaults_table())
    crud_table("defaults_table", table, problems, commit, on_update=shown,
               height=rows_px(len(st.session_state.get("defaults_table_working", table))),   # every row in view
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app (blank on a new row until saved)."), "Choice": st.column_config.TextColumn(help="The input: its name on the page "
                                                                     "(e.g. Days). Each Page has one row per input."),
                              "Choice Values": st.column_config.TextColumn(help="What the input starts as (e.g. 7). "
                                                                   "Blank: the app's own default (none, for buttons)."),
                              "Allowed Values": st.column_config.TextColumn("Allowed Values",
                                                                   help="The values Choice Values may be set to: all the input's "
                                                                        "values, or those typed here (comma-separated). The page "
                                                                        "then offers only those (buttons, Days, coupons). Clear "
                                                                        "it for all of them again. A text box takes words typed "
                                                                        "here (e.g. Pay, Free); clear it for any text. Dates "
                                                                        "and single on / off buttons cannot be narrowed.")})


def page_readme():
    """The app's README (README.md, beside this file), as written: admins only."""
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    readme = Path(__file__).with_name("README.md")
    text = readme.read_text(encoding="utf-8") if readme.exists() else "README.md is not there."
    words = search_box("readme", "Any word in the README")
    if not words:
        st.markdown(text)
        return
    st.markdown(readme_lines_with(text, words, st.session_state["readme_search"]))


def readme_lines_with(text: str, words: str, typed: str) -> str:
    """The README's lines with the text (any case), the text marked in each, as markdown: how many first; the lines of its
    pages table kept as a table, under its headings."""
    lines = text.splitlines()
    head, rows, others = [], [], []
    for n, line in enumerate(lines):
        if line.startswith("|"):
            if not head and n + 1 < len(lines) and re.fullmatch(r"\|[\s:|-]+\|", lines[n + 1].strip()):
                head = [line, lines[n + 1]]                  # (the table's headings and its line below them)
                continue
            if words in line.lower() and not re.fullmatch(r"\|[\s:|-]+\|", line.strip()):
                rows.append(line)
        elif line.strip() and words in line.lower():
            others.append(line)
    mark = (lambda s: re.sub(re.escape(typed), lambda m: f"**{m.group(0)}**", s, flags=re.IGNORECASE)) if "*" not in typed else (lambda s: s)
    count = len(others) + len(rows)
    said = f"{count} line{' of the README has' if count == 1 else 's of the README have'} '{typed}'."
    parts = [said] + [mark(line) for line in others]             # (each its own paragraph)
    if rows:
        parts.append("\n".join([*head, *[mark(r) for r in rows]]))   # (one table)
    return "\n\n".join(parts)


def search_box(name: str, placeholder: str) -> str:
    """A page's Search: a box and a Search button (or Enter), and Clear once something is searched for. The text searched
    for, in lower case ('' for none); kept while the page is left and come back to."""
    key = f"{name}_search"
    with st.form(f"{key}_form", border=False, enter_to_submit=True):
        row = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
        text = row.text_input("Search", value=st.session_state.get(key, ""), placeholder=placeholder, max_chars=60, width=260,
                              label_visibility="collapsed")
        if row.form_submit_button("Search"):
            st.session_state[key] = text.strip()
    if st.session_state.get(key) and st.button("Clear", key=f"{key}_clear"):
        st.session_state[key] = ""
        st.rerun()
    return (st.session_state.get(key) or "").lower()


def rows_with(table: pd.DataFrame, words: str) -> pd.DataFrame:
    """The rows of table with the text in any of their cells (any case)."""
    hit = pd.Series(False, index=table.index)
    for col in table.columns:
        hit |= table[col].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)).str.lower().str.contains(words, regex=False)
    return table[hit].reset_index(drop=True)


def searched_rows(name: str, table: pd.DataFrame, words: str, column_config: dict | None = None) -> bool:
    """With something searched for: the table's rows that have it, to read (an admin clears the search to change the table,
    so that a save never meets only some of its rows); True. Else False."""
    if not words:
        return False
    found = rows_with(table, words)
    st.caption(f"{len(found)} of {len(table)} rows {'has' if len(found) == 1 else 'have'} '{st.session_state[f'{name}_search']}'."
               + (" Clear the search to change the table." if user.is_admin else ""))
    if len(found):
        show_table(found, column_config, hide_index=True, width="content", height=rows_px(len(found)))
    return True


def page_help_table():
    """The abbreviations the pages use: everyone can read them, and search them; admins change them (Insert, Update, Delete,
    each saved at once; Ignore), the whole table, not a search's rows."""
    table = db.help_rows()
    if searched_rows("help", table, search_box("help", "Abbreviation or description"),
                     {"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app.")}):
        return
    if not user.is_admin:
        show_table(table, hide_index=True, width="content", height=rows_px(len(table)),   # every row in view
                     column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app (blank on a new row until saved).")})
        return
    crud_table("help_table", table, db.help_problems, lambda rows: f"Saved: {db.save_help(rows)} row(s).", on_update=db.help_sorted,   # (Update: in Abbreviation order)
               height=rows_px(len(st.session_state.get("help_table_working", table))),   # every row in view
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app (blank on a new row until saved).")})


def page_conditions():
    """The Conditions table: Condition (unique, whatever its case), its Object and its Values; admins only (Insert, Update, Delete, each
    saved at once; Ignore; Reset to Previous)."""
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.conditions_rows()
    crud_table("conditions_table", table, db.conditions_problems, lambda rows: f"Saved: {db.save_conditions(rows)} row(s).",
               on_update=db.conditions_sorted,                  # (Update: in Condition order)
               height=rows_px(len(st.session_state.get("conditions_table_working", table))),   # every row in view
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app (blank on a new row until saved)."), "Condition": st.column_config.TextColumn("Condition *", help="Required, unique "
                                                                       "(whatever its case), at most 60 characters."),
                              "Object": st.column_config.TextColumn(help="What it is for, at most 60 "
                                                                        "characters."),
                              "Values": st.column_config.TextColumn(help="Its values, at most 500 characters.")})


PREDICTIONS_NEED_BIRTH = ("Predictions need your birth details: enter them here, and once they are saved you go back to "
                          "Predictions.")


def page_predictions():
    """Predictions, from the Prediction Rules table, for the birth chart of the customer picked (DOB charts only): Birth
    chart, its points at the rules' angles at birth; Transits, when the planets now come to the rules' angles with it,
    between a start and an end date; each with its Prediction."""
    _, prep = pick_customer()
    no_birth = prep is None or prep.now_only or prep.jd_birth is None or not prep.birth   # (no birth details, or DOB not open)
    if no_birth and not user.is_admin and "me" in PAGE_BY_PATH:   # a member: told so, on DOB Details, to add them there
        locked = prep is not None and prep.locked
        unusable = prep is not None and not prep.ok and prep.message   # (birth details that cannot be worked out: why)
        st.session_state["_dob_locked"] = ((prep.message or access.PAID_NOTE) if locked else
                                           f"{prep.message} Fix it here to see Predictions." if unusable else
                                           PREDICTIONS_NEED_BIRTH)   # (shown on DOB Details)
        if locked:
            st.session_state["_open_more_days"] = True         # Get more days of access, open
        st.session_state["_back_to"] = nav.url_path           # (once their details are saved: back to Predictions)
        st.switch_page(PAGE_BY_PATH["me"])
    head = st.container(horizontal=True, vertical_alignment="top", gap="xsmall")
    if not need_chart(prep):
        return
    if no_birth:                                              # (an admin: no customer, or one without birth details)
        st.info(prep.message or "Predictions need birth details: add them on the DOB page.")
        return
    jds = period(prep, head, "Predictions")                  # (every planet: no Planets buttons)
    if jds is None:
        return
    every = db.prediction_rules()
    if not every:
        st.info("No prediction rules yet." + (" Add them on the Prediction Rules page." if user.is_admin else ""))
        return
    nn = core.moon_north_node(prep.jd_birth)                  # (the birth chart's nodes too)
    birth = {**prep.birth, "NN": nn, "SN": ((nn[0] + 180.0) % 360.0, -nn[1])}
    birth_predictions([r[1:] for r in every if r[0] == "Birth"], birth)
    orb_csv = db.orb_table().to_csv(index=False)
    passes_table("Transits", [r[1:] for r in every if r[0] == "Transit"], jds, orb_csv, birth)
    passes_table("Sky", [r[1:] for r in every if r[0] == "Sky"], jds, orb_csv)
    distance_predictions([r[1:] for r in every if r[0] == "Distance"], jds)


def aspect_label(kind: str, angle: int) -> str:
    """A rule's aspect as the Predictions tables show it: RA 90° (Square), De parallel, RA+De 90° (Square)."""
    if kind == "De":
        return "De parallel" if int(angle) == 0 else "De contra-parallel"
    name = db.aspect_name(kind, angle)
    return f"{kind} {int(angle)}°" + (f" ({name})" if name else "")


def passes_table(title: str, rules: list, jds: tuple, orb_csv: str, birth: dict | None = None) -> None:
    """Transits (birth given: the planets now with the birth chart) or Sky (the planets now with each other): each pass
    over the period, soonest first, with the rule's Event and Prediction."""
    st.markdown(f"**{title}**")
    if not rules:
        st.caption(f"The Prediction Rules table has no {'Transit' if birth else 'Sky'} rows.")
        return
    with st.spinner(f"Finding {title.lower()}..."):
        events = (_predictions_cached(tuple(sorted(birth.items())), tuple(r[:4] for r in rules), *jds, orb_csv) if birth is not None
                  else _sky_cached(tuple(r[:4] for r in rules), *jds, orb_csv))
    texts = {r[:4]: r[4:6] for r in rules}                   # (Event, Prediction)
    st.caption(f"{len(events)} in this period." if events else "None in this period.")
    if not events:
        return
    at = lambda jd: core.jd_to_datetime(jd).strftime("%Y-%m-%d %H:%M")
    one, other = ("Moving", "Birth") if birth is not None else ("Planet", "With")
    rows = [{"Exact (UT)": at(exact), one: core.with_symbols(m), other: core.with_symbols(b),
             "Aspect": aspect_label(k, a),
             "Begins (UT)": at(begins) if begins is not None else "before Start", "Ends (UT)": at(ends) if ends is not None else "after End",
             "Off": off, "Event": texts.get((m, b, k, a), ("", ""))[0], "Prediction": texts.get((m, b, k, a), ("", ""))[1]}
            for m, b, k, a, begins, exact, ends, off in events]
    show_table(pd.DataFrame(rows), hide_index=True, width="content",
               column_config={"Off": st.column_config.NumberColumn(format="%.2f", help="Degrees from the angle at Exact.")})


def distance_predictions(rules: list, jds: tuple) -> None:
    """Distance: each time a planet is at its closest to (Near) or farthest from (Far) the Earth over the period, soonest
    first, with its distance (AU, Distance(%)) and the rule's Event and Prediction."""
    st.markdown("**Distance**")
    if not rules:
        st.caption("The Prediction Rules table has no Distance rows.")
        return
    events = _closest_farthest_cached(tuple((r[0], r[2]) for r in rules), *jds)
    texts = {(r[0], r[2]): r[4:6] for r in rules}            # (planet, Near / Far): (Event, Prediction)
    st.caption(f"{len(events)} in this period." if events else "None in this period.")
    if not events:
        return
    rows = [{"Exact (UT)": core.jd_to_datetime(jd).strftime("%Y-%m-%d %H:%M"), "Planet": core.with_symbols(p),
             "Kind": "Closest" if kind == "Near" else "Farthest", "AU": au, "Distance(%)": pct,
             "Event": texts.get((p, kind), ("", ""))[0], "Prediction": texts.get((p, kind), ("", ""))[1]}
            for p, kind, jd, au, pct in events]
    show_table(pd.DataFrame(rows), hide_index=True, width="content",
               column_config={"AU": st.column_config.NumberColumn(format="%.4f", help="Its distance from the Earth then (AU)."),
                              "Distance(%)": st.column_config.NumberColumn(format="%.2f", help="As Planets Distance(%) shows it: 0 its closest, 100 its farthest (1800-2400).")})


def birth_predictions(rules: list, birth: dict) -> None:
    """Birth: the Birth rows of the Prediction Rules table whose two points are at their angle at birth (within the
    pair's orb in Aspect Rules), closest first, each with its Prediction."""
    st.markdown("**Birth**")
    o = orbs()
    rows = []
    for a, b, kind, angle, text, reading in rules:
        if a not in birth or b not in birth:
            continue
        off = core.transit_gap(kind, angle, *birth[a], birth[b])
        orb = o.pair(angle, a, b, is_dec=kind == "De")
        de_apart = min(abs(birth[a][1] - birth[b][1]), abs(birth[a][1] + birth[b][1]))   # (RA+De: equal or mirrored De)
        if off <= orb and (kind != "RA+De" or de_apart <= o.pair(angle, a, b, is_dec=True)):
            rows.append({"Planet": core.with_symbols(a), "With": core.with_symbols(b), "Aspect": aspect_label(kind, angle),
                         "Off": off, "Event": text, "Prediction": reading})
    if not rules:
        st.caption("The Prediction Rules table has no Birth rows.")
        return
    if not rows:
        st.caption("None of the Birth rows is at its angle in this birth chart.")
        return
    rows.sort(key=lambda r: r["Off"])
    show_table(pd.DataFrame(rows), hide_index=True, width="content",
                 column_config={"Off": st.column_config.NumberColumn(format="%.2f", help="Degrees from the angle at birth.")})


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _predictions_cached(birth, rules, jd_from, jd_to, orb_csv):
    import io
    ev = core.transit_events(dict(birth), list(rules), jd_from, jd_to, core.Orbs(pd.read_csv(io.StringIO(orb_csv))))
    return [(e.moving, e.birth, e.kind, e.angle, e.begins, e.exact, e.ends, e.off) for e in ev]


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _sky_cached(rules, jd_from, jd_to, orb_csv):
    import io
    ev = core.sky_events(list(rules), jd_from, jd_to, core.Orbs(pd.read_csv(io.StringIO(orb_csv))))
    return [(e.moving, e.birth, e.kind, e.angle, e.begins, e.exact, e.ends, e.off) for e in ev]


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _closest_farthest_cached(rules, jd_from, jd_to):
    return [(e.planet, e.kind, e.jd, e.au, e.pct) for e in core.distance_events(list(rules), jd_from, jd_to)]


def page_prediction_rules():
    """The Predictions table: a row per Chart, Moving, Birth, Kind and Angle (unique together), with its Event;
    admins only (Insert, Update, Delete, each saved at once; Ignore; Reset to Previous)."""
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.predictions_rows()
    if searched_rows("predictions", table, search_box("predictions", "Any column (e.g. Sa, square, De)"),
                     {"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app.")}):
        return
    crud_table("predictions_table", table, db.predictions_problems, lambda rows: f"Saved: {db.save_predictions(rows)} row(s).",
               on_update=db.predictions_sorted,               # (Update: in the page's order)
               height=rows_px(min(30, len(st.session_state.get("predictions_table_working", table)))),   # (thousands of rows: 30 in view, the rest by scrolling)
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app (blank on a new row until saved)."),
                              "Chart": st.column_config.SelectboxColumn("Chart *", options=db.PRED_CHARTS,
                                                                        help="Birth: two points at the angle in the birth chart. Transit: a planet now coming to the angle with a birth point. Sky: two planets now at the angle with each other. Distance: a planet at its closest (Near) or farthest (Far) from the Earth."),
                              "Moving": st.column_config.SelectboxColumn("Moving *", options=db.PRED_BIRTH,
                                                                          help="Transit, Sky: a planet now (not CB). Birth: the first point of the birth chart. Distance: the planet (Mo .. Sa)."),
                              "Birth": st.column_config.SelectboxColumn("Birth *", options=db.PRED_BIRTH + ["Ea"],
                                                                        help="Transit, Birth: the point of the birth chart (CB: house 10 at birth). Sky: the other planet now. Distance: Ea (the Earth)."),
                              "Kind": st.column_config.SelectboxColumn("Kind *", options=db.PRED_KINDS,
                                                                       help="RA: the RA between the two is the Angle. De: Angle 0 parallel, 180 contra-parallel. RA+De: in aspect by Aspect Rules (RA within its orb of the Angle, and De within the De orb, equal or mirrored). Distance rows: Near or Far, Angle 0."),
                              "Angle": st.column_config.NumberColumn("Angle *", min_value=0, max_value=180, step=1, format="%d",
                                                                     help="0 to 180 (De: 0 or 180)."),
                              "Aspect": st.column_config.TextColumn(disabled=True, help="The aspect by name, from Kind and Angle (as Aspect Rules names them: Conjunction 0, Opposition 180, Square 90 ..; De: Parallel, Contra-parallel; Distance: Closest, Farthest). Set by the app."),
                              "Event": st.column_config.TextColumn("Event *", help="Its reading, at most 500 characters."),
                              "Prediction": st.column_config.TextColumn(help="The prediction for the row (optional), at most 500 characters.")})


def page_naming():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    # the page's names for the table's columns (the store keeps its own)
    shown_as = {"SN": "SAbr", "Symbol": "Symb", "Name": "SDesc", "Color": "RGB", "Color_Name": "Color", "Size": "Size_Geo"}   # (Size_Clock-3D, Size_Helio as they are)
    back = {v: k for k, v in shown_as.items()}
    table = db.all_planets().assign(_sn=lambda d: d["SN"]).rename(columns=shown_as)[["id", "Symb", "SAbr", "SDesc", "RGB", "Color", "Size_Clock-2D", "Size_Clock-3D", "Size_Geo", "Size_Helio", "_sn"]]
    crud_table("planets_table", table, lambda rows: db.planet_problems(rows.rename(columns=back)),
               lambda rows: "Saved: {} added, {} changed, {} deleted.".format(*db.save_planets(rows.rename(columns=back))),
               height=rows_px(len(st.session_state.get("planets_table_working", table))) + 16,   # every row in view, above the scroll bar
               column_config={"_sn": None, "id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The row's number, set by the app (blank on a new row until saved).")}, width="content")


def page_aspects():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.orb_table()
    st.caption("A pair is in aspect when RA is within the RA orb of the angle and the two De values within the De orb of "
               "equal or mirrored, at every angle. One row of orbs for every aspect; a pair uses the total of its two "
               "planets' orbs (RA and De each); CB and CN have their own (0 to start: the planet's orb alone).")
    show = table[db.ORB_COLUMNS].head(1)
    edited = edit_table(show, hide_index=True, num_rows="fixed", key="orb_editor", width="content",
                            column_config={c: st.column_config.NumberColumn(core.with_symbols(c[:-3]) + (" RA" if c.endswith("-RA") else " De"),
                                                                            min_value=0.0, format="%g")
                                           for c in db.ORB_COLUMNS})   # ☽︎ RA, ☉︎ RA .. ☽︎ De ..
    said = st.session_state.pop("orb_said", None)
    if said:
        st.success(said)
    if TITLE_SLOT.button("Update", key="orb_save"):   # (on the title line, beside the page's name)
        wrong = db.orb_problems(edited)
        if wrong:
            st.error("Not updated. " + " ".join(wrong))
        else:
            db.save_orb_table(edited)
            st.cache_data.clear()                             # charts kept with the old orbs
            st.session_state.pop("orb_editor", None)
            st.session_state["orb_said"] = "Updated: these orbs now apply to every aspect."
            st.rerun()
    if TITLE_SLOT.button("Ignore", key="orb_ignore"):                 # the changes not saved are dropped: the orbs as saved
        for name in ("orb_editor", "orb_reset_ask"):
            st.session_state.pop(name, None)
        st.session_state["orb_said"] = "Changes ignored: the orbs are as saved."
        st.rerun()
    if TITLE_SLOT.button("Reset to Previous", key="orb_reset"):   # back to the orbs before the last Update (never the app's defaults)
        st.session_state["orb_reset_ask"] = True
    if st.session_state.get("orb_reset_ask"):
        previous = db.previous_orbs()
        if previous is None:
            st.info("Nothing to go back to: the orbs have not been updated since this was added.")
            st.session_state.pop("orb_reset_ask", None)
            return
        st.warning("Put the orbs back to their values before the last Update? (Pressed again, it goes back to these.)")
        yes, no = st.columns(2, width=220)
        if yes.button("Yes, reset", type="primary", key="orb_reset_yes"):
            db.save_orb_table(previous)                       # (the orbs it replaces are kept as the previous ones)
            for name in ("orb_reset_ask", "orb_editor"):
                st.session_state.pop(name, None)
            st.cache_data.clear()
            st.session_state["orb_said"] = "Reset: the orbs are as they were before the last Update."
            st.rerun()
        if no.button("No", key="orb_reset_no"):
            st.session_state.pop("orb_reset_ask", None)
            st.rerun()


def page_accounts():
    """The Customers table: a row per login, with its Access, Start Date and End Date (End Date typed to lengthen or
    shorten DOB)."""
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    df = db.accounts_table()
    names = {"email": "Email", "access": "Access", "start_date": "Start Date", "end_date": "End Date"}
    show = df[["id", "email", "access", "start_date", "end_date"]].rename(columns=names)
    back = {v: k for k, v in names.items()}

    def commit(rows: pd.DataFrame) -> str:
        base = st.session_state.get("acct_editor_base")
        return "Saved: {} added, {} changed, {} deleted.".format(
            *db.save_accounts(rows.rename(columns=back), df if base is None else base.rename(columns=back), by=user.email))

    crud_table("acct_editor", show, lambda rows: db.account_problems(rows.rename(columns=back)), commit, width="content",
               height="auto" if len(st.session_state.get("acct_editor_working", show)) <= 18 else 700,
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True,
                                                                  help="The row's number, set by the app (blank on a new row until saved)."),
                              "Email": st.column_config.TextColumn("Email *", help="The Google account email they sign "
                                                                   "in with: required, one row per email."),
                              "Access": st.column_config.SelectboxColumn("Access", options=list(access.ACCESS),
                                                                         help="Now, DOB, Admin "
                                                                              "(see the page's help); blank is saved as Now."),
                              "Start Date": st.column_config.DatetimeColumn("Start Date", format="YYYY-MM-DD HH:mm",
                                                                            help="When DOB counts from (UT). Change it "
                                                                                 "to count from another day (the day paid, say); "
                                                                                 "changing Access alone sets it to now."),
                              "End Date": st.column_config.DatetimeColumn("End Date", format="YYYY-MM-DD HH:mm",
                                                                          help="When DOB runs out (UT): after it, the Now "
                                                                               "charts only. Type a new one and press Update to "
                                                                               "lengthen or shorten DOB (the row becomes DOB).")})


def birth_date(y, m, d) -> date | None:
    """Year, Mon, Date as one date (None when any is missing or they make no date)."""
    try:
        return date(int(y), int(m), int(d))
    except (TypeError, ValueError, OverflowError):
        return None


def date_parts(v) -> tuple:
    """A date as typed in a table (a date, a datetime or YYYY-MM-DD text) as (Year, Mon, Date); blanks when none. (Not
    through pandas' Timestamp, which stops at 2262; births go to 2399.)"""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.year, v.month, v.day
    try:
        d = date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return None, None, None
    return d.year, d.month, d.day


def birth_clock(h, m) -> time | None:
    """Hr24, Min as one time of day (None when the hour is missing or they make no time)."""
    try:
        return time(int(h), 0 if m is None or pd.isna(m) else int(m))
    except (TypeError, ValueError):
        return None


def time_parts(v) -> tuple:
    """A time as typed in a table (a time, a datetime or HH:MM text) as (Hr24, Min); blanks when none."""
    if isinstance(v, datetime):
        v = v.time()
    if isinstance(v, time):
        return v.hour, v.minute
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:.]\s*(\d{2})(?::\d{2})?\s*", str(v or ""))
    if m and int(m[1]) < 24 and int(m[2]) < 60:
        return int(m[1]), int(m[2])
    return None, None


def page_customers():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    if db.is_local_sqlite() and not auth._secret("dev_user"):
        st.warning("Saved in a local SQLite file. On Streamlit Community Cloud that file is lost on every restart: "
                   "set the secret db_url to a hosted Postgres database (see README).")
    df = db.all_customers()
    # UTC is not shown (a blank one is looked up from the birth place; one already kept stays, see below); Created and
    # Last_Updated (UT) are, read only (set by the app); the time last opened (Accessed) is kept but not shown
    shown_fields = [f for f in db.FIELDS if f not in ("utc", "year", "mon", "mn")]   # (Date: the whole birth date; Time: hour and minute)
    stamps = {"added_at": "Created", "updated_at": "Last_Updated"}
    show = df[["id"] + shown_fields + ["added_at", "updated_at"]].rename(columns={**db.LABELS, **stamps})
    show[db.LABELS["day"]] = [birth_date(y, m, d) for y, m, d in zip(df["year"], df["mon"], df["day"])]
    show[db.LABELS["hr"]] = [birth_clock(h, m) for h, m in zip(df["hr"], df["mn"])]
    show = show.rename(columns={db.LABELS["hr"]: "Local-Time-24hr"})
    # First Name, A-Z, to begin with; the column headers sort by any column. Saving matches rows by their record, so the
    # order shown does not matter
    by_name = show[db.LABELS["name"]].map(lambda v: v.strip().lower() if isinstance(v, str) else v)
    show = show.loc[by_name.sort_values(na_position="last", kind="stable").index].reset_index(drop=True)
    def for_store(rows: pd.DataFrame) -> pd.DataFrame:
        back = {**{v: k for k, v in db.LABELS.items()}, **{v: k for k, v in stamps.items()}}
        out = rows.rename(columns={"Local-Time-24hr": db.LABELS["hr"]}).rename(columns=back).drop(columns=["updated_at"], errors="ignore")   # (Last_Updated: the app's)
        parts = [date_parts(v) for v in out["day"]]                 # the Date column back into Year, Mon, Date
        out["year"], out["mon"], out["day"] = [p[0] for p in parts], [p[1] for p in parts], [p[2] for p in parts]
        clock = [time_parts(v) for v in out["hr"]]                  # and the Time column into Hr24, Min
        out["hr"], out["mn"] = [c[0] for c in clock], [c[1] for c in clock]
        out["utc"] = out["id"].map(df.set_index("id")["utc"])   # each customer's kept UTC, unchanged (new: blank)
        return out

    def commit(rows: pd.DataFrame) -> str:
        # against what the working copy started from: a member who joined or changed their details since is left alone
        base = st.session_state.get("cust_editor_base")
        return "Saved: {} added, {} changed, {} deleted.".format(
            *db.save_customers(for_store(rows), df if base is None else for_store(base), by=user.email))

    crud_table("cust_editor", show, lambda rows: db.customer_problems(for_store(rows)), commit,
               height="auto" if len(st.session_state.get("cust_editor_working", show)) <= 18 else 700,   # nothing below it overlapped
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, help="The record's number, set by the app (blank on a new row until saved)."),
                                "First Name": st.column_config.TextColumn("First Name *", help="Required."),
                                "Last Name": st.column_config.TextColumn("Last Name *", help="Required."),
                                "Local-Time-24hr": st.column_config.TimeColumn("Local-Time-24hr *", help="Birth time, local, 24 h: required.",
                                                                    format="HH:mm", step=60),
                                "Date": st.column_config.DateColumn("Date *", help="Birth date: required, 1800 to 2399.",
                                                                    format="YYYY-MM-DD", min_value=date(1800, 1, 1),
                                                                    max_value=date(2399, 12, 31)),
                                "Email (login)": st.column_config.TextColumn("Email (login) *",
                                help="Required. The Google account email this customer signs in with (they see only "
                                     "their own). An email's own customer is its first; it may have any number more (people added "
                                     "under that login, or a family). It refers to the Customers page: an Email new there gets "
                                     "a row with DOB for 1 day (so does a login with Access Now getting its first record), and what it may "
                                     "see is its Access there."),
                                "Country": st.column_config.TextColumn("Country *", help="Birth place: required."),
                                "State": st.column_config.TextColumn("State *", help="Birth place: required."),
                                "City": st.column_config.TextColumn("City *", help="Birth place: required."),
                                "Other": st.column_config.TextColumn(help="Anything else to keep with the record."),
                                "Country-N": st.column_config.TextColumn("Country-N *", help="Place now: required."),
                                "State-N": st.column_config.TextColumn("State-N *", help="Place now: required."),
                                "City-N": st.column_config.TextColumn("City-N *", help="Place now: required."),
                                "Other-N": st.column_config.TextColumn(help="Anything else about the place now."),
                                "Created": st.column_config.DatetimeColumn("Created", format="YYYY-MM-DD HH:mm",
                                                                           help="When the record was added (UT). Set by the app "
                                                                                "when left blank; may be changed."),
                                "Last_Updated": st.column_config.DatetimeColumn("Last_Updated", format="YYYY-MM-DD HH:mm",
                                                                                disabled=True,
                                                                                help="When the record was last changed (UT), set by the app.")})
    with st.expander("Import from the workbook"):
        st.write("Save the workbook's Customers tab as CSV (Customer, Country, State, City, Other, Year, Mon, Date, "
                 "Hr24, Min, Country-N, State-N, City-N, Other-N; Other and Other-N may be left out) and upload it. "
                 "Names already here are skipped. Then add each customer's Email (login): it is required to save.")
        up = st.file_uploader("Customers CSV", type="csv")
        if up is not None and st.button("Import"):
            try:
                n = db.import_workbook_csv(up.getvalue(), by=user.email)
            except (ValueError, OverflowError, SQLAlchemyError) as exc:   # nothing is saved
                st.error(f"That file could not be imported, so nothing was added: {exc}")
            else:
                st.cache_data.clear()
                st.session_state["cust_editor_said"] = (f"Imported {n} customers. Add each one's login email to let them "
                                                        "see their charts.")
                st.rerun()


def page_my_details():
    row, prep = pick_customer()
    if row is None:
        new_member_form()
        more_days_box()                                       # (every member can add days, birth details or not)
        page_notes()
        return
    if GRANT.many and not user.is_admin:                      # DOB members: a person to add, at the top
        with st.expander("Add a DOB"):
            add_person_form()
    if int(row["id"]) == access.QUICK:
        st.info("This search is not saved. Pick a saved person in the sidebar to see or change their details.")
        more_days_box()
        page_notes()
    else:
        if prep and prep.ok and not prep.now_only:           # (Now charts only: their birth is not worked out)
            st.write(f"Born on a {prep.weekday}; UTC offset {prep.utc:+.2f} ({prep.tz}); birth place "
                     f"{prep.birth_lat}, {prep.birth_lon}.")
        with st.expander("Edit a DOB"):
            details_form(row)
        more_days_box()                                       # every member adds DOB days themselves (free for now; later
                                                              # paid), below Edit a DOB
        page_notes()


def page_notes():
    """DOB Details' messages, below its boxes: DOB not open (they picked it on a chart page), days added, their details
    saved."""
    locked = st.session_state.pop("_dob_locked", None)
    if locked:
        st.warning(locked if isinstance(locked, str) else access.PAID_NOTE)
    said = st.session_state.pop("days_added", None)
    if said:
        st.success(said)
    if st.session_state.pop("details_saved", False):
        st.success("Your details are saved.")


FREE_COUPONS = ("free",)                                       # coupons that add days free (any case); payment to come


def more_days_box():
    """Get more days of access, for every member (not admins: their access has no end): they pick how many (access.DAY_PACKS) and
    they are added at once, from their End Date while it runs, else from now. Free for now; to become a paid option
    (the payment goes here, before db.add_days)."""
    if user.is_admin:
        return
    # (open when they were sent here for it: they picked DOB, which is not open to them)
    with st.expander("Get more days of access",
                     expanded=st.session_state.pop("_open_more_days", False)):
        note = (GRANT.note or "DOB charts open.") if GRANT.dob else "Now charts only: add days here to open the DOB charts."
        st.caption(note + " Days are added to your End Date while it runs, else from now. For now, apply the coupon "
                   "Free to add them free.")
        # (a form: Enter in Pay / Coupon adds the days as Add days does; before, Enter only changed the box, and nothing
        # was added)
        with st.form("more_days_form", border=False, enter_to_submit=True):
            c1, c2, c3, _ = st.columns([1, 1.4, 1, 2.6], vertical_alignment="bottom")
            # (both start as the Defaults table says: DOB Details / Days and / Pay / Coupon)
            start_days = default_choice("DOB Details", "Days")
            packs = [int(d) for d in offered("DOB Details", "Days", [str(d) for d in access.DAY_PACKS])]   # (Allowed Values)
            days = c1.selectbox("Days", packs, index=packs.index(int(start_days)) if str(start_days or "").isdigit()
                                and int(start_days) in packs else 0, key="more_days")
            coupon = c2.text_input("Pay / Coupon", value=default_choice("DOB Details", "Pay / Coupon") or "",
                                   key="more_days_coupon", max_chars=TEXT_MOST,   # (payment to come)
                                  placeholder="Type the coupon")   # (not "Free": a grey hint read as already typed in)
            pressed = c3.form_submit_button("Add days", type="primary")
        if pressed:
            words = allowed_words("DOB Details", "Pay / Coupon")   # (only these, when its Allowed Values names them)
            if words and (coupon or "").strip().lower() not in [w.lower() for w in words]:
                st.error(f"No days added: Pay / Coupon takes {', '.join(words)}.")
                return
            if (coupon or "").strip().lower() not in FREE_COUPONS:   # (the payment goes here, in place of a coupon)
                st.error("No days added: type the coupon Free in Pay / Coupon (payment is not open yet), then press Add days.")
                return
            try:
                end = db.add_days(user.email, int(days), (coupon or "").strip() or None)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["days_added"] = f"{days} day{'s' if days != 1 else ''} added: DOB until {end:%Y-%m-%d %H:%M} UT."
                st.rerun()


core.SIZE_TEXTS, core.SIZE_WORDS, core.SIZE_TEXTS_HELIO, core.SIZE_TEXTS_GLOBE, core.SIZE_TEXTS_CLOCK = db.planet_sizes()   # and their sizes
core.SYMBOL_TEXTS = db.planet_symbols()                       # and their symbols, shown in place of the SNs
DEFAULT_TEXTS = db.defaults_map()                             # what each page's inputs start as (the Defaults table)
DEFAULT_ALLOWED = db.defaults_allowed_map()                   # and what each may be set to (its Allowed Values)
core.COLOURS.update(core.DEFAULT_COLOURS | db.planet_colours())   # every chart's colours are the Symbols table's (a deleted row's, the usual one)
def add_person_form():
    """A person to add under their login (DOB members, on DOB Details): its form, with Search Only and Save and Search."""
    st.caption(("Saved under your login, to see their DOB charts while your DOB access runs; " if GRANT.dob else
                "Saved under your login, to see their Now charts; ") + "their place now starts as yours. Search Only shows "
               "their DOB charts, not saved, as a Search choice in the sidebar (no name or place now needed); Save and Search "
               "saves them, then shows their charts.")
    own = visible_customers()
    own = own[own["id"] == OWN_ID]
    details_form(pd.Series({f: own.iloc[0][f] for f in ("country_n", "state_n", "city_n", "other_n")}) if len(own) else None,
                 person=True)


pages = [st.Page(page_astroclock, title="AstroClock-2D", icon=":material/science:", url_path="astroclock-2d"),
         st.Page(page_globe, title="AstroClock-3D", icon=":material/language:", url_path="astroclock-3d"),
         st.Page(page_predictions, title="Predictions", icon=":material/auto_awesome:", url_path="predictions"),
         st.Page(page_centric, title="Geo/Helio Model", icon=":material/orbit:", url_path="geo-helio-model"),
         st.Page(page_range, title="Planets Cycles", icon=":material/show_chart:", url_path="planets-cycles"),
         st.Page(page_distance, title="Planets Distance(%)", icon=":material/straighten:", url_path="planets-distance")]
if user.is_admin:                                             # the Aspect Rules, App Conditions, DOB, Symbols, Page Defaults, Help, Logins, Readme pages: admins only
    pages += [st.Page(page_aspects, title="Aspect Rules", icon=":material/tune:", url_path="aspect-rules"),
              st.Page(page_conditions, title="App Conditions", icon=":material/rule:", url_path="conditions"),
              st.Page(page_accounts, title="Customers", icon=":material/badge:", url_path="customers"),
              st.Page(page_customers, title="DOB", icon=":material/group:", url_path="dob"),
              st.Page(page_help_table, title="Help", icon=":material/help:", url_path="help"),
              st.Page(page_logins, title="Logins", icon=":material/history:", url_path="logins"),
              st.Page(page_defaults, title="Page Defaults", icon=":material/settings:", url_path="defaults"),
              st.Page(page_prediction_rules, title="Prediction Rules", icon=":material/menu_book:", url_path="prediction-rules"),
              st.Page(page_readme, title="Readme", icon=":material/description:", url_path="readme"),
              st.Page(page_naming, title="Symbols", icon=":material/planet:", url_path="symbols")]
else:
    pages.append(st.Page(page_my_details, title="DOB Details", icon=":material/person:", url_path="me"))
    pages.append(st.Page(page_help_table, title="Help", icon=":material/help:", url_path="help"))   # (to read; admins change it)
home = st.Page(lambda: None, title="Home", url_path="home", default=True, visibility="hidden")   # the root URL: sends to AstroClock-2D
nav = st.navigation([home] + pages, expanded=True)            # every page shown (no "View more"): the Customer box right below
PAGE_BY_PATH = {p.url_path: p for p in pages}                 # (to go to a page from another)
if nav is home:                                               # / opens /astroclock-2d, keeping any query
    st.switch_page(PAGE_BY_PATH["astroclock-2d"], query_params=st.query_params.to_dict())
st.session_state["_page"] = nav.title                        # the page, for the Logins rows written on it
_chosen = _pick_customer()                                    # the sidebar's customer, for every page
top_line(nav.title, *_chosen)
nav.run()
st.sidebar.caption(f"Swiss Ephemeris via {se.BACKEND}. Equatorial (RA / De) only.")
st.sidebar.caption("Orchestrated by Senthil Muthuraj  \nBuilt by AI/SI Agents")   # at the foot of every page's sidebar: one
                                                                                  # caption, two lines (no gap between them)
