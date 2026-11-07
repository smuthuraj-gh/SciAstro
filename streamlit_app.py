"""Equatorial (RA / Dec) charts with Swiss Ephemeris - the web version of the Excel workbook.

Pages: AstroMap, Planets Distance(%), Planets Cycles, Aspects (its aspects as tables) for everyone (their own customers only); Aspects Details and
Customers for admins; My details for users. Run locally:  .venv\\Scripts\\streamlit run streamlit_app.py
"""
from __future__ import annotations

import html
from datetime import datetime, time, timezone

import pandas as pd
import streamlit as st

from app import auth, db
from app.chartdata import Prepared, now_local_text, now_values, prepare
from astro import core, distancechart, mapchart, rangechart, se

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


PAGE_HELP = {"AstroMap": "Map: the world map (coastlines). DOB: the planets at birth. "
                         "Now: the planets now. Major Aspects: conjunction, sextile, square, trine, "
                         "opposition. Minor Aspects: 30, 45, 72, 135, 144, 150 degrees."}


def top_line(title: str, row: pd.Series | None):
    """Every page's top line: its title at the left, the chosen customer's First Name at the right."""
    # one row drawn here (not Streamlit's row, which can wrap the name onto a line of its own): both on one baseline
    name = str(row.get("name") or "").strip() if row is not None else ""
    help_text = PAGE_HELP.get(title)
    help_mark = (f'<span title="{html.escape(help_text)}" style="cursor:help; opacity:0.6; margin-left:6px; '
                 f'font-weight:400">&#9432;</span>') if help_text else ""
    st.html(f'<div style="display:flex; align-items:baseline; justify-content:space-between; gap:16px; '
            f'flex-wrap:nowrap; font-weight:600">'
            f'<span style="white-space:nowrap">{html.escape(title)}{help_mark}</span>'
            f'<span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{html.escape(name)}</span>'
            f'</div>')


def _pick_customer() -> tuple[pd.Series | None, Prepared | None]:
    df = visible_customers()
    st.sidebar.markdown(f"**{user.name}**" + ("  \n:blue-badge[admin]" if user.is_admin else ""))
    auth.sign_out_button(user)
    if df.empty:
        st.sidebar.info("No customers yet." if user.is_admin else "No birth details are linked to your email yet.")
        return None, None
    names = df["name"].tolist()
    prev = st.session_state.get("customer")
    idx = names.index(prev) if prev in names else 0
    name = st.sidebar.selectbox("Customer", names, index=idx, key="customer")
    row = df[df["name"] == name].iloc[0]
    prep = prepare(record_items(row))
    if not prep.ok:
        st.sidebar.error(prep.message)
    else:
        st.sidebar.caption(f"{int(row['year'])}-{int(row['mon']):02d}-{int(row['day']):02d} {prep.weekday} "
                           f"{int(row['hr']):02d}:{int(row['mn']):02d}, UTC {prep.utc:+.2f}  \n"
                           f"{row['city']}, {row['state'] or ''}, {row['country'] or ''} ({prep.birth_lat}, {prep.birth_lon})")
    return row, prep


def orbs() -> core.Orbs:
    return core.Orbs(db.orb_table())


def need_chart(prep: Prepared | None) -> bool:
    if prep is None:
        st.info("Choose a customer in the sidebar." if user.is_admin else "Ask the admin to add your birth details.")
        return False
    if not prep.ok:
        st.warning(prep.message)
        return False
    return True


# ---------------------------------------------------------------- pages
def page_map():
    row, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="center", gap="small")    # buttons, then the key
    if not need_chart(prep):
        return
    shown = head.pills("Show", ["Map", "DOB", "Now", "Major Aspects", "Minor Aspects"],
                       selection_mode="multi", default=["DOB", "Major Aspects", "Minor Aspects"],
                       key="map_show_v8", label_visibility="collapsed")
    show_birth, show_now = "DOB" in shown, "Now" in shown
    major, minor = "Major Aspects" in shown, "Minor Aspects" in shown
    jd_now = core.now_jd()
    now_pts, d_now = now_values(jd_now)
    m = mapchart.MapInput(
        birth=prep.birth, now=now_pts, cn=prep.cn, jd_birth=prep.jd_birth, jd_now=jd_now,
        d_birth=prep.d_birth, d_now=d_now, show_birth=show_birth, show_now=show_now, major=major, minor=minor,
        show_map="Map" in shown)
    key = mapchart.key_html(m)
    if key:                                                   # birth marks with D, then Distance% Average: next to Minor Aspects
        head.markdown(key, unsafe_allow_html=True, width="content")
    # Laid out at its own fixed size (every label is spaced for it) and scaled down whole to fit a narrower column:
    # st.plotly_chart would re-lay it out narrower and bring the labels back on top of each other
    # (the HTML is built only from the chart, never from what a user typed, so its script is safe to run)
    st.html(mapchart.fit_html(mapchart.map_figure(m, orbs())), unsafe_allow_javascript=True)
    if show_now:
        st.caption(f"Now: {now_local_text(prep.cn_tz)}" + ("" if prep.cn else " - no City-N for this customer, so no CN"))


def period(prep: Prepared, row=None) -> tuple[float, float] | None:
    """The Start / End inputs (UT; birth to now unless changed) as Julian days, or None (with a warning) if unusable.
    With row (a horizontal container) they go into it, each just wide enough; otherwise in four columns."""
    birth_dt = core.jd_to_datetime(prep.jd_birth)
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    c = [row] * 4 if row is not None else st.columns(4)
    dw, tw = (125, 80) if row is not None else ("stretch", "stretch")
    d0 = c[0].date_input("Start Date (UT)", value=birth_dt.date(), min_value=datetime(1800, 1, 1),
                         max_value=datetime(2399, 12, 31), width=dw)
    t0 = c[1].time_input("Time (UT)", key="start_time", value=time(birth_dt.hour, birth_dt.minute), width=tw)
    d1 = c[2].date_input("End Date (UT)", value=now_dt.date(), min_value=datetime(1800, 1, 1),
                         max_value=datetime(2399, 12, 31), width=dw)
    t1 = c[3].time_input("Time (UT)", key="end_time", value=time(now_dt.hour, now_dt.minute), width=tw)
    start, end = datetime.combine(d0, t0), datetime.combine(d1, t1)
    if end <= start:
        st.warning("The end must be after the start.")
        return None
    if (end - start).days > 100 * 366:
        st.warning("That period is too long - choose about 100 years at most.")
        return None
    return core.jd_of_datetime(start), core.jd_of_datetime(end)


def cycles_inputs(title: str, keys: str, aspect_buttons: bool = True):
    """The title and inputs of Planets Cycles (and Aspects, which shares them; keys keeps each page's buttons
    apart): (period as Julian days, planets, angles, minor on), or None when there is nothing to show yet.
    Planets Cycles has a button per major angle; Aspects (aspect_buttons False) has one Major Aspects and one
    Minor Aspects on / off button instead, and its angles are all five major ones when Major Aspects is on."""
    row, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return None
    jds = period(prep, head)
    # on / off buttons, as on Distance: every choice always in view
    dec_on = head.pills("Planets", core.BUTTON_ORDER, selection_mode="multi",
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


def page_range():
    got = cycles_inputs("Planets Cycles", "")
    if got is None:
        return
    jds, dec_on, angles, _ = got
    with st.spinner("Drawing..."):
        fig, note = _range_cached(tuple(dec_on), tuple(angles), *jds, db.orb_table().to_csv(index=False))
    # fixed size, scaled down whole to fit (its tags are placed for that size), as AstroMap
    st.html(mapchart.fit_html(fig), unsafe_allow_javascript=True)
    if note:
        st.caption(note)


def page_aspects_view():
    """Planets Cycles' aspects as tables: one per chosen angle, one row per time two of the planets come into it,
    newest first; then, with the Minor Aspects switch on, one per minor angle too."""
    got = cycles_inputs("Aspects", "asp_", aspect_buttons=False)   # Major / Minor Aspects on / off buttons
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
    left, right = st.columns(2, gap="large")                  # major aspects on the left, minor on the right
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
            rows.append({"Date / Time (UT)": core.jd_to_datetime(jd).strftime("%Y-%m-%d %H:%M"), "Aspect": title,
                         "Planet 1": p1, "Dec 1": f"{de1:+.2f}", "Planet 2": p2, "Dec 2": f"{de2:+.2f}"})
        # a plain table (not st.dataframe, whose canvas draws its text smaller): all text on the pages is 13 px
        where.table(pd.DataFrame(rows).style.hide(axis="index"), width="content")


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
    row, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall")   # the inputs (title: top line)
    if not need_chart(prep):
        return
    jds = period(prep, head)
    # on / off buttons: all seven planets always in view (a selection box would hide some, or not fit on the line)
    dist_on = head.pills("Planets", core.BUTTON_ORDER, selection_mode="multi",
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



def page_aspects():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    pick_customer()
    table = db.orb_table()
    st.caption("A pair is in aspect when RA is within the RA orb of the angle and Dec within the Dec orb of equal "
               "(conjunction), mirrored (opposition) or either (the others). A pair uses the larger of its two planets' "
               "orbs; CB and CN take the planet's.")
    edited = st.data_editor(table, hide_index=True, width="stretch", key="orb_editor",
                            disabled=["Aspect", "Angle"], num_rows="fixed")
    c = st.columns([1, 1, 6])
    if c[0].button("Save orbs", type="primary"):
        num = edited.drop(columns=["Aspect", "Angle"]).apply(pd.to_numeric, errors="coerce")
        if num.isna().any().any() or (num < 0).any().any():
            st.error("Every orb must be a number of 0 or more.")
        else:
            db.save_orb_table(edited)
            st.cache_data.clear()
            st.success("Saved.")
    if c[1].button("Reset to defaults"):
        db.save_orb_table(core.default_orb_table())
        st.cache_data.clear()
        st.rerun()


def page_customers():
    pick_customer()
    if db.is_local_sqlite() and not auth._secret("dev_user"):
        st.warning("Saved in a local SQLite file. On Streamlit Community Cloud that file is lost on every restart: "
                   "set the secret db_url to a hosted Postgres database (see README).")
    df = db.all_customers()
    show = df[["id"] + db.FIELDS].rename(columns=db.LABELS)
    edited = st.data_editor(show, hide_index=True, width="stretch", num_rows="dynamic", key="cust_editor",
                            column_config={"id": None, "Email (login)": st.column_config.TextColumn(
                                help="The Google account email this customer signs in with (they see only their own). "
                                     "Each email can belong to one customer only.")})
    if st.button("Save changes", type="primary"):
        back = {v: k for k, v in db.LABELS.items()}
        try:
            a, ch, de = db.save_customers(edited.rename(columns=back), df)
        except ValueError as e:                               # e.g. a login email used twice: nothing saved
            st.error(f"{e}. Nothing was saved.")
        else:
            st.cache_data.clear()
            st.success(f"Saved: {a} added, {ch} changed, {de} deleted.")
            st.rerun()
    with st.expander("Import from the workbook"):
        st.write("Save the workbook's Customers tab as CSV (Customer, Country, State, City, Year, Mon, Date, Hr24, Min, "
                 "Country-N, State-N, City-N) and upload it. Names already here are skipped.")
        up = st.file_uploader("Customers CSV", type="csv")
        if up is not None and st.button("Import"):
            n = db.import_workbook_csv(up.getvalue())
            st.cache_data.clear()
            st.success(f"Imported {n} customers. Add each one's login email to let them see their charts.")


def page_my_details():
    row, prep = pick_customer()
    if row is None:
        st.info("No birth details are linked to your email yet. Ask the admin to add them.")
        return
    st.table(pd.DataFrame({"": [db.LABELS[f].split(" (")[0] for f in db.FIELDS if f not in ("email", "utc")],
                           "Value": [row[f] for f in db.FIELDS if f not in ("email", "utc")]}).astype(str))
    if prep and prep.ok:
        st.write(f"Born on a {prep.weekday}; UTC offset {prep.utc:+.2f} ({prep.tz}); birth place "
                 f"{prep.birth_lat}, {prep.birth_lon}.")


pages = [st.Page(page_map, title="AstroMap", icon=":material/public:", url_path="astromap", default=True),
         st.Page(page_aspects_view, title="Aspects", icon=":material/scatter_plot:", url_path="aspects"),
         st.Page(page_range, title="Planets Cycles", icon=":material/show_chart:", url_path="planets-cycles"),
         st.Page(page_distance, title="Planets Distance(%)", icon=":material/straighten:", url_path="planets-distance")]
if user.is_admin:                                             # the Aspects Details and Customers pages: admins only
    pages += [st.Page(page_aspects, title="Aspects Details", icon=":material/tune:", url_path="aspects-details"),
              st.Page(page_customers, title="Customers", icon=":material/group:", url_path="customers")]
else:
    pages.append(st.Page(page_my_details, title="My details", icon=":material/person:", url_path="me"))
nav = st.navigation(pages)
_chosen = _pick_customer()                                    # the sidebar's customer, for every page
top_line(nav.title, _chosen[0])
nav.run()
st.sidebar.caption(f"Swiss Ephemeris via {se.BACKEND}. Equatorial (RA / Dec) only.")
