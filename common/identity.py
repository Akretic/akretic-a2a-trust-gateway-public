from __future__ import annotations

from typing import Any

import yaml

from common.models import Actor
from common.paths import env_path


def load_personas(path: str | None = None) -> dict[str, Any]:
    persona_path = env_path("PERSONAS_PATH", path or "policies/personas.yaml")
    with persona_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["personas"]


def derive_actor(persona_key: str = "procurement_user", *, personas_path: str | None = None) -> Actor:
    personas = load_personas(personas_path)
    if persona_key not in personas:
        raise KeyError(f"Unknown demo persona: {persona_key}")
    return Actor.from_dict(personas[persona_key])


def derive_actor_from_request(
    *,
    demo_persona: str | None,
    body_claims: dict[str, Any] | None = None,
    personas_path: str | None = None,
) -> Actor:
    """Derive identity from trusted demo adapter input, ignoring request-body privilege claims.

    `body_claims` is accepted only so tests can prove it cannot upgrade identity.
    """
    persona = demo_persona or "procurement_user"
    actor = derive_actor(persona, personas_path=personas_path)
    _ = body_claims  # Explicitly ignored by design.
    return actor
