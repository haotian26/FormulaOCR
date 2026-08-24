"""Stage H provider/config regression checks with a fake HTTP transport."""

from __future__ import annotations

import json
import sys

from api.config import APIProviderProfile, APIProfileStore
from api.providers import (
    MathpixProvider,
    OpenAICompatibleProvider,
    RemoteProviderError,
    normalize_api_latex,
    validate_endpoint,
)


class FakeSettings:
    def __init__(self) -> None:
        self.values = {}

    def value(self, key, defaultValue=None, type=None):
        value = self.values.get(key, defaultValue)
        if type is bool:
            return bool(value)
        return value

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


class FakeKeychain:
    def __init__(self):
        self.values = {}
        self.deleted = []

    def get(self, account):
        return dict(self.values.get(account, {}))

    def set(self, account, value):
        self.values[account] = dict(value)

    def delete(self, account):
        self.deleted.append(account)
        self.values.pop(account, None)


class BrokenKeychain:
    def get(self, _account):
        raise RuntimeError("Keychain unavailable")

    def set(self, _account, _value):
        raise RuntimeError("Keychain unavailable")

    def delete(self, _account):
        pass


class FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    responses = []
    requests = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def request(self, method, url, headers=None, json=None):
        self.requests.append((method, url, headers or {}, json))
        return self.responses.pop(0)


def fake_factory(**_kwargs):
    return FakeClient()


def main() -> None:
    assert normalize_api_latex("```latex\nx^2\n```") == "x^2"
    assert normalize_api_latex({"latex": "\\frac{1}{2}"}) == r"\frac{1}{2}"
    assert validate_endpoint("  https://example.com/v1/  ") == "https://example.com/v1"
    try:
        validate_endpoint("http://example.com/v1")
    except RemoteProviderError:
        pass
    else:
        raise AssertionError("remote HTTP must be rejected")

    settings = FakeSettings()
    keychain = FakeKeychain()
    store = APIProfileStore(settings, keychain)
    profile = APIProviderProfile(name="Test", model="vision", api_key="secret")
    store.set_api_enabled(True)
    store.save_profiles([profile])
    saved = json.loads(settings.values["api_profiles"])
    assert "api_key" not in saved[0]
    assert keychain.values[profile.id]["api_key"] == "secret"
    loaded = store.load_profiles()[0]
    assert loaded.api_key == "secret"
    store.save_profiles([])
    assert profile.id in keychain.deleted

    broken_profile = APIProviderProfile(name="Broken", model="vision")
    broken_store = APIProfileStore(FakeSettings(), BrokenKeychain())
    broken_store.settings.setValue("api_profiles", json.dumps([broken_profile.public_dict()]))
    broken_loaded = broken_store.load_profiles()[0]
    assert broken_loaded.api_key == ""
    assert broken_store.last_keychain_error == "Keychain unavailable"

    FakeClient.responses = [FakeResponse(200, {"data": [{"id": "vision"}]})]
    models = OpenAICompatibleProvider(profile, client_factory=fake_factory).list_models()
    assert models == ["vision"]
    endpoint_profile = APIProviderProfile(
        name="Endpoint", base_url="https://example.com/v1/chat/completions", model="vision", api_key="secret"
    )
    FakeClient.responses = [FakeResponse(200, {"data": [{"id": "vision"}]})]
    OpenAICompatibleProvider(endpoint_profile, client_factory=fake_factory).list_models()
    assert FakeClient.requests[-1][1] == "https://example.com/v1/models"
    FakeClient.responses = [FakeResponse(200, {"choices": [{"message": {"content": "```latex\nE=mc^2\n```"}}]}, {"x-request-id": "redacted-test"})]
    result = OpenAICompatibleProvider(profile, client_factory=fake_factory).recognize(b"png")
    assert result.raw_latex == "E=mc^2"
    method, url, headers, body = FakeClient.requests[-1]
    assert method == "POST" and url.endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer secret"
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")

    FakeClient.responses = [
        FakeResponse(503, {"error": "busy"}),
        FakeResponse(200, {"choices": [{"message": {"content": r"x+y"}}]}),
    ]
    retry_result = OpenAICompatibleProvider(profile, client_factory=fake_factory).recognize(b"png")
    assert retry_result.raw_latex == "x+y"

    math_profile = APIProviderProfile(
        provider_type="mathpix", name="Mathpix", base_url="https://api.mathpix.com",
        app_id="id", app_key="key",
    )
    FakeClient.responses = [FakeResponse(200, {"latex_styled": r"\frac{1}{2}", "confidence": 0.91})]
    math_result = MathpixProvider(math_profile, client_factory=fake_factory).recognize(b"png")
    assert math_result.raw_latex == r"\frac{1}{2}"
    assert math_result.confidence == 0.91
    _, math_url, math_headers, math_body = FakeClient.requests[-1]
    assert math_url.endswith("/v3/text")
    assert math_headers["app_key"] == "key"
    assert math_body["improve_mathpix"] is False
    print("Stage H provider/config checks: PASS")


if __name__ == "__main__":
    main()
