"""One interface, three backends.

MockProvider   : scripted answers for tests and development. Never spends quota.
OllamaProvider : local model, no rate limits. Use for the sample agent under test.
GeminiProvider : free tier via REST, with a client-side rate limiter and 429 backoff.
                 Reserve it for the judge and the semantic checks.

Rule of the project: development iterations run on mock or Ollama. Cloud quota is
spent only on final runs, and every response is cached by the caller.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional, Protocol, Union

import httpx

from ..config import Settings


class Provider(Protocol):
    name: str

    def complete(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str: ...


class MockProvider:
    """Answers from a dict (substring of prompt -> response) or a callable. Records every call."""

    name = "mock"

    def __init__(self, script: Union[dict, Callable[[str, Optional[str]], str], None] = None, default: str = "{}"):
        self.script = script or {}
        self.default = default
        self.calls: list[dict] = []

    def complete(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        if callable(self.script):
            return self.script(prompt, system)
        for key, value in self.script.items():
            if key in prompt:
                return value
        return self.default


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434", timeout: float = 120.0):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout

    def complete(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str:
        payload = {"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"
        r = httpx.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("response", "")


class RateLimiter:
    """Simple spacing limiter: at most ``rpm`` calls per minute from this process."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / max(rpm, 1)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self.interval


class GeminiError(RuntimeError):
    pass


class GeminiProvider:
    name = "gemini"
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    models_endpoint = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite", rpm: int = 10,
                 max_retries: int = 5, timeout: float = 60.0):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiProvider")
        self.api_key, self.model, self.timeout = api_key, model, timeout
        self.limiter = RateLimiter(rpm)
        self.max_retries = max_retries
        self.calls = 0

    def list_models(self) -> list[dict]:
        """Models this key can call with generateContent, as {name, display, methods}."""
        r = httpx.get(self.models_endpoint, params={"key": self.api_key, "pageSize": 200}, timeout=self.timeout)
        r.raise_for_status()
        out = []
        for m in r.json().get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                out.append({"name": m.get("name", "").replace("models/", ""), "display": m.get("displayName"),
                            "methods": methods})
        return out

    def complete(self, prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str:
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        url = self.endpoint.format(model=self.model)
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            r = httpx.post(url, params={"key": self.api_key}, json=body, timeout=self.timeout)
            self.calls += 1
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    raise GeminiError(f"Gemini {r.status_code} after {attempt} retries: {r.text[:300]}")
                retry_after = r.headers.get("retry-after")
                time.sleep(float(retry_after) if retry_after else delay)
                delay = min(delay * 2, 60.0)
                continue
            if r.status_code == 404:
                raise GeminiError(f"model '{self.model}' not found for this key. Run: python scripts/llm_check.py "
                                  f"to list the models you can use, then set GEMINI_MODEL in .env")
            if r.status_code in (400, 401, 403):
                raise GeminiError(f"Gemini {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            data = r.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return json.dumps(data)
        raise RuntimeError("unreachable")


def provider_from_env(settings: Optional[Settings] = None) -> Provider:
    settings = settings or Settings.from_env()
    if settings.llm == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.gemini_rpm)
    if settings.llm == "ollama":
        return OllamaProvider(settings.ollama_model, settings.ollama_host)
    return MockProvider()
