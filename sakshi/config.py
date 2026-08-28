"""Runtime settings, read from environment variables (and a local .env if present).

Nothing here is required for drop 1. With no Razorpay keys the interceptor
runs in stub mode; with SAKSHI_LLM unset the mock provider is used.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional: python-dotenv
    from dotenv import load_dotenv

    load_dotenv()
    # A locally generated demo key can live outside .env (and outside Git) without
    # overwriting a developer's real deployment key.  It is only a fallback.
    if not os.environ.get("SAKSHI_EVIDENCE_PRIVATE_KEY_B64"):
        load_dotenv(".atlas-evidence.env", override=True)
except Exception:  # pragma: no cover
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Razorpay test-mode credentials. Leave empty to run the interceptor in stub mode.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_base_url: str = "https://api.razorpay.com"
    razorpay_webhook_secret: str = ""

    # Base64url-encoded Ed25519 private key. Required for production-grade signed evidence.
    evidence_private_key_b64: str = ""
    evidence_key_id: str = "sakshi-dev-1"

    # LLM provider: mock | ollama | gemini
    llm: str = "mock"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_rpm: int = 10  # stay under the free tier; check your own quota page
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Ledger location. ":memory:" is used by tests.
    db_path: str = "data/sakshi.db"

    # Atlas uses this durable store only when the configured Ed25519 key is present.
    # This separation keeps demo/test evidence from a merchant's broader Sakshi ledger.
    atlas_evidence_db: str = "data/atlas_evidence.db"

    @property
    def has_razorpay_keys(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def has_durable_atlas_evidence(self) -> bool:
        return bool(self.evidence_private_key_b64 and self.atlas_evidence_db)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", ""),
            razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET", ""),
            razorpay_base_url=os.environ.get("RAZORPAY_BASE_URL", "https://api.razorpay.com"),
            razorpay_webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", ""),
            evidence_private_key_b64=os.environ.get("SAKSHI_EVIDENCE_PRIVATE_KEY_B64", ""),
            evidence_key_id=os.environ.get("SAKSHI_EVIDENCE_KEY_ID", "sakshi-dev-1"),
            llm=os.environ.get("SAKSHI_LLM", "mock").lower(),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            gemini_rpm=_int("GEMINI_RPM", 10),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
            db_path=os.environ.get("SAKSHI_DB", "data/sakshi.db"),
            atlas_evidence_db=os.environ.get("ATLAS_EVIDENCE_DB", "data/atlas_evidence.db"),
        )
