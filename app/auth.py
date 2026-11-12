"""Who is signed in, and what they may see.

Sign-in is Streamlit's built-in OpenID Connect login (st.login), configured in secrets under [auth] (e.g. Google).
Admins are the emails listed in the secret `admins`, and anyone whose customer record has Access Admin;
they see and edit every customer and the orb table. Everyone else sees only the customers whose Email matches theirs
(several for a Group), and what their Access allows (app/access.py).

For running on your own PC only, the secret `dev_user` (an email) signs in as that user without a login provider.
Never set it on a hosted app.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from .db import _secret, has_admin_rights


@dataclass
class User:
    email: str
    name: str
    is_admin: bool
    dev: bool = False


def _admins() -> set[str]:
    a = _secret("admins", [])
    if isinstance(a, str):
        a = [x for x in a.replace(";", ",").split(",")]
    return {x.strip().lower() for x in a if x and x.strip()}


def _is_admin(email: str) -> bool:
    """An admin: listed in the admins secret, or made one by their customer record (Access Admin)."""
    return email in _admins() or has_admin_rights(email)


def _auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def current_user() -> User:
    """The signed-in user; shows the sign-in screen (and stops) when nobody is."""
    dev = _secret("dev_user")
    if dev and st.get_option("server.address") not in ("localhost", "127.0.0.1"):
        st.error("dev_user is set, but this server is not limited to localhost: remove dev_user from the secrets.")
        st.stop()
    if dev:
        email = str(dev).strip().lower()
        return User(email, email, _is_admin(email), dev=True)
    if not _auth_configured():
        st.error("Sign-in is not set up yet: add an [auth] section to the app's secrets (see README).")
        st.stop()
    if not st.user.is_logged_in:
        st.title("Equatorial charts")
        st.write("Sign in to see your charts.")
        if st.button("Sign in with Google", type="primary"):
            st.login()
        st.stop()
    email = (st.user.get("email") or "").lower()
    if not email or (st.user.get("email_verified") is False):
        st.error("Your sign-in did not give a verified email address.")
        st.stop()
    return User(email, st.user.get("name") or email, _is_admin(email))


def sign_out_button(user: User):
    if user.dev:
        st.sidebar.caption(f"Local test sign-in: {user.email}")
    elif st.sidebar.button("Sign out"):
        st.logout()
