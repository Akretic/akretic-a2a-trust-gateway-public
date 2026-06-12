from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from common.models import Actor
from common.structured_logging import log_event

LOCAL_TEST_MODE = "local"
VERTEX_MODE = "vertex"
RUNTIME_LOCAL = "local"
RUNTIME_CLOUD = "cloud"
DENIED_SOURCE_CANARIES = {
    "executive_acquisition_memo": (
        "Project Helios",
        "confidential acquisition timing",
        "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE",
    )
}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class GeminiError(RuntimeError):
    """Base class for Gemini adapter failures safe to show in demo failure states."""


class GeminiConfigurationError(GeminiError):
    """Raised when required Gemini/Vertex configuration is missing or invalid."""


class GeminiUnavailableError(GeminiError):
    """Raised when Vertex/Gemini cannot complete a configured request."""


class GeminiContentViolation(GeminiError):
    """Raised when model input or output would violate the P2 context boundary."""


def runtime_mode(value: str | None = None) -> str:
    mode = (value or os.getenv("AKRETIC_RUNTIME_MODE", RUNTIME_LOCAL)).strip().lower()
    if mode not in {RUNTIME_LOCAL, RUNTIME_CLOUD}:
        raise GeminiConfigurationError(f"Unknown runtime mode: {mode}")
    return mode


def resolve_model_mode(*, requested_mode: str | None = None, runtime: str | None = None) -> str:
    active_runtime = runtime_mode(runtime)
    if active_runtime == RUNTIME_CLOUD:
        if requested_mode and requested_mode != VERTEX_MODE:
            raise GeminiConfigurationError("Cloud runtime requires Vertex Gemini mode")
        legacy_mode = os.getenv("AKRETIC_GEMINI_MODE")
        if legacy_mode and legacy_mode.strip().lower() != VERTEX_MODE:
            raise GeminiConfigurationError("Cloud runtime cannot use local deterministic summaries")
        return VERTEX_MODE
    return (requested_mode or os.getenv("AKRETIC_GEMINI_MODE", LOCAL_TEST_MODE)).strip().lower()


def vertex_config() -> dict[str, str]:
    return {
        "project_id": os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID", ""),
        "location": os.getenv("GOOGLE_CLOUD_LOCATION", ""),
        "model": os.getenv("VERTEX_MODEL", ""),
    }


def _prompt_hash(prompt: dict[str, Any]) -> str:
    material = "\n".join([prompt["system_instruction"], prompt["contents"]])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_no_denied_source_text(
    *,
    text: str,
    denied_source_ids: list[str],
    surface: str,
) -> None:
    lower_text = text.lower()
    for source_id in denied_source_ids:
        for canary in DENIED_SOURCE_CANARIES.get(source_id, ()):
            if canary.lower() in lower_text:
                raise GeminiContentViolation(
                    f"Denied source content detected in {surface} for source_id {source_id}"
                )


def _assert_pending_approval_not_completed(
    *,
    text: str,
    export_decision: dict[str, Any],
) -> None:
    if export_decision.get("outcome") != "approval_required":
        return
    lower_text = text.lower()
    completed_phrases = (
        "export completed",
        "export is complete",
        "external export completed",
        "action completed",
        "approval completed",
        "approved and sent",
        "sent externally",
        "sent to external",
        "successfully exported",
    )
    if any(phrase in lower_text for phrase in completed_phrases):
        raise GeminiContentViolation(
            "Model output claimed an approval-gated action completed while approval is pending"
        )


def _classify_vertex_error(exc: Exception) -> str:
    detail = f"{type(exc).__name__} {exc}".lower()
    if any(token in detail for token in ("credential", "defaultcredentials", "unauthenticated")):
        return (
            "Vertex/Gemini credential error: verify ADC locally or the Cloud Run "
            "runtime service account credential path."
        )
    if any(token in detail for token in ("permission", "forbidden", "403", "denied", "iam")):
        return (
            "Vertex/Gemini permission error: verify the runtime service account has "
            "least-privilege Vertex AI access."
        )
    if any(token in detail for token in ("quota", "resourceexhausted", "429", "rate limit")):
        return (
            "Vertex/Gemini quota error: quota or rate limit is unavailable for the "
            "configured project, location, or model."
        )
    if any(token in detail for token in ("billing", "org policy", "organization policy")):
        return "Vertex/Gemini billing or organization policy error blocked the request."
    if any(token in detail for token in ("not found", "404", "invalid model", "location")):
        return "Vertex/Gemini model, project, or location configuration error."
    if any(token in detail for token in ("api has not been used", "api disabled", "enable it")):
        return "Vertex AI API is unavailable or disabled for the configured project."
    return (
        "Vertex/Gemini API error: verify project, location, model, quota, and "
        "credentials in Cloud Run logs."
    )


def build_vendor_review_prompt(
    *,
    query: str,
    actor: Actor,
    retrieval: dict[str, Any],
    export_decision: dict[str, Any],
) -> dict[str, Any]:
    permitted_chunks = retrieval.get("chunks", [])
    permitted_source_ids = _dedupe([chunk["source_id"] for chunk in permitted_chunks])
    denied_source_ids = [source["source_id"] for source in retrieval.get("denied_sources", [])]

    context_blocks = []
    for chunk in permitted_chunks:
        context_blocks.append(
            "\n".join(
                [
                    f"source_id: {chunk['source_id']}",
                    f"title: {chunk['title']}",
                    f"classification: {chunk['classification']}",
                    "text:",
                    chunk["text"],
                ]
            )
        )

    system_instruction = (
        "You are the Akretic A2A Trust Gateway root summarizer. "
        "Use only the permitted context provided in the prompt. "
        "Do not infer, summarize, reveal, or quote denied source contents. "
        "If an external action is approval_required, state that it is pending approval and has not completed. "
        "Authorization, approval, identity, and evidence decisions are already made outside the model."
    )
    contents = "\n\n".join(
        [
            "Vendor-risk review target: VendorNova",
            f"Requester query: {query}",
            f"Derived actor: {actor.actor_id} role={actor.role} groups={', '.join(actor.groups)}",
            f"Permitted source IDs: {', '.join(permitted_source_ids) or 'none'}",
            f"Denied source IDs withheld from context: {', '.join(denied_source_ids) or 'none'}",
            f"External export policy outcome: {export_decision['outcome']}",
            "Permitted context:",
            "\n\n---\n\n".join(context_blocks) if context_blocks else "No permitted context returned.",
            (
                "Return a concise VendorNova review summary with source IDs, open evidence gaps, "
                "and the current approval/export status. Do not state that an approval-gated "
                "export or action completed unless the policy outcome explicitly allows completion."
            ),
        ]
    )
    _assert_no_denied_source_text(
        text=f"{system_instruction}\n{contents}",
        denied_source_ids=denied_source_ids,
        surface="Gemini prompt",
    )

    return {
        "system_instruction": system_instruction,
        "contents": contents,
        "permitted_source_ids": permitted_source_ids,
        "denied_source_ids": denied_source_ids,
    }


def _local_summary(prompt: dict[str, Any], export_decision: dict[str, Any]) -> str:
    sources = ", ".join(prompt["permitted_source_ids"]) or "none"
    return (
        "LOCAL_DETERMINISTIC_SUMMARY_FOR_TESTS_ONLY: "
        "VendorNova review assembled from permitted synthetic context only. "
        f"Permitted sources: {sources}. "
        f"External export decision: {export_decision['outcome']}."
    )


def _vertex_summary(
    *,
    prompt: dict[str, Any],
    project_id: str,
    location: str,
    model: str,
) -> str:
    from google import genai
    from google.genai.types import GenerateContentConfig, HttpOptions

    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        http_options=HttpOptions(api_version="v1"),
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt["contents"],
        config=GenerateContentConfig(
            system_instruction=prompt["system_instruction"],
            temperature=0.2,
            max_output_tokens=512,
        ),
    )
    return response.text or ""


def lightweight_vertex_check() -> dict[str, Any]:
    runtime = runtime_mode()
    mode = resolve_model_mode(runtime=runtime)
    config = vertex_config()
    model = config["model"] or "gemini-2.5-flash"
    project_id = config["project_id"]
    location = config["location"] or "us-central1"
    if mode != VERTEX_MODE:
        return {
            "ok": runtime == RUNTIME_LOCAL,
            "runtime_mode": runtime,
            "model_mode": mode,
            "model": "local-deterministic-test-summary",
            "latency_ms": 0,
            "note": "Vertex warmup is only required in cloud runtime.",
        }
    missing = []
    if not project_id:
        missing.append("GOOGLE_CLOUD_PROJECT or PROJECT_ID")
    if runtime == RUNTIME_CLOUD and not config["location"]:
        missing.append("GOOGLE_CLOUD_LOCATION")
    if runtime == RUNTIME_CLOUD and not config["model"]:
        missing.append("VERTEX_MODEL")
    if missing:
        raise GeminiConfigurationError("Vertex Gemini mode requires: " + ", ".join(missing))

    from google import genai
    from google.genai.types import GenerateContentConfig, HttpOptions

    started = time.perf_counter()
    try:
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
            http_options=HttpOptions(api_version="v1"),
        )
        response = client.models.generate_content(
            model=model,
            contents="Return the single word ready.",
            config=GenerateContentConfig(temperature=0, max_output_tokens=4),
        )
    except Exception as exc:
        error = _classify_vertex_error(exc)
        event_type = "vertex_timeout"
        detail = f"{type(exc).__name__} {exc}".lower()
        if "429" in detail or "quota" in detail or "rate" in detail:
            event_type = "vertex_429"
        elif any(token in detail for token in ("500", "502", "503", "504", "unavailable")):
            event_type = "vertex_5xx"
        log_event(
            event_type,
            service="vertex-gemini",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error_class=type(exc).__name__,
            retry_count=0,
        )
        raise GeminiUnavailableError(error) from exc
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    text = response.text or ""
    return {
        "ok": True,
        "runtime_mode": runtime,
        "model_mode": mode,
        "model": model,
        "project_id": project_id,
        "location": location,
        "latency_ms": latency_ms,
        "output_hash": _text_hash(text),
    }


def summarize_vendor_review(
    *,
    query: str,
    actor: Actor,
    retrieval: dict[str, Any],
    export_decision: dict[str, Any],
    mode: str | None = None,
) -> dict[str, Any]:
    prompt = build_vendor_review_prompt(
        query=query,
        actor=actor,
        retrieval=retrieval,
        export_decision=export_decision,
    )
    runtime = runtime_mode()
    mode = resolve_model_mode(requested_mode=mode, runtime=runtime)
    config = vertex_config()
    model = config["model"] or "gemini-2.5-flash"
    project_id = config["project_id"]
    location = config["location"] or "us-central1"
    prompt_hash = _prompt_hash(prompt)
    guardrails = [
        "denied_source_text_guard",
        "approval_pending_guard",
        "permitted_context_only",
    ]

    if mode == LOCAL_TEST_MODE:
        text = _local_summary(prompt, export_decision)
        _assert_no_denied_source_text(
            text=text,
            denied_source_ids=prompt["denied_source_ids"],
            surface="local model output",
        )
        _assert_pending_approval_not_completed(text=text, export_decision=export_decision)
        output_hash = _text_hash(text)
        return {
            "mode": mode,
            "runtime_mode": runtime,
            "model": "local-deterministic-test-summary",
            "text": text,
            "prompt": prompt,
            "service_path": "local deterministic summary for tests only",
            "prompt_hash": prompt_hash,
            "output_hash": output_hash,
            "completion_hash": output_hash,
            "guardrails": guardrails,
        }

    if mode != VERTEX_MODE:
        raise GeminiConfigurationError(f"Unknown Gemini mode: {mode}")
    missing = []
    if not project_id:
        missing.append("GOOGLE_CLOUD_PROJECT or PROJECT_ID")
    if runtime == RUNTIME_CLOUD and not config["location"]:
        missing.append("GOOGLE_CLOUD_LOCATION")
    if runtime == RUNTIME_CLOUD and not config["model"]:
        missing.append("VERTEX_MODEL")
    if missing:
        raise GeminiConfigurationError(
            "Vertex Gemini mode requires: " + ", ".join(missing)
        )

    try:
        text = _vertex_summary(
            prompt=prompt,
            project_id=project_id,
            location=location,
            model=model,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__} {exc}".lower()
        if "429" in detail or "quota" in detail or "rate" in detail:
            event_type = "vertex_429"
        elif any(token in detail for token in ("500", "502", "503", "504", "unavailable")):
            event_type = "vertex_5xx"
        elif "timeout" in detail:
            event_type = "vertex_timeout"
        else:
            event_type = "vertex_5xx"
        log_event(event_type, service="vertex-gemini", retry_count=0, error_class=type(exc).__name__)
        raise GeminiUnavailableError(_classify_vertex_error(exc)) from exc

    _assert_no_denied_source_text(
        text=text,
        denied_source_ids=prompt["denied_source_ids"],
        surface="Vertex model output",
    )
    _assert_pending_approval_not_completed(text=text, export_decision=export_decision)
    output_hash = _text_hash(text)
    return {
        "mode": mode,
        "runtime_mode": runtime,
        "model": model,
        "text": text,
        "prompt": prompt,
        "service_path": "Vertex AI Gemini via google-genai",
        "project_id": project_id,
        "location": location,
        "prompt_hash": prompt_hash,
        "output_hash": output_hash,
        "completion_hash": output_hash,
        "guardrails": guardrails,
    }
