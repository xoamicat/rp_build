"""Intercepting proxy for Razorpay's API.

Point any agent's Razorpay base URL at this service (default http://localhost:8787).
Every request and response is written to the ledger, linked to a Sakshi transaction
by the ``X-Sakshi-Txn`` header or by ``notes.sakshi_txn`` in the body.

Two modes:
  forward = True   : relay to api.razorpay.com with the keys from the environment (test mode)
  forward = False  : answer from the in-memory StubGateway (no keys, no network)

This is the observation source for Stage 2: what the agent actually created versus
what it promised in the conversation.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..gateway import StubGateway
from ..ledger import Ledger

_SENSITIVE = {"card", "cvv", "number", "expiry_month", "expiry_year", "contact", "email", "vpa"}


def redact(obj):
    """Drop fields that could carry card or contact data before they reach the ledger."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k.lower() in _SENSITIVE else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def txn_of(body: dict, headers) -> str:
    header = headers.get("x-sakshi-txn")
    if header:
        return header
    notes = body.get("notes") if isinstance(body, dict) else None
    if isinstance(notes, dict) and notes.get("sakshi_txn"):
        return str(notes["sakshi_txn"])
    return "unlinked"


def _json_or_text(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return {"_raw": response.text[:2000]}


def stub_dispatch(stub: StubGateway, method: str, path: str, body: dict) -> tuple[int, dict]:
    parts = [p for p in path.split("/") if p]
    try:
        if method == "POST" and parts == ["orders"]:
            order = stub.create_order(
                amount=int(body.get("amount", 0)),
                currency=body.get("currency", "INR"),
                receipt=body.get("receipt"),
                notes=body.get("notes") or {},
            )
            return 200, order
        if method == "GET" and len(parts) == 2 and parts[0] == "orders":
            return 200, stub.fetch_order(parts[1])
        if method == "PATCH" and len(parts) == 2 and parts[0] == "orders":
            return 200, stub.update_order_notes(parts[1], body.get("notes") or {})
        if method == "GET" and len(parts) == 2 and parts[0] == "payments":
            return 200, stub.fetch_payment(parts[1])
        if method == "POST" and len(parts) == 3 and parts[0] == "payments" and parts[2] == "refund":
            return 200, stub.create_refund(parts[1], amount=body.get("amount"), notes=body.get("notes"))
        if method == "POST" and len(parts) == 3 and parts[0] == "payments" and parts[2] == "capture":
            payment = stub.fetch_payment(parts[1])
            return 200, payment
    except KeyError:
        return 400, {"error": {"code": "BAD_REQUEST_ERROR", "description": "entity not found in stub"}}
    except ValueError as exc:
        return 400, {"error": {"code": "BAD_REQUEST_ERROR", "description": str(exc)}}
    return 404, {"error": {"code": "NOT_SUPPORTED_IN_STUB", "description": f"{method} /v1/{path}"}}


def create_app(ledger: Ledger, settings: Optional[Settings] = None, forward: Optional[bool] = None,
               stub: Optional[StubGateway] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    forward = settings.has_razorpay_keys if forward is None else forward
    stub = stub or StubGateway()

    client: Optional[httpx.AsyncClient] = None
    if forward:
        client = httpx.AsyncClient(
            base_url=settings.razorpay_base_url,
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            timeout=30.0,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if client is not None:
            await client.aclose()

    app = FastAPI(title="Sakshi interceptor", version="0.1.0", lifespan=lifespan)
    app.state.ledger = ledger
    app.state.stub = stub
    app.state.forward = forward

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "mode": "forward" if forward else "stub", "events": len(ledger.events())}

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    async def intercept(path: str, request: Request):
        raw = await request.body()
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"_raw": raw.decode("utf-8", errors="replace")[:2000]}
        txn = txn_of(body, request.headers)
        ledger.append(txn, "rzp.request", "agent", {
            "method": request.method, "path": f"/v1/{path}", "query": dict(request.query_params), "body": redact(body),
        })
        if forward and client is not None:
            upstream = await client.request(
                request.method, f"/v1/{path}", params=dict(request.query_params),
                content=raw if raw else None, headers={"Content-Type": "application/json"},
            )
            status, data = upstream.status_code, _json_or_text(upstream)
        else:
            status, data = stub_dispatch(stub, request.method, path, body)
        ledger.append(txn, "rzp.response", "razorpay", {"status": status, "body": redact(data)})
        return JSONResponse(data, status_code=status)


    return app


def main() -> None:  # pragma: no cover
    """Run with: python -m sakshi.proxy.app"""
    import uvicorn

    settings = Settings.from_env()
    ledger = Ledger(settings.db_path)
    uvicorn.run(create_app(ledger, settings), host="127.0.0.1", port=8787)


if __name__ == "__main__":  # pragma: no cover
    main()
