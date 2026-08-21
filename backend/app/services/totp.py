from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

import qrcode

from app.core.config import get_settings

TOTP_PERIOD = 30
TOTP_DIGITS = 6
TOTP_ALGORITHM = "SHA1"


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def totp_code(secret: str, *, at_time: int | None = None) -> str:
    timestamp = int(time.time() if at_time is None else at_time)
    counter = timestamp // TOTP_PERIOD
    digest = hmac.new(
        _decode_secret(secret),
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp(secret: str, code: str, *, window: int = 1) -> bool:
    normalized = "".join(character for character in code if character.isdigit())
    if len(normalized) != TOTP_DIGITS:
        return False
    now = int(time.time())
    return any(
        hmac.compare_digest(totp_code(secret, at_time=now + offset * TOTP_PERIOD), normalized)
        for offset in range(-window, window + 1)
    )


def build_otpauth_uri(secret: str, account: str, *, issuer: str = "ARGWS Git Monitor") -> str:
    label = f"{issuer}:{account}"
    return (
        f"otpauth://totp/{quote(label, safe='')}?"
        f"secret={quote(secret)}&issuer={quote(issuer)}&algorithm={TOTP_ALGORITHM}"
        f"&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


def build_qr_data_uri(uri: str) -> str:
    image = qrcode.make(uri, box_size=7, border=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def generate_recovery_codes(count: int = 8) -> list[str]:
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(5).upper()
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    settings = get_settings()
    normalized = code.strip().replace(" ", "").upper()
    value = f"{settings.app_secret_key}:{normalized}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def recovery_code_index(code: str, hashes: list[str]) -> int | None:
    candidate = hash_recovery_code(code)
    for index, stored_hash in enumerate(hashes):
        if hmac.compare_digest(candidate, stored_hash):
            return index
    return None
