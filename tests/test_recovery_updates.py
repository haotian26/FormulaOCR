"""Offline recovery/update tests: disposable history, mocked HTTP, no Keychain."""
import base64
import io
import json
import threading

import httpx
import pytest
from PIL import Image

from sidecar.server import Sidecar, check_for_updates, RELEASE_API, RELEASE_PAGE, MAX_RELEASE_BYTES


def png(color="white"):
    stream = io.BytesIO()
    Image.new("RGB", (3, 2), color).save(stream, format="PNG")
    return stream.getvalue()


def test_restart_rehydrates_image_without_recognition_or_new_history(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMULAOCR_DATA_ROOT", str(tmp_path))
    first = Sidecar()
    contents = png()
    record = first.history.create_local(contents, local_raw_latex="x", local_formatted_latex="x", local_draft_latex="edited", local_render_error=None)
    session = first.dispatch("system.health", {})["session_id"]
    first.close()
    second = Sidecar()
    try:
        monkeypatch.setattr(second, "_ensure_engine", lambda: pytest.fail("Recovery must not run OCR"))
        monkeypatch.setattr(second, "_load_profiles", lambda: pytest.fail("Recovery must not load credentials"))
        assert second.dispatch("system.health", {})["session_id"] != session
        restored = second.dispatch("image.open", {"image_id": "same-image", "history_id": record.id, "png_base64": base64.b64encode(contents).decode()})
        assert restored["session_id"] == second.session_id
        assert second.image_records["same-image"] == record.id
        assert len(second.history.list_records()) == 1
        assert second.history.get(record.id).local_draft_latex == "edited"
    finally:
        second.close()


def test_restore_rejects_mismatched_record_without_changing_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMULAOCR_DATA_ROOT", str(tmp_path))
    service = Sidecar()
    try:
        record = service.history.create_local(png(), local_raw_latex="x", local_formatted_latex="x", local_draft_latex="x", local_render_error=None)
        with pytest.raises(ValueError, match="does not match"):
            service.dispatch("image.open", {"image_id": "wrong", "history_id": record.id, "png_base64": base64.b64encode(png("black")).decode()})
        assert not service.images and not service.image_records
        with pytest.raises(ValueError, match="not found"):
            service.dispatch("image.open", {"history_id": "missing", "png_base64": base64.b64encode(png()).decode()})
    finally:
        service.close()


def client_with(payload=None, *, status=200, content=None):
    def handler(request):
        assert str(request.url) == RELEASE_API
        assert request.method == "GET"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(status, json=payload) if content is None else httpx.Response(status, content=content)
    return lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler), **kwargs)


def release(tag="v0.4.3", **extra):
    return {"tag_name": tag, "html_url": f"{RELEASE_PAGE}/tag/{tag}", "draft": False, "prerelease": False, **extra}


@pytest.mark.parametrize(("latest", "available"), [("v0.4.3", True), ("v0.4.2", False), ("v0.4.1", False), ("v0.10.0", True)])
def test_manual_update_compares_numeric_stable_versions(latest, available):
    result = check_for_updates("0.4.2", client_factory=client_with(release(latest)))
    assert result["update_available"] is available
    assert result["url"] == f"{RELEASE_PAGE}/tag/{latest}"


@pytest.mark.parametrize("payload", [release(html_url="https://example.org/download"), release("v0.5.0-beta"), release("v00.5.0"), release(prerelease=True), release(draft=True), []])
def test_manual_update_rejects_untrusted_release_metadata(payload):
    with pytest.raises(ValueError):
        check_for_updates("0.4.2", client_factory=client_with(payload))


@pytest.mark.parametrize("status", [301, 404, 403, 500])
def test_manual_update_does_not_follow_redirects_or_claim_success_on_http_error(status):
    with pytest.raises(ValueError):
        check_for_updates("0.4.2", client_factory=client_with(status=status))


def test_manual_update_response_is_bounded_and_json_validated():
    with pytest.raises(ValueError, match="size limit"):
        check_for_updates("0.4.2", client_factory=client_with(content=b"x" * (MAX_RELEASE_BYTES + 1)))
    with pytest.raises(ValueError, match="Cannot check"):
        check_for_updates("0.4.2", client_factory=client_with(content=b"invalid"))


def test_current_version_is_validated_before_network():
    with pytest.raises(ValueError):
        check_for_updates("../../malformed", client_factory=lambda **_: pytest.fail("Must validate before connecting"))


def test_update_network_work_does_not_occupy_history_settings_workers(monkeypatch):
    from sidecar import server
    control_ran = threading.Event()

    class FakeSidecar:
        def dispatch(self, method, params):
            if method == "system.checkForUpdates":
                if not control_ran.wait(timeout=2):
                    raise RuntimeError("Network work blocked the control queue")
            elif method == "settings.get":
                control_ran.set()
            return {"ok": True}

        def close(self):
            pass

    output = io.StringIO()
    requests = [{"id": str(index), "method": method, "params": {}} for index, method in enumerate([
        "system.checkForUpdates", "system.checkForUpdates", "settings.get", "system.shutdown",
    ])]
    monkeypatch.setattr(server, "Sidecar", FakeSidecar)
    monkeypatch.setattr(server.sys, "stdin", io.StringIO("\n".join(json.dumps(request) for request in requests)))
    monkeypatch.setattr(server.sys, "stdout", output)
    assert server.main() == 0
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == 4 and all(response["ok"] for response in responses)
