"""Equatorial (RA / Dec) charts with Swiss Ephemeris - the web version of the Excel workbook.

Pages: AstroGlobe, Celestial Sphere 3D, Planets Distance(%), Planets Cycles, Aspects (its aspects as tables) for everyone (their own customers only); Aspects Details,
Customers and Naming Conventions for admins; My details for users. Run locally:  .venv\\Scripts\\streamlit run streamlit_app.py
"""
from __future__ import annotations

import html
import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import auth, db
from app.chartdata import Prepared, locate_cached, now_values, prepare
from astro import core, distancechart, globechart, mapchart, places, rangechart, se, space3d

# wide pages, the sidebar (menu, customer) starting closed so the charts get the whole window; » opens it
st.set_page_config(page_title="Equatorial charts", page_icon=":material/public:", layout="wide",
                   initial_sidebar_state="collapsed")
# all text on all pages is 13 px: the theme (.streamlit/config.toml) sets body text and headings; this also brings
# Streamlit's smaller text (captions, buttons, labels, menus, tooltips) up to 13 px. Icons keep their own size.
st.html("""<style>
.stApp :is(p, span, div, label, small, a, li, input, textarea, button, td, th, code, h1, h2, h3, h4, h5, h6):not([data-testid="stIconMaterial"]),
[data-baseweb="popover"] :is(p, span, div, li):not([data-testid="stIconMaterial"]),
[role="dialog"] :is(p, span, div, li, h1, h2, h3, button):not([data-testid="stIconMaterial"]),
[data-testid="stTooltipContent"] * { font-size: 13px !important; }
/* except the planet dots in the Distance(%) row, bigger (mapchart.DOT_SCALE) */
.stApp span.key-dot { font-size: """ + str(round(mapchart.FONT * mapchart.DOT_SCALE)) + """px !important; }
/* an editable table's cell editor opens outside the table: it undoes the page's zoom, as the table does, to open on its cell */
#portal { zoom: calc(1 / var(--app-zoom, 1)); }
/* a pulldown list is placed by screen position outside the page, so the page's zoom would move it again and off its box:
   its holder undoes the zoom, and its text is sized to match the page's */
body > div:has(> [data-testid="stSelectboxVirtualDropdown"]) { zoom: calc(1 / var(--app-zoom, 1)); }
[data-testid="stSelectboxVirtualDropdown"] * { font-size: calc(13px * var(--app-zoom, 1)) !important; }
/* AstroGlobe's lists: two a line, the last alone not stretched across */
.st-key-globe_bodies button, .st-key-globe_paths button, .st-key-globe_coords button, .st-key-globe_speed button,
.st-key-globe_major button, .st-key-globe_minor button, .st-key-space_speed button
  { flex: 0 0 auto !important; width: auto !important; }
/* AstroGlobe's speed buttons, as small as their text allows */
.st-key-globe_speed button, .st-key-space_speed button { padding-left: 4px !important; padding-right: 4px !important; }
/* the button that opens the sidebar (pages, customer) is titled Menu, so it is clear what it opens */
[data-testid="stExpandSidebarButton"] { width: auto !important; padding: 0 6px !important; gap: 4px;
  display: inline-flex !important; align-items: center; }
[data-testid="stExpandSidebarButton"]::after { content: "Menu"; font-size: 13px; font-weight: 600;
  color: rgba(47, 45, 43, 0.8); white-space: nowrap; }
</style>""")
# Everything (text, buttons, tables, charts, map) resizes with the window, as one picture: the whole app is zoomed so
# that the page's content column is always WIDTH (1100) px before zooming, the width the charts are laid out at. So the
# charts are never scaled on their own and all text, chart text too, is always the same size (13 px x the zoom).
st.html("""<script>
(() => {
  if (window.__appZoom) { window.__appZoom(); return; }
  const WIDTH = """ + str(mapchart.WIDTH - mapchart.INSET_L - mapchart.INSET_R) + """;   // the text column
  function zoom() {
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
      window.dispatchEvent(new Event("resize"));             // the charts fit themselves again (mapchart.fit_html)
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


# ---------------------------------------------------------------- who can see which customers
def visible_customers() -> pd.DataFrame:
    return db.all_customers() if user.is_admin else db.customers_for(user.email)


def record_items(row: pd.Series) -> tuple:
    out = []
    for f in db.FIELDS:
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
    "AstroGlobe": "Time, with Now and DOB below it: which moments to show. The Earth inside the celestial sphere, its axis tilted 23.44 degrees and joining the North and South Celestial Poles (NCP, SCP); ECE and WCE are East and West on the Celestial Equator. "
                  "Rotate in 1s: the Earth turns about that fixed axis, west to east, while the sphere stands still, and time "
                  "runs from each moment, until it is turned off: the clock beside the name gives the date and time, and the Sun, "
                  "Moon and planets move over the sphere as they really did (time starts again after 4 years; refresh the page to go back "
                  "to the start). Below it, Manual: the Earth, the celestial sphere, Houses, RA, Dec, Lati and Long are frozen together; drag the chart sideways to turn them as one unit and see the other side of the AstroGlobe. Or pick a speed to start, how much time passes each second: 1h an hour, 1d a day, 1w a week, 1m a month; with none picked it holds still. The Earth starts as it was at that "
                  "moment, so a planet is straight above the place it was overhead. Each planet is on the sphere at its RA and Declination, with its symbol inside its marker (☉ Su, ☽ Mo, ☿ Me, ♀ Ve, ♂ Ma, ♃ Ju, ♄ Sa), sized as the Size column of Naming Conventions says, usually by how big it looks from the Earth then (a "
                  "logarithmic scale, as to true scale the planets would not show; point at one for its Dec/Lati, RA, Angular Size, Distance from earth and the others approaching and leaving it in Dec/Lati; at CB or CN for its Long, Dec/Lati, RA and the planets approaching and leaving its Dec/Lati). The far side of the sphere is "
                  "fainter, and hidden behind the Earth. Planets, picking from the list below it: which of the Sun, Moon and planets to show, with their RA and Dec lines, and the Moon's north and south nodes (NN, SN), where its path crosses the Sun's, drawn with their symbols (☊ and ☋; point at one for its details). Maj Aspects (0, 60, 90, 120, 180; black) and Min Aspects (30, 45, 72, 135, 144, 150; grey): pick the angles to draw a line between any two planets shown that are in that aspect, by the orbs in Aspects Details, as time runs; dotted for Now, each with its tag, as 0-Ju-Ma, along it where there is room (point at a line for its name). Coordinates, with Houses, RA, Dec, Lati and Long below it: which lines to show. Houses: twelve lines on the sphere, 30 degrees apart from the RA of CB (solid) and of CN (dashed), named H01 to H12, turning with the Earth, with each line's RA at its lower right (on the near side, where there is room). RA, Dec: the RA lines and the Dec lines of each planet on the sphere, and "
                  "of CB and CN on the Earth. Distance(%) from earth (DOB+Now)/2, at the end of the buttons' line: the average of each planet's Distance(%) at birth and now, whatever time the clock shows; below it, with DOB chosen, Distance(%) from earth on DOB. Lati, Long: the Earth's lines of latitude and of longitude, every 30 degrees, turning with it. Planet Path, picking from the list below it: the Sun's over a year, and the others' over one trip round "
                  "the sky around that moment (Moon 27.32 days around the clock's date, moving as time runs; Mercury, Venus a year; Mars 687; Jupiter 4333; Saturn 10759; NN, SN 6793.5, 18.6 years, close to the Sun's path, as the nodes lie on it). DOB: at birth, solid lines, with CB, a baby, at the birth place. Now: the planets "
                  "now, hollow, dashed lines, with CN, a house, at the place now.",
    "Celestial Sphere 3D": "The paths of the Sun, Moon and planets around the Earth (Ea), each at its own distance from the Earth (on AstroGlobe all are on one sphere). "
                  "Each point is placed by its RA, Dec and distance. North is up, the axis from NCP to SCP tilted 23.44 degrees on the page, with everything else leaning with it. AU values: rings on the plane of the Earth's equator, each with its distance from the Earth in AU (1 AU is about the Sun's distance). "
                  "Rotate in 1s: Manual: time stands still, and dragging the drawing turns it, what is behind being fainter. Or pick a speed, how much time passes each second: 1h an hour, 1d a day, 1w a week, 1m a month: the clock beside the name gives the date and time, and the Sun, Moon and planets move as they really did, nearer and farther, the Moon's path going with it (time starts again after 4 years; refresh the page to go back to the start). With none picked it holds still. Each has its symbol inside its marker (☉ Su, ☽ Mo, ☿ Me, ♀ Ve, ♂ Ma, ♃ Ju, ♄ Sa, ⊕ Ea). Sizes follow the Size column of Naming Conventions: usually a planet by how big it looks from the Earth at that moment (a logarithmic scale, as to true scale the planets would not show), so it grows as it comes nearer, and the Earth a little bigger than the Moon (to true scale it would be far smaller than a dot). Point at a planet for its Dec/Lati, RA, Angular Size and distance, or at a path for its span and distances. "
                  "Time: Now is hollow with dashed paths, DOB solid; each path is one trip round the sky around that moment (Sun, Mercury and Venus a year; Moon 27.32 days; Mars 687; Jupiter 4333; Saturn 10759). "
                  "Distance scale: on Log each AU ring is ten times the distance of the one inside it, so the Moon's path and Saturn's can be seen together; True is to scale, where the Moon's path is too small to tell from the Earth (pick Mo alone to see it); Mo Log has the Sun and planets as on True and the Moon as on Log, so only the Moon is not to scale (the AU rings are for the others, and pointing at the Moon still gives its real distance). A label with no room is left off: point at its mark.",
    "Aspects": "The aspects between the chosen planets over the period, as tables, newest first: one table per "
               "angle, a row each time two planets came into it (RA within the angle's RA orb, Declination within "
               "its Dec orb). Major Aspects: 0, 60, 90, 120, 180 degrees. Minor Aspects: 30, 45, 72, 135, 144, "
               "150 degrees. Dates and times are UT.",
    "Planets Cycles": "Each chosen planet's Declination (-M lines) over the period, with dots and tags where two of "
                      "them are in a chosen major aspect (0 to 180 degrees). A tag with no room is left off: point at "
                      "its dot to see it. Dates and times are UT.",
    "Planets Distance(%)": "Each chosen planet's distance from the Earth (-D lines) over the period, as D: the % "
                           "between its nearest (0) and farthest (100) over 1800 to 2400. Dates and times are UT.",
    "Naming Conventions": "The Naming Conventions table: the short name (SN), long name (Name) and colour of each planet, the Earth (Ea), the Moon's nodes (NN, SN), the place now (CN) and the birth place (CB). Seen by admins only, who can "
               "use Insert for a new row, type changes in the table and press Update, tick Del and press Delete; nothing is saved until Commit. Click a column name to sort. SN is unique, and stays once a row is in the table. Symbol is what the pages show in place of its SN, the SN itself when blank. On AstroGlobe and Celestial Sphere 3D the conventional symbols are drawn, in the row's Color; anything else is shown as typed. Color is rgb(r,g,b) or #rrggbb; Color_Name is its name in words, for reference, and may be blank. Size says how AstroGlobe and Celestial Sphere 3D draw the Sun, Moon, planets and Ea: Angular Size, by how big it looks from the Earth; a number, its radius in pixels; Bigger than, Smaller than or Same as another, by its SN or Name (Bigger than Moon); anything else or blank, as usual (a planet by its angular size, Ea a little bigger than the Moon). The other rows do not use it. The charts take the colours from here: a planet's marker, RA and Dec lines and path; Ea's mark and name on Celestial Sphere 3D; NN's and SN's symbol; CN's and CB's mark, name, RA and Dec lines. The Ea, NN, SN, CN and CB rows come back if deleted.",
    "Aspects Details": "The orbs: for each aspect and planet, how far from exact (in RA and in Declination) still "
                       "counts as the aspect. A pair of planets uses the larger of their two orbs. Changes here "
                       "apply to every chart.",
    "Customers": "Insert for a new customer, type changes and press Update, tick Del and press Delete; nothing is saved until Commit. Click a column name to sort. ID is the record's number, set by the app. Required (*): Email (login), First Name, "
                 "Last Name, Country, State, City, the birth date and time (Year, Mon, Date, Hr24, Min), and where they "
                 "live now (Country-N, State-N, City-N). "
                 "Email (login) is the Google account each customer signs in with (one customer per email; they see "
                 "only their own). Other and Other-N: anything else to keep about the birth place and the place now "
                 "(not used in the charts). The UTC offset is looked up from the birth place and date. Added, Updated "
                 "and Accessed (UT) are set by the app: when the customer was added, last changed, and last opened "
                 "their charts. Import adds customers from the workbook's Customers CSV.",
    "My details": "Your own birth details, used for all your charts. Edit my details to change them; your login "
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
        + ('<span class="globe-clock" style="white-space:pre"></span>' if title in ("AstroGlobe", "Celestial Sphere 3D") else "") +   # its script writes it
        f'</div>')
    # the slot fills the rest of the line
    TITLE_SLOT = line.container(width="stretch", horizontal=True, gap="small")


TITLE_SLOT = None                                             # set by top_line for the page being shown


PLACE_SEARCH_DOWN = "The place search is not answering just now. Please try again in a few minutes."


def _pick_customer() -> tuple[pd.Series | None, Prepared | None]:
    df = visible_customers()
    st.sidebar.markdown(f"**{user.name}**" + ("  \n:blue-badge[admin]" if user.is_admin else ""))
    auth.sign_out_button(user)
    if df.empty:
        st.sidebar.info("No customers yet." if user.is_admin else "Enter your birth details on the page to start.")
        return None, None
    # chosen by record (names need not be unique: the login email is the key), shown as First and Last Name, with the
    # email added where two customers share both
    full = (df["name"].fillna("") + " " + df["last_name"].fillna("")).str.strip()
    label = {int(i): (f"{f} ({e})" if (full == f).sum() > 1 and e else f)
             for i, f, e in zip(df["id"], full, df["email"].fillna(""))}
    ids = list(label)
    prev = st.session_state.get("customer_id")
    idx = ids.index(prev) if prev in ids else 0
    cid = st.sidebar.selectbox("Customer", ids, index=idx, format_func=label.get, key="customer_id")
    row = df[df["id"] == cid].iloc[0]
    try:
        prep = prepare(record_items(row))
    except places.LookupDown:
        prep = Prepared(False, PLACE_SEARCH_DOWN)
    if not prep.ok:
        st.sidebar.error(prep.message)
    else:
        hr, mn = row.get("hr"), row.get("mn")
        if hr is None or pd.isna(hr):
            at = "time unknown, 12:00 used"
        else:
            at = f"{int(hr):02d}:{0 if mn is None or pd.isna(mn) else int(mn):02d}"
        st.sidebar.caption(f"{int(row['year'])}-{int(row['mon']):02d}-{int(row['day']):02d} {prep.weekday} "
                           f"{at}, UTC {prep.utc:+.2f}  \n"
                           + ", ".join(str(row[f]) for f in ("city", "state", "country") if pd.notna(row[f]))
                           + f" ({prep.birth_lat}, {prep.birth_lon})")
    mark_accessed()
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


def new_member_form():
    """A member signing in for the first time (no record has their email yet) enters their own birth details; the
    record is saved with their login email, so they see their charts at once. One record per email."""
    st.write("Welcome! Enter your birth details to see your charts. They are kept private: only you (and the admin) "
             "can see them.")
    details_form(None)


def details_form(row: pd.Series | None):
    """A member's own birth details: empty for a new member, or their record to change (row). Saved with their
    login email, which stays the same (it is the key)."""
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
    if row is not None and val("hr") is not None:
        at0 = f"{int(val('hr')):02d}:{int(val('mn') or 0):02d}"
    with st.form("member_details" if row is None else "edit_details"):
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
        state = c2.text_input("State / region *", value=txt("state"), max_chars=120)
        country = c3.text_input("Country *", value=txt("country"), max_chars=120)
        other = c4.text_input("District/Others", value=txt("other"), max_chars=500,
                              help="The district, or anything else about the birth place (optional; not used in the "
                                   "charts).")
        st.markdown("**Where you live now** (for the Now charts)")
        c1, c2, c3, c4 = st.columns(4)
        city_n = c1.text_input("City *", value=txt("city_n"), max_chars=500, key="city_n")
        state_n = c2.text_input("State / region *", value=txt("state_n"), max_chars=120, key="state_n")
        country_n = c3.text_input("Country *", value=txt("country_n"), max_chars=120, key="country_n")
        other_n = c4.text_input("District/Other-N", value=txt("other_n"), max_chars=500, key="other_n",
                                help="The district, or anything else about where you live now (optional; not used "
                                     "in the charts).")
        sent = st.form_submit_button("Save my details" if row is None else "Save changes", type="primary")
    if not sent:
        return
    at = None
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*", at_txt or "")
    if m and int(m[1]) < 24 and int(m[2]) < 60:
        at = time(int(m[1]), int(m[2]))
    elif (at_txt or "").strip():
        st.error("Birth time: type it as hh:mm in 24 hours, e.g. 14:30 or 09:05.")
        return
    missing = [n for n, v in (("First Name", first), ("Last Name", last), ("Birth date", born), ("Birth time", at),
                              ("City", city), ("State / region", state), ("Country", country),
                              ("City (now)", city_n), ("State / region (now)", state_n), ("Country (now)", country_n))
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
    if row is None:
        db.add_own_customer(rec, user.email)   # an email that already has a record keeps it (nothing is changed)
    else:
        def num(v):
            return None if v is None else int(float(v))
        same_birth = (all(num(val(f)) == rec[f] for f in ("year", "mon", "day", "hr", "mn"))
                      and all(rec[f].strip() == txt(f).strip() for f in ("city", "state", "country")))
        rec["utc"] = val("utc") if same_birth else None   # a new birth time or place: its UTC offset is looked up
        db.update_own_customer(rec, user.email)
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


# ---------------------------------------------------------------- pages
def period(prep: Prepared, row=None) -> tuple[float, float] | None:
    """The Start / End inputs (UT; birth to now unless changed) as Julian days, or None (with a warning) if unusable.
    With row (a horizontal container) they go into it, each just wide enough; otherwise in four columns."""
    birth_dt = core.jd_to_datetime(prep.jd_birth)
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    c = [row] * 4 if row is not None else st.columns(4)
    dw, tw = (125, 80) if row is not None else ("stretch", "stretch")
    d0 = c[0].date_input("Start Date (UT)", value=birth_dt.date(), min_value=datetime(1800, 1, 1),
                         max_value=datetime(2399, 12, 31), width=dw)
    t0 = c[1].time_input("Time (UT)", key=f"start_time_{prep.jd_birth}", value=time(birth_dt.hour, birth_dt.minute), width=tw)
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


def cycles_inputs(keys: str, aspect_buttons: bool = True):
    """The inputs of Planets Cycles (and Aspects, which shares them; keys keeps each page's buttons
    apart): (period as Julian days, planets, angles, minor on), or None when there is nothing to show yet.
    Planets Cycles has a button per major angle; Aspects (aspect_buttons False) has one Major Aspects and one
    Minor Aspects on / off button instead, and its angles are all five major ones when Major Aspects is on."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return None
    jds = period(prep, head)
    # on / off buttons, as on Distance: every choice always in view
    dec_on = head.pills("Planets", core.BUTTON_ORDER, selection_mode="multi", format_func=core.symbol_of,
                        default=["Sa", "Ju"], key=f"{keys}dec_on_v2") or []
    ea_names = {v: k for k, v in rangechart.EA_NAME.items()}   # 0°, 60°, 90°, 120°, 180° -> their angles
    minor = False
    if aspect_buttons:
        ea = head.pills("Major Aspects", list(ea_names), selection_mode="multi", default=["0°", "180°"],
                        key=f"{keys}ea_on_v5") or []
    else:                                                     # one on / off button for each group
        groups = head.pills("Aspects", ["Major Aspects", "Minor Aspects"], selection_mode="multi",
                            default=["Major Aspects", "Minor Aspects"], key=f"{keys}groups_v2") or []
        ea = list(ea_names) if "Major Aspects" in groups else []
        minor = "Minor Aspects" in groups
    if jds is None:
        return None
    return jds, dec_on, [ea_names[e] for e in ea], minor


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
        return tuple(box.pills(f"Which {title}", names, selection_mode="multi", default=default, key=f"globe_{key}", format_func=core.symbol_of,
                               label_visibility="collapsed", width=width))

    shown = stacked(("Now", "DOB"), ("DOB",), title="Time")
    all_bodies = list(globechart.BODY_CHOICES)
    with_nodes = all_bodies + list(globechart.NODE_CHOICES)   # three a line: Su Mo Me, Ve Ma Ju, Sa NN SN
    bodies = options_under("Planets", "bodies", with_nodes, with_nodes, width=132)
    paths = options_under("Planet Path", "paths", with_nodes, [], width=132)
    major = options_under("Maj Aspects", "major", [str(a) for a in sorted(core.MAJOR)], [str(a) for a in sorted(core.MAJOR)], width=90)
    minor = options_under("Min Aspects", "minor", [str(a) for a in core.MINOR], [str(a) for a in core.MINOR], width=90)
    coords = head.container(width="content", gap="xxsmall")   # Coordinates, with its options below it in fixed rows
    if coords.pills("Coordinates", ["Coordinates"], default="Coordinates", key="globe_coords_on", label_visibility="collapsed"):
        for row_of in (["Houses"], ["RA", "Dec"], ["Lati", "Long"]):
            shown += coords.pills(f"Coordinates {row_of[0]}", row_of, selection_mode="multi", default=[n for n in row_of if n == "Houses"],
                                  key=f"globe_coords_{row_of[0]}", label_visibility="collapsed")
    spin = head.container(width="content", gap="xxsmall")     # Rotate, with how fast below it
    day_seconds, manual = None, False
    if spin.pills("Rotate in 1s", ["Rotate in 1s"], default="Rotate in 1s", key="globe_rotate", label_visibility="collapsed"):
        speed = spin.pills("Rotate speed", [globechart.MANUAL] + list(globechart.SPEEDS), default=globechart.MANUAL, key="globe_speed",
                           label_visibility="collapsed", width=92)    # (Manual, 1h on a line; 1d, 1w, 1m on the next)
        manual = speed == globechart.MANUAL                           # the Earth is dragged round by hand
        day_seconds = globechart.SPEEDS.get(speed)                    # nothing picked: it holds still
    jd_now = core.now_jd()
    now_pts, d_now = now_values(jd_now)
    key = mapchart.globe_key_html(prep.d_birth, d_now, "DOB" in shown)
    if key:                                                   # at the end of the buttons' line, after Rotate in 1s
        head.container(width="stretch", horizontal_alignment="right").markdown(key, unsafe_allow_html=True, width="content")
    utc_now = datetime.now(ZoneInfo(prep.cn_tz)).utcoffset().total_seconds() / 3600.0 if prep.cn_tz else None
    g = globechart.GlobeInput(
        birth=prep.birth, now=now_pts, jd_birth=prep.jd_birth, jd_now=jd_now,
        cb=(prep.birth_lat, prep.birth_lon), cn=prep.cn, show_birth="DOB" in shown, show_now="Now" in shown,
        show_ra="RA" in shown, show_dec="Dec" in shown, show_latitude="Lati" in shown,
        show_longitude="Long" in shown, show_houses="Houses" in shown, bodies=bodies, paths=paths,
        aspects=tuple(int(a) for a in major + minor), orbs=orbs(),
        utc_birth=prep.utc, utc_now=utc_now)
    # (the HTML is built only from the chart, never from what a user typed, so its script is safe to run)
    st.html(mapchart.fit_html(globechart.globe_figure(g),
                              after_js=globechart.globe_js(g, day_seconds, manual)),
            unsafe_allow_javascript=True)


def page_space():
    """The paths at their real distances, in 3D."""
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    if not need_chart(prep):
        return
    shown = head.pills("Time", ["Now", "DOB"], selection_mode="multi", default=["DOB"], key="space_time") or []
    bodies = head.pills("Planets", list(globechart.BODY_CHOICES), selection_mode="multi", default=["Su", "Mo"], format_func=core.symbol_of,
                        key="space_bodies") or []
    scale = head.pills("Distance scale", space3d.SCALES, default=space3d.MO_LOG, key="space_scale") or space3d.MO_LOG
    show_au = bool(head.pills("AU values", ["AU values"], key="space_au", label_visibility="collapsed"))
    speed = head.pills("Rotate in 1s", [globechart.MANUAL] + list(globechart.SPEEDS), default=globechart.MANUAL, key="space_speed")
    manual = speed == globechart.MANUAL                       # time stands still, and the drawing is dragged round
    day_seconds = globechart.SPEEDS.get(speed)                # nothing picked: it holds still
    if not shown or not bodies:
        st.info("Choose a time and at least one planet.")
        return
    utc_now = datetime.now(ZoneInfo(prep.cn_tz)).utcoffset().total_seconds() / 3600.0 if prep.cn_tz else None
    moments = [m for m in (("Now", core.now_jd(), utc_now), ("DOB", prep.jd_birth, prep.utc)) if m[0] in shown]
    st.html(space3d.space_html(bodies, moments, scale, str(prep.jd_birth), day_seconds, manual, show_au), unsafe_allow_javascript=True)


def page_range():
    got = cycles_inputs("")
    if got is None:
        return
    jds, dec_on, angles, _ = got
    with st.spinner("Drawing..."):
        fig, note = _range_cached(tuple(dec_on), tuple(angles), *jds, db.orb_table().to_csv(index=False))
    # fixed size, scaled down whole to fit (its tags are placed for that size)
    st.html(mapchart.fit_html(fig), unsafe_allow_javascript=True)
    if note:
        st.caption(note)


def page_aspects_view():
    """Planets Cycles' aspects as tables: one per chosen angle, one row per time two of the planets come into it,
    newest first; then, with the Minor Aspects switch on, one per minor angle too."""
    got = cycles_inputs("asp_", aspect_buttons=False)   # Major / Minor Aspects on / off buttons
    if got is None:
        return
    jds, dec_on, angles, minor = got
    if len(dec_on) < 2:
        st.info("Choose at least two planets.")
        return
    if not angles and not minor:
        st.info("Turn on Major Aspects or Minor Aspects.")
        return
    orb_csv = db.orb_table().to_csv(index=False)
    # major aspects on the left, minor right next to them (each as wide as its tables, not half the page)
    both = st.container(horizontal=True, gap="large", vertical_alignment="top")
    left, right = both.container(width="content"), both.container(width="content")
    if angles:                                                # all five major angles
        with st.spinner("Finding aspects..."):
            _aspect_tables(_events_cached(tuple(dec_on), tuple(angles), *jds, orb_csv), angles, left)
    if minor:                                                 # 30, 45, 72, 135, 144, 150 degrees
        with st.spinner("Finding minor aspects..."):
            _aspect_tables(_events_cached(tuple(dec_on), tuple(core.MINOR), *jds, orb_csv), core.MINOR, right)


def _aspect_tables(events: list, angles: list[int], where):
    """A table per angle (with its count), one row per aspect, newest first, in where (a column)."""
    for ang in angles:
        ev = sorted((e for e in events if e[1] == ang), key=lambda e: e[0], reverse=True)   # newest first
        where.markdown(f"**{ang}°** &nbsp; {len(ev)} aspect{'' if len(ev) == 1 else 's'}")
        if not ev:
            where.caption("None in this period.")
            continue
        rows = []
        for jd, _, title, de1, de2 in ev:
            p1, p2 = title.split("-")[1:3]
            rows.append({"Date / Time (UT)": core.jd_to_datetime(jd).strftime("%Y-%m-%d %H:%M"), "Aspect": core.with_symbols(title),
                         "Planet 1": core.symbol_of(p1), "Dec 1": de1, "Planet 2": core.symbol_of(p2), "Dec 2": de2})
        # sorted by clicking a column's name; Dec as numbers, so that they sort as numbers
        where.dataframe(pd.DataFrame(rows), hide_index=True, width="content",
                        column_config={"Dec 1": st.column_config.NumberColumn(format="%+.2f"),
                                       "Dec 2": st.column_config.NumberColumn(format="%+.2f")})


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _events_cached(dec_on, angles, jd_from, jd_to, orb_csv):
    import io
    ev = core.aspect_events(list(dec_on), jd_from, jd_to, list(angles), core.Orbs(pd.read_csv(io.StringIO(orb_csv))))
    return [(e.jd, e.angle, e.title, e.de1, e.de2) for e in sorted(ev, key=lambda e: e.jd)]


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _range_cached(dec_on, ea, jd_from, jd_to, orb_csv):
    import io
    return rangechart.range_figure(list(dec_on), list(ea), jd_from, jd_to, core.Orbs(pd.read_csv(io.StringIO(orb_csv))))


def page_distance():
    _, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return
    jds = period(prep, head)
    # on / off buttons: all seven planets always in view (a selection box would hide some, or not fit on the line)
    dist_on = head.pills("Planets", core.BUTTON_ORDER, selection_mode="multi", format_func=core.symbol_of,
                         default=["Sa", "Ju"], key="dist_on_v2") or []
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



# Customers, Naming Conventions and Aspects Details: Insert, Update, Delete and Commit on the title line, as in a database. Editable tables
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


def page_naming():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.all_planets().assign(_sn=lambda d: d["SN"])
    crud_table("planets_table", table, db.planet_problems,
               lambda rows: "Committed: {} added, {} changed, {} deleted.".format(*db.save_planets(rows)),
               height=28 * (len(st.session_state.get("planets_table_working", table)) + 1) + 3,   # every row in view
               column_config={"_sn": None, "Symbol": st.column_config.TextColumn(width="small"), "Name": st.column_config.TextColumn(width=150), "Color": st.column_config.TextColumn(width=130),
                              "Size": st.column_config.TextColumn(width=130)}, width="content")


def page_aspects():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    table = db.orb_table()
    st.caption("A pair is in aspect when RA is within the RA orb of the angle and Dec within the Dec orb of equal "
               "(conjunction), mirrored (opposition) or either (the others). A pair uses the larger of its two planets' "
               "orbs; CB and CN take the planet's.")
    crud_table("orb_editor", table.assign(_angle=table["Angle"]), db.orb_problems,
               lambda rows: (db.save_orb_table(rows[rows["Angle"].notna()].drop(columns="_angle")), "Committed.")[1],
               column_config={"_angle": None, "Angle": st.column_config.NumberColumn("Angle", format="%g", width="small"),
                              **{c: st.column_config.NumberColumn(core.with_symbols(c)) for c in db.ORB_COLUMNS}})
    if st.button("Reset to defaults"):
        db.save_orb_table(core.default_orb_table())
        st.session_state.pop("orb_editor_working", None)
        st.session_state.pop("orb_editor_base", None)
        st.session_state.pop("orb_editor", None)
        st.cache_data.clear()
        st.rerun()


def page_customers():
    if db.is_local_sqlite() and not auth._secret("dev_user"):
        st.warning("Saved in a local SQLite file. On Streamlit Community Cloud that file is lost on every restart: "
                   "set the secret db_url to a hosted Postgres database (see README).")
    df = db.all_customers()
    # UTC is not shown (a blank one is looked up from the birth place; one already kept stays, see below); the times
    # Added / Updated / Accessed are shown at the end, set by the app, not typed
    shown_fields = [f for f in db.FIELDS if f != "utc"]
    show = df[["id"] + shown_fields + list(db.STAMPS)].rename(columns={**db.LABELS, **db.STAMPS})
    # First Name, A-Z, to begin with; the column headers sort by any column. Saving matches rows by their record, so the
    # order shown does not matter
    by_name = show[db.LABELS["name"]].map(lambda v: v.strip().lower() if isinstance(v, str) else v)
    show = show.loc[by_name.sort_values(na_position="last", kind="stable").index].reset_index(drop=True)
    stamp_cols = {label: st.column_config.DatetimeColumn(label, format="YYYY-MM-DD HH:mm", disabled=True,
                                                         help=help_text)
                  for label, help_text in (("Added", "When the customer was added (UT)."),
                                           ("Updated", "When the details last changed (UT)."),
                                           ("Accessed", "When the customer last opened their charts (UT); "
                                                        "an admin looking does not count."))}
    def for_store(rows: pd.DataFrame) -> pd.DataFrame:
        back = {v: k for k, v in db.LABELS.items()}
        out = rows.rename(columns=back).drop(columns=list(db.STAMPS.values()), errors="ignore")
        out["utc"] = out["id"].map(df.set_index("id")["utc"])   # each customer's kept UTC, unchanged (new: blank)
        return out

    def commit(rows: pd.DataFrame) -> str:
        # against what the working copy started from: a member who joined or changed their details since is left alone
        base = st.session_state.get("cust_editor_base")
        return "Committed: {} added, {} changed, {} deleted.".format(
            *db.save_customers(for_store(rows), df if base is None else for_store(base)))

    crud_table("cust_editor", show, lambda rows: db.customer_problems(for_store(rows)), commit,
               height=min(27 * (len(st.session_state.get("cust_editor_working", show)) + 2), 700),   # above its scroll bar
               column_config={"id": st.column_config.NumberColumn("ID", format="%d", disabled=True, width="small", help="The record's number, set by the app (blank on a new row until saved)."), **stamp_cols,
                                "First Name": st.column_config.TextColumn("First Name *", help="Required."),
                                "Last Name": st.column_config.TextColumn("Last Name *", help="Required."),
                                "Hr24": st.column_config.NumberColumn("Hr24 *", help="Birth time, hour 0-23: required.",
                                                                      format="%d", step=1, min_value=0, max_value=23,
                                                                      width="small"),
                                "Min": st.column_config.NumberColumn("Min *", help="Birth time, minute 0-59: required.",
                                                                     format="%d", step=1, min_value=0, max_value=59,
                                                                     width="small"),
                                "Year": st.column_config.NumberColumn("Year *", help="Birth date: required.",
                                                                      format="%d", step=1, width="small"),
                                "Mon": st.column_config.NumberColumn("Mon *", help="Birth date: required.",
                                                                     format="%d", step=1, min_value=1, max_value=12,
                                                                     width="small"),
                                "Date": st.column_config.NumberColumn("Date *", help="Birth date: required.",
                                                                      format="%d", step=1, min_value=1, max_value=31,
                                                                      width="small"),
                                "Email (login)": st.column_config.TextColumn("Email (login) *",
                                help="Required. The Google account email this customer signs in with (they see only "
                                     "their own). Each email can belong to one customer only."),
                                "Country": st.column_config.TextColumn("Country *", help="Birth place: required."),
                                "State": st.column_config.TextColumn("State *", help="Birth place: required."),
                                "City": st.column_config.TextColumn("City *", help="Birth place: required."),
                                "Other": st.column_config.TextColumn(help="Anything else to keep with the record."),
                                "Country-N": st.column_config.TextColumn("Country-N *", help="Place now: required."),
                                "State-N": st.column_config.TextColumn("State-N *", help="Place now: required."),
                                "City-N": st.column_config.TextColumn("City-N *", help="Place now: required."),
                                "Other-N": st.column_config.TextColumn(help="Anything else about the place now.")})
    with st.expander("Import from the workbook"):
        st.write("Save the workbook's Customers tab as CSV (Customer, Country, State, City, Other, Year, Mon, Date, "
                 "Hr24, Min, Country-N, State-N, City-N, Other-N; Other and Other-N may be left out) and upload it. "
                 "Names already here are skipped. Then add each customer's Email (login): it is required to save.")
        up = st.file_uploader("Customers CSV", type="csv")
        if up is not None and st.button("Import"):
            try:
                n = db.import_workbook_csv(up.getvalue())
            except ValueError as exc:                          # nothing is saved
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


core.SIZE_TEXTS, core.SIZE_WORDS = db.planet_sizes()         # and their sizes
core.SYMBOL_TEXTS = db.planet_symbols()                       # and their symbols, shown in place of the SNs
core.COLOURS.update(db.planet_colours())                      # every chart's colours are the Naming Conventions table's
pages = [st.Page(page_globe, title="AstroGlobe", icon=":material/language:", url_path="astroglobe", default=True),
         st.Page(page_space, title="Celestial Sphere 3D", icon=":material/orbit:", url_path="celestial-sphere-3d"),
         st.Page(page_aspects_view, title="Aspects", icon=":material/scatter_plot:", url_path="aspects"),
         st.Page(page_range, title="Planets Cycles", icon=":material/show_chart:", url_path="planets-cycles"),
         st.Page(page_distance, title="Planets Distance(%)", icon=":material/straighten:", url_path="planets-distance")]
if user.is_admin:                                             # the Aspects Details, Customers, Naming Conventions pages: admins only
    pages += [st.Page(page_aspects, title="Aspects Details", icon=":material/tune:", url_path="aspects-details"),
              st.Page(page_customers, title="Customers", icon=":material/group:", url_path="customers"),
              st.Page(page_naming, title="Naming Conventions", icon=":material/planet:", url_path="naming-conventions")]
else:
    pages.append(st.Page(page_my_details, title="My details", icon=":material/person:", url_path="me"))
nav = st.navigation(pages)
_chosen = _pick_customer()                                    # the sidebar's customer, for every page
top_line(nav.title, _chosen[0])
nav.run()
st.sidebar.caption(f"Swiss Ephemeris via {se.BACKEND}. Equatorial (RA / Dec) only.")
