import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

import auth

SUB = "11111111-1111-1111-1111-111111111111"
ISSUER = "https://proj.supabase.co/auth/v1"


@pytest.fixture(autouse=True)
def supabase_env(no_env_file, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(auth, "_supabase_cache", {})


@pytest.fixture
def key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def make_token(key, monkeypatch):
    monkeypatch.setattr(auth, "_signing_key", lambda token: key.public_key())

    def make(signing_key=None, **overrides):
        claims = {
            "sub": SUB, "email": "a@example.test", "role": "authenticated", "aud": "authenticated",
            "iss": ISSUER, "exp": int(time.time()) + 3600, "user_metadata": {"full_name": "Test User"},
        } | overrides
        return jwt.encode(claims, signing_key or key, algorithm="ES256")

    return make


def hs256_token(**overrides):
    claims = {"sub": SUB, "role": "authenticated", "aud": "authenticated", "iss": ISSUER,
              "exp": int(time.time()) + 3600} | overrides
    return jwt.encode(claims, "a-shared-secret-of-at-least-32-bytes!", algorithm="HS256")


def test_valid_token_returns_user(make_token):
    assert auth.verify_token(make_token()) == auth.User(id=SUB, email="a@example.test", name="Test User")


def test_missing_name_gives_empty_string(make_token):
    assert auth.verify_token(make_token(user_metadata={})).name == ""


def test_expired_token_rejected(make_token):
    with pytest.raises(auth.AuthError):
        auth.verify_token(make_token(exp=int(time.time()) - 10))


def test_wrong_issuer_rejected(make_token):
    with pytest.raises(auth.AuthError):
        auth.verify_token(make_token(iss="https://evil.example/auth/v1"))


def test_non_authenticated_role_rejected(make_token):
    with pytest.raises(auth.AuthError):
        auth.verify_token(make_token(role="anon"))


def test_forged_signature_rejected(make_token):
    forged = make_token(signing_key=ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(auth.AuthError):
        auth.verify_token(forged)


def test_garbage_token_rejected():
    with pytest.raises(auth.AuthError):
        auth.verify_token("not-a-jwt")


def test_unsigned_token_rejected():
    # alg "none" must never be accepted, whatever the claims say
    header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
    body = jwt.utils.base64url_encode(
        f'{{"sub":"{SUB}","role":"authenticated","aud":"authenticated","iss":"{ISSUER}","exp":{int(time.time()) + 3600}}}'.encode()
    ).decode()
    with pytest.raises(auth.AuthError):
        auth.verify_token(f"{header}.{body}.")


def test_hs256_token_uses_supabase_check(monkeypatch):
    monkeypatch.setattr(auth, "_user_from_supabase",
                        lambda token: {"id": SUB, "email": "b@example.test", "user_metadata": {"full_name": "B"}})
    assert auth.verify_token(hs256_token()) == auth.User(id=SUB, email="b@example.test", name="B")


def test_hs256_rejected_when_supabase_says_no(monkeypatch):
    def refuse(token):
        raise auth.AuthError("rejected")
    monkeypatch.setattr(auth, "_user_from_supabase", refuse)
    with pytest.raises(auth.AuthError):
        auth.verify_token(hs256_token())


def test_supabase_check_is_cached_until_expiry(monkeypatch):
    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers))
        return httpx.Response(200, json={"id": SUB, "email": "b@example.test"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(auth.httpx, "get", fake_get)
    token = hs256_token()

    assert auth.verify_token(token).id == SUB
    assert auth.verify_token(token).id == SUB

    assert len(calls) == 1
    url, headers = calls[0]
    assert url == "https://proj.supabase.co/auth/v1/user"
    assert headers == {"apikey": "sb_publishable_test", "Authorization": f"Bearer {token}"}


def test_supabase_check_non_200_rejected(monkeypatch):
    monkeypatch.setattr(auth.httpx, "get", lambda url, headers, timeout: httpx.Response(
        401, json={"msg": "invalid JWT"}, request=httpx.Request("GET", url)))
    with pytest.raises(auth.AuthError):
        auth.verify_token(hs256_token())


def test_supabase_check_network_error_rejected(monkeypatch):
    def boom(url, headers, timeout):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(auth.httpx, "get", boom)
    with pytest.raises(auth.AuthError):
        auth.verify_token(hs256_token())


def test_dependency_returns_user_for_bearer_token(make_token):
    assert auth.current_user(f"Bearer {make_token()}").id == SUB


def test_dependency_401_without_header():
    with pytest.raises(HTTPException) as e:
        auth.current_user(None)
    assert e.value.status_code == 401
    assert e.value.detail == "Sign in to continue."


def test_dependency_401_bad_scheme():
    with pytest.raises(HTTPException) as e:
        auth.current_user("Token abc")
    assert e.value.status_code == 401


def test_dependency_401_for_rejected_token():
    with pytest.raises(HTTPException) as e:
        auth.current_user("Bearer not-a-jwt")
    assert e.value.status_code == 401
