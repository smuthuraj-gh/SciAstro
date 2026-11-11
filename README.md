# Equatorial charts (web)

The web version of the Excel workbook `Sen_Test_v2.xlsm`: Swiss Ephemeris RA / Dec only (no tropical or sidereal
zodiac), with the same rules.

| Page | Who | What |
|---|---|---|
| AstroClock-2D | everyone | the top page of the menu: the Geo drawing in 2D, seen from above the north celestial pole, each body at its RA and its distance from the Earth, with only the 12 AU circle and an RA scale round it, 1 to 360, tagged RA below the clock, a Declination graph to its left from +31 to -31 degrees with each body at its Dec, a Distance(%) graph to its right from 0 to 100 with the planets at Ave and DOB left of its line and at Now right of it, an arrow from the Earth through each body out to the circle, and the twelve house lines, H01 to H12 (their tags turned along the circle), 30 degrees apart from the RA of CB (solid) and of CN (dotted), turning with the Earth, shown with the Houses button (on to start); always on the Fit scale; buttons Time, Planets (with NN, SN: on the Moon's path, at the Moon's distance, joined by a line, 180 degrees apart) and Rotate in 1s (Manual: time stands still; 1s, 1m, 1h, 1d, 1w, 1mo, 1y: that much time each second), its own choices, starting as the Defaults table says |
| AstroClock-3D | everyone | the Earth inside the celestial sphere, its axis fixed at a 23.44 degree tilt and joining the celestial poles, turning about that axis west to east while the sphere stands still and time runs on a date and time clock; each planet moving over the sphere at its RA and Dec as it really did, sized by its angular size then (logarithmic scale), with its RA and Dec lines, the celestial equator, and CB / CN on the Earth; Time, with Now / DOB below it / Planets, with Su / Mo / Me / Ve / Ma / Ju / Sa below it to pick which to show / Major Aspects (0, 60, 90, 120, 180) / Minor Aspects (30, 45, 72, 135, 144, 150) drawing the aspects between the planets as time runs / Coordinates, with House / RA / Dec / Lati / Long below it (Lati, Long: the Earth's lines of latitude and longitude, every 30 degrees) / Planet Path, with Su / Mo / Me / Ve / Ma / Ju / Sa below it to pick from (each over one trip round the sky) / Rotate in 1s, with Manual (drag to turn the view and see the hidden side; time stands still) / 1s / 1m / 1h / 1d / 1w / 1mo / 1y (that much time each second; 1m a minute, 1mo a month) below it |
| Aspects Table | everyone | Planets Cycles' aspects as tables: one per angle, one row per aspect (date, planets, their Dec), newest first; a Major Aspects button with 0, 60, 90, 120, 180 to pick from below it, and a Minor Aspects button with 30, 45, 72, 135, 144, 150 |
| Planets Cycles | everyone | Dec (-M) lines from birth to now, with dots and tags for the Major Aspects (0, 60, 90, 120, 180) and Minor Aspects (30, 45, 72, 135, 144, 150) picked |
| Planets Distance(%) | everyone | distance (-D) lines from birth to now: D, the % between each planet's nearest and farthest |
| Geo/Helio Model | everyone | Centric Model: Geo (GeoCentric) or Helio (HelioCentric). GeoCentric: the paths of the Sun, Moon and planets in 3D, each at its real distance from the Earth (Fit: each tenfold distance the same room, without the empty space between the Moon and the planets; or True); Rotate in 1s: Manual to drag it round, or a speed to run time. HelioCentric: as GeoCentric, with the Sun at the centre: the paths of the planets and the Earth around the Sun in 3D, and the Moon round the Earth (a dot, drawn farther out than to scale), each at its real distance from the Sun (RA, Dec and distance as seen from the Sun; Fit or True) |
| Aspect Rules | admins | the orbs per aspect and planet; a pair uses the larger of its two planets' orbs; Insert, Update, Delete, Commit |
| Customers | admins | Insert, Update, Delete, Commit customers, click a column name to sort; import the workbook's Customers tab as CSV |
| Symbols | admins | the table in the database: SAbr (unique), Symb (shown in place of the SAbr on the pages), SDesc, RGB (the charts' colours for the planets, Ea, NN, SN, CN and CB), Color (its name, for reference), Size_Clock-2D (how AstroClock-2D, its Dec and Distance(%) graphs size the planets, Ea, the nodes and places), Size_Clock-3D (the same, on AstroClock-3D), Size_Geo (on Geo/Helio Model's Geo), Size_Helio (on its Helio); Insert, Update, Delete, Commit; click a column name to sort |
| Defaults | admins | the table in the database: Page, Options (a page input) and Choices (what it starts as: the buttons on; DOB or Now; Start Date (UT) + a time), one row per Page and Title, read by every page as it is drawn; sorted by Page, Title, Options; Insert, Update, Delete, Commit; click a column name to sort |
| Logins | admins | the table in the database, newest first: Email (who was signed in), Activity (View: opened a customer, once per visit; Create, Update, Delete: a customer added, changed or deleted), Date_Time (UT); tick rows and Delete, or Delete all (asks first) |
| My details | users | their own birth details, with Edit my details to change them (the login email stays) |

Users sign in with Google and see only the customers whose **Email (login)** is theirs. A new member (no customer
has their email yet) gets a form to enter their own birth details, saved with their login email; a member already
there goes straight to their charts. The login email is the key: one customer per email (First Names may repeat).
Admins are listed in the `admins` secret.

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
5. Sign in with your admin Google account, open **Customers**, import the workbook's Customers CSV, and type each
   customer's Google email in **Email (login)**.

## Licence

Swiss Ephemeris (and so `pyswisseph` and the `.se1` files in `ephe/`) is under the GNU AGPL: anyone using the hosted
app must be able to get its source, so this code is published under the AGPL too (a public GitHub repository does
this; see `LICENSE`). Customer data never goes in the repository.

Source: https://github.com/smuthuraj-gh/SciAstro
