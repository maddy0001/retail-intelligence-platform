"""
security.py — password hashing, login tokens and the FastAPI auth dependencies.

Passwords are hashed with scrypt (Python standard library) and a random salt;
the plain password is never stored. Logins return a signed JWT (HS256) that
the React app sends as `Authorization: Bearer <token>`.
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import COLL_USERS
from .db import get_db
from .settings import settings

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                   n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(digest)))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user["_id"]), "role": user.get("role", "customer"),
               "cid": user.get("customer_id"), "iat": now,
               "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def user_from_token(db, token: str):
    try:
        payload = decode_token(token)
        return db[COLL_USERS].find_one({"_id": ObjectId(payload["sub"])})
    except (jwt.PyJWTError, InvalidId, KeyError):
        return None


_bearer = HTTPBearer(auto_error=False)


def optional_user(creds: HTTPAuthorizationCredentials = Depends(_bearer), db=Depends(get_db)):
    if not creds:
        return None
    return user_from_token(db, creds.credentials)


def current_user(user=Depends(optional_user)):
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in to continue.",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_admin(user=Depends(current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")
    return user


def public_user(user: dict) -> dict:
    return {"id": str(user["_id"]), "name": user.get("name"), "email": user.get("email"),
            "role": user.get("role", "customer"), "customer_id": user.get("customer_id")}
