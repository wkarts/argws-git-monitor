import hashlib
import hmac

from app.services.webhook_security import verify_github_signature


def test_github_webhook_signature():
    body = b'{"zen":"test"}'
    secret = "test-webhook-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_github_signature(body, signature, secret)
    assert not verify_github_signature(body + b"x", signature, secret)
    assert not verify_github_signature(body, None, secret)
