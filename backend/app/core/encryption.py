from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionService:
    def __init__(self, key: str | None = None) -> None:
        configured_key = key or get_settings().encryption_key
        self._fernet = Fernet(configured_key.encode("utf-8"))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Não foi possível descriptografar a credencial armazenada.") from exc
