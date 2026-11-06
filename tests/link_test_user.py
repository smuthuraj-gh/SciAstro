"""Local test helper: link a customer to a login email in the local SQLite store (python tests/link_test_user.py NAME EMAIL)."""
import sys
from pathlib import Path

import sqlalchemy as sa

db = Path(__file__).resolve().parent.parent / "private" / "app.db"
name, email = sys.argv[1], sys.argv[2]
with sa.create_engine(f"sqlite:///{db.as_posix()}").begin() as c:
    n = c.execute(sa.text("update customers set email = :e where name = :n"), {"e": email.lower(), "n": name}).rowcount
print(f"{n} customer(s) named {name} linked to {email}")
