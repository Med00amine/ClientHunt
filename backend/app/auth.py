import hashlib
import hmac
import time

from fastapi import Depends, HTTPException, Request

from .config import get_settings

COOKIE = "ch_session"
MAX_AGE = 12 * 3600


def _sign(ts: str) -> str:
    return hmac.new(get_settings().session_secret.encode(), ts.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def valid_token(tok: str | None) -> bool:
    if not tok or "." not in tok:
        return False
    ts, sig = tok.split(".", 1)
    return ts.isdigit() and hmac.compare_digest(sig, _sign(ts)) and time.time() - int(ts) < MAX_AGE


def auth_enabled() -> bool:
    return bool(get_settings().app_password)


def require_auth(request: Request) -> None:
    if auth_enabled() and not valid_token(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Not authenticated")


Authed = Depends(require_auth)
