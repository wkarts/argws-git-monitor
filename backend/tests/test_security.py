from app.core.encryption import EncryptionService
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("StrongPassword@123")
    assert hashed != "StrongPassword@123"
    assert verify_password("StrongPassword@123", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip():
    token, _ = create_access_token("00000000-0000-0000-0000-000000000001", is_superuser=True)
    payload = decode_access_token(token)
    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["superuser"] is True


def test_refresh_token_is_stored_as_hash():
    raw, hashed, _ = create_refresh_token()
    assert raw != hashed
    assert hash_refresh_token(raw) == hashed


def test_encryption_roundtrip():
    service = EncryptionService()
    encrypted = service.encrypt("github_pat_very-secret-token")
    assert "very-secret" not in encrypted
    assert service.decrypt(encrypted) == "github_pat_very-secret-token"
