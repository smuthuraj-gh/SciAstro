# Equatorial charts (web)

The web version of the Excel workbook `Sen_Test_v2.xlsm`: Swiss Ephemeris RA / Dec only (no tropical or sidereal
zodiac), with the same rules.

| Page | Who | What |
|---|---|---|
| AstroGlobe | everyone | the Earth inside the celestial sphere, each planet's Distance(%) from earth (DOB+Now)/2 and on DOB beside the buttons, its axis fixed at a 23.44 degree tilt and joining the celestial poles, turning about that axis west to east while the sphere stands still and time runs on a date and time clock; each planet moving over the sphere at its RA and Dec as it really did, sized by its angular size then (logarithmic scale), with its RA and Dec lines, the celestial equator, and CB / CN on the Earth; Time, with Now / DOB below it / Planets, with Su / Mo / Me / Ve / Ma / Ju / Sa below it to pick which to show / Maj Aspects (0, 60, 90, 120, 180) / Min Aspects (30, 45, 72, 135, 144, 150) drawing the aspects between the planets as time runs / Coordinates, with House / RA / Dec / Lati / Long below it (Lati, Long: the Earth's lines of latitude and longitude, every 30 degrees) / Planet Path, with Su / Mo / Me / Ve / Ma / Ju / Sa below it to pick from (each over one trip round the sky) / Rotate in 1s, with Manual (drag to turn the view and see the hidden side; time stands still) / 1h / 1d / 1w / 1m (that much time each second) below it |
| Aspects | everyone | Planets Cycles' aspects as tables: one per angle, one row per aspect (date, planets, their Dec), newest first; a Major Aspects button (all five major angles) and a Minor Aspects button (30° / 45° / 72° / 135° / 144° / 150°) |
| Planets Cycles | everyone | Dec (-M) lines from birth to now, with 0° / 60° / 90° / 120° / 180° aspect dots and tags |
| Planets Distance(%) | everyone | distance (-D) lines from birth to now: D, the % between each planet's nearest and farthest |
| GeoCentric | everyone | the paths of the Sun, Moon and planets in 3D, each at its real distance from the Earth (Log, True, or True-Log: Log without the empty space between the Moon and the planets); Rotate in 1s: Manual to drag it round, or a speed to run time |
| Aspects Details | admins | the orbs per aspect and planet; a pair uses the larger of its two planets' orbs; Insert, Update, Delete, Commit |
| Customers | admins | Insert, Update, Delete, Commit customers, click a column name to sort; import the workbook's Customers tab as CSV |
| Naming Conventions | admins | the table in the database: SAbr (unique), Symb (shown in place of the SAbr on the pages), SDesc, RGB (the charts' colours for the planets, Ea, NN, SN, CN and CB), Color (its name, for reference), Size (how the charts size the planets and Ea); Insert, Update, Delete, Commit; click a column name to sort |
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
