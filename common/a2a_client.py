from __future__ import annotations

import os
import hashlib
import asyncio
import json
import random
import subprocess
import time
from typing import Any
from uuid import uuid4

import httpx

from common.evidence import append_event
from common.models import Actor
from common.structured_logging import log_event

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_CARD_CACHE_TTL_SECONDS = 600.0
_AGENT_CARD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _stable_hash(value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _timeout() -> httpx.Timeout:
    connect = _float_env("AKRETIC_A2A_CONNECT_TIMEOUT_SECONDS", 5.0)
    read = _float_env("AKRETIC_A2A_READ_TIMEOUT_SECONDS", 30.0)
    return httpx.Timeout(connect=connect, read=read, write=connect, pool=connect)


def _total_timeout_seconds() -> float:
    return _float_env("AKRETIC_A2A_TOTAL_TIMEOUT_SECONDS", 45.0)


def _cache_ttl_seconds() -> float:
    return min(max(_float_env("AKRETIC_A2A_CARD_CACHE_TTL_SECONDS", DEFAULT_CARD_CACHE_TTL_SECONDS), 300.0), 900.0)


def _cache_key(base_url: str, service_name: str | None = None) -> str:
    service = (service_name or "").strip()
    return f"{service}|{base_url.rstrip('/')}"


def _auth_headers(base_url: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(headers or {})
    if os.getenv("AKRETIC_CLOUD_RUN_AUTH") != "identity_token":
        return merged

    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    audience = base_url.rstrip("/")
    try:
        token = id_token.fetch_id_token(Request(), audience)
    except Exception:
        token = _gcloud_identity_token(audience)
    merged["Authorization"] = f"Bearer {token}"
    return merged


def cloud_run_auth_headers(base_url: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    return _auth_headers(base_url, headers)


def _gcloud_identity_token(audience: str) -> str:
    gcloud = "gcloud.cmd" if os.name == "nt" else "gcloud"
    impersonate = (
        os.getenv("AKRETIC_CLOUD_RUN_IMPERSONATE_SERVICE_ACCOUNT")
        or os.getenv("GOOGLE_IMPERSONATE_SERVICE_ACCOUNT")
        or ""
    ).strip()
    commands: list[list[str]] = []
    if impersonate:
        commands.append(
            [
                gcloud,
                "auth",
                "print-identity-token",
                f"--impersonate-service-account={impersonate}",
                f"--audiences={audience}",
                "--include-email",
            ]
        )
    commands.append([gcloud, "auth", "print-identity-token", f"--audiences={audience}"])
    commands.append([gcloud, "auth", "print-identity-token"])

    errors: list[str] = []
    for command in commands:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=30)
        token = completed.stdout.strip()
        if completed.returncode == 0 and token:
            return token
        errors.append((completed.stderr or completed.stdout or "no output").strip())
    raise RuntimeError("unable to mint Cloud Run identity token with gcloud: " + " | ".join(errors))


async def fetch_agent_card(base_url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return await fetch_agent_card_cached(base_url, headers=headers)


async def fetch_agent_card_cached(
    base_url: str,
    headers: dict[str, str] | None = None,
    *,
    service_name: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    key = _cache_key(base_url, service_name)
    now = time.monotonic()
    cached = _AGENT_CARD_CACHE.get(key)
    if not refresh and cached and cached[0] > now:
        log_event("a2a_cache_hit", callee=service_name, service=service_name, retry_count=0)
        return dict(cached[1])

    log_event("a2a_cache_miss", callee=service_name, service=service_name, retry_count=0)
    url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    request_headers = _auth_headers(base_url, headers)
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        for attempt in range(1, 4):
            started = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    client.get(url, headers=request_headers),
                    timeout=_total_timeout_seconds(),
                )
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                if response.status_code in RETRY_STATUS_CODES and attempt < 3:
                    log_event(
                        "a2a_retry",
                        callee=service_name,
                        service=service_name,
                        latency_ms=latency_ms,
                        timeout_ms=round(_total_timeout_seconds() * 1000),
                        retry_count=attempt,
                        error_class=f"http_{response.status_code}",
                    )
                    await asyncio.sleep(random.uniform(0.15, 0.45) * attempt)
                    continue
                response.raise_for_status()
                card = response.json()
                _AGENT_CARD_CACHE[key] = (time.monotonic() + _cache_ttl_seconds(), dict(card))
                return card
            except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
                last_exc = exc
                log_event(
                    "a2a_card_timeout",
                    callee=service_name,
                    service=service_name,
                    timeout_ms=round(_total_timeout_seconds() * 1000),
                    retry_count=attempt,
                    error_class=type(exc).__name__,
                )
                if attempt >= 3:
                    raise
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status not in RETRY_STATUS_CODES or attempt >= 3:
                    raise
                log_event(
                    "a2a_retry",
                    callee=service_name,
                    service=service_name,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    timeout_ms=round(_total_timeout_seconds() * 1000),
                    retry_count=attempt,
                    error_class=f"http_{status}",
                )
            await asyncio.sleep(random.uniform(0.15, 0.45) * attempt)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"unable to fetch Agent Card for {base_url}")


def _skill_is_idempotent(skill: str, payload: dict[str, Any]) -> bool:
    if skill in {
        "authorize_intent",
        "classify_resource",
        "explain_decision",
        "issue_decision_receipt",
        "validate_decision_receipt",
        "retrieve_permitted_context",
        "retrieve_by_query",
        "list_sources",
        "redact_context",
        "research_vendor_profile",
        "check_public_risk_signals",
        "verify_chain",
        "generate_report",
    }:
        return True
    if skill in {"decide_approval", "request_approval", "record_event"}:
        return bool(payload.get("idempotency_key"))
    return False


async def call_skill(
    *,
    base_url: str,
    skill: str,
    payload: dict[str, Any],
    run_id: str,
    caller_agent_id: str,
    actor: Actor,
    evidence_path: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    correlation_id = payload.get("correlation_id") or f"corr_{uuid4().hex}"
    payload = {**payload, "run_id": run_id, "correlation_id": correlation_id}
    request_hash = _stable_hash({"skill": skill, "payload": payload})
    agent_card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    started = time.perf_counter()
    request_headers = _auth_headers(base_url, headers)
    card = await fetch_agent_card_cached(base_url, headers=headers)
    attempts = 3 if _skill_is_idempotent(skill, payload) else 1
    result: dict[str, Any] | None = None
    http_status = 0
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await asyncio.wait_for(
                    client.post(
                        f"{base_url.rstrip('/')}/{skill}",
                        json=payload,
                        headers=request_headers,
                    ),
                    timeout=_total_timeout_seconds(),
                )
                http_status = response.status_code
                if response.status_code in RETRY_STATUS_CODES and attempt < attempts:
                    await fetch_agent_card_cached(base_url, headers=headers, refresh=True)
                    log_event(
                        "a2a_retry",
                        run_id=run_id,
                        correlation_id=correlation_id,
                        caller=caller_agent_id,
                        callee=card.get("name"),
                        skill=skill,
                        service=card.get("name"),
                        latency_ms=round((time.perf_counter() - started) * 1000, 2),
                        timeout_ms=round(_total_timeout_seconds() * 1000),
                        retry_count=attempt,
                        error_class=f"http_{response.status_code}",
                    )
                    await asyncio.sleep(random.uniform(0.15, 0.45) * attempt)
                    continue
                response.raise_for_status()
                result = response.json()
                break
            except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
                log_event(
                    "a2a_skill_timeout",
                    run_id=run_id,
                    correlation_id=correlation_id,
                    caller=caller_agent_id,
                    callee=card.get("name"),
                    skill=skill,
                    service=card.get("name"),
                    timeout_ms=round(_total_timeout_seconds() * 1000),
                    retry_count=attempt,
                    error_class=type(exc).__name__,
                )
                if attempt >= attempts:
                    raise
                await fetch_agent_card_cached(base_url, headers=headers, refresh=True)
                await asyncio.sleep(random.uniform(0.15, 0.45) * attempt)
            except httpx.HTTPStatusError:
                raise
    if result is None:
        raise RuntimeError(f"A2A skill {skill} returned no result")
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response_hash = _stable_hash(result)
    event = append_event(
        run_id=run_id,
        actor=actor,
        agent_id=caller_agent_id,
        action="a2a_call",
        resource_id=card.get("name", base_url),
        outcome="result",
        reason=f"called remote A2A skill {skill}",
        correlation_id=correlation_id,
        path=evidence_path,
        metadata={
            "caller": caller_agent_id,
            "callee": card.get("name"),
            "skill": skill,
            "base_url": base_url,
            "agent_card_url": agent_card_url,
            "advertised_url": card.get("url"),
            "http_status": http_status,
            "latency_ms": latency_ms,
            "policy_decision_id": payload.get("policy_decision_id"),
            "decision_receipt_id": (
                payload.get("policy_decision_receipt") or payload.get("decision_receipt") or {}
            ).get("decision_id"),
            "request_hash": request_hash,
            "response_hash": response_hash,
            "identity_source": "demo identity adapter",
            "browser_transport": "not used for server-side A2A call",
            "verifier_transport": "x-akretic-persona header",
            "transport": "x-akretic-persona header",
        },
    )
    return {
        **result,
        "_a2a_event": {
            "event_id": event["event_id"],
            "event_hash": event["event_hash"],
            "agent_card_url": agent_card_url,
            "base_url": base_url,
            "caller": caller_agent_id,
            "callee": card.get("name"),
            "skill": skill,
            "correlation_id": correlation_id,
            "outcome": event["outcome"],
            "http_status": http_status,
            "latency_ms": latency_ms,
            "request_hash": request_hash,
            "response_hash": response_hash,
        },
    }
