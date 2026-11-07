# Equatorial charts (web)

The web version of the Excel workbook `Sen_Test_v2.xlsm`: Swiss Ephemeris RA / Dec only (no tropical or sidereal
zodiac), with the same rules.

| Page | Who | What |
|---|---|---|
| AstroMap | everyone | planets at birth and now over a world map turned by the sky; Map / DOB / Now / Major Aspects / Minor Aspects; each planet's D and Distance% Average beside the buttons, D-N beside the Longitude / RA title; aspect and house lines; hover a mark for RA, Dec, D |
| Planets Distance(%) | everyone | distance (-D) lines from birth to now: D, the % between each planet's nearest and farthest |
| Planets Cycles | everyone | Dec (-M) lines from birth to now, with 0° / 60° / 90° / 120° / 180° aspect dots and tags |
| Tables | everyone | Planets, D, D-N, Distance% Average |
| Aspects Details | admins | the orbs per aspect and planet; a pair uses the larger of its two planets' orbs |
| Customers | admins | add, edit, delete customers; import the workbook's Customers tab as CSV |
| My details | users | their own birth details |

Users sign in with Google and see only the customers whose **Email (login)** is theirs. Admins are listed in the
`admins` secret.

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
