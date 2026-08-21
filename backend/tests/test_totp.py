from __future__ import annotations

from app.services.totp import (
    build_otpauth_uri,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    recovery_code_index,
    totp_code,
    verify_totp,
)


def test_totp_roundtrip(monkeypatch):
    secret = generate_totp_secret()
    fixed_time = 1_700_000_000
    code = totp_code(secret, at_time=fixed_time)
    monkeypatch.setattr("app.services.totp.time.time", lambda: fixed_time)
    assert len(code) == 6
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000") or code == "000000"


def test_otpauth_uri_contains_account_and_secret():
    secret = generate_totp_secret()
    uri = build_otpauth_uri(secret, "admin@example.com")
    assert uri.startswith("otpauth://totp/")
    assert secret in uri
    assert "issuer=ARGWS%20Git%20Monitor" in uri


def test_recovery_codes_can_be_located_without_storing_plain_text():
    codes = generate_recovery_codes(4)
    hashes = [hash_recovery_code(code) for code in codes]
    assert len(codes) == 4
    assert len(set(codes)) == 4
    assert all(code not in hashes for code in codes)
    assert recovery_code_index(codes[2].lower(), hashes) == 2
    assert recovery_code_index("INVALID-CODE", hashes) is None
