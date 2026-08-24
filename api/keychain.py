"""Small Keychain adapter with no plaintext fallback."""

from __future__ import annotations

import json
from typing import Any


class KeychainStore:
    """Store one JSON secret per provider profile in the platform keyring."""

    def __init__(self, service: str) -> None:
        self.service = service

    def _module(self):
        try:
            import keyring  # type: ignore
        except ImportError as exc:  # pragma: no cover - packaged app supplies it
            raise RuntimeError("API 密钥存储需要 keyring/macOS Keychain 依赖") from exc
        return keyring

    def get(self, account: str) -> dict[str, Any]:
        value = self._module().get_password(self.service, account)
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def set(self, account: str, value: dict[str, Any]) -> None:
        self._module().set_password(self.service, account, json.dumps(value, ensure_ascii=False))

    def delete(self, account: str) -> None:
        try:
            self._module().delete_password(self.service, account)
        except Exception:
            # Deletion is idempotent when the account is already absent.
            pass
