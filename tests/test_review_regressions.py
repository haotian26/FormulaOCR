import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from sidecar.server import Sidecar
from sidecar.settings import SettingsStore
from converter.latex_to_mathml import latex_to_mathml, MathMLConversionError


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMULAOCR_DATA_ROOT", str(tmp_path))
    value = Sidecar()
    yield value
    value.close()


def png(color="white"):
    buffer = io.BytesIO()
    Image.new("RGBA", (16, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def record(service):
    return service.history.create_local(png(), local_raw_latex="F^-", local_formatted_latex="F^-", local_draft_latex="F^-", local_render_error=None)


def test_settings_are_atomic_patches(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(store.save, [{"language": "en"}, {"history_limit": 30}]))
    assert store.get()["language"] == "en"
    assert store.get()["history_limit"] == 30
    assert store.get()["auto_copy"] is False
    assert not list(tmp_path.glob(".*tmp*"))


@pytest.mark.parametrize("value", [19, 2001, 20.5, True, "200"])
def test_invalid_limits_do_not_write(tmp_path, value):
    store = SettingsStore(tmp_path / "settings.json")
    with pytest.raises(ValueError):
        store.save({"history_limit": value})
    assert not store.path.exists()


def test_unknown_secret_not_persisted(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save({"api_key": "not-a-real-secret", "language": "en"})
    assert "api_key" not in store.path.read_text()


def test_corrupt_settings_preserve_original(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken")
    with pytest.raises(ValueError):
        SettingsStore(path).save({"auto_copy": True})
    assert path.read_text() == "{broken"


def test_empty_draft_and_api_branch_survive_history_restore(service):
    item = record(service)
    service.history.update_api(item.id, api_raw_latex="F^-", api_formatted_latex="F^-", api_draft_latex="", api_profile_name="Test", api_model="fake", api_render_error=None)
    service.dispatch("history.updateDraft", {"id":item.id, "source":"local", "latex":""})
    payload = service.dispatch("history.get", {"id":item.id})
    assert payload["local_draft_latex"] == ""
    assert payload["api_draft_latex"] == ""
    assert payload["has_api"] is True


def test_history_reopen_reuses_record_for_api(service):
    item = record(service)
    opened = service.dispatch("history.open", {"id":item.id})
    assert service.image_records[opened["image_id"]] == item.id
    service.dispatch("image.release", {"image_id":opened["image_id"]})
    assert not service.images and not service.image_records


def test_concurrent_history_updates_are_serialized(service):
    item = record(service)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: service.history.update_draft(item.id, "local", str(n)), range(40)))
    assert service.history.get(item.id).local_draft_latex in {str(n) for n in range(40)}
    assert service.history._connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_api_result_survives_history_failure(service, monkeypatch):
    item = record(service)
    opened = service.dispatch("history.open", {"id":item.id})
    profile = SimpleNamespace(id="p", enabled=True)
    monkeypatch.setattr(service, "_load_profiles", lambda: ([profile], True, "p"))
    result = SimpleNamespace(raw_latex="F^-", profile_name="Test", model="fake")
    from api.providers import RemoteOCRResult
    result = RemoteOCRResult("F^-", "openai_compatible", "Test", "fake", 1)
    with patch("api.providers.provider_for_profile", return_value=SimpleNamespace(recognize=lambda _: result)), patch.object(service.history, "update_api", side_effect=OSError("disk full")):
        payload = service.dispatch("api.recognize", {"image_id":opened["image_id"], "profile_id":"p"})
    assert payload["raw_latex"] == "F^-"
    assert "disk full" in payload["history_error"]


def test_image_validation_rejects_invalid_and_flattens_transparency(service):
    with pytest.raises(Exception):
        service.dispatch("image.open", {"png_base64":base64.b64encode(b"invalid").decode()})
    opened = service.dispatch("image.open", {"png_base64":base64.b64encode(png((0, 0, 0, 0))).decode()})
    assert service._image(opened).getpixel((0,0)) == (255,255,255)


@pytest.mark.parametrize("source", [r"\phantom{x+y}", "{x", "}x{", r"\begin{matrix}x", r"\href{javascript:bad}{x}"])
def test_invalid_or_invisible_formula_is_not_success(source):
    with pytest.raises(MathMLConversionError):
        latex_to_mathml(source)


@pytest.mark.parametrize("source", [r"\{x\}", r"\begin{matrix}a&\begin{matrix}b\end{matrix}\end{matrix}", r"x+\phantom{y}", r"3\mathrm{F}^{-}", r"\mathrm{HF}^{\circ}"])
def test_valid_formula_structures_remain_renderable(source):
    assert latex_to_mathml(source).startswith("<math")


def test_profile_save_rolls_back_keychain_on_disk_failure(service, monkeypatch):
    class MemoryKeychain:
        values = {"p": {"api_key":"old"}}
        def __init__(self, _service): pass
        def get(self, account): return dict(self.values.get(account, {}))
        def set(self, account, value): self.values[account] = value
        def delete(self, account): self.values.pop(account, None)
    monkeypatch.setattr("api.keychain.KeychainStore", MemoryKeychain)
    values = {"profiles":[{"id":"p", "name":"Test", "model":"test", "base_url":"https://example.com/v1", "api_key":"new"}]}
    with patch("sidecar.server.atomic_json", side_effect=OSError("disk full")), pytest.raises(OSError):
        service.dispatch("profiles.save", values)
    assert MemoryKeychain.values["p"]["api_key"] == "old"


def test_profile_metadata_does_not_read_or_write_keychain(service):
    service.profile_store_path.write_text(json.dumps({"profiles":[{"id":"p", "name":"Test"}]}))
    with patch("api.keychain.KeychainStore.get", side_effect=AssertionError("unexpected secret access")):
        assert service.dispatch("profiles.list", {})["profiles"][0]["id"] == "p"


def test_aligned_renders_as_table_without_visible_ampersands():
    import xml.etree.ElementTree as ET
    source = r"\begin{aligned}x&=1\\y&=2\end{aligned}"
    result = ET.fromstring(latex_to_mathml(source))
    ns = {"m":"http://www.w3.org/1998/Math/MathML"}
    assert len(result.findall(".//m:mtr", ns)) == 2
    assert "&" not in "".join(result.itertext())


@pytest.mark.parametrize("status", [401, 404, 429, 500])
def test_api_http_errors_are_reported(status):
    import httpx
    from api.config import APIProviderProfile
    from api.providers import OpenAICompatibleProvider, RemoteProviderError
    factory = lambda **kwargs: httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error":{"message":"test failure"}})), **kwargs)
    profile = APIProviderProfile.from_public_dict({"base_url":"https://example.com/v1"})
    with pytest.raises(RemoteProviderError, match=str(status)):
        OpenAICompatibleProvider(profile, client_factory=factory).list_models()


@pytest.mark.parametrize("address", ["https://user:password@example.com", "https://example.com?key=secret", "http://example.com"])
def test_api_rejects_insecure_endpoint(address):
    from api.providers import validate_endpoint, RemoteProviderError
    with pytest.raises(RemoteProviderError):
        validate_endpoint(address)
