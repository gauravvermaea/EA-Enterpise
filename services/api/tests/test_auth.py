import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from eax import auth

ISSUER = "https://localhost/auth/realms/eaexplorer"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


def make_token(private_key, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER, "aud": ["eax-api", "account"], "sub": "u1", "iat": now, "exp": now + 300,
        "preferred_username": "eaadmin", "email": "eaadmin@example.org",
        "realm_access": {"roles": ["viewer", "system-admin"]},
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_valid_token_gives_user_and_roles(keypair):
    private, public = keypair
    claims = auth.decode_token(make_token(private), key=public)
    user = auth.user_from_claims(claims)
    assert user.username == "eaadmin"
    assert user.has_role("system-admin")


def test_issuer_with_explicit_port_is_accepted(keypair):
    private, public = keypair
    token = make_token(private, iss="https://localhost:443/auth/realms/eaexplorer")
    assert auth.decode_token(token, key=public)["iss"].endswith("/eaexplorer")


def test_wrong_audience_is_refused(keypair):
    private, public = keypair
    with pytest.raises(jwt.InvalidAudienceError):
        auth.decode_token(make_token(private, aud="something-else"), key=public)


def test_foreign_issuer_is_refused(keypair):
    private, public = keypair
    with pytest.raises(jwt.InvalidIssuerError):
        auth.decode_token(make_token(private, iss="https://evil.example/realms/x"), key=public)


def test_protected_endpoints_need_a_token(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/jobs/heartbeat", json={}).status_code in (401, 422)
    assert client.get("/api/v1/audit").status_code == 401
