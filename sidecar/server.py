"""Long-running, dependency-light JSON Lines bridge for the Tauri UI.

The bridge deliberately owns no GUI state.  Every request has an id and every
response is a single JSON object, which makes the process easy to supervise,
restart and test without a local HTTP server.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import traceback
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from gui.history import HistoryStore


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


class Sidecar:
    def __init__(self) -> None:
        self.engine = None
        self.images: dict[str, bytes] = {}
        self.image_records: dict[str, str] = {}
        self.history = HistoryStore(root=self._history_root())
        self.data_root = self._data_root()
        self.profile_store_path = self.data_root / "api_profiles.json"
        self._engine_lock = threading.Lock()
        self._history_lock = threading.RLock()

    @staticmethod
    def _data_root() -> Path:
        configured = os.environ.get("FORMULAOCR_DATA_ROOT", "").strip()
        return Path(configured).expanduser() if configured else Path.home() / "Library" / "Application Support" / "FormulaOCR"

    @classmethod
    def _history_root(cls) -> Path | None:
        configured = os.environ.get("FORMULAOCR_DATA_ROOT", "").strip()
        return Path(configured).expanduser() / "history" if configured else None

    def close(self) -> None:
        self.images.clear()
        self.image_records.clear()
        self.history.close()

    def _ensure_engine(self):
        if self.engine is None:
            from app.application import build_engine

            self.engine = build_engine()
        return self.engine

    @staticmethod
    def _history_payload(record) -> dict[str, Any]:
        """Return a history record using today's display normalization.

        Raw OCR/API fields remain untouched for audit and restore purposes.
        Older saved drafts are normalized only in the payload, so records
        created before a formatting fix do not keep rendering stale italics.
        """

        from ocr.postprocess import normalize_latex

        payload = _json_value(record)
        mode = record.recognition_mode if record.recognition_mode in {"chemistry", "math"} else "chemistry"
        payload["local_formatted_latex"] = normalize_latex(record.local_raw_latex, mode=mode)
        if not record.local_draft_latex:
            payload["local_draft_latex"] = payload["local_formatted_latex"]
        if record.api_raw_latex:
            payload["api_formatted_latex"] = normalize_latex(record.api_raw_latex, mode=mode)
            if not record.api_draft_latex:
                payload["api_draft_latex"] = payload["api_formatted_latex"]
        payload["has_api"] = record.has_api
        return payload

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "system.health":
            return {"ok": True, "pid": os.getpid(), "protocol": 1}
        if method == "system.shutdown":
            self.close()
            return {"ok": True}
        if method == "ocr.preload":
            started = time.perf_counter()
            with self._engine_lock:
                engine = self._ensure_engine()
                engine.load()
            return {
                "loaded": engine.is_loaded(),
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }
        if method == "image.open":
            raw = params.get("png_base64", "")
            image_id = str(params.get("image_id") or uuid.uuid4().hex)
            self.images[image_id] = base64.b64decode(raw)
            return {"image_id": image_id, "bytes": len(self.images[image_id])}
        if method == "image.openPath":
            path = self._validated_staged_path(str(params.get("path", "")))
            image_id = str(params.get("image_id") or uuid.uuid4().hex)
            try:
                contents = path.read_bytes()
                from PIL import Image
                Image.open(io.BytesIO(contents)).verify()
                self.images[image_id] = contents
            finally:
                path.unlink(missing_ok=True)
            return {"image_id": image_id, "bytes": len(self.images[image_id])}
        if method == "image.release":
            self.images.pop(str(params.get("image_id", "")), None)
            self.image_records.pop(str(params.get("image_id", "")), None)
            return {"ok": True}
        if method == "ocr.recognize":
            mode = str(params.get("mode", "chemistry"))
            if mode not in {"chemistry", "math"}:
                raise ValueError("mode must be chemistry or math")
            image = self._image(params)
            engine = self._ensure_engine()
            started = time.perf_counter()
            with self._engine_lock:
                result = engine.recognize(image)
            payload = _json_value(result)
            formatted = result.format_for(mode)
            payload["formatted_latex"] = formatted
            payload["mode"] = mode
            payload["elapsed_ms"] = (time.perf_counter() - started) * 1000
            try:
                render_error = None
                try:
                    from converter.latex_to_mathml import latex_to_mathml
                    latex_to_mathml(formatted)
                except Exception as render_exc:
                    render_error = str(render_exc)
                with self._history_lock:
                    record = self.history.create_local(
                        self.images[str(params.get("image_id", ""))],
                        local_raw_latex=result.raw_latex,
                        local_formatted_latex=formatted,
                        local_draft_latex=formatted,
                        local_render_error=render_error,
                        recognition_mode=mode,
                    )
                self.image_records[str(params.get("image_id", ""))] = record.id
                payload["history_id"] = record.id
            except Exception as exc:
                payload["history_error"] = str(exc)
            return payload
        if method == "ocr.format":
            from ocr.postprocess import normalize_latex
            mode = str(params.get("mode", "chemistry"))
            return {"formatted_latex": normalize_latex(str(params.get("latex", "")), mode=mode), "mode": mode}
        if method == "conversion.toMathML":
            from converter.latex_to_mathml import latex_to_mathml
            return {"mathml": latex_to_mathml(str(params.get("latex", "")))}
        if method == "settings.get":
            path = self.data_root / "settings.json"
            if not path.is_file():
                return {
                    "auto_copy": False,
                    "hide_dock_on_close": True,
                    "hotkey": "ctrl+alt+cmd+o",
                    "history_limit": 200,
                    "layout_restore_mode": "remember_window_history_closed",
                    "layout_version": 2,
                    "default_recognition_mode": "chemistry",
                }
            return json.loads(path.read_text(encoding="utf-8"))
        if method == "settings.save":
            values = dict(params.get("values") or {})
            self.data_root.mkdir(parents=True, exist_ok=True)
            temporary = self.data_root / ".settings.json.tmp"
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.data_root / "settings.json")
            return values
        if method == "profiles.list":
            profiles, enabled, active_id = self._load_profiles()
            return {"api_enabled": enabled, "active_profile_id": active_id, "profiles": [profile.public_dict() for profile in profiles]}
        if method == "profiles.save":
            self._save_profiles(params)
            profiles, enabled, active_id = self._load_profiles()
            return {"api_enabled": enabled, "active_profile_id": active_id, "profiles": [profile.public_dict() for profile in profiles]}
        if method == "api.listModels":
            from api.providers import provider_for_profile
            from api.config import APIProviderProfile
            profiles, enabled, active_id = self._load_profiles()
            profile_id = str(params.get("profile_id") or active_id)
            draft = params.get("profile")
            stored = next((item for item in profiles if item.id == profile_id), None)
            profile = APIProviderProfile.from_public_dict(draft) if isinstance(draft, dict) else stored
            if profile is None:
                raise ValueError("没有找到 API 配置")
            if isinstance(draft, dict):
                profile.api_key = str(draft.get("api_key") or (stored.api_key if stored else ""))
                profile.app_id = str(draft.get("app_id") or (stored.app_id if stored else ""))
                profile.app_key = str(draft.get("app_key") or (stored.app_key if stored else ""))
            if profile.provider_type == "mathpix":
                return {"models": [], "message": "Mathpix 不提供模型列表"}
            models = provider_for_profile(profile).list_models()
            return {"models": list(dict.fromkeys(models))}
        if method == "api.testProfile":
            from api.providers import provider_for_profile
            from api.config import APIProviderProfile
            profiles, enabled, active_id = self._load_profiles()
            profile_id = str(params.get("profile_id") or active_id)
            draft = params.get("profile")
            stored = next((item for item in profiles if item.id == profile_id), None)
            profile = APIProviderProfile.from_public_dict(draft) if isinstance(draft, dict) else stored
            if profile is None:
                raise ValueError("没有找到 API 配置")
            if isinstance(draft, dict):
                profile.api_key = str(draft.get("api_key") or (stored.api_key if stored else ""))
                profile.app_id = str(draft.get("app_id") or (stored.app_id if stored else ""))
                profile.app_key = str(draft.get("app_key") or (stored.app_key if stored else ""))
            if profile.provider_type == "mathpix":
                return {"ok": True, "message": "Mathpix 将在实际 API 重识别时验证，不发送测试请求"}
            models = provider_for_profile(profile).list_models()
            return {"ok": True, "message": f"连接成功，获取到 {len(models)} 个模型", "models": list(dict.fromkeys(models))}
        if method == "api.recognize":
            from api.providers import provider_for_profile
            profiles, enabled, active_id = self._load_profiles()
            if not enabled:
                raise ValueError("API 重识别未启用")
            profile_id = str(params.get("profile_id") or active_id)
            profile = next((item for item in profiles if item.id == profile_id and item.enabled), None)
            if profile is None:
                raise ValueError("没有可用的 API 配置")
            result = provider_for_profile(profile).recognize(self.images[str(params.get("image_id", ""))])
            payload = _json_value(result)
            mode = str(params.get("mode", "chemistry"))
            if mode not in {"chemistry", "math"}:
                raise ValueError("mode must be chemistry or math")
            from ocr.postprocess import normalize_latex
            formatted = normalize_latex(result.raw_latex, mode=mode)
            payload["formatted_latex"] = formatted
            payload["mode"] = mode
            image_id = str(params.get("image_id", ""))
            record_id = self.image_records.get(image_id)
            if record_id:
                try:
                    from converter.latex_to_mathml import latex_to_mathml
                    latex_to_mathml(formatted)
                    render_error = None
                except Exception as render_exc:
                    render_error = str(render_exc)
                updated = self.history.update_api(
                    record_id,
                    api_raw_latex=result.raw_latex,
                    api_formatted_latex=formatted,
                    api_draft_latex=formatted,
                    api_profile_name=result.profile_name,
                    api_model=result.model,
                    api_render_error=render_error,
                )
                payload["history_id"] = record_id if updated else None
            return payload
        if method == "history.list":
            records = [self._history_payload(record) for record in self.history.list_records()]
            return {"records": records}
        if method == "history.get":
            record = self.history.get(str(params.get("id", "")))
            if record is None:
                return None
            return self._history_payload(record)
        if method == "history.image":
            record = self.history.get(str(params.get("id", "")))
            if record is None:
                raise ValueError("history record not found")
            return {"png_base64": base64.b64encode(Path(record.image_path).read_bytes()).decode("ascii")}
        if method == "history.thumbnail":
            record = self.history.get(str(params.get("id", "")))
            if record is None:
                raise ValueError("history record not found")
            from PIL import Image
            with Image.open(record.image_path) as source:
                preview = source.convert("RGB")
                preview.thumbnail((192, 128), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                preview.save(output, format="PNG", optimize=True)
            return {"png_base64": base64.b64encode(output.getvalue()).decode("ascii")}
        if method == "history.delete":
            return {"deleted": self.history.delete(str(params.get("id", "")))}
        if method == "history.deleteMany":
            ids = [str(item) for item in params.get("ids", [])]
            return {"deleted": self.history.delete_many(ids)}
        if method == "history.deleteAll":
            return {"deleted": self.history.delete_all()}
        if method == "history.updateDraft":
            record_id = str(params.get("id", ""))
            source = str(params.get("source", "local"))
            self.history.update_draft(record_id, source, str(params.get("latex", "")))
            self.history.set_active_source(record_id, source)
            return {"ok": True}
        if method == "history.setLimit":
            limit = self.history.set_limit(int(params.get("limit", 200)))
            return {"limit": limit, "pruned": True}
        if method == "history.setMode":
            self.history.set_recognition_mode(str(params.get("id", "")), str(params.get("mode", "chemistry")))
            return {"ok": True}
        raise ValueError(f"unknown method: {method}")

    def _image(self, params: dict[str, Any]) -> Any:
        image_id = str(params.get("image_id", ""))
        if image_id not in self.images:
            raise ValueError("image_id is missing or has been released")
        try:
            from PIL import Image
            return Image.open(io.BytesIO(self.images[image_id])).convert("RGB")
        except Exception as exc:
            raise ValueError(f"无法读取图片：{exc}") from exc

    @staticmethod
    def _validated_staged_path(raw_path: str) -> Path:
        if not raw_path:
            raise ValueError("staged image path is missing")
        configured = os.environ.get("FORMULAOCR_STAGE_ROOT", "").strip()
        if not configured:
            raise ValueError("staged image root is not configured")
        root = Path(configured).expanduser().resolve()
        path = Path(raw_path).expanduser().resolve()
        if path.parent != root or path.suffix.lower() != ".png":
            raise ValueError("staged image path is outside the approved directory")
        return path

    def _load_profiles(self):
        from api.config import APIProviderProfile
        values: list[dict[str, Any]] = []
        enabled = False
        active_id = ""
        if self.profile_store_path.is_file():
            try:
                payload = json.loads(self.profile_store_path.read_text(encoding="utf-8"))
                values = payload.get("profiles", []) if isinstance(payload, dict) else []
                enabled = bool(payload.get("api_enabled", False)) if isinstance(payload, dict) else False
                active_id = str(payload.get("active_profile_id", "")) if isinstance(payload, dict) else ""
            except (OSError, json.JSONDecodeError):
                pass
        profiles = []
        for value in values:
            if not isinstance(value, dict):
                continue
            profile = APIProviderProfile.from_public_dict(value)
            try:
                from api.keychain import KeychainStore
                service = os.environ.get("FORMULAOCR_KEYCHAIN_SERVICE", "FormulaOCR API Dev")
                store = KeychainStore(service)
                secret = store.get(profile.id) or {}
                # Early 0.3.0 alpha builds accidentally used the development
                # service from production. Preserve those credentials once,
                # while all new release writes go to the production service.
                if not secret and service == "FormulaOCR API":
                    secret = KeychainStore("FormulaOCR API Dev").get(profile.id) or {}
                    if secret:
                        store.set(profile.id, secret)
                profile.api_key = str(secret.get("api_key", ""))
                profile.app_id = str(secret.get("app_id", ""))
                profile.app_key = str(secret.get("app_key", ""))
            except Exception:
                pass
            profiles.append(profile)
        return profiles, enabled, active_id

    def _save_profiles(self, params: dict[str, Any]) -> None:
        from api.config import APIProviderProfile
        previous_profiles, _, _ = self._load_profiles()
        previous_ids = {profile.id for profile in previous_profiles}
        values = params.get("profiles", [])
        profiles = []
        for value in values:
            if not isinstance(value, dict):
                continue
            profile = APIProviderProfile.from_public_dict(value)
            # Empty form fields mean “keep the existing Keychain secret”.
            try:
                from api.keychain import KeychainStore
                existing = KeychainStore(os.environ.get("FORMULAOCR_KEYCHAIN_SERVICE", "FormulaOCR API Dev")).get(profile.id) or {}
            except Exception:
                existing = {}
            profile.api_key = str(value.get("api_key") or existing.get("api_key", ""))
            profile.app_id = str(value.get("app_id") or existing.get("app_id", ""))
            profile.app_key = str(value.get("app_key") or existing.get("app_key", ""))
            profiles.append(profile)
            try:
                from api.keychain import KeychainStore
                secret = {"api_key": profile.api_key, "app_id": profile.app_id, "app_key": profile.app_key}
                KeychainStore(os.environ.get("FORMULAOCR_KEYCHAIN_SERVICE", "FormulaOCR API Dev")).set(profile.id, secret)
            except Exception as exc:
                raise ValueError(f"API 密钥无法保存到 Keychain：{exc}") from exc
        self.data_root.mkdir(parents=True, exist_ok=True)
        try:
            from api.keychain import KeychainStore
            keychain = KeychainStore(os.environ.get("FORMULAOCR_KEYCHAIN_SERVICE", "FormulaOCR API Dev"))
            for deleted in previous_ids - {profile.id for profile in profiles}:
                keychain.delete(deleted)
        except Exception:
            pass
        payload = {
            "api_enabled": bool(params.get("api_enabled", False)),
            "active_profile_id": str(params.get("active_profile_id", profiles[0].id if profiles else "")),
            "profiles": [profile.public_dict() for profile in profiles],
        }
        temporary = self.profile_store_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.profile_store_path)


def main() -> int:
    sidecar = Sidecar()
    output_lock = threading.Lock()

    def respond(request: dict[str, Any]) -> None:
        request_id = request.get("id")
        try:
            result = sidecar.dispatch(str(request.get("method", "")), request.get("params") or {})
            response = {"id": request_id, "ok": True, "result": _json_value(result)}
        except Exception as exc:
            response = {
                "id": request_id,
                "ok": False,
                "error": {"code": type(exc).__name__, "message": str(exc), "retryable": False},
            }
            if os.environ.get("FORMULAOCR_SIDECAR_DEBUG"):
                traceback.print_exc(file=sys.stderr)
        with output_lock:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()

    try:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="formulaocr") as executor:
            for line in sys.stdin:
                if not line.strip():
                    continue
                request = json.loads(line)
                if request.get("method") == "system.shutdown":
                    executor.shutdown(wait=True)
                    respond(request)
                    break
                executor.submit(respond, request)
    finally:
        try:
            sidecar.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
