"""Non-secret API profiles and macOS Keychain-backed credentials."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .keychain import KeychainStore


class SettingsLike(Protocol):
    def value(self, key: str, defaultValue: Any = None, type: type | None = None) -> Any: ...
    def setValue(self, key: str, value: Any) -> None: ...
    def sync(self) -> None: ...


@dataclass
class APIProviderProfile:
    """A provider configuration; secret fields are transient and never serialized."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    provider_type: str = "openai_compatible"
    name: str = "自定义模型"
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    timeout_s: int = 45
    prompt_override: str = ""
    enabled: bool = True
    api_key: str = field(default="", repr=False)
    app_id: str = field(default="", repr=False)
    app_key: str = field(default="", repr=False)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("api_key", "app_id", "app_key"):
            data.pop(key, None)
        data["timeout_s"] = max(5, min(120, int(self.timeout_s)))
        return data

    @classmethod
    def from_public_dict(cls, value: dict[str, Any]) -> "APIProviderProfile":
        allowed = {
            "id", "provider_type", "name", "base_url", "model", "timeout_s",
            "prompt_override", "enabled",
        }
        data = {key: value[key] for key in allowed if key in value}
        data["timeout_s"] = max(5, min(120, int(data.get("timeout_s", 45))))
        data["provider_type"] = str(data.get("provider_type", "openai_compatible"))
        return cls(**data)


class APIProfileStore:
    """Persist profile metadata in QSettings and secrets in the system keychain."""

    SERVICE = "FormulaOCR API"

    def __init__(self, settings: SettingsLike, keychain: KeychainStore | None = None) -> None:
        self.settings = settings
        self.keychain = keychain or KeychainStore(self.SERVICE)
        self.last_keychain_error: str | None = None

    @property
    def api_enabled(self) -> bool:
        return bool(self.settings.value("api_enabled", False, type=bool))

    def set_api_enabled(self, enabled: bool) -> None:
        self.settings.setValue("api_enabled", bool(enabled))
        self.settings.sync()

    @property
    def active_profile_id(self) -> str:
        return str(self.settings.value("api_active_profile", ""))

    def set_active_profile_id(self, profile_id: str) -> None:
        self.settings.setValue("api_active_profile", profile_id)
        self.settings.sync()

    def load_profiles(self) -> list[APIProviderProfile]:
        self.last_keychain_error = None
        raw = self.settings.value("api_profiles", "[]")
        try:
            values = json.loads(str(raw)) if raw else []
        except (TypeError, json.JSONDecodeError):
            values = []
        if not isinstance(values, list):
            return []
        profiles = [APIProviderProfile.from_public_dict(v) for v in values if isinstance(v, dict)]
        for profile in profiles:
            try:
                self._load_secrets(profile)
            except Exception as exc:
                # Keep non-secret profile metadata loadable when Keychain access
                # is temporarily unavailable. Never fall back to plaintext.
                self.last_keychain_error = str(exc)
                profile.api_key = ""
                profile.app_id = ""
                profile.app_key = ""
        return profiles

    def save_profiles(self, profiles: list[APIProviderProfile]) -> None:
        previous = {p.id for p in self.load_profiles()}
        current = {p.id for p in profiles}
        for profile in profiles:
            self._save_secrets(profile)
        for deleted in previous - current:
            self.keychain.delete(deleted)
        payload = json.dumps([p.public_dict() for p in profiles], ensure_ascii=False, separators=(",", ":"))
        self.settings.setValue("api_profiles", payload)
        if self.active_profile_id not in current:
            self.settings.setValue("api_active_profile", profiles[0].id if profiles else "")
        self.settings.sync()

    def _load_secrets(self, profile: APIProviderProfile) -> None:
        secret = self.keychain.get(profile.id) or {}
        if profile.provider_type == "mathpix":
            profile.app_id = str(secret.get("app_id", ""))
            profile.app_key = str(secret.get("app_key", ""))
        else:
            profile.api_key = str(secret.get("api_key", ""))

    def _save_secrets(self, profile: APIProviderProfile) -> None:
        if profile.provider_type == "mathpix":
            self.keychain.set(profile.id, {"app_id": profile.app_id, "app_key": profile.app_key})
        else:
            self.keychain.set(profile.id, {"api_key": profile.api_key})

    def active_profile(self) -> APIProviderProfile | None:
        profiles = self.load_profiles()
        active = self.active_profile_id
        for profile in profiles:
            if profile.id == active and profile.enabled:
                return profile
        return next((p for p in profiles if p.enabled), None)
