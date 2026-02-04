from __future__ import annotations

from dataclasses import dataclass

from app.common.config import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency fallback
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]


@dataclass
class ContentCipher:
    _fernet: Fernet | None

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            return plaintext
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        if not self._fernet:
            return ciphertext
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return ciphertext


def build_content_cipher() -> ContentCipher:
    key = settings.content_encryption_key
    if not key or Fernet is None:
        return ContentCipher(_fernet=None)

    try:
        fernet = Fernet(key.encode("utf-8"))
    except Exception:
        return ContentCipher(_fernet=None)
    return ContentCipher(_fernet=fernet)
