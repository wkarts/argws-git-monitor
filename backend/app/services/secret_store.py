from __future__ import annotations

import json
from typing import Any

from app.core.encryption import EncryptionService


class SecretStore:
    """Serializa e criptografa secrets. Nunca devolve o valor completo para schemas de leitura."""

    def __init__(self) -> None:
        self.encryption = EncryptionService()

    def encrypt_dict(self, value: dict[str, Any] | None) -> str | None:
        if not value:
            return None
        return self.encryption.encrypt(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )

    def decrypt_dict(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        payload = json.loads(self.encryption.decrypt(value))
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def hint(value: dict[str, Any] | None) -> str | None:
        if not value:
            return None
        for key in ("access_token", "token", "secret_key", "password", "private_key", "key"):
            raw = str(value.get(key) or "")
            if raw:
                tail = raw[-4:] if len(raw) >= 4 else raw
                return f"{key}:****************{tail}"
        return "credencial protegida"
