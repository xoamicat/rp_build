import httpx
import pytest

from sakshi.llm import GeminiError, GeminiProvider


class _Resp:
    def __init__(self, status, payload=None, text="", headers=None):
        self.status_code, self._payload, self.text, self.headers = status, payload or {}, text, headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


def test_gemini_parses_candidates_and_retries_429(monkeypatch):
    calls = []

    def fake_post(url, params=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return _Resp(429, text="quota", headers={"retry-after": "0"})
        return _Resp(200, {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    p = GeminiProvider("k", "gemini-x", rpm=6000)
    assert p.complete("hi", system="s", json_mode=True) == '{"ok": true}'
    assert len(calls) == 2 and p.calls == 2
    assert calls[0]["generationConfig"]["responseMimeType"] == "application/json"
    assert calls[0]["systemInstruction"]["parts"][0]["text"] == "s"


def test_gemini_404_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(404, text="not found"))
    with pytest.raises(GeminiError) as exc:
        GeminiProvider("k", "gemini-old", rpm=6000).complete("hi")
    assert "llm_check.py" in str(exc.value)


def test_gemini_list_models_filters_generate_content(monkeypatch):
    payload = {"models": [
        {"name": "models/gemini-2.5-flash-lite", "displayName": "Lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/embedding-001", "displayName": "Emb", "supportedGenerationMethods": ["embedContent"]},
    ]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200, payload))
    names = [m["name"] for m in GeminiProvider("k", "gemini-2.5-flash-lite").list_models()]
    assert names == ["gemini-2.5-flash-lite"]
