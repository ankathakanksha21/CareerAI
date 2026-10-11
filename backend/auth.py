"""Who is calling: a Supabase access token in, a User out.

Projects with signing keys issue ES256 or RS256 tokens, checked here against the project's
public keys (JWKS). Older projects sign with a shared secret (HS256); Supabase advises against
checking those locally, so they are validated by asking Supabase and the answer is cached."""
import hashlib
import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Header, HTTPException

from config import env, supabase_url

ASYMMETRIC = ("ES256", "RS256")
_jwks: tuple[str, jwt.PyJWKClient] | None = None  # (url it was built for, client)
_supabase_cache: dict[str, tuple[float, dict]] = {}  # sha256(token) -> (expires at, user)


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str


class AuthError(Exception):
    pass


def _signing_key(token: str):
    global _jwks
    url = f"{supabase_url()}/auth/v1/.well-known/jwks.json"
    if not _jwks or _jwks[0] != url:
        _jwks = (url, jwt.PyJWKClient(url, cache_keys=True, lifespan=600))
    return _jwks[1].get_signing_key_from_jwt(token).key


def _user_from_supabase(token: str) -> dict:
    now = time.time()
    digest = hashlib.sha256(token.encode()).hexdigest()
    cached = _supabase_cache.get(digest)
    if cached and cached[0] > now:
        return cached[1]
    try:
        r = httpx.get(f"{supabase_url()}/auth/v1/user", timeout=10,
                      headers={"apikey": env("SUPABASE_PUBLISHABLE_KEY"), "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise AuthError("could not reach Supabase") from e
    if r.status_code != 200:
        raise AuthError("Supabase rejected the token")
    user = r.json()
    expires = jwt.decode(token, options={"verify_signature": False}).get("exp", 0)
    for key in [k for k, (until, _) in _supabase_cache.items() if until <= now]:
        del _supabase_cache[key]
    _supabase_cache[digest] = (float(expires), user)
    return user


def verify_token(token: str) -> User:
    if not supabase_url():
        raise AuthError("SUPABASE_URL is not set")
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg in ASYMMETRIC:
            claims = jwt.decode(token, _signing_key(token), algorithms=list(ASYMMETRIC), audience="authenticated",
                                issuer=f"{supabase_url()}/auth/v1", options={"require": ["exp", "sub"]})
            if claims.get("role") != "authenticated":
                raise AuthError("not a signed-in user")
            user_id, email, meta = claims["sub"], claims.get("email"), claims.get("user_metadata")
        elif alg == "HS256":
            user = _user_from_supabase(token)
            user_id, email, meta = user["id"], user.get("email"), user.get("user_metadata")
        else:
            raise AuthError(f"unsupported token algorithm: {alg}")
    except (jwt.PyJWTError, KeyError) as e:
        raise AuthError(str(e)) from e
    return User(id=str(user_id), email=email or "", name=((meta or {}).get("full_name") or "").strip())


def current_user(authorization: str | None = Header(None)) -> User:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Sign in to continue.")
    try:
        return verify_token(token.strip())
    except AuthError:
        raise HTTPException(401, "Sign in to continue.")
