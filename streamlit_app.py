"""Equatorial (RA / Dec) charts with Swiss Ephemeris - the web version of the Excel workbook.

Pages: AstroClock-2D, AstroClock-3D, Geo/Helio Model, Planets Distance(%), Planets Cycles, Aspects (its aspects as tables) for everyone (their own customers only);
Aspect Rules, Customers, Symbols, Defaults and Logins for admins; My details for users. Run locally:  .venv\\Scripts\\streamlit run streamlit_app.py
"""
from __future__ import annotations

import html
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import access, auth, db, location
from app.chartdata import NOW_ONLY, Prepared, locate_cached, now_values, prepare
from astro import core, distancechart, globechart, mapchart, places, rangechart, se, space3d

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
.st-key-globe_bodies button, .st-key-globe_paths button, .st-key-globe_coords button, .st-key-globe_speed button,
.st-key-globe_major button, .st-key-globe_minor button, .st-key-space_speed button
  { flex: 0 0 auto !important; width: auto !important; }
/* the circles: every planet, every angle, every speed but Manual */
:is(.st-key-sci_bodies, .st-key-globe_bodies, .st-key-globe_paths, .st-key-space_bodies, .st-key-space_paths, .st-key-helio_bodies, .st-key-helio_paths,
    [class*="dec_on_v2"], .st-key-dist_on_v2) button,
:is(.st-key-globe_major, .st-key-globe_minor, .st-key-asp_major, .st-key-asp_minor, .st-key-sci_major, .st-key-sci_minor, [class*="ea_on_v5"], [class*="minor_on_v1"]) button,
:is(.st-key-helio_speed, .st-key-space_speed, .st-key-globe_speed) button:not(:first-child), .st-key-sci_speed button
  { border-radius: 50% !important; width: 24px !important; min-width: 24px !important; height: 24px !important; min-height: 24px !important;
    padding: 0 !important; justify-content: center !important; flex: 0 0 auto !important; }
/* angles and speeds in a smaller type, so that 120 and 1mo fit the same circle as 0 and 1s */
.stApp :is(.st-key-globe_major, .st-key-globe_minor, .st-key-asp_major, .st-key-asp_minor, .st-key-sci_major, .st-key-sci_minor, [class*="ea_on_v5"], [class*="minor_on_v1"]) button :is(p, span, div),
.stApp :is(.st-key-helio_speed, .st-key-space_speed, .st-key-globe_speed) button:not(:first-child) :is(p, span, div), .stApp .st-key-sci_speed button :is(p, span, div)
  { font-size: 10px !important; }
/* every action button (Insert, Commit, Delete, Yes, Sign out ..): the same small pill */
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
    const want = z * main.clientWidth / (WIDTH + pad);
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
location.visitor_location()                                   # where they are: looked up once per visit, before any Logins row is written
# what they may use, by their customer record(s)' Access (an admin: everything)
_MINE = [] if user.is_admin else db.customers_for(user.email).to_dict("records")   # their records (all share their email)
GRANT = (access.Grant(admin=True, dob=True, many=True) if user.is_admin
         else access.grant(_MINE, datetime.now(timezone.utc).replace(tzinfo=None)))
OWN_ID = access.own_record_id(_MINE)                          # their own record (the others: people added under their login)


# ---------------------------------------------------------------- who can see which customers
def visible_customers() -> pd.DataFrame:
    """An admin: every customer. A member: with Group (or TrGrp running), every record under their login; else their own."""
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
    "AstroClock-3D": "Time, with Now and DOB below it: which moments to show. The Earth inside the celestial sphere, its axis tilted 23.44 degrees and joining the North and South Celestial Poles (NCP, SCP); ECE and WCE are East and West on the Celestial Equator. "
                  "Rotate in 1s: the Earth turns about that fixed axis, west to east, while the sphere stands still, and time "
                  "runs from each moment, until it is turned off: the clock beside the name gives the date and time, and the Sun, "
                  "Moon and planets move over the sphere as they really did (time starts again after 72 years; refresh the page to go back "
                  "to the start). Below it, Manual: the Earth, the celestial sphere, House, RA, Dec, Lati and Long are frozen together; drag the chart sideways to turn them as one unit and see the other side of the AstroClock-3D. Or pick a speed to start, how much time passes each second: 1s a second, 1m a minute, 1h an hour, 1d a day, 1w a week, 1mo a month, 1y a year; with none picked it holds still. The Earth starts as it was at that "
                  "moment, so a planet is straight above the place it was overhead. Each planet is on the sphere at its RA and Declination, with its symbol inside its marker (☉ Su, ☽ Mo, ☿ Me, ♀ Ve, ♂ Ma, ♃ Ju, ♄ Sa), sized as the Size_Clock-3D column of Symbols says, usually by how big it looks from the Earth then (a "
                  "logarithmic scale, as to true scale the planets would not show; point at one for its Dec/Lati, RA, Angular Size, Distance from earth and the others approaching and leaving it in Dec/Lati; at CB or CN for its Long, Dec/Lati, RA and the planets approaching and leaving its Dec/Lati). The far side of the sphere is "
                  "fainter, and hidden behind the Earth. Planets, picking from the list below it: which of the Sun, Moon and planets to show, with their RA and Dec lines, and the Moon's north and south nodes (NN, SN), where its path crosses the Sun's, drawn with their symbols (☊ and ☋; point at one for its details). Major Aspects (0, 60, 90, 120, 180; black) and Minor Aspects (30, 45, 72, 135, 144, 150; grey): pick the angles to draw a line between any two planets or nodes shown (not NN with SN) that are in that aspect, by the orbs in Aspect Rules, as time runs; dotted for DOB, each with its tag, as 0-Ma-Ju, along it where there is room, or beside it when the two are too close (point at a line for its name). Coordinates, with House, Celes, RA, Dec, Lati and Long below it: which lines to show. Celes: the axis with the names NCP and SCP and the dots at the poles, and the celestial equator with the names WCE and ECE. House: twelve lines on the sphere, 30 degrees apart from the RA of CB (dashed) and of CN (solid), named H01 to H12, turning with the Earth, with each line's RA at its lower right (on the near side, where there is room). RA, Dec: the RA lines and the Dec lines of each planet, and of NN and SN, on the sphere, and "
                  "of CB and CN on the Earth. Lati, Long: the Earth's lines of latitude and of longitude, every 30 degrees, turning with it. Planet Path, picking from the list below it: a trail behind each body picked, drawn only while time runs, "
                  "where it has really been since time started running (none while it stands still; each start begins new ones; up to 72 years). DOB: at birth, hollow, dashed lines, with CB, a baby, at the birth place. Now: the planets "
                  "now, solid lines, with CN, a house, at the place now.",
    "Geo/Helio Model": "Centric Model: Geo, GeoCentric, the Earth at the centre, or Helio, HelioCentric, the Sun at the centre; each keeps its own choices on the other buttons. "
                  "GeoCentric: the paths of the Sun, Moon and planets around the Earth (Ea), each at its own distance from the Earth (on AstroClock-3D all are on one sphere). "
                  "Each point is placed by its RA, Dec and distance. North is up, the axis from NCP to SCP tilted 23.44 degrees on the page, with everything else leaning with it. AU: all the tags, NCP, SCP and the RA names, and rings on the plane of the Earth's equator, each with its distance from the Earth in AU, out to 20 AU (1 AU is about the Sun's distance); off, the drawing has no tags. "
                  "Rotate in 1s: Manual: time stands still, and dragging the drawing turns it, what is behind being fainter. Or pick a speed, how much time passes each second: 1s a second, 1m a minute, 1h an hour, 1d a day, 1w a week, 1mo a month, 1y a year: the clock beside the name gives the date and time, and the Sun, Moon and planets move as they really did, nearer and farther, the Moon's path going with it (time starts again after 72 years; refresh the page to go back to the start). With none picked it holds still. Each has its symbol inside its marker (☉ Su, ☽ Mo, ☿ Me, ♀ Ve, ♂ Ma, ♃ Ju, ♄ Sa, ⊕ Ea). Sizes follow the Size_Geo column of Symbols: usually a planet by how big it looks from the Earth at that moment (a logarithmic scale, as to true scale the planets would not show), so it grows as it comes nearer, and the Earth as its Size says (Tiny, a dot, when it says nothing readable; to true scale it would be far smaller still). Point at a planet for its Dec/Lati, RA, Angular Size and distance, or at a path for its span and distances. "
                  "Planet Path: which of the planets shown have their paths drawn. Time: DOB is hollow with dashed paths, Now solid; each path is a trail behind its planet, drawn only while time runs: where it has really been since time started running, kept for up to 72 years, when time starts again (a trail over many years is drawn with fewer points). With time standing still there are no trails, and each start begins new ones. "
                  "Coordinates: Fit, True and AU below it. On Fit each tenfold distance takes the same room, so the Moon's path and Saturn's can be seen together, and the empty space between the Moon's path and the planets' is taken out (it alone is not to scale); True is to scale, where the Moon's path is too small to tell from the Earth (pick Mo alone to see it). A label with no room is left off: point at its mark. "
                    "HelioCentric: as GeoCentric, with the Sun (Su) at the centre: the paths of the planets and the Earth (Ea) around the Sun, each at its own distance from the Sun, "
                    "placed by its RA, Dec and distance as seen from the Sun, on the same frame as from the Earth (the plane of the Earth's equator, north up). The Moon (Mo) goes round the Earth: seen from the Sun it is where the Earth is, so it is drawn close round the Earth's mark (a dot when its Size_Helio is Tiny, as it starts), farther out than to scale, in its real direction from the Earth and nearer and farther with its real distance (its path loops round the Earth's). "
                    "AU: all the tags, NCP, SCP and the RA names, and rings on the plane of the Earth's equator, each with its distance from the Sun in AU (1 AU is about the Earth's distance; on Fit 0.5, 1, 2.5, 5, 10 and 20 AU, on True 1, 2.5, 5, 10 and 20 AU, nearer ones being inside the Sun's mark there); off, the drawing has no tags. "
                    "Rotate in 1s: Manual: time stands still, and dragging the drawing turns it, what is behind being fainter. Or pick a speed, how much time passes each second (1s, 1m, 1h, 1d, 1w, 1mo, 1y): the clock beside the name gives the date and time, and the planets and the Earth move round the Sun as they really did (time starts again after 72 years; refresh the page to go back to the start). With none picked it holds still. "
                    "Each has its symbol inside its marker (☿ Me, ♀ Ve, ⊕ Ea, ☽ Mo, ♂ Ma, ♃ Ju, ♄ Sa, ☉ Su). Sizes follow the Size_Helio column of Symbols: usually a planet by how big it looks from the Earth at that moment (a logarithmic scale), the Sun and the Earth as their Sizes say. Point at a planet for its Dec/Lati, RA, Angular Size and distance from the Sun, or at a path for its span and distances. "
                    "Planet Path: which of the planets shown have their paths drawn. Time: DOB is hollow with dashed paths, Now solid; each path is a trail behind its planet, drawn only while time runs, kept for up to 72 years (with time standing still there are no trails, and each start begins new ones). "
                    "Coordinates: Fit, True and AU below it. On Fit each tenfold distance takes the same room, so Mercury's path and Saturn's can be seen together; True is to scale. A label with no room is left off: point at its mark.",
    "Aspects": "The aspects between the chosen planets, and the Moon's nodes (NN, SN; by their own orbs in Aspect Rules, ☊ and ☋, the larger of the pair's as for two planets; never with each other), over the period, as tables, newest first: one table per "
               "angle, a row each time two planets came into it (RA within the orb of the angle, and the two Declinations "
               "within the same orb of equal or mirrored). Major Aspects: on or off, with the angles 0, 60, 90, 120, 180 to pick from below it. Minor Aspects: "
               "the same, with 30, 45, 72, 135, 144, 150. Dates and times are UT.",
    "Planets Cycles": "Each chosen planet's Declination (-M lines) over the period, with dots and tags where two of "
                      "them are in a chosen major or minor aspect. A tag with no room is left off: point at "
                      "its dot to see it. Dates and times are UT.",
    "AstroClock-2D": "Left of the clock, Dec: each planet's Declination on a scale from +31 to -31 degrees, moving as time runs, all on lines of one length, so that planets at the same Declination overlap (point at one for its value). Right of the clock, a Distance(%) graph the same way, from 0 (nearest) to 100 (farthest): the planets at DOB and at Now to the left of its line, and at Ave (the average of the two, moving as time runs) to the right. Major Aspects and Minor Aspects: the angles to draw; two planets at the same time in one of them, by the orbs in Aspect Rules, are joined by a line tagged as 0-Ma-Ju. Rotate in 1s: pick a speed for time to run; with none picked it stands still, and dragging the drawing moves it by hand: right is later, left is back, as far as where it started, 6 hours a pixel.",
    "Planets Distance(%)": "Each chosen planet's distance from the Earth (-D lines) over the period, as D: the % "
                           "between its nearest (0) and farthest (100) over 1800 to 2400. Dates and times are UT.",
    "Logins": "The Logins table, newest first: who (Email, the signed-in login) did what (Activity) and when (Date_Time, "
              "UT). View: opened a customer's charts (once per customer per visit). Create, Update, Delete: added, changed or "
              "deleted a customer (on Customers, by import, or their own My details), a row per customer. Login: signed in with "
              "no birth details yet, seeing the Now charts only (once per visit). Seen by admins only; "
              "click a column name to sort. To delete rows, tick them in the Del column and press Delete, or press Delete all; "
              "either asks first, and a deleted row cannot be brought back.",
    "Defaults": "The Defaults table: what each page's inputs start as. A row per input: its Page, its Options and its "
                "Choices. Buttons: the ones on, comma-separated, by name, SAbr or symbol (e.g. Ju, Sa; 0, 180; Manual), "
                "blank for none; one on / off button (AU): On or Off. Start Date (UT): DOB or Now. End Date (UT): Now, or "
                "Start Date (UT) + a time, e.g. 5 days, 2 years 6 months (years, months, weeks, days), which moves with the "
                "Start. Commit checks each row against the page's input. An input with no row starts as the app's own default. "
                "Rows are sorted by Page, Options, Choices; click a column name to sort by it. Changes apply when a page is next opened (a button already changed this visit keeps its choice). Seen by admins "
                "only, who can Insert, Update, Delete and Commit rows.",
    "Symbols": "The Symbols table: the short name (SAbr), symbol (Symb), long name (SDesc) and colour (RGB, and its name, Color) of each planet, the Earth (Ea), the Moon's nodes (NN, SN), the place now (CN) and the birth place (CB). Seen by admins only, who can "
               "use Insert for a new row, type changes in the table and press Update, tick Del and press Delete; nothing is saved until Commit. Click a column name to sort. SAbr is unique, and stays once a row is in the table. Symb is what the pages show in place of its SAbr, the SAbr itself when blank. On AstroClock-2D, AstroClock-3D and Geo/Helio Model the conventional symbols are drawn, in the row's RGB colour; anything else is shown as typed, an emoji such as the baby in its own colours. RGB is rgb(r,g,b) or #rrggbb; Color is its name in words, for reference, and may be blank. Size_Clock-3D says how AstroClock-3D draws the Sun, Moon, planets, Ea, the nodes NN and SN and the places CB and CN: Angular Size, by how big it looks from the Earth; Tiny, a dot with no symbol; Small, 9 pixels; a number, its radius in pixels; Bigger than, Smaller than or Same as another, by its SAbr or SDesc (Bigger than Moon); blank, as usual (a planet by its angular size, Ea a dot, the nodes and places 9 pixels). Size_Clock-2D says the same for AstroClock-2D, its Dec and Distance(%) graphs (it starts as Size_Geo), Size_Geo for Geo/Helio Model's Geo, and Size_Helio for its Helio (it starts as Size_Geo, with the Moon Tiny). The charts take the colours from here: a planet's marker, RA and Dec lines and path; Ea's mark and name on Geo/Helio Model's Geo; NN's and SN's symbol; CN's and CB's mark, name, RA and Dec lines. The Ea, NN, SN, CN and CB rows come back if deleted.",
    "Aspect Rules": "The orbs: for each aspect and planet, how far from exact still counts as the aspect, the same "
                       "for RA and for Declination. A pair of planets uses the larger of their two orbs. A new row's Angle, "
                       "if left blank, comes from its Aspect's name, one of Conjunction, Opposition, Square, Trine, Sextile, Semi-sextile, Semi-square, Quintile, "
                       "Sesquiquadrate, Bi-quintile, Quincunx. Changes here "
                       "apply to every chart.",
    "Customers": "Insert for a new customer, type changes and press Update, tick Del and press Delete; nothing is saved until Commit. Click a column name to sort. ID is the record's number, and Created and Last_Updated (UT) when it was added and last changed, all set by the app. Required (*): Email (login), First Name, "
                 "Last Name, Country, State, City, the birth date and time (Year, Mon, Date, Hr24, Min), and where they "
                 "live now (Country-N, State-N, City-N). "
                 "Email (login) is the Google account each customer signs in with (one customer per email; they see "
                 "only their own). Other and Other-N: anything else to keep about the birth place and the place now "
                 "(not used in the charts). The UTC offset is looked up from the birth place and date. Import adds customers from the workbook's Customers CSV.",
    "My details": "Your own birth details, used for the DOB charts (without them, the Now charts only). Edit my details to change them; your login "
                  "email stays the same.",
}


def top_line(title: str, row: pd.Series | None):
    """Every page's top line: its title (with its help), then the chosen customer's First and Last Name."""
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
        f'<span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{html.escape(name)}</span>'
        + ('<span class="globe-clock" style="white-space:pre"></span>' if title in ("AstroClock-2D", "AstroClock-3D", "Geo/Helio Model") else "") +   # its script writes it
        f'</div>')
    # the slot fills the rest of the line
    TITLE_SLOT = line.container(width="stretch", horizontal=True, gap="small")


TITLE_SLOT = None                                             # set by top_line for the page being shown


PLACE_SEARCH_DOWN = "The place search is not answering just now. Please try again in a few minutes."


def _pick_customer() -> tuple[pd.Series | None, Prepared | None]:
    df = visible_customers()
    st.sidebar.markdown(f"**{user.name}**" + ("  \n:blue-badge[admin]" if user.is_admin else ""))
    auth.sign_out_button(user)
    locked_note = st.session_state.pop("_dob_locked", None)   # they picked DOB, which is not open to them: why
    if locked_note:
        st.toast(locked_note if isinstance(locked_note, str) else access.PAID_NOTE)
    if df.empty:
        if user.is_admin:                                     # (anyone signed in sees the Now charts)
            st.sidebar.info("No customers yet.")
            return None, Prepared(True, "Add a customer on the Customers page for the DOB charts.", now_only=True, locked=True)
        # a new member: no form to fill in, a Login row (once per visit), and the Now charts (birth details can be added in
        # My details, for the DOB ones)
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
    if GRANT.many:                                            # unlimited access (and admins): a birth typed in, not saved
        label[access.QUICK] = "+ Quick birth (not saved)"
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
        prep = Prepared(True, access.PAID_NOTE, now_only=True, locked=True,   # at the place they live now
                        cn=prep.cn if prep.ok else None, cn_tz=prep.cn_tz if prep.ok else None)
        st.sidebar.caption(GRANT.note)
    elif not prep.ok:                                         # birth details that cannot be worked out: the Now charts still
        st.sidebar.error(prep.message)
        prep = Prepared(True, prep.message + (" Fix it on the Customers page." if user.is_admin else " Fix it in My details."),
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
        db.log_view(user.email)
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
    """A birth typed in the sidebar, not saved: its DOB charts, with the place now of base (their own record)."""
    box = st.sidebar.container(border=True)
    born = box.date_input("Birth date", value=None, min_value=datetime(1800, 1, 1).date(), max_value=datetime(2399, 12, 31).date(),
                          format="YYYY-MM-DD", key="quick_date")
    at_txt = box.text_input("Birth time (local, 24 h)", placeholder="hh:mm", max_chars=5, key="quick_time")
    city = box.text_input("City", key="quick_city")
    state = box.text_input("State/Region", key="quick_state")
    country = box.text_input("Country", key="quick_country")
    row = pd.Series({**base.to_dict(), "id": access.QUICK, "name": "Quick birth", "last_name": "", "other": None,
                     "utc": None, "city": city.strip(), "state": state.strip(), "country": country.strip()})
    try:
        at = birth_time(at_txt)
    except ValueError:
        return row, Prepared(False, "Quick birth: type the birth time as hh:mm in 24 hours, e.g. 14:30.")
    if born is None or at is None or not all(v.strip() for v in (city, state, country)):
        box.caption("Type a birth date, time and place to see its DOB charts. Nothing is saved.")
        return row, Prepared(False, "Quick birth: type a birth date, time and place in the sidebar.")
    row = pd.Series({**row.to_dict(), "year": born.year, "mon": born.month, "day": born.day, "hr": at.hour, "mn": at.minute})
    try:
        prep = prepare(record_items(row))
    except places.LookupDown:
        return row, Prepared(False, PLACE_SEARCH_DOWN)
    if prep.ok:
        box.caption(f"{born} {prep.weekday} {at:%H:%M}, UTC {prep.utc:+.2f} ({prep.birth_lat}, {prep.birth_lon}). Not saved.")
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
    buttons are drawn) and the form opens on My details; once saved, they come back to this page. One whose Access does
    not open the DOB charts is told so instead."""
    if not picked:
        return
    for k, v in keys_reset:
        st.session_state[k] = v
    if _chosen[1] is not None and _chosen[1].locked:
        st.session_state["_dob_locked"] = _chosen[1].message or access.PAID_NOTE
        st.rerun()
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
        plan = None
        if row is None and not person:                        # signing up: which free 1-day trial (TrInd or TrGrp)
            st.markdown("**Access** (a free 1-day trial; after it, the admin can keep it for you)")
            plan = st.radio("Access", ["Individual", "Group"], horizontal=True, label_visibility="collapsed", key="signup_plan",
                            captions=["Your own DOB and Now charts", "Your DOB and Now charts, people you add, and quick births"])
        sent = st.form_submit_button("Save person" if person else "Save my details" if row is None else "Save changes",
                                     type="primary")
    if not sent:
        return
    try:
        at = birth_time(at_txt)
    except ValueError:
        st.error("Birth time: type it as hh:mm in 24 hours, e.g. 14:30 or 09:05.")
        return
    missing = [n for n, v in (("First Name", first), ("Last Name", last), ("Birth date", born), ("Birth time", at),
                              ("City", city), ("State/Region", state), ("Country", country),
                              ("City (now)", city_n), ("State/Region (now)", state_n), ("Country (now)", country_n))
               if not (v.strip() if isinstance(v, str) else v)]
    if missing:
        st.error("Please fill in: " + ", ".join(missing) + ".")
        return
    try:
        born_at = locate_cached(city.strip(), state.strip(), country.strip())
        lives_at = locate_cached(city_n.strip(), state_n.strip(), country_n.strip())
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
    if person:
        st.session_state["_select_customer"] = db.add_person(rec, user.email)   # shown in the sidebar at once
        st.session_state["person_added"] = f"{first} {last} is added: chosen in the sidebar."
    elif row is None:
        db.add_own_customer(rec, user.email, group=plan == "Group")   # an email that already has a record keeps it (nothing is changed)
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
SPEED_CHOICES = [globechart.MANUAL] + list(globechart.SPEEDS)
FLAT_SPEED_CHOICES = list(globechart.SPEEDS)                  # AstroClock-2D's: no Manual (with none picked time stands still)
GLOBE_MAJOR = [str(a) for a in sorted(core.MAJOR)]
GLOBE_MINOR = [str(a) for a in core.MINOR]
START, END = "start", "end"                                   # the two date inputs (not buttons)


def default_inputs() -> dict[tuple[str, str], tuple]:
    """Every page input the Defaults table can set, by (Page, Options): (its choices, or START / END; more than one may be
    picked; the app's own default, used when the table has no row for it)."""
    globe = list(globechart.BODY_CHOICES) + list(globechart.NODE_CHOICES)
    out = {("AstroClock-2D", "Time"): (["Now", "DOB"], True, ["Now"]),
           ("AstroClock-2D", "Planets"): (globe, True, globe),
           ("AstroClock-2D", "Major Aspects"): (GLOBE_MAJOR, True, []),
           ("AstroClock-2D", "Minor Aspects"): (GLOBE_MINOR, True, []),
           ("AstroClock-2D", "Houses"): (["Houses"], False, "Houses"),
           ("AstroClock-2D", "Rotate in 1s"): (FLAT_SPEED_CHOICES, False, None),
           ("AstroClock-3D", "Time"): (["Now", "DOB"], True, ["Now"]),
           ("AstroClock-3D", "Planets"): (globe, True, globe),
           ("AstroClock-3D", "Planet Path"): (globe, True, ["Su"]),
           ("AstroClock-3D", "Major Aspects"): (GLOBE_MAJOR, True, []),
           ("AstroClock-3D", "Minor Aspects"): (GLOBE_MINOR, True, []),
           ("AstroClock-3D", "Coordinates"): (["House", "Celes", "RA", "Dec", "Lati", "Long"], True, ["Celes"]),
           ("AstroClock-3D", "Rotate in 1s"): (SPEED_CHOICES, False, globechart.MANUAL),
           ("Geo/Helio Model", "Centric Model"): (["Geo", "Helio"], False, "Geo")}
    for model, bodies in (("Geo", globechart.BODY_CHOICES), ("Helio", space3d.HELIO_BODIES)):
        out |= {("Geo/Helio Model", f"{model} Time"): (["Now", "DOB"], True, ["Now"]),
                ("Geo/Helio Model", f"{model} Planets"): (list(bodies), True, list(bodies)),
                ("Geo/Helio Model", f"{model} Planet Path"): (list(bodies), True, list(bodies)),
                ("Geo/Helio Model", f"{model} Coordinates"): (list(space3d.SCALES), False, space3d.FIT),
                ("Geo/Helio Model", f"{model} AU"): (["AU"], False, "AU"),
                ("Geo/Helio Model", f"{model} Rotate in 1s"): (SPEED_CHOICES, False, globechart.MANUAL)}
    for page, end, planets in (("Aspects", (0, 5), core.BUTTON_ORDER + ["NN", "SN"]), ("Planets Cycles", (360, 0), core.BUTTON_ORDER),
                               ("Planets Distance(%)", (24, 0), core.BUTTON_ORDER)):
        out |= {(page, "Start Date (UT)"): (START, False, "DOB"), (page, "End Date (UT)"): (END, False, end),
                (page, "Planets"): (list(planets), True, ["Sa", "Ju"])}
    out[("Aspects", "Aspects")] = (["Major Aspects", "Minor Aspects"], True, ["Major Aspects", "Minor Aspects"])
    out[("Aspects", "Major Aspects")] = (GLOBE_MAJOR, True, GLOBE_MAJOR)
    out[("Aspects", "Minor Aspects")] = (GLOBE_MINOR, True, GLOBE_MINOR)
    out[("Planets Cycles", "Major Aspects")] = ([str(a) for a in rangechart.EA_NAME], True, ["0", "180"])
    out[("Planets Cycles", "Minor Aspects")] = (GLOBE_MINOR, True, [])
    return out


def _word(text: str) -> str:
    """A choice as typed, to compare: lower case, without spaces, degree signs or the text-style mark of a symbol."""
    return "".join(ch for ch in str(text).lower() if ch not in " °\ufe0e\ufe0f")


def read_options(choices, multi: bool, text: str):
    """The Defaults table's Choices text as the input's start: (value, what was not understood). Buttons: the choices named
    (by name, SAbr, symbol or planet name, any case, comma-separated; for one on / off button On or Off). Start: DOB or Now.
    End: Now, or Start Date (UT) + a time such as 5 days, 2 years 6 months, 30 years (years, months, weeks, days)."""
    text = (text or "").strip()
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
    """What this input starts as: the Defaults table's Choices for it, read as read_options says; with no row, or Choices it
    cannot read, the app's own default."""
    choices, multi, own = default_inputs()[(page, title)]
    text = DEFAULT_TEXTS.get((page.lower(), title.lower()))
    if text is None:
        return own
    value, wrong = read_options(choices, multi, text)
    return own if wrong else value


def options_problems(rows: pd.DataFrame) -> list[str]:
    """The Defaults rows whose Page and Options are no input of the app, or whose Choices it cannot read."""
    inputs = {(p.lower(), t.lower()): (p, t, spec) for (p, t), spec in default_inputs().items()}
    out = []
    for _, r in rows.iterrows():
        page, title = db._cell(r["Page"]), db._cell(r["Options"])
        if not (page and title):
            continue                                          # (said by db.defaults_problems)
        known = inputs.get((page.lower(), title.lower()))
        if known is None:
            out.append(f"{page} / {title}: no page has that input")
            continue
        choices, multi, _ = known[2]
        _, wrong = read_options(choices, multi, db._cell(r["Choices"]))
        if wrong:
            if choices == START:
                hint = "DOB or Now"
            elif choices == END:
                hint = "Now, or Start Date (UT) + a time such as 5 days or 2 years 6 months"
            else:
                hint = ("one of " if not multi else "any of ") + ", ".join(choices) + (" (or On / Off)" if len(choices) == 1 else "")
            one = "only one can be picked"
            said = ", ".join(w for w in wrong if w != one)
            out.append(f"{page} / {title}: " + (f"Choices '{said}' not understood: {hint}" if said else f"pick {hint}"))
    return out


# ---------------------------------------------------------------- pages
def add_months(when: datetime, months: int) -> datetime:
    """That many calendar months later, on the same day of the month (or the month's last day, if it has fewer days)."""
    y, m = divmod(when.month - 1 + months, 12)
    year, month = when.year + y, m + 1
    last = (datetime(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return when.replace(year=year, month=month, day=min(when.day, last))


def period(prep: Prepared, row=None, page: str = "") -> tuple[float, float] | None:
    """The Start / End inputs (UT) as Julian days, or None (with a warning) if unusable. They start as the Defaults table
    says for this page (Start: DOB or Now; End: Now, or Start Date (UT) + a time, which moves with the Start).
    With row (a horizontal container) they go into it, each just wide enough; otherwise in four columns."""
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    birth_dt = core.jd_to_datetime(prep.jd_birth) if prep.jd_birth is not None else now_dt   # (Now charts only: from now)
    c = [row] * 4 if row is not None else st.columns(4)
    dw, tw = (125, 80) if row is not None else ("stretch", "stretch")
    start0 = now_dt if default_choice(page, "Start Date (UT)") == "Now" else birth_dt
    start0 = min(max(start0, datetime(1800, 1, 1)), datetime(2399, 12, 31))   # (the dates allowed)
    d0 = c[0].date_input("Start Date (UT)", value=start0.date(), min_value=datetime(1800, 1, 1),
                         max_value=datetime(2399, 12, 31), width=dw, key=f"start_date_{page}_{prep.jd_birth}_{start0.date()}")
    t0 = c[1].time_input("Time (UT)", key=f"start_time_{page}_{prep.jd_birth}_{start0 is now_dt}",
                         value=time(start0.hour, start0.minute), width=tw)
    after = default_choice(page, "End Date (UT)")             # (months, days) after the Start, or "Now"
    if after != "Now":                                        # the End follows the Start: a changed Start sets it again
        end_dt = add_months(datetime.combine(d0, t0), after[0]) + timedelta(days=after[1])
        end_dt = min(end_dt, datetime(2399, 12, 31, 23, 59))   # (the last date allowed)
        d1 = c[2].date_input("End Date (UT)", value=end_dt.date(), min_value=datetime(1800, 1, 1),
                             max_value=datetime(2399, 12, 31), width=dw, key=f"end_date_{page}_{d0}_{t0}_{after}")
        t1 = c[3].time_input("Time (UT)", key=f"end_time_{page}_{d0}_{t0}_{after}", value=end_dt.time(), width=tw)
    else:
        d1 = c[2].date_input("End Date (UT)", value=now_dt.date(), min_value=datetime(1800, 1, 1),
                             max_value=datetime(2399, 12, 31), width=dw)
        t1 = c[3].time_input("Time (UT)", key=f"end_time_{now_dt.date()}", value=time(now_dt.hour, now_dt.minute), width=tw)
    start, end = datetime.combine(d0, t0), datetime.combine(d1, t1)
    if end <= start:
        st.warning("The end must be after the start.")
        return None
    if (end - start).days > 100 * 366:
        st.warning("That period is too long - choose about 100 years at most.")
        return None
    return core.jd_of_datetime(start), core.jd_of_datetime(end)


def cycles_inputs(keys: str, aspect_buttons: bool = True, nodes: bool = False, page: str = "Planets Cycles"):
    """The inputs of Planets Cycles (and Aspects, which shares them; keys keeps each page's buttons
    apart): (period as Julian days, planets, major angles, minor angles), or None when there is nothing to show yet.
    Planets Cycles has a button per major and per minor angle; Aspects (aspect_buttons False) has a Major Aspects and a
    Minor Aspects on / off button instead, each with its angles to pick from below it. nodes: NN and SN
    buttons too (Aspects)."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return None
    jds = period(prep, head, page)
    # on / off buttons, as on Distance: every choice always in view
    choices = core.BUTTON_ORDER + (["NN", "SN"] if nodes else [])
    dec_on = core.in_order(titled(head, "Planets", f"{keys}t_planets", core.shown_order(choices), f"{keys}dec_on_v2", default_choice(page, "Planets"),
                                  selection_mode="multi", format_func=core.symbol_of), choices)
    ea_names = {str(a): a for a in rangechart.EA_NAME}         # the buttons 0, 60, 90, 120, 180 -> their angles
    minor = []
    if aspect_buttons:
        ea = core.in_order(titled(head, "Major Aspects", f"{keys}t_major", list(ea_names), f"{keys}ea_on_v5", default_choice(page, "Major Aspects"),
                                  selection_mode="multi"), list(ea_names))
        minor = [int(a) for a in core.in_order(titled(head, "Minor Aspects", f"{keys}t_minor", GLOBE_MINOR, f"{keys}minor_on_v1",
                                                      default_choice(page, "Minor Aspects"), selection_mode="multi"), GLOBE_MINOR)]
    else:                                                     # an on / off button for each group, with its angles below it
        groups = default_choice(page, "Aspects")

        def group(title: str, key: str, names: list) -> list:
            box = head.container(width="content", gap="xxsmall")
            if not box.pills(title, [title], default=title if title in groups else None, key=f"{keys}{key}_on", label_visibility="collapsed"):
                return []
            return core.in_order(box.pills(f"Which {title}", names, selection_mode="multi", default=default_choice(page, title),
                                           key=f"{keys}{key}", label_visibility="collapsed", width=len(names) * 33), names)   # all on one line

        ea = group("Major Aspects", "major", GLOBE_MAJOR)
        minor = [int(a) for a in group("Minor Aspects", "minor", GLOBE_MINOR)]
    if jds is None:
        return None
    return jds, dec_on, [ea_names[e] for e in ea], minor


def page_astroclock():
    """AstroClock-2D: the top page of the menu, for everyone: the Geo drawing in 2D, seen from above the north celestial
    pole, with only the 12 AU circle and an RA scale round it, 1 to 360, always on the Fit scale, an arrow from the Earth through each body out to the circle, and the twelve house lines of CB and CN (the Houses button under Coordinates, on to start). Its buttons, Time, Planets
    (with NN, SN: on the Moon's path, at the Moon's distance, joined by a line, 180 degrees apart) and Rotate in 1s (how fast time runs; none picked: it stands still, and dragging the drawing sideways moves it),
    are its own, and start as the Defaults table says."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="small")
    if not need_chart(prep):
        return
    space_page(head, prep, "sci", "Ea", globechart.BODY_CHOICES + globechart.NODE_CHOICES, model="Geo", flat=True)


def page_globe():
    """The Earth turning inside the celestial sphere: the planets and their RA and Dec lines on the sphere, CB, CN on it."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="top", gap="small")
    if not need_chart(prep):
        return

    def stacked(names: tuple, default: tuple, title: str | None = None) -> list:
        """Buttons one below another; those on. Under a title button, shown only with that on."""
        box = head.container(width="content", gap="xxsmall")
        if title and not box.pills(title, [title], default=title, key=f"globe_{title}_on", label_visibility="collapsed"):
            return []
        return [n for n in names if box.pills(n, [n], default=n if n in default else None, key=f"globe_{n}",
                                              label_visibility="collapsed")]

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
        dob_asked(bool(st.session_state.get("globe_DOB")), ("globe_DOB", None))
        shown = stacked(("Now", "DOB"), ("Now",), title="Time")
    else:
        shown = stacked(("Now", "DOB"), default_choice("AstroClock-3D", "Time"), title="Time")
    all_bodies = list(globechart.BODY_CHOICES)
    with_nodes = all_bodies + list(globechart.NODE_CHOICES)   # shown three a line: Mo Su Me, Ve Ma Ju, Sa NN SN
    bodies = options_under("Planets", "bodies", with_nodes, default_choice("AstroClock-3D", "Planets"), width=112)
    paths = options_under("Planet Path", "paths", with_nodes, default_choice("AstroClock-3D", "Planet Path"), width=112)
    major = options_under("Major Aspects", "major", GLOBE_MAJOR, default_choice("AstroClock-3D", "Major Aspects"), width=90)
    minor = options_under("Minor Aspects", "minor", GLOBE_MINOR, default_choice("AstroClock-3D", "Minor Aspects"), width=90)
    coords_on = default_choice("AstroClock-3D", "Coordinates")
    coords = head.container(width="content", gap="xxsmall")   # Coordinates, with its options below it in fixed rows
    if coords.pills("Coordinates", ["Coordinates"], default="Coordinates", key="globe_coords_on", label_visibility="collapsed"):
        for row_of in (["House", "Celes"], ["RA", "Dec"], ["Lati", "Long"]):
            shown += coords.pills(f"Coordinates {row_of[0]}", row_of, selection_mode="multi", default=[n for n in row_of if n in coords_on],
                                  key=f"globe_coords_{row_of[0]}", label_visibility="collapsed")
    spin = head.container(width="content", gap="xxsmall")     # Rotate, with how fast below it
    day_seconds, manual = None, False
    if spin.pills("Rotate in 1s", ["Rotate in 1s"], default="Rotate in 1s", key="globe_rotate", label_visibility="collapsed"):
        speed = spin.pills("Rotate speed", SPEED_CHOICES, default=default_choice("AstroClock-3D", "Rotate in 1s"), key="globe_speed",
                           label_visibility="collapsed", width=96)   # (Manual, 1s on a line; 1m, 1h, 1d on the next; then 1w, 1mo, 1y)
        manual = speed == globechart.MANUAL                           # the Earth is dragged round by hand
        day_seconds = globechart.SPEEDS.get(speed)                    # nothing picked: it holds still
    jd_now = core.now_jd()
    now_pts, _ = now_values(jd_now)
    utc_now = datetime.now(ZoneInfo(prep.cn_tz)).utcoffset().total_seconds() / 3600.0 if prep.cn_tz else None
    g = globechart.GlobeInput(
        birth=prep.birth, now=now_pts, jd_birth=prep.jd_birth, jd_now=jd_now,
        cb=None if prep.now_only else (prep.birth_lat, prep.birth_lon), cn=prep.cn, show_birth="DOB" in shown, show_now="Now" in shown,
        show_ra="RA" in shown, show_dec="Dec" in shown, show_latitude="Lati" in shown,
        show_longitude="Long" in shown, show_celes="Celes" in shown, show_houses="House" in shown, bodies=bodies, paths=paths,
        aspects=tuple(int(a) for a in major + minor), orbs=orbs(),
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
    model = (titled(head, "Centric Model", "t_centric", list(CENTRIC_MODELS), "centric_model", default_choice("Geo/Helio Model", "Centric Model"))
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


def space_page(head, prep, key: str, centre: str, choices: tuple, model: str = "Geo", flat: bool = False):
    """GeoCentric (centre Ea) or HelioCentric (centre Su): its buttons each keep their own choice (key), also while the other
    model is shown; they start as the Defaults table says (Geo Time .. Helio Rotate in 1s)."""
    def start(title: str):
        return default_choice("AstroClock-2D", title) if flat else default_choice("Geo/Helio Model", f"{model} {title}")
    if prep.now_only:                                         # no birth details: Now, and DOB opens the form for them
        dob_asked("DOB" in (st.session_state.get(f"{key}_time") or []), (f"{key}_time", ["Now"]), (f"_kept_{key}_time", ["Now"]))
        shown = titled(head, "Time", f"{key}_t_time", ["Now", "DOB"], f"{key}_time", ["Now"], selection_mode="multi") or []
    else:
        shown = titled(head, "Time", f"{key}_t_time", ["Now", "DOB"], f"{key}_time", start("Time"), selection_mode="multi") or []
    bodies = core.in_order(titled(head, "Planets", f"{key}_t_bodies", core.shown_order(choices), f"{key}_bodies", start("Planets"), selection_mode="multi",
                                  format_func=core.symbol_of), choices)
    aspects = ()
    if flat:      # no Planet Path, Coordinates or AU buttons: no paths, always Fit
        major = core.in_order(titled(head, "Major Aspects", f"{key}_t_major", GLOBE_MAJOR, f"{key}_major", start("Major Aspects"), selection_mode="multi"), GLOBE_MAJOR)
        minor = core.in_order(titled(head, "Minor Aspects", f"{key}_t_minor", GLOBE_MINOR, f"{key}_minor", start("Minor Aspects"), selection_mode="multi"), GLOBE_MINOR)
        aspects = tuple(int(a) for a in major + minor)
        with_paths, scale, show_au = [], space3d.FIT, True
        coords = head.container(width="content", gap="xxsmall")   # Coordinates, with Houses below it (the title off: no houses)
        show_houses = bool(kept_pills(coords, "Coordinates", ["Coordinates"], f"{key}_t_coords", "Coordinates", label_visibility="collapsed")
                           and kept_pills(coords, "Houses", ["Houses"], f"{key}_houses", start("Houses"), label_visibility="collapsed"))
    else:
        with_paths = core.in_order(titled(head, "Planet Path", f"{key}_t_paths", core.shown_order(choices), f"{key}_paths", start("Planet Path"),
                                          selection_mode="multi", format_func=core.symbol_of), choices)
        coords = head.container(width="content", gap="xxsmall")   # Coordinates, with Fit, True and AU below it
        scale, show_au = space3d.FIT, False                   # (with the title off: Fit, no tags)
        if kept_pills(coords, "Coordinates", ["Coordinates"], f"{key}_t_scale", "Coordinates", label_visibility="collapsed"):
            below = coords.container(horizontal=True, width="content", gap="xxsmall")
            scale = kept_pills(below, "Which Coordinates", space3d.SCALES, f"{key}_scale", start("Coordinates"), label_visibility="collapsed") or space3d.FIT
            show_au = bool(kept_pills(below, "AU", ["AU"], f"{key}_au", start("AU"), label_visibility="collapsed"))
    speed = titled(head, "Rotate in 1s", f"{key}_t_speed", FLAT_SPEED_CHOICES if flat else SPEED_CHOICES, f"{key}_speed", start("Rotate in 1s"))
    manual = speed == globechart.MANUAL                       # time stands still, and the drawing is dragged round (not on the flat page: no Manual there)
    day_seconds = globechart.SPEEDS.get(speed)                # nothing picked: it holds still
    jd_now = core.now_jd()
    ave_jds = None
    if flat and not prep.now_only:                            # AstroClock-2D: the Ave planets on its Distance(%) graph, moving as time runs
        ave_jds = {"DOB": prep.jd_birth, "Now": jd_now}
    if not shown or not bodies:
        st.info("Choose a time and at least one planet.")
        # nothing drawn: no clock beside the name either (the last drawing's would stay there)
        st.html("<script>document.querySelectorAll('.globe-clock').forEach((e) => { e.textContent = ''; });</script>",
                unsafe_allow_javascript=True)
        return
    utc_now = datetime.now(ZoneInfo(prep.cn_tz)).utcoffset().total_seconds() / 3600.0 if prep.cn_tz else None
    moments = [m for m in (("Now", jd_now, utc_now), ("DOB", prep.jd_birth, prep.utc)) if m[0] in shown]
    st.html(space3d.space_html(bodies, moments, scale, str(prep.jd_birth), day_seconds, manual, show_au, tuple(with_paths), centre, flat,
                               {**({"DOB": ("CB", prep.birth_lon)} if prep.birth_lon is not None else {}),
                                **({"Now": ("CN", prep.cn[1])} if prep.cn else {})} if flat and show_houses else None, ave_jds,
                               aspects, orbs() if aspects else None),
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


def page_aspects_view():
    """Planets Cycles' aspects as tables: one per chosen angle, one row per time two of the planets come into it,
    newest first; then, with the Minor Aspects switch on, one per minor angle too."""
    got = cycles_inputs("asp_", aspect_buttons=False, nodes=True, page="Aspects")   # Major / Minor Aspects on / off buttons; NN, SN too
    if got is None:
        return
    jds, dec_on, angles, minor = got
    if len(dec_on) < 2:
        st.info("Choose at least two planets.")
        return
    if not angles and not minor:
        st.info("Turn on Major Aspects or Minor Aspects, and pick at least one angle.")
        return
    orb_csv = db.orb_table().to_csv(index=False)
    # major aspects on the left, minor right next to them (each as wide as its tables, not half the page)
    both = st.container(horizontal=True, gap="large", vertical_alignment="top")
    left, right = both.container(width="content"), both.container(width="content")
    if angles:                                                # the major angles picked
        with st.spinner("Finding aspects..."):
            _aspect_tables(_events_cached(tuple(dec_on), tuple(angles), *jds, orb_csv), angles, left)
    if minor:                                                 # the minor angles picked
        with st.spinner("Finding minor aspects..."):
            _aspect_tables(_events_cached(tuple(dec_on), tuple(minor), *jds, orb_csv), minor, right)


def _aspect_tables(events: list, angles: list[int], where):
    """A table per angle (with its count), one row per aspect, newest first, in where (a column)."""
    for ang in angles:
        ev = sorted((e for e in events if e[1] == ang), key=lambda e: e[0], reverse=True)   # newest first
        where.markdown(f"**{ang}°** &nbsp; {len(ev)} aspect{'' if len(ev) == 1 else 's'}")
        if not ev:
            where.caption("None in this period.")
            continue
        rows = []
        for jd, _, title, de1, de2, ra1, ra2 in ev:       # (the Aspect names the two planets)
            rd = abs(ra1 - ra2)
            rows.append({"Date / Time (UT)": core.jd_to_datetime(jd).strftime("%Y-%m-%d %H:%M"), "Aspect": core.with_symbols(title),
                         "RAD": 360.0 - rd if rd > 180.0 else rd,     # RAD: the angle in RA between the two, 0-180
                         "DeD": abs(de1 - de2)})                      # DeD: how far apart they are in Dec
        # sorted by clicking a column's name; RAD and DeD as numbers, so that they sort as numbers
        where.dataframe(pd.DataFrame(rows), hide_index=True, width="content",
                        column_config={"RAD": st.column_config.NumberColumn(format="%.2f"),
                                       "DeD": st.column_config.NumberColumn(format="%.2f")})


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _events_cached(dec_on, angles, jd_from, jd_to, orb_csv):
    import io
    ev = core.aspect_events(list(dec_on), jd_from, jd_to, list(angles), core.Orbs(pd.read_csv(io.StringIO(orb_csv))))
    return [(e.jd, e.angle, e.title, e.de1, e.de2, e.ra1, e.ra2) for e in sorted(ev, key=lambda e: e.jd)]


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
    dist_on = core.in_order(titled(head, "Planets", "t_dist", core.shown_order(core.BUTTON_ORDER), "dist_on_v2", default_choice("Planets Distance(%)", "Planets"),
                                   selection_mode="multi", format_func=core.symbol_of), core.BUTTON_ORDER)
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



# Customers, Symbols and Aspect Rules: Insert, Update, Delete and Commit on the title line, as in a database. Editable tables
# sort by their column headers only while they cannot add or delete rows themselves, so these buttons do that. Insert, Update
# and Delete change only the working copy shown (Delete takes the rows ticked in the first column; Update checks what has
# been typed); nothing reaches the database until Commit, which also takes what has been typed since.
def crud_table(key: str, show: pd.DataFrame, problems, commit, column_config: dict | None = None, width: str = "stretch",
               height: int | None = None) -> None:
    """problems(rows) gives what is wrong with the rows as they stand; commit(rows) saves them and gives what to report."""
    pressed = next((name for name in ("Insert", "Update", "Delete", "Commit")
                    if TITLE_SLOT.button(name, key=f"{key}_{name}", type="primary" if name == "Commit" else "secondary")), None)
    view = st.session_state.get(f"{key}_working", show).copy()
    view.insert(0, "Del", False)
    edited = st.data_editor(view, hide_index=True, width=width, num_rows="fixed", key=key, height=height or "auto",
                            column_config={"Del": st.column_config.CheckboxColumn("Del", width="small",
                                                                                  help="Tick, then press Delete."),
                                           **(column_config or {})}).reset_index(drop=True)
    rows, ticked = edited.drop(columns="Del"), edited["Del"].fillna(False).astype(bool)
    said = st.session_state.pop(f"{key}_said", None)           # below the table, so that it does not move
    if said:
        st.success(said)
    elif f"{key}_working" in st.session_state:
        st.caption("Changes not committed yet: press Commit to save them.")

    def stage(new_rows: pd.DataFrame, note: str) -> None:
        st.session_state.setdefault(f"{key}_base", show)       # what the working copy started from (see page_customers)
        st.session_state[f"{key}_working"] = new_rows.reset_index(drop=True)
        st.session_state.pop(key, None)
        st.session_state[f"{key}_said"] = note
        st.rerun()

    if pressed == "Insert":
        stage(rows.reindex(range(len(rows) + 1)), "A new row is at the bottom of the table. Press Commit to save it.")
    elif pressed == "Delete":
        if ticked.any():
            stage(rows[~ticked], f"{int(ticked.sum())} row(s) taken out. Press Commit to delete them from the database.")
        st.warning("Tick the rows to delete in the Del column first.")
    elif pressed in ("Update", "Commit"):
        wrong = problems(rows)
        if wrong:
            st.error(f"Not {'updated' if pressed == 'Update' else 'committed'}. " + "; ".join(wrong))
        elif pressed == "Update":
            stage(rows, "Updated. Press Commit to save it to the database.")
        else:
            try:
                report = commit(rows)
            except SQLAlchemyError as exc:                     # nothing is saved: the working copy stays
                st.error(f"Not committed. The database refused it: {getattr(exc, 'orig', exc)}")
                return
            st.cache_data.clear()                              # charts kept with the old values
            st.session_state.pop(f"{key}_working", None)
            st.session_state.pop(f"{key}_base", None)
            st.session_state.pop(key, None)
            st.session_state[f"{key}_said"] = report
            st.rerun()


def page_logins():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    pressed = next((name for name in ("Delete", "Delete all")
                    if TITLE_SLOT.button(name, key=f"logins_{name}")), None)
    table = db.logins_table()
    view = table.copy()
    view.insert(0, "Del", False)
    # (ticks are kept by row position: a new key when the rows move, so that a tick cannot land on another row)
    edited = st.data_editor(view, hide_index=True, width="content", num_rows="fixed",
                            key=f"logins_table_{len(table)}_{table['Id'].iloc[0] if len(table) else 0}",
                            height="auto" if len(table) <= 18 else 700, disabled=["Email", "Activity", "Date_Time", "Location"],
                            column_config={"Del": st.column_config.CheckboxColumn("Del", width="small", help="Tick, then press Delete."),
                                           "Id": None, "Email": st.column_config.TextColumn(width=260),
                                           "Activity": st.column_config.TextColumn(width=100),
                                           "Date_Time": st.column_config.DatetimeColumn("Date_Time (UT)", format="YYYY-MM-DD HH:mm:ss",
                                                                                        width=170),
                                           "Location": st.column_config.TextColumn(width=260, help="Where the visitor was: City, State, "
                                                                                   "Country from their IP address (approximate); Local on a "
                                                                                   "local network; blank when not known.")})
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
            st.session_state["logins_said"] = f"Deleted {n} row(s)."
            st.rerun()
        if no.button("No", key="logins_no"):
            st.session_state.pop("logins_ask", None)
            st.rerun()


def page_defaults():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.defaults_table()
    crud_table("defaults_table", table, lambda rows: db.defaults_problems(rows) + options_problems(rows),
               lambda rows: f"Committed: {db.save_defaults(rows)} row(s).",
               height=30 * (len(st.session_state.get("defaults_table_working", table)) + 1) + 8,   # every row in view
               column_config={"Page": st.column_config.TextColumn(width=170), "Options": st.column_config.TextColumn(width=170),
                              "Choices": st.column_config.TextColumn(width="large")})


def page_naming():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    # the page's names for the table's columns (the store keeps its own)
    shown_as = {"SN": "SAbr", "Symbol": "Symb", "Name": "SDesc", "Color": "RGB", "Color_Name": "Color", "Size": "Size_Geo"}   # (Size_Clock-3D, Size_Helio as they are)
    back = {v: k for k, v in shown_as.items()}
    table = db.all_planets().assign(_sn=lambda d: d["SN"]).rename(columns=shown_as)[["Symb", "SAbr", "SDesc", "RGB", "Color", "Size_Clock-2D", "Size_Clock-3D", "Size_Geo", "Size_Helio", "_sn"]]
    crud_table("planets_table", table, lambda rows: db.planet_problems(rows.rename(columns=back)),
               lambda rows: "Committed: {} added, {} changed, {} deleted.".format(*db.save_planets(rows.rename(columns=back))),
               height=30 * (len(st.session_state.get("planets_table_working", table)) + 1) + 24,   # every row in view, above the scroll bar
               column_config={"_sn": None, "Symb": st.column_config.TextColumn(width="small"), "SDesc": st.column_config.TextColumn(width=135),
                              "RGB": st.column_config.TextColumn(width=118), "Size_Clock-3D": st.column_config.TextColumn(width=112), "Size_Geo": st.column_config.TextColumn(width=112), "Size_Helio": st.column_config.TextColumn(width=112), "Size_Clock-2D": st.column_config.TextColumn(width=112)}, width="content")


def page_aspects():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.orb_table()
    st.caption("A pair is in aspect when RA is within the orb of the angle and the two Decs within the same orb of "
               "equal or mirrored, at every angle. A pair uses the larger of its two planets' "
               "orbs; CB and CN take the planet's.")
    crud_table("orb_editor", table.assign(_angle=table["Angle"]), lambda rows: db.orb_problems(db.with_angles(rows)),
               lambda rows: (db.save_orb_table(db.with_angles(rows).pipe(lambda r: r[r["Angle"].notna()]).drop(columns="_angle")),
                             "Committed.")[1],
               column_config={"_angle": None, "Angle": st.column_config.NumberColumn("Angle", format="%g", width="small"),   # a new row's, if blank, from its Aspect's name
                              **{c: st.column_config.NumberColumn(core.with_symbols(c.removesuffix("-RA"))) for c in db.ORB_COLUMNS}})   # ☽︎, ☉︎ ..
    if st.button("Reset to defaults"):
        st.session_state["orb_reset_ask"] = True
    if st.session_state.get("orb_reset_ask"):
        st.warning("Put every orb back to its default for good? This cannot be undone.")
        yes, no = st.columns(2, width=220)
        if yes.button("Yes, reset", type="primary", key="orb_reset_yes"):
            db.save_orb_table(core.default_orb_table())
            for name in ("orb_reset_ask", "orb_editor_working", "orb_editor_base", "orb_editor"):
                st.session_state.pop(name, None)
            st.cache_data.clear()
            st.rerun()
        if no.button("No", key="orb_reset_no"):
            st.session_state.pop("orb_reset_ask", None)
            st.rerun()


def page_customers():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    if db.is_local_sqlite() and not auth._secret("dev_user"):
        st.warning("Saved in a local SQLite file. On Streamlit Community Cloud that file is lost on every restart: "
                   "set the secret db_url to a hosted Postgres database (see README).")
    df = db.all_customers()
    # UTC is not shown (a blank one is looked up from the birth place; one already kept stays, see below); Created and
    # Last_Updated (UT) are, read only (set by the app); the time last opened (Accessed) is kept but not shown
    shown_fields = [f for f in db.FIELDS if f != "utc"]
    stamps = {"added_at": "Created", "updated_at": "Last_Updated", "access_from": "Access_From"}
    order = [c for f in shown_fields for c in ((f, "access_from") if f == "access" else (f,))]   # Access_From next to Access
    show = df[["id"] + order + ["added_at", "updated_at"]].rename(columns={**db.LABELS, **stamps})
    # First Name, A-Z, to begin with; the column headers sort by any column. Saving matches rows by their record, so the
    # order shown does not matter
    by_name = show[db.LABELS["name"]].map(lambda v: v.strip().lower() if isinstance(v, str) else v)
    show = show.loc[by_name.sort_values(na_position="last", kind="stable").index].reset_index(drop=True)
    def for_store(rows: pd.DataFrame) -> pd.DataFrame:
        back = {**{v: k for k, v in db.LABELS.items()}, **{v: k for k, v in stamps.items()}}
        out = rows.rename(columns=back).drop(columns=["updated_at"], errors="ignore")   # (Last_Updated: the app's)
        out["utc"] = out["id"].map(df.set_index("id")["utc"])   # each customer's kept UTC, unchanged (new: blank)
        return out

    def commit(rows: pd.DataFrame) -> str:
        # against what the working copy started from: a member who joined or changed their details since is left alone
        base = st.session_state.get("cust_editor_base")
        return "Committed: {} added, {} changed, {} deleted.".format(
            *db.save_customers(for_store(rows), df if base is None else for_store(base), by=user.email))

    crud_table("cust_editor", show, lambda rows: db.customer_problems(for_store(rows)), commit,
               height="auto" if len(st.session_state.get("cust_editor_working", show)) <= 18 else 700,   # nothing below it overlapped
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, width="small", help="The record's number, set by the app (blank on a new row until saved)."),
                                "First Name": st.column_config.TextColumn("First Name *", help="Required."),
                                "Last Name": st.column_config.TextColumn("Last Name *", help="Required."),
                                "Hr24": st.column_config.NumberColumn("Hr24 *", help="Birth time, hour 0-23: required.",
                                                                      format="%d", step=1, min_value=0, max_value=23,
                                                                      width="small"),
                                "Min": st.column_config.NumberColumn("Min *", help="Birth time, minute 0-59: required.",
                                                                     format="%d", step=1, min_value=0, max_value=59,
                                                                     width="small"),
                                "Year": st.column_config.NumberColumn("Year *", help="Birth date: required, 1800 to 2399.",
                                                                      format="%d", step=1, min_value=1800, max_value=2399,
                                                                      width="small"),
                                "Mon": st.column_config.NumberColumn("Mon *", help="Birth date: required.",
                                                                     format="%d", step=1, min_value=1, max_value=12,
                                                                     width="small"),
                                "Date": st.column_config.NumberColumn("Date *", help="Birth date: required.",
                                                                      format="%d", step=1, min_value=1, max_value=31,
                                                                      width="small"),
                                "Email (login)": st.column_config.TextColumn("Email (login) *",
                                help="Required. The Google account email this customer signs in with (they see only "
                                     "their own). An email's own customer is the one with an Access; it may have any number more, "
                                     "with Access blank (people added under that login, or a family)."),
                                "Created By": st.column_config.TextColumn("Created By",
                                help="Who added the record (their login email). Set by the app (the admin, or the "
                                     "customer themself on signing up) when left blank; may be changed."),
                                "Access": st.column_config.SelectboxColumn("Access", options=list(access.ACCESS), width="small",
                                help="Free: the Now charts only. Ind: the DOB and Now charts of their own record, no time "
                                     "limit. Group: unlimited, no time limit: the DOB and Now charts of every record under "
                                     "their login, people they add on My details, and quick births not saved. Ind and Group "
                                     "are the paid options. TrInd, TrGrp: free trials of Ind and Group, for 1 day from "
                                     "Access_From (a member signing up with their birth details gets one: TrInd or TrGrp, as they pick). Admin: an admin. "
                                     "Blank (people added under a login), or a trial run "
                                     "out: the Now charts only."),
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
                                                                                help="When the record was last changed (UT), set by the app."),
                                "Access_From": st.column_config.DatetimeColumn("Access_From", format="YYYY-MM-DD HH:mm",
                                                                               help="When Access was set (UT): TrInd and TrGrp count "
                                                                                    "from it. Set to now when Access changes, unless "
                                                                                    "you set it here too (to the day paid, say).")})
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
        return
    if st.session_state.get("person_added"):
        st.success(st.session_state.pop("person_added"))
    if GRANT.many and not user.is_admin:
        with st.expander("Add a person", expanded=int(row["id"]) == access.QUICK):
            st.caption("Saved under your login, to see their DOB charts while your unlimited access runs; their place now "
                       "starts as yours.")
            own = visible_customers()
            own = own[own["id"] == OWN_ID]
            details_form(pd.Series({f: own.iloc[0][f] for f in ("country_n", "state_n", "city_n", "other_n")}) if len(own) else None,
                         person=True)
    if int(row["id"]) == access.QUICK:
        st.info("A quick birth is not saved. Pick a saved person in the sidebar to see or change their details.")
        return
    def shown(v) -> str:                                      # a blank stays blank, and a whole number has no .0
        if pd.isna(v):
            return ""
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)

    st.dataframe(pd.DataFrame({"Field": [db.LABELS[f].split(" (")[0] for f in db.FIELDS if f not in ("email", "utc")],
                               "Value": [shown(row[f]) for f in db.FIELDS if f not in ("email", "utc")]}),
                 hide_index=True, width="content")
    if prep and prep.ok:
        st.write(f"Born on a {prep.weekday}; UTC offset {prep.utc:+.2f} ({prep.tz}); birth place "
                 f"{prep.birth_lat}, {prep.birth_lon}.")
    if st.session_state.pop("details_saved", False):
        st.success("Your details are saved.")
    with st.expander("Edit my details"):
        details_form(row)


core.SIZE_TEXTS, core.SIZE_WORDS, core.SIZE_TEXTS_HELIO, core.SIZE_TEXTS_GLOBE, core.SIZE_TEXTS_CLOCK = db.planet_sizes()   # and their sizes
core.SYMBOL_TEXTS = db.planet_symbols()                       # and their symbols, shown in place of the SNs
DEFAULT_TEXTS = db.defaults_map()                             # what each page's inputs start as (the Defaults table)
core.COLOURS.update(core.DEFAULT_COLOURS | db.planet_colours())   # every chart's colours are the Symbols table's (a deleted row's, the usual one)
pages = [st.Page(page_astroclock, title="AstroClock-2D", icon=":material/science:", url_path="astroclock-2d"),
         st.Page(page_globe, title="AstroClock-3D", icon=":material/language:", url_path="astroclock-3d"),
         st.Page(page_centric, title="Geo/Helio Model", icon=":material/orbit:", url_path="geo-helio-model"),
         st.Page(page_aspects_view, title="Aspects", icon=":material/scatter_plot:", url_path="aspects"),
         st.Page(page_range, title="Planets Cycles", icon=":material/show_chart:", url_path="planets-cycles"),
         st.Page(page_distance, title="Planets Distance(%)", icon=":material/straighten:", url_path="planets-distance")]
if user.is_admin:                                             # the Aspect Rules, Customers, Symbols, Defaults, Logins pages: admins only
    pages += [st.Page(page_aspects, title="Aspect Rules", icon=":material/tune:", url_path="aspect-rules"),
              st.Page(page_customers, title="Customers", icon=":material/group:", url_path="customers"),
              st.Page(page_defaults, title="Defaults", icon=":material/settings:", url_path="defaults"),
              st.Page(page_logins, title="Logins", icon=":material/history:", url_path="logins"),
              st.Page(page_naming, title="Symbols", icon=":material/planet:", url_path="symbols")]
else:
    pages.append(st.Page(page_my_details, title="My details", icon=":material/person:", url_path="me"))
home = st.Page(lambda: None, title="Home", url_path="home", default=True, visibility="hidden")   # the root URL: sends to AstroClock-2D
nav = st.navigation([home] + pages)
PAGE_BY_PATH = {p.url_path: p for p in pages}                 # (to go to a page from another)
if nav is home:                                               # / opens /astroclock-2d, keeping any query
    st.switch_page(PAGE_BY_PATH["astroclock-2d"], query_params=st.query_params.to_dict())
_chosen = _pick_customer()                                    # the sidebar's customer, for every page
top_line(nav.title, _chosen[0])
nav.run()
st.sidebar.caption(f"Swiss Ephemeris via {se.BACKEND}. Equatorial (RA / Dec) only.")
