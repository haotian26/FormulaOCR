"""Stage H GUI regression checks for model fetching and selection."""

from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication

from api.config import APIProviderProfile
import gui.api_worker as api_worker
from gui.api_settings import APISettingsDialog


class Store:
    api_enabled = True
    active_profile_id = "p1"

    def __init__(self, profiles):
        self.profiles = list(profiles)
        self.saved = None

    def load_profiles(self):
        return self.profiles

    def set_api_enabled(self, value):
        self.api_enabled = value

    def save_profiles(self, profiles):
        self.profiles = list(profiles)
        self.saved = list(profiles)

    def set_active_profile_id(self, value):
        self.active_profile_id = value


class FakeProvider:
    def __init__(self, profile, models=None, error=None, delay=0):
        self.profile = profile
        self.models = models if models is not None else []
        self.error = error
        self.delay = delay

    def list_models(self):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise RuntimeError(self.error)
        return self.models


def wait_for_worker(app: QApplication, dialog: APISettingsDialog) -> None:
    deadline = time.monotonic() + 5
    while dialog._model_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert dialog._model_thread is None
    for _ in range(3):
        app.processEvents()
        time.sleep(0.01)


def main() -> None:
    app = QApplication.instance() or QApplication([])

    profiles = [
        APIProviderProfile(id="p1", name="One", base_url="https://example.com/v1", model="legacy", api_key="key"),
        APIProviderProfile(id="p2", name="Two", base_url="https://example.com/v1", api_key="key"),
    ]
    store = Store(profiles)
    api_worker.provider_for_profile = lambda profile: FakeProvider(
        profile, models=["vision", "vision", "ocr", "  "], delay=0.02
    )
    dialog = APISettingsDialog(store)
    dialog.show()
    app.processEvents()
    try:
        assert dialog.model_fetch_button.text() == "获取模型"
        dialog._fetch_models()
        wait_for_worker(app, dialog)
        assert [dialog.model_edit.itemText(i) for i in range(dialog.model_edit.count())] == ["vision", "ocr"]
        assert dialog.model_edit.currentText() == "legacy"
        dialog.model_edit.setCurrentText("ocr")
        assert dialog.save_button.isEnabled()
        dialog._save()
        assert not dialog.save_button.isEnabled()
        assert dialog.save_button.text() == "保存"
        assert dialog.save_feedback.text() == "✓ 已保存"

        dialog.profile_list.setCurrentRow(1)
        dialog._fetch_models()
        dialog.profile_list.setCurrentRow(0)
        wait_for_worker(app, dialog)
        assert dialog._selected_id == "p1"
        assert dialog.model_edit.findText("vision") < 0
    finally:
        dialog.close()
        app.processEvents()

    mathpix = APIProviderProfile(
        id="mathpix", provider_type="mathpix", name="Mathpix",
        base_url="https://api.mathpix.com", app_id="id", app_key="key",
    )
    mathpix_dialog = APISettingsDialog(Store([mathpix]))
    mathpix_dialog.show()
    app.processEvents()
    try:
        assert not mathpix_dialog.model_field.isVisible()
        assert not mathpix_dialog.model_fetch_button.isVisible()
    finally:
        mathpix_dialog.close()
        app.processEvents()

    error_profile = APIProviderProfile(
        id="error", base_url="https://example.com/v1", model="keep", api_key="key",
    )
    error_store = Store([error_profile])
    api_worker.provider_for_profile = lambda profile: FakeProvider(profile, error="HTTP 401")
    error_dialog = APISettingsDialog(error_store)
    error_dialog.show()
    app.processEvents()
    try:
        error_dialog._fetch_models()
        wait_for_worker(app, error_dialog)
        assert error_dialog.model_edit.currentText() == "keep"
        assert "HTTP 401" in error_dialog.model_status_label.text()
    finally:
        error_dialog.close()
        app.processEvents()

    print("Stage H GUI model controls: PASS")


if __name__ == "__main__":
    main()
