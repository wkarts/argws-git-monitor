from __future__ import annotations

import hashlib
import hmac


def verify_github_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Validate GitHub's X-Hub-Signature-256 header in constant time."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
