"""Remote OCR worker; API calls never run on the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal, Slot

from api.providers import RemoteOCRResult, provider_for_profile


class APIWorker(QObject):
    result_ready = Signal(object)
    error = Signal(str)

    @Slot(object, object)
    def recognize(self, profile, image_png: bytes) -> None:
        try:
            result = provider_for_profile(profile).recognize(image_png)
        except Exception as exc:
            self.error.emit(str(exc))
            return
        if not isinstance(result, RemoteOCRResult):
            self.error.emit("API 返回了无效识别结果")
            return
        self.result_ready.emit(result)


class ModelListWorker(QObject):
    """Fetch an OpenAI-compatible model list without blocking the settings UI."""

    request = Signal(int, object)
    models_ready = Signal(int, object)
    error = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self.request.connect(self.list_models, Qt.ConnectionType.QueuedConnection)

    @Slot(int, object)
    def list_models(self, request_id: int, profile) -> None:
        try:
            models = provider_for_profile(profile).list_models()
        except Exception as exc:
            self.error.emit(request_id, str(exc))
            return
        if not isinstance(models, list):
            self.error.emit(request_id, "API 返回了无效模型列表")
            return
        self.models_ready.emit(request_id, [str(model) for model in models if str(model).strip()])
