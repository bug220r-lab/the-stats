"""Provider authentication and explicit authorization, before reading any data."""
from dataclasses import dataclass
import json
import time
from urllib.parse import urlparse

from stats_app.config import Settings


@dataclass(frozen=True)
class Principal:
    name: str
    role: str


def require_admin(principal: Principal) -> None:
    if principal.role != "admin":
        raise PermissionError("Only an approved admin can import data.")


def approved_users(settings: Settings) -> list[dict]:
    if not settings.approved_users_file:
        raise ValueError("Hosted access denied: configure STATS_APPROVED_USERS_FILE.")
    if urlparse(settings.expected_issuer).scheme != "https":
        raise ValueError("Hosted access denied: STATS_EXPECTED_ISSUER must be an HTTPS issuer.")
    users = json.loads(settings.approved_users_file.read_text(encoding="utf-8"))
    if not isinstance(users, list) or not users:
        raise ValueError("Hosted access denied: approved-user list is empty.")
    seen = set()
    for user in users:
        if not isinstance(user, dict) or user.get("role") not in {"viewer", "admin"}:
            raise ValueError("Invalid approved-user role.")
        if user.get("issuer") != settings.expected_issuer or not user.get("subject") or not user.get("name"):
            raise ValueError("Each approved user needs an issuer, subject, name and role.")
        if "REPLACE" in str(user) or "<" in str(user):
            raise ValueError("Replace all approved-user placeholders before hosting.")
        key = (user["issuer"], user["subject"])
        if key in seen:
            raise ValueError("Duplicate approved identity.")
        seen.add(key)
    return users


def authorize_claims(claims: dict, users: list[dict], expected_issuer: str) -> Principal:
    if claims.get("iss") != expected_issuer or not claims.get("sub"):
        raise PermissionError("Access denied: unexpected provider or missing subject.")
    try:
        valid_expiry = float(claims.get("exp", 0)) > time.time()
    except (TypeError, ValueError):
        valid_expiry = False
    if not valid_expiry:
        raise PermissionError("Sign-in expired or expiry unavailable. Sign in again.")
    for user in users:
        if user["issuer"] == claims["iss"] and user["subject"] == claims["sub"]:
            return Principal(user["name"], user["role"])
    raise PermissionError("Access denied: this identity is not on the approved-user list.")


def enforce_access(settings: Settings) -> Principal:
    import streamlit as st
    if settings.mode == "local":
        if st.get_option("server.address") != "127.0.0.1":
            st.error("Local access refused. Bind server.address to 127.0.0.1 or configure hosted access.")
            st.stop()
        return Principal("Local user", "admin")
    try:
        users = approved_users(settings)
        auth = dict(st.secrets["auth"])
        required = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
        if any(not auth.get(key) or "REPLACE" in str(auth[key]) or "<" in str(auth[key]) for key in required):
            raise ValueError("Hosted access denied: provider sign-in is not fully configured.")
        if any(urlparse(auth[key]).scheme != "https" for key in ("redirect_uri", "server_metadata_url")):
            raise ValueError("Hosted provider URLs must use HTTPS.")
        if len(auth["cookie_secret"]) < 32:
            raise ValueError("Hosted cookie_secret must contain at least 32 random characters.")
    except (OSError, ValueError, KeyError) as exc:
        st.error(str(exc))
        st.stop()
    if not st.user.is_logged_in:
        st.info("This is a private dashboard. Sign in with the approved identity provider.")
        if st.button("Sign in"):
            st.login()
        st.stop()
    try:
        principal = authorize_claims(st.user.to_dict(), users, settings.expected_issuer)
    except PermissionError as exc:
        st.error(str(exc))
        if st.button("Sign out"):
            st.logout()
        st.stop()
    st.sidebar.caption(f"{principal.name} · {principal.role}")
    if st.sidebar.button("Sign out"):
        st.logout()
    return principal
