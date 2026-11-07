"""Equatorial (RA / Dec) charts with Swiss Ephemeris - the web version of the Excel workbook.

Pages: AstroMap, Planets Distance(%), Planets Cycles, Tables for everyone (their own customers only); Aspects and
Customers for admins; My details for users. Run locally:  .venv\\Scripts\\streamlit run streamlit_app.py
"""
from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd
import streamlit as st

from app import auth, db
from app.chartdata import Prepared, now_local_text, now_values, prepare
from astro import core, distancechart, mapchart, rangechart, se

st.set_page_config(page_title="Equatorial charts", page_icon=":material/public:", layout="wide")

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


def pick_customer() -> tuple[pd.Series | None, Prepared | None]:
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
    head = st.container(horizontal=True, vertical_alignment="center", gap="small")    # title, buttons, then the key
    head.subheader("AstroMap", width="content", wrap=False,
                   help="Map: the world map (coastlines). DOB: the planets at birth. "
                        "Now: the planets now. Major Aspects: conjunction, sextile, square, trine, "
                        "opposition. Minor Aspects: 30, 45, 72, 135, 144, 150 degrees.")
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
    if key:                                                   # the planets, CB, CN key, next to Minor Aspects
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


def page_range():
    row, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall")   # the title, then the inputs
    head.subheader("Planets Cycles", width="content", wrap=False)
    if not need_chart(prep):
        return
    jds = period(prep, head)
    # on / off buttons, as on Distance: every choice always in view
    dec_on = head.pills("Planets", core.BUTTON_ORDER, selection_mode="multi",
                        default=["Sa", "Ju"], key="dec_on_v2") or []
    ea_names = {v: k for k, v in rangechart.EA_NAME.items()}   # 0°, 60°, 90°, 120°, 180° -> their angles
    ea = head.pills("Major Aspects", list(ea_names), selection_mode="multi", default=["0°", "180°"],
                    key="ea_on_v5") or []
    if jds is None:
        return
    with st.spinner("Drawing..."):
        fig, note = _range_cached(tuple(dec_on), tuple(ea_names[e] for e in ea), *jds, db.orb_table().to_csv(index=False))
    # fixed size, scaled down whole to fit (its tags are placed for that size), as AstroMap
    st.html(mapchart.fit_html(fig), unsafe_allow_javascript=True)
    if note:
        st.caption(note)


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _range_cached(dec_on, ea, jd_from, jd_to, orb_csv):
    import io
    return rangechart.range_figure(list(dec_on), list(ea), jd_from, jd_to, core.Orbs(pd.read_csv(io.StringIO(orb_csv))))


def page_distance():
    row, prep = pick_customer()
    head = st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall")   # the title, then the inputs
    head.subheader("Planets Distance(%)", width="content", wrap=False)
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
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    st.caption("D = % between the planet's least and greatest distance from the Earth (1800-2400): 0 nearest, "
               "100 farthest.")


@st.cache_data(ttl=3600, max_entries=50, show_spinner=False)
def _distance_cached(dist_on, jd_from, jd_to):
    return distancechart.distance_figure(list(dist_on), jd_from, jd_to)


def page_tables():
    row, prep = pick_customer()
    st.subheader("Tables")
    if not need_chart(prep):
        return
    jd_now = core.now_jd()
    rows = []
    for p in core.PLANETS:
        b, n = core.position(p, prep.jd_birth), core.position(p, jd_now)
        d, dn = core.distance_pct(p, b.dist_au), core.distance_pct(p, n.dist_au)
        rows.append({"Planets": p, "D": d, "D-N": dn, "D-A": round((d + dn) / 2, 2), "_ra": prep.birth[p][0],
                     "_up_b": b.dist_speed >= 0, "_up_n": n.dist_speed >= 0})
    df = pd.DataFrame(rows).sort_values("_ra").reset_index(drop=True)

    def colour(col):
        key = "_up_b" if col.name == "D" else "_up_n"
        return [f"color: {'rgb(255,0,0)' if up else 'rgb(0,128,0)'}" for up in df[key]]

    shown = df[["Planets", "D", "D-N", "D-A"]]
    st.dataframe(shown.style.apply(colour, subset=["D", "D-N", "D-A"]).format({"D": "{:.1f}", "D-N": "{:.1f}", "D-A": "{:.1f}"}),
                 hide_index=True, width="content")
    st.caption("D = % between the planet's least and greatest distance (1800-2400); D at birth, D-N now, D-A their "
               "average. Red: distance growing, green: shrinking. Click a heading to sort.")


def page_aspects():
    if not user.is_admin:                                     # admins only (not in a user's menu either)
        st.stop()
    st.subheader("Aspects")
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
    st.subheader("Customers")
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
    st.subheader("My details")
    if row is None:
        st.info("No birth details are linked to your email yet. Ask the admin to add them.")
        return
    st.table(pd.DataFrame({"": [db.LABELS[f].split(" (")[0] for f in db.FIELDS if f not in ("email", "utc")],
                           "Value": [row[f] for f in db.FIELDS if f not in ("email", "utc")]}).astype(str))
    if prep and prep.ok:
        st.write(f"Born on a {prep.weekday}; UTC offset {prep.utc:+.2f} ({prep.tz}); birth place "
                 f"{prep.birth_lat}, {prep.birth_lon}.")


pages = [st.Page(page_map, title="AstroMap", icon=":material/public:", url_path="astromap", default=True),
         st.Page(page_distance, title="Planets Distance(%)", icon=":material/straighten:", url_path="planets-distance"),
         st.Page(page_range, title="Planets Cycles", icon=":material/show_chart:", url_path="planets-cycles"),
         st.Page(page_tables, title="Tables", icon=":material/table:", url_path="tables")]
if user.is_admin:                                             # the Aspects and Customers pages: admins only
    pages += [st.Page(page_aspects, title="Aspects", icon=":material/tune:", url_path="aspects"),
              st.Page(page_customers, title="Customers", icon=":material/group:", url_path="customers")]
else:
    pages.append(st.Page(page_my_details, title="My details", icon=":material/person:", url_path="me"))
st.navigation(pages).run()
st.sidebar.caption(f"Swiss Ephemeris via {se.BACKEND}. Equatorial (RA / Dec) only.")
