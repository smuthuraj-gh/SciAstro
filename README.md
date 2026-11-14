# Equatorial charts (web)

The web version of the Excel workbook `Sen_Test_v2.xlsm`: Swiss Ephemeris RA / Dec only (no tropical or sidereal
zodiac), with the same rules.

| Page | Who | What |
|---|---|---|
| AstroClock-2D | everyone | the top page of the menu: the Geo drawing in 2D, seen from above the north celestial pole, each body at its RA and its distance from the Earth, with only the 12 AU circle and an RA scale round it, 1 to 360, tagged RA below the clock, a Declination graph to its left from +31 to -31 degrees with each body at its Dec, a Distance(%) graph to its right from 0 to 100 with the planets at DOB and Now left of its line and at Ave right of it, an arrow from the Earth through each body out to the circle, and the twelve house lines, H01 to H12 (their tags turned along the circle), 30 degrees apart from the RA of CB (dotted) and of CN (solid), turning with the Earth, shown with the House button under Coordinates (on to start); Aspect, also under Coordinates, puts every planet on one circle at its RA, whatever its distance, to see conjunctions; always on the Fit scale; buttons Time, Planets (with NN, SN: on the Moon's path, at the Moon's distance, joined by a line, 180 degrees apart), Major Aspects and Minor Aspects (the angles to draw as lines between planets in aspect), and Rotate in 1s (1s, 1m, 1h, 1d, 1w, 1mo, 1y: that much time each second; none picked: time stands still, and dragging the drawing sideways moves it), its own choices, starting as the Defaults table says |
| AstroClock-3D | everyone | the Earth inside the celestial sphere, its axis fixed at a 23.44 degree tilt and joining the celestial poles, turning about that axis west to east while the sphere stands still and time runs on a date and time clock; each planet moving over the sphere at its RA and Dec as it really did, sized by its angular size then (logarithmic scale), with its RA and Dec lines, the celestial equator, and CB / CN on the Earth; Time, with Now / DOB below it / Planets, with Su / Mo / Me / Ve / Ma / Ju / Sa below it to pick which to show / Major Aspects (0, 60, 90, 120, 180) / Minor Aspects (30, 45, 72, 135, 144, 150) drawing the aspects between the planets as time runs / Coordinates, with House / RA / Dec / Lati / Long below it (Lati, Long: the Earth's lines of latitude and longitude, every 30 degrees) / Planet Path, with Su / Mo / Me / Ve / Ma / Ju / Sa below it to pick from (each over one trip round the sky) / Rotate in 1s, with Manual (drag to turn the view and see the hidden side; time stands still) / 1s / 1m / 1h / 1d / 1w / 1mo / 1y (that much time each second; 1m a minute, 1mo a month) below it |
| Aspects | everyone | Planets Cycles' aspects as tables: one per angle, one row per aspect (date, planets, their Dec), newest first; a Major Aspects button with 0, 60, 90, 120, 180 to pick from below it, and a Minor Aspects button with 30, 45, 72, 135, 144, 150 |
| Planets Cycles | everyone | Dec (-M) lines from birth to now, with dots and tags for the Major Aspects (0, 60, 90, 120, 180) and Minor Aspects (30, 45, 72, 135, 144, 150) picked |
| Planets Distance(%) | everyone | distance (-D) lines from birth to now: D, the % between each planet's nearest and farthest |
| Geo/Helio Model | everyone | Centric Model: Geo (GeoCentric) or Helio (HelioCentric). GeoCentric: the paths of the Sun, Moon and planets in 3D, each at its real distance from the Earth (Fit: each tenfold distance the same room, without the empty space between the Moon and the planets; or True); Rotate in 1s: Manual to drag it round, or a speed to run time. HelioCentric: as GeoCentric, with the Sun at the centre: the paths of the planets and the Earth around the Sun in 3D, and the Moon round the Earth (a dot, drawn farther out than to scale), each at its real distance from the Sun (RA, Dec and distance as seen from the Sun; Fit or True) |
| Aspect Rules | admins | the orbs per aspect and planet, an RA orb and a Dec orb each (RA within the RA orb of the angle, the two Decs within the Dec orb of equal or mirrored); a pair uses the larger of its two planets' orbs; Insert, Update, Delete, Commit |
| Customers | admins | one row per login: Email, Access (Now, DOB, Admin), Start Date (as the admin sets it, else when Access or Days was saved) and End Date (worked out, not typed: Start Date + Days, for DOB), with a Days box (how many days DOB lasts: typed, then Commit; not kept); a row is made with Now on someone's first sign-in; a login's first DOB record (signing up, or saved on the DOB page or imported) gives it DOB for 1 day (a new row, or one with Access Now); the DOB records refer to it by Email (a changed Email changes theirs too; a row they still use cannot be deleted) |
| DOB | admins | the customers' birth details: Insert, Update, Delete, Commit, click a column name to sort; import the workbook's Customers tab as CSV. |
| Symbols | admins | the table in the database: SAbr (unique), Symb (shown in place of the SAbr on the pages), SDesc, RGB (the charts' colours for the planets, Ea, NN, SN, CN and CB), Color (its name, for reference), Size_Clock-2D (how AstroClock-2D, its Dec and Distance(%) graphs size the planets, Ea, the nodes and places), Size_Clock-3D (the same, on AstroClock-3D), Size_Geo (on Geo/Helio Model's Geo), Size_Helio (on its Helio); Insert, Update, Delete, Commit; click a column name to sort |
| Defaults | admins | the table in the database: Page, Options (a page input) and Choices (what it starts as: the buttons on; DOB or Now; Start Date (UT) + a time), one row per Page and Title, read by every page as it is drawn; sorted by Page, Title, Options; Insert, Update, Delete, Commit; click a column name to sort |
| Logins | admins | the table in the database, newest first: Email (who was signed in), Activity (View: opened a customer, once per visit; Create, Update, Delete: a customer added, changed or deleted; Login: signed in with no birth details yet, once per visit), Date_Time (UT), Location (City, State, Country from the visitor's IP address, looked up once per visit with ipapi.co; Local on a local network; blank when not known), Device (their browser and system, e.g. Chrome on Windows), Time zone (their browser's), Access (theirs then; 'ended' after a trial ran out); tick rows and Delete, or Delete all (asks first) |
| DOB Details | users | their own birth details, seen and changed in Edit a DOB (the login email stays); Get more days: the customer picks 1, 7, 30, 90, 180 or 365 days and they are added at once (no payment yet), to their End Date while it runs, else from now (Access becomes DOB); DOB members have Add a DOB at the top of this page, for a person's form: Search Only shows that birth's charts, not saved, as a Search choice in the sidebar; Save and Search saves the person and shows theirs; each then goes to the chart page they came from (else AstroClock-2D) |

Drawing rule: wherever planets are drawn, on every page and graph, a smaller planet sits on top of a bigger one, so that it stays visible when they are close.

Layout rule: everything on all pages stays aligned to the top left.

Font rule: on all pages, text is at most 12 px and at least 10 px.

Now rule: anyone signed in can always see the Now charts, on every chart page: with no birth details, with Access Now or a DOB past its End Date, or with birth details that cannot be worked out (picking DOB then says why it is not open). The Time buttons show DOB first to someone whose Access is DOB, 1Day, DOBT or DOBGT, and Now first to anyone else, DOB still there (a new member picks it to reach the form for their birth details).

Users sign in with Google and see only the customers whose **Email (login)** is theirs. A new member (no customer
has their email yet) is not asked for anything: a Login row goes into the Logins table and they see the Now charts;
picking DOB opens the form for their birth details (also in DOB Details), saved with their login email, and brings
them back to the chart, now with DOB.
A member already there goes straight to their charts. The login email is the key: its own customer is the one with an Access (First Names may repeat), and it may have any
number more with Access blank (people the member added, or a family), which that login sees with DOB access. Admins are listed in the `admins` secret, or have Access Admin.

Access (app/access.py), on the Customers table, one row per login: Now, the Now charts only; DOB, the paid option (for Days days): the DOB and Now charts of every DOB record under their login, people they add (Add a DOB, on DOB Details), and births searched for there without saving (Search Only: a Search choice in the sidebar, which Save this birth there keeps as a person under their login); admins have New User in the sidebar for a birth typed in, not saved; Admin, an admin. End Date, worked out by the app: Start Date + the Days typed (not kept; a new DOB with none: 1 day); a changed Start Date counts from that day (keeping the length, or with the Days typed), a changed Access or Days typed alone from now; after End Date, the Now charts only. Someone signing in for the first time gets a row with Now; signing up with their birth details gives DOB for 1 day, which the admin can make longer by typing Days. When DOB (then called 1Day) came to end after 1 day, each such row with no End Date got 1 day from then, once. When the Customers table came in, each login's Access and Access_From were copied into it once from its first DOB record (blank: Now). Earlier Access names are changed to the new ones when the app starts: 1Day, 1Year, DOBG, Individual, Ind, Group and 1wu / 1mu / 1yu to DOB; the 1-day trials DOBT and DOBGT (and Trial-Ind, TrInd, TrDOB, Trial-Grp, TrGrp, TrGroup) to DOB with End Date 1 day after Start Date; Free, FreeInd and FreeGrp to Now.

## Run on this PC

```
cd C:\sweph\web
.venv\Scripts\streamlit run streamlit_app.py --server.address localhost
```

`.streamlit/secrets.toml` (not committed) holds `dev_user`, a test sign-in that works only on localhost.
Customers are kept in `private/app.db` (not committed). On Windows the Swiss Ephemeris DLL
`C:\sweph\bin\swedll64.dll` is used; elsewhere `pyswisseph`.

Check the calculations against the workbook (kept in private/, as it holds a customer's birth data): `.venv\Scripts\python private\tests\check_vs_excel.py`.

## Put it on Streamlit Community Cloud

1. **Database**: create a free Postgres database (Neon or Supabase) and copy its connection URL.
2. **Google sign-in**: in Google Cloud console create an OAuth client ID (Web application) with the redirect URI
   `https://YOUR-APP.streamlit.app/oauth2callback`.
3. **GitHub**: the code is at `smuthuraj-gh/SciAstro` (public, AGPLv3 `LICENSE`). `.venv`, `private` and
   `.streamlit/secrets.toml` are never pushed (`.gitignore` leaves them out).
4. **Deploy**: on share.streamlit.io choose New app, the repository, `streamlit_app.py`; under Advanced settings
   pick Python 3.12 and paste `secrets.example.toml` filled in. Do not add `dev_user`.
5. Sign in with your admin Google account, open **DOB**, import the workbook's Customers CSV, and type each
   customer's Google email in **Email (login)**.

## Licence

Swiss Ephemeris (and so `pyswisseph` and the `.se1` files in `ephe/`) is under the GNU AGPL: anyone using the hosted
app must be able to get its source, so this code is published under the AGPL too (a public GitHub repository does
this; see `LICENSE`). Customer data never goes in the repository.

Source: https://github.com/smuthuraj-gh/SciAstro
