"""HTTP adapters for user-triggered remote formula OCR."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse


DEFAULT_PROMPT = (
    "Transcribe only the mathematical formula in this image as valid LaTeX. "
    "Return LaTeX only, without Markdown fences or explanation. Preserve every "
    "letter's case, chemical subscripts/superscripts, charges, reaction arrows, "
    "parenthesized state symbols, fractions, roots, integrals and line breaks. "
    "Attach simultaneous scripts to the same base as X_{sub}^{sup}; never emit "
    "an empty script followed by a separate group. Do not invent or simplify chemistry."
)


@dataclass(frozen=True)
class RemoteOCRResult:
    raw_latex: str
    provider_type: str
    profile_name: str
    model: str
    elapsed_ms: float
    confidence: float | None = None
    request_id: str | None = None


class RemoteProviderError(RuntimeError):
    """An API error safe to show in the GUI."""


class RemoteFormulaProvider(Protocol):
    def recognize(self, image_png: bytes) -> RemoteOCRResult: ...

    def list_models(self) -> list[str]: ...


def validate_endpoint(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RemoteProviderError("API 地址必须是完整的 http(s) URL")
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RemoteProviderError("API 地址不能包含用户名、密码、查询参数或片段")
    if parsed.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise RemoteProviderError("远程 API 必须使用 HTTPS；HTTP 只允许本机地址")
    return cleaned


def _httpx():
    try:
        import httpx  # type: ignore
    except ImportError as exc:  # pragma: no cover - packaged app supplies it
        raise RemoteProviderError("API 识别需要 httpx 依赖") from exc
    return httpx


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def normalize_api_latex(value: Any) -> str:
    """Accept conservative common API wrappers while preserving formula text."""

    if isinstance(value, dict):
        value = value.get("latex", value.get("latex_styled", value.get("content", "")))
    text = _extract_text(value).strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    if text.startswith("\\[") and text.endswith("\\]"):
        text = text[2:-2].strip()
    return text


class _HTTPProviderBase:
    def __init__(self, profile, *, client_factory=None) -> None:
        self.profile = profile
        self._client_factory = client_factory

    def _client(self):
        if self._client_factory is not None:
            return self._client_factory(timeout=max(5, min(120, int(self.profile.timeout_s))))
        httpx = _httpx()
        factory = httpx.Client
        return factory(timeout=max(5, min(120, int(self.profile.timeout_s))))

    def _request(self, method: str, url: str, *, headers=None, json_body=None) -> tuple[Any, str | None]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with self._client() as client:
                    response = client.request(method, url, headers=headers, json=json_body)
                    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                    if response.status_code in {408, 429} or response.status_code >= 500:
                        if attempt == 0:
                            continue
                    if response.status_code >= 400:
                        detail = ""
                        try:
                            error_payload = response.json()
                            if isinstance(error_payload, dict):
                                error_value = error_payload.get("error", error_payload.get("message", ""))
                                if isinstance(error_value, dict):
                                    error_value = error_value.get("message", "")
                                if isinstance(error_value, str):
                                    detail = error_value.strip()
                        except (ValueError, json.JSONDecodeError):
                            pass
                        suffix = f"：{detail[:240]}" if detail else ""
                        raise RemoteProviderError(f"API 返回 HTTP {response.status_code}{suffix}")
                    try:
                        return response.json(), request_id
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise RemoteProviderError("API 返回的不是有效 JSON") from exc
            except RemoteProviderError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    continue
        raise RemoteProviderError(f"API 请求失败：{last_error or '未知网络错误'}")


class OpenAICompatibleProvider(_HTTPProviderBase):
    def _base(self) -> str:
        base = validate_endpoint(self.profile.base_url)
        suffix = "/chat/completions"
        return base[:-len(suffix)] if base.endswith(suffix) else base

    def _chat_url(self) -> str:
        base = self._base()
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def recognize(self, image_png: bytes) -> RemoteOCRResult:
        if not self.profile.api_key:
            raise RemoteProviderError("未配置 API Key")
        if not self.profile.model.strip():
            raise RemoteProviderError("未配置模型 ID")
        started = time.perf_counter()
        data_url = "data:image/png;base64," + base64.b64encode(image_png).decode("ascii")
        body = {
            "model": self.profile.model.strip(),
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": self.profile.prompt_override.strip() or DEFAULT_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        }
        payload, request_id = self._request(
            "POST", self._chat_url(),
            headers={"Authorization": f"Bearer {self.profile.api_key}", "Content-Type": "application/json"},
            json_body=body,
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RemoteProviderError("API 响应缺少 choices.message.content") from exc
        latex = normalize_api_latex(content)
        if not latex:
            raise RemoteProviderError("API 没有返回 LaTeX")
        return RemoteOCRResult(
            raw_latex=latex,
            provider_type="openai_compatible",
            profile_name=self.profile.name,
            model=self.profile.model,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            request_id=request_id,
        )

    def list_models(self) -> list[str]:
        payload, _ = self._request(
            "GET", f"{self._base()}/models",
            headers={"Authorization": f"Bearer {self.profile.api_key}"} if self.profile.api_key else {},
        )
        values = payload.get("data", []) if isinstance(payload, dict) else []
        return [str(item["id"]) for item in values if isinstance(item, dict) and item.get("id")]


class MathpixProvider(_HTTPProviderBase):
    def _base(self) -> str:
        base = self.profile.base_url
        if not base or base == "https://api.openai.com/v1":
            base = "https://api.mathpix.com"
        return validate_endpoint(base)

    def recognize(self, image_png: bytes) -> RemoteOCRResult:
        if not self.profile.app_id or not self.profile.app_key:
            raise RemoteProviderError("未配置 Mathpix App ID/App Key")
        started = time.perf_counter()
        body = {
            "src": "data:image/png;base64," + base64.b64encode(image_png).decode("ascii"),
            "formats": ["latex_styled"],
            "rm_spaces": True,
            "rm_fonts": False,
            "improve_mathpix": False,
        }
        payload, request_id = self._request(
            "POST", f"{self._base()}/v3/text",
            headers={"app_id": self.profile.app_id, "app_key": self.profile.app_key, "Content-Type": "application/json"},
            json_body=body,
        )
        latex = normalize_api_latex(payload)
        if not latex:
            raise RemoteProviderError("Mathpix 没有返回 LaTeX")
        confidence = payload.get("confidence") if isinstance(payload, dict) else None
        if confidence is None and isinstance(payload, dict):
            confidence = payload.get("latex_confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        return RemoteOCRResult(
            raw_latex=latex,
            provider_type="mathpix",
            profile_name=self.profile.name,
            model="Mathpix",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            confidence=confidence,
            request_id=request_id,
        )

    def list_models(self) -> list[str]:
        return []


def provider_for_profile(profile, *, client_factory=None) -> RemoteFormulaProvider:
    if profile.provider_type == "mathpix":
        return MathpixProvider(profile, client_factory=client_factory)
    return OpenAICompatibleProvider(profile, client_factory=client_factory)
