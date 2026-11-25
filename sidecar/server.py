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
import re
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
from .settings import SettingsStore, atomic_json


RELEASE_API = "https://api.github.com/repos/haotian26/FormulaOCR/releases/latest"
RELEASE_PAGE = "https://github.com/haotian26/FormulaOCR/releases"
MAX_RELEASE_BYTES = 64 * 1024


def _stable_version(value: Any) -> tuple[int, int, int]:
    # GitHub's latest endpoint excludes prereleases. Reject ambiguous tags
    # rather than guessing how to order them or constructing an unsafe URL.
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value, re.ASCII):
        raise ValueError("Release version must be a stable semantic version")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def check_for_updates(current: str, *, client_factory=None) -> dict[str, Any]:
    current_version = _stable_version(current)
    import httpx
    factory = client_factory or httpx.Client
    # This is reached only by the explicit user-triggered command. Never use
    # credentials, cookies, redirects, proxy environment, or a caller URL.
    try:
        with factory(timeout=httpx.Timeout(10, connect=5), follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", RELEASE_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "FormulaOCR-update-check"}) as response:
                if response.status_code == 404:
                    raise ValueError("No public stable release is available to check")
                if response.status_code != 200:
                    raise ValueError(f"Update check returned HTTP {response.status_code}")
                body = bytearray()
                deadline = time.monotonic() + 15
                for chunk in response.iter_bytes(chunk_size=8192):
                    if time.monotonic() > deadline:
                        raise ValueError("Update check exceeded its time limit")
                    if len(body) + len(chunk) > MAX_RELEASE_BYTES:
                        raise ValueError("Release response exceeds the safe size limit")
                    body.extend(chunk)
        payload = json.loads(body)
    except (httpx.HTTPError, UnicodeError, json.JSONDecodeError) as exc:
        # Network error details may contain local proxy information. Return a
        # fixed message rather than an upstream body, URL, or traceback.
        raise ValueError("Cannot check for updates; check your network and try again") from exc
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise ValueError("The release response is not a published stable release")
    latest = payload.get("tag_name")
    latest_version = _stable_version(latest)
    url = payload.get("html_url")
    if url != f"{RELEASE_PAGE}/tag/{latest}":
        raise ValueError("The release response contains an unexpected destination")
    return {"current": current, "latest": latest.removeprefix("v"), "update_available": latest_version > current_version, "url": url}


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
        self.session_id = uuid.uuid4().hex
        self.engine = None
        self.images: dict[str, bytes] = {}
        self.image_records: dict[str, str] = {}
        self.data_root = self._data_root()
        self.settings = SettingsStore(self.data_root / "settings.json")
        self.history = HistoryStore(root=self._history_root(), limit=self.settings.get()["history_limit"])
        self.profile_store_path = self.data_root / "api_profiles.json"
        self._engine_lock = threading.RLock()
        self._history_lock = threading.RLock()
        self._profile_lock = threading.RLock()
        self._closed = False

    @staticmethod
    def _data_root() -> Path:
        configured = os.environ.get("FORMULAOCR_DATA_ROOT", "").strip()
        return Path(configured).expanduser() if configured else Path.home() / "Library" / "Application Support" / "FormulaOCR"

    @classmethod
    def _history_root(cls) -> Path | None:
        configured = os.environ.get("FORMULAOCR_DATA_ROOT", "").strip()
        return Path(configured).expanduser() / "history" if configured else None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.images.clear()
        self.image_records.clear()
        self.history.close()

    def _ensure_engine(self):
        with self._engine_lock:
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
        if record.local_draft_latex is None:
            payload["local_draft_latex"] = payload["local_formatted_latex"]
        if record.api_raw_latex:
            payload["api_formatted_latex"] = normalize_latex(record.api_raw_latex, mode=mode)
            if record.api_draft_latex is None:
                payload["api_draft_latex"] = payload["api_formatted_latex"]
        payload["has_api"] = record.has_api
        return payload

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "system.health":
            return {"ok": True, "pid": os.getpid(), "protocol": 1, "session_id": self.session_id}
        if method == "system.checkForUpdates":
            return check_for_updates(str(params.get("current", "")))
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
            if not isinstance(raw, str) or len(raw) > 45 * 1024 * 1024 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", image_id):
                raise ValueError("Invalid image restore payload")
            contents = self._validated_image(base64.b64decode(raw, validate=True))
            history_id = params.get("history_id")
            if history_id is not None:
                if not isinstance(history_id, str):
                    raise ValueError("history_id must be a string")
                record = self.history.get(history_id)
                if record is None:
                    raise ValueError("history record not found")
                if self._validated_image(Path(record.image_path).read_bytes()) != contents:
                    raise ValueError("Restored image does not match its history record")
            self.images[image_id] = contents
            self.image_records.pop(image_id, None)
            if history_id is not None:
                self.image_records[image_id] = history_id
            return {"image_id": image_id, "bytes": len(contents), "history_id": history_id, "session_id": self.session_id}
        if method == "image.openPath":
            path = self._validated_staged_path(str(params.get("path", "")))
            image_id = str(params.get("image_id") or uuid.uuid4().hex)
            try:
                contents = path.read_bytes()
                self.images[image_id] = self._validated_image(contents)
            finally:
                path.unlink(missing_ok=True)
            return {"image_id": image_id, "bytes": len(self.images[image_id]), "session_id": self.session_id}
        if method == "image.release":
            self.images.pop(str(params.get("image_id", "")), None)
            self.image_records.pop(str(params.get("image_id", "")), None)
            return {"ok": True}
        if method == "ocr.recognize":
            mode = str(params.get("mode", "chemistry"))
            if mode not in {"chemistry", "math"}:
                raise ValueError("mode must be chemistry or math")
            image_id = str(params.get("image_id", ""))
            image_bytes = self.images.get(image_id)
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
                    previous_id = self.image_records.get(image_id)
                    previous = self.history.get(previous_id) if previous_id else None
                    record = self.history.create_local(
                        image_bytes,
                        local_raw_latex=result.raw_latex,
                        local_formatted_latex=formatted,
                        local_draft_latex=formatted,
                        local_render_error=render_error,
                        recognition_mode=mode,
                    )
                    # Retrying local OCR must preserve the existing API branch,
                    # including its draft, even if retention evicts the old row.
                    if previous and previous.has_api:
                        self.history.update_api(
                            record.id,
                            api_raw_latex=previous.api_raw_latex,
                            api_formatted_latex=previous.api_formatted_latex,
                            api_draft_latex=previous.api_draft_latex,
                            api_profile_name=previous.api_profile_name,
                            api_model=previous.api_model,
                            api_render_error=previous.api_render_error,
                        )
                        self.history.set_active_source(record.id, "local")
                if image_id in self.images:
                    self.image_records[image_id] = record.id
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
            return self.settings.get()
        if method == "settings.save":
            return self.settings.save(params.get("values") or {})
        if method == "profiles.list":
            profiles, enabled, active_id = self._load_profiles(with_secrets=False)
            return {"api_enabled": enabled, "active_profile_id": active_id, "profiles": [profile.public_dict() for profile in profiles]}
        if method == "profiles.save":
            with self._profile_lock:
                self._save_profiles(params)
                profiles, enabled, active_id = self._load_profiles(with_secrets=False)
            return {"api_enabled": enabled, "active_profile_id": active_id, "profiles": [profile.public_dict() for profile in profiles]}
        if method == "profiles.activate":
            with self._profile_lock:
                profiles, enabled, _ = self._load_profiles(with_secrets=False)
                active_id = str(params.get("id", ""))
                if not any(profile.id == active_id and profile.enabled for profile in profiles):
                    raise ValueError("没有可用的 API 配置")
                atomic_json(self.profile_store_path, {"api_enabled": enabled, "active_profile_id": active_id, "profiles": [p.public_dict() for p in profiles]})
                return {"active_profile_id": active_id}
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
                from api.providers import validate_endpoint
                validate_endpoint(profile.base_url)
                if not profile.app_id.strip() or not profile.app_key.strip():
                    raise ValueError("未配置 Mathpix App ID/App Key")
                return {"ok": True, "message": "Mathpix 凭据格式已检查；服务端有效性需实际识别验证，本次未联网"}
            models = provider_for_profile(profile).list_models()
            return {"ok": True, "message": f"连接成功，获取到 {len(models)} 个模型", "models": list(dict.fromkeys(models))}
        if method == "api.recognize":
            from api.providers import provider_for_profile
            if params.get("automatic") and not self.settings.get()["default_api_ocr"]:
                raise ValueError("默认 API 识别已关闭")
            profiles, enabled, active_id = self._load_profiles()
            if not enabled:
                raise ValueError("API 重识别未启用")
            profile_id = str(params.get("profile_id") or active_id)
            profile = next((item for item in profiles if item.id == profile_id and item.enabled), None)
            if profile is None:
                raise ValueError("没有可用的 API 配置")
            mode = str(params.get("mode", "chemistry"))
            if mode not in {"chemistry", "math"}:
                raise ValueError("mode must be chemistry or math")
            image_id = str(params.get("image_id", ""))
            image_bytes = self.images.get(image_id)
            if image_bytes is None:
                raise ValueError("image_id is missing or has been released")
            record_id = self.image_records.get(image_id)
            result = provider_for_profile(profile).recognize(image_bytes)
            payload = _json_value(result)
            from ocr.postprocess import normalize_latex
            formatted = normalize_latex(result.raw_latex, mode=mode)
            payload["formatted_latex"] = formatted
            payload["mode"] = mode
            try:
                from converter.latex_to_mathml import latex_to_mathml
                latex_to_mathml(formatted)
                render_error = None
            except Exception as render_exc:
                render_error = str(render_exc)
            try:
                fields = dict(api_raw_latex=result.raw_latex, api_formatted_latex=formatted,
                              api_draft_latex=formatted, api_profile_name=result.profile_name,
                              api_model=result.model, api_render_error=render_error)
                with self._history_lock:
                    updated = self.history.update_api(record_id, **fields) if record_id else None
                    if updated is None:
                        updated = self.history.create_api(image_bytes, recognition_mode=mode, **fields)
                    if image_id in self.images:
                        self.image_records[image_id] = updated.id
                    payload["history_id"] = updated.id
            except Exception as exc:
                payload["history_error"] = str(exc)
            return payload
        if method == "history.open":
            record = self.history.get(str(params.get("id", "")))
            if record is None:
                raise ValueError("history record not found")
            image_id = uuid.uuid4().hex
            contents = self._validated_image(Path(record.image_path).read_bytes())
            self.images[image_id] = contents
            self.image_records[image_id] = record.id
            return {"record": self._history_payload(record), "image_id": image_id, "png_base64": base64.b64encode(contents).decode("ascii"), "session_id": self.session_id}
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
            with self.history._lock:
                self.history.update_draft(record_id, source, str(params.get("latex", "")))
                if params.get("activate", True):
                    self.history.set_active_source(record_id, source)
            return {"ok": True}
        if method == "history.setLimit":
            limit = self.history.set_limit(int(params.get("limit", 200)))
            return {"limit": limit, "pruned": True}
        if method == "history.setMode":
            self.history.set_recognition_mode(str(params.get("id", "")), str(params.get("mode", "chemistry")))
            return {"ok": True}
        raise ValueError(f"unknown method: {method}")

    @staticmethod
    def _validated_image(contents: bytes) -> bytes:
        from PIL import Image, ImageOps
        if not contents or len(contents) > 32 * 1024 * 1024:
            raise ValueError("Image must be between 1 byte and 32 MB")
        with Image.open(io.BytesIO(contents)) as source:
            if source.width * source.height > 40_000_000:
                raise ValueError("Image exceeds 40 megapixels")
            image = ImageOps.exif_transpose(source)
            # Transparent clipboard backgrounds must not become black ink.
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            output = io.BytesIO()
            background.convert("RGB").save(output, format="PNG")
            return output.getvalue()

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

    def _load_profiles(self, *, with_secrets=True):
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
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("Cannot read API profiles; the original file was preserved") from exc
        profiles = []
        for value in values:
            if not isinstance(value, dict):
                continue
            profile = APIProviderProfile.from_public_dict(value)
            if not with_secrets:
                profiles.append(profile)
                continue
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
            except Exception as exc:
                raise ValueError("Cannot read API credentials from Keychain") from exc
            profiles.append(profile)
        return profiles, enabled, active_id

    def _save_profiles(self, params: dict[str, Any]) -> None:
        from api.config import APIProviderProfile
        from api.keychain import KeychainStore
        from api.providers import validate_endpoint
        previous_profiles, _, _ = self._load_profiles(with_secrets=False)
        previous_ids = {profile.id for profile in previous_profiles}
        values = params.get("profiles", [])
        profiles = []
        updates = {}
        seen = set()
        for value in values:
            if not isinstance(value, dict):
                raise ValueError("API profile must be an object")
            profile = APIProviderProfile.from_public_dict(value)
            if not profile.id or profile.id in seen:
                raise ValueError("API profile IDs must be unique")
            seen.add(profile.id)
            if profile.provider_type not in {"mathpix", "openai_compatible"}:
                raise ValueError("Unsupported API provider")
            profile.name = profile.name.strip()
            if not profile.name:
                raise ValueError("API profile name is required")
            if profile.enabled or profile.base_url.strip():
                profile.base_url = validate_endpoint(profile.base_url)
            if profile.enabled and profile.provider_type == "openai_compatible" and not profile.model.strip():
                raise ValueError("未配置模型 ID")
            profiles.append(profile)
            updates[profile.id] = {key: str(value[key]).strip() for key in ("api_key", "app_id", "app_key") if value.get(key)}
        active_id = str(params.get("active_profile_id", ""))
        if not any(p.id == active_id and p.enabled for p in profiles):
            active_id = next((p.id for p in profiles if p.enabled), "")
        payload = {
            "api_enabled": bool(params.get("api_enabled", False)),
            "active_profile_id": active_id,
            "profiles": [profile.public_dict() for profile in profiles],
        }
        keychain = KeychainStore(os.environ.get("FORMULAOCR_KEYCHAIN_SERVICE", "FormulaOCR API"))
        changed = {account for account, patch in updates.items() if patch}
        deleted = previous_ids - seen
        originals = {account: keychain.get(account) for account in changed | deleted}
        applied = []
        try:
            for account in changed:
                applied.append(account)
                keychain.set(account, {**originals[account], **updates[account]})
            for account in deleted:
                applied.append(account)
                keychain.delete(account)
            atomic_json(self.profile_store_path, payload)
        except Exception:
            # Never report a failed Save after silently replacing a credential.
            for account in reversed(applied):
                if originals[account]:
                    keychain.set(account, originals[account])
                else:
                    keychain.delete(account)
            raise


def main() -> int:
    sidecar = Sidecar()
    output_lock = threading.Lock()

    def respond(request: dict[str, Any]) -> None:
        request_id = request.get("id")
        try:
            if not isinstance(request.get("id"), str) or not isinstance(request.get("method"), str) or not isinstance(request.get("params", {}), dict):
                raise ValueError("Request requires a string id, a method, and object params")
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
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr") as ocr_queue, \
             ThreadPoolExecutor(max_workers=2, thread_name_prefix="api") as api_queue, \
             ThreadPoolExecutor(max_workers=2, thread_name_prefix="control") as control_queue:
            for line in sys.stdin:
                if not line.strip():
                    continue
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise ValueError("Request must be an object")
                except (ValueError, json.JSONDecodeError):
                    respond({"id": None, "method": "", "params": {}})
                    continue
                if request.get("method") == "system.shutdown":
                    ocr_queue.shutdown(wait=True, cancel_futures=True)
                    api_queue.shutdown(wait=True, cancel_futures=True)
                    control_queue.shutdown(wait=True)
                    respond(request)
                    break
                method = str(request.get("method", ""))
                executor = ocr_queue if method in {"ocr.preload", "ocr.recognize"} else api_queue if method.startswith("api.") or method == "system.checkForUpdates" else control_queue
                executor.submit(respond, request)
    finally:
        try:
            sidecar.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
