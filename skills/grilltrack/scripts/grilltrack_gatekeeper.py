#!/usr/bin/env python3
"""Live lock gatekeeper for GrillTrack decisions.

Evaluates whether a proposed decision lock matches the user's actual scope and
detects overlocking pathologies (situational measurements locked as law,
temporal deferrals locked as permanent prohibitions, bundled compound clauses,
or one-off tactical PR chores).

Routing order in `auto` mode:
1. Primary rail: TypeSafe Jev (`jev-1.13.0` via `https://api.typesafe.ai/v1/systemone`
   or loopback `TYPESAFE_BASE_URL`), matching `ai-shed/jev-decision`.
2. Automatic fallback when Jev credits are exhausted or unavailable: OpenAI
   Responses Decision API (`gpt-6.1-sol`, strict `json_schema`).
3. Offline deterministic fallback: local pattern rubric.

Never prints or persists API keys or raw error response bodies.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


JEV_HOSTED_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_DEFAULT_MODEL = "jev-1.13.0"
JEV_KEYCHAIN_SERVICE = "typesafe-jev"

OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
OPENAI_DEFAULT_MODEL = "gpt-6.1-sol"
OPENAI_KEYCHAIN_SERVICE = "api-oracle"
OPENAI_KEYCHAIN_ACCOUNT = "OPENAI_API_KEY"

GATE_MODES = {"auto", "jev", "openai", "heuristic", "off"}

DECISION_TYPES = ("durable", "slice", "deferral", "tactical")
OVERLOCK_CATEGORIES = (
    "clean",
    "bundled_extra_invariants",
    "numeric_measurement_locked_as_law",
    "temporal_deferral_locked_as_rule",
    "provisional_direction_locked_as_final",
)

_TEMPORAL_DEFERRAL_RE = re.compile(
    r"\b(?:"
    r"wait(?:s|ing)?\s+for\s+(?:a\s+)?later\s+phase|"
    r"defer(?:red)?\s+(?:to|until)|"
    r"parked\s+(?:until|for\s+later)|"
    r"not\s+in\s+v1\b.*?\blater|"
    r"comes?\s+in\s+phase\s+[234]|"
    r"skip\s+for\s+now"
    r")\b",
    re.IGNORECASE,
)

_SITUATIONAL_METRIC_RE = re.compile(
    r"\b(?:"
    r"\d[\d,]*\s*(?:bytes?|b)\s+(?:reserve|headroom|left\s+under)|"
    r"leave\s+at\s+least\s+\d[\d,]*\s*(?:bytes?|kib)|"
    r"port\s+\d{4,5}\b"
    r")\b",
    re.IGNORECASE,
)

_ONE_OFF_CHORE_RE = re.compile(
    r"\b(?:"
    r"merge\s+main\s+into\s+pr|"
    r"rerun\s+ci\s+on\s+pr|"
    r"rebase\s+branch|"
    r"bump\s+beta\s+tag"
    r")\b",
    re.IGNORECASE,
)


def _read_macos_keychain(
    service: str, account: str | None = None
) -> str | None:
    if sys.platform != "darwin":
        return None
    cmd = ["/usr/bin/security", "find-generic-password", "-s", service]
    if account:
        cmd.extend(["-a", account])
    cmd.append("-w")
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    token = proc.stdout.strip()
    return token or None


def _resolve_jev_key(env: dict[str, str]) -> str | None:
    if env.get("JEV_DISABLED") == "1":
        return None
    direct = (env.get("TYPESAFE_API_KEY") or "").strip()
    if direct:
        return direct
    service = (env.get("JEV_KEYCHAIN_SERVICE") or JEV_KEYCHAIN_SERVICE).strip()
    return _read_macos_keychain(service)


def _resolve_openai_key(env: dict[str, str]) -> str | None:
    direct = (env.get("OPENAI_API_KEY") or "").strip()
    if direct:
        return direct
    return _read_macos_keychain(
        OPENAI_KEYCHAIN_SERVICE, account=OPENAI_KEYCHAIN_ACCOUNT
    )


def _build_jev_questions() -> dict[str, Any]:
    return {
        "decision_type": {
            "type": "choice",
            "instructions": (
                "Classify the true scope of this decision based on the question, "
                "choice, rationale, and user_reply."
            ),
            "criteria": {
                "durable": (
                    "Permanent repo-wide architectural, domain, or security "
                    "invariant meant to govern future work indefinitely."
                ),
                "slice": (
                    "Scoped to the current PR, feature slice, or immediate "
                    "milestone, not a permanent law."
                ),
                "deferral": (
                    "Pausing, parking, or deferring a feature ('not now', "
                    "'wait for a later phase', 'after v1') rather than "
                    "permanently banning it."
                ),
                "tactical": (
                    "A situational measurement (e.g. exact bytes of headroom "
                    "right now), one-off repair, or temporary plumbing step."
                ),
            },
        },
        "overlock_risk": {
            "type": "choice",
            "instructions": (
                "Did the proposed choice/rationale overlock beyond what the "
                "user actually endorsed?"
            ),
            "criteria": {
                "clean": (
                    "Choice accurately and narrowly reflects the user's intent "
                    "with no extra unapproved constraints."
                ),
                "bundled_extra_invariants": (
                    "Agent bundled multiple architectural rules or unapproved "
                    "side constraints into a short affirmative reply."
                ),
                "numeric_measurement_locked_as_law": (
                    "Agent turned a situational number or point-in-time "
                    "headroom measurement into a permanent numeric reserve."
                ),
                "temporal_deferral_locked_as_rule": (
                    "Agent turned 'not right now / wait for later phase' into "
                    "a permanent 'locked' prohibition instead of a deferral."
                ),
                "provisional_direction_locked_as_final": (
                    "Agent locked a tentative or exploratory user reply as a "
                    "hard permanent requirement."
                ),
            },
        },
        "scope_faithful": {
            "type": "noul",
            "instructions": (
                "Does the declared scope match the user's actual intent "
                "without overlocking?"
            ),
        },
    }


def evaluate_via_jev(
    state: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
    timeout_sec: float = 15.0,
) -> dict[str, Any] | None:
    runtime_env = env if env is not None else dict(os.environ)
    api_key = _resolve_jev_key(runtime_env)
    base_url = (runtime_env.get("TYPESAFE_BASE_URL") or "").strip()
    if base_url:
        endpoint = base_url.rstrip("/") + "/v1/systemone"
        model = runtime_env.get("JEV_MODEL") or "kev-latest"
    else:
        if not api_key:
            return None
        endpoint = JEV_HOSTED_ENDPOINT
        model = runtime_env.get("JEV_MODEL") or JEV_DEFAULT_MODEL

    payload = {
        "model": model,
        "state": state,
        "questions": _build_jev_questions(),
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read(1024 * 1024).decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None

    answers = parsed.get("answers")
    if not isinstance(answers, dict):
        return None
    dt_ans = answers.get("decision_type") or {}
    ol_ans = answers.get("overlock_risk") or {}
    sf_ans = answers.get("scope_faithful") or {}

    decision_type = dt_ans.get("choice")
    overlock_risk = ol_ans.get("choice")
    if decision_type not in DECISION_TYPES or overlock_risk not in OVERLOCK_CATEGORIES:
        return None

    confidence = float(ol_ans.get("confidence", dt_ans.get("confidence", 0.8)))
    scope_faithful_prob = float(sf_ans.get("noul", 1.0))
    return _adjudicate_verdict(
        declared_scope=str(state.get("declared_scope") or "durable"),
        decision_type=decision_type,
        overlock_risk=overlock_risk,
        confidence=confidence,
        scope_faithful_prob=scope_faithful_prob,
        provider="jev",
        model=str(parsed.get("model") or model),
    )


def evaluate_via_openai(
    state: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
    timeout_sec: float = 20.0,
) -> dict[str, Any] | None:
    runtime_env = env if env is not None else dict(os.environ)
    api_key = _resolve_openai_key(runtime_env)
    if not api_key:
        return None

    model = (
        runtime_env.get("GRILLTRACK_OPENAI_MODEL")
        or runtime_env.get("OPENAI_DECISION_MODEL")
        or OPENAI_DEFAULT_MODEL
    ).strip()

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision_type",
            "overlock_risk",
            "confidence",
            "scope_faithful",
            "reason",
        ],
        "properties": {
            "decision_type": {
                "type": "string",
                "enum": list(DECISION_TYPES),
            },
            "overlock_risk": {
                "type": "string",
                "enum": list(OVERLOCK_CATEGORIES),
            },
            "confidence": {
                "type": "number",
            },
            "scope_faithful": {
                "type": "boolean",
            },
            "reason": {
                "type": "string",
            },
        },
    }

    system_prompt = (
        "You are the GrillTrack Lock Gatekeeper. Classify whether the proposed "
        "decision lock matches the user's true scope (durable, slice, deferral, "
        "or tactical) and whether it introduces an overlock pathology "
        "(bundled_extra_invariants, numeric_measurement_locked_as_law, "
        "temporal_deferral_locked_as_rule, or provisional_direction_locked_as_final)."
    )

    body = {
        "model": model,
        "instructions": system_prompt,
        "input": json.dumps(state, sort_keys=True),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "grilltrack_lock_verdict",
                "strict": True,
                "schema": schema,
            }
        },
    }

    request = urllib.request.Request(
        OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read(1024 * 1024).decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        parsed = json.loads(raw)
        output_text = parsed.get("output_text")
        if not output_text:
            for item in parsed.get("output") or []:
                for content in item.get("content") or []:
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        output_text = content["text"]
                        break
        if not output_text:
            return None
        verdict = json.loads(output_text)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None

    decision_type = verdict.get("decision_type")
    overlock_risk = verdict.get("overlock_risk")
    if decision_type not in DECISION_TYPES or overlock_risk not in OVERLOCK_CATEGORIES:
        return None

    return _adjudicate_verdict(
        declared_scope=str(state.get("declared_scope") or "durable"),
        decision_type=decision_type,
        overlock_risk=overlock_risk,
        confidence=float(verdict.get("confidence", 0.85)),
        scope_faithful_prob=1.0 if verdict.get("scope_faithful") else 0.2,
        provider="openai",
        model=str(parsed.get("model") or model),
        custom_reason=str(verdict.get("reason") or "").strip() or None,
    )


def _extract_metric_tokens(text: str) -> set[str]:
    return {
        re.sub(r"[\s,_-]+", " ", match.group(0).strip().lower())
        for match in _SITUATIONAL_METRIC_RE.finditer(text)
    }


def evaluate_via_heuristic(state: dict[str, Any]) -> dict[str, Any]:
    declared_scope = str(state.get("declared_scope") or "durable")
    question = str(state.get("question") or "")
    choice = str(state.get("choice") or "")
    rationale = str(state.get("rationale") or "")
    user_reply = str(state.get("user_reply") or "")
    combined = f"{choice}\n{rationale}"
    choice_metrics = _extract_metric_tokens(combined)
    endorsed_metrics = _extract_metric_tokens(f"{question}\n{user_reply}")
    unendorsed_metrics = choice_metrics - endorsed_metrics

    decision_type = declared_scope if declared_scope in {"durable", "slice", "deferral"} else "durable"
    overlock_risk = "clean"
    confidence = 0.85
    scope_faithful_prob = 0.95
    reason: str | None = None

    if _TEMPORAL_DEFERRAL_RE.search(combined) and declared_scope == "durable":
        decision_type = "deferral"
        overlock_risk = "temporal_deferral_locked_as_rule"
        confidence = 0.90
        scope_faithful_prob = 0.15
        reason = (
            "Choice text describes a temporal deferral ('wait for a later phase' / "
            "'parked until' / 'deferred'), which must use `--scope deferral "
            "--revisit-when <trigger>` or `defer` rather than locking as a permanent rule."
        )
    elif unendorsed_metrics and declared_scope == "durable":
        decision_type = "tactical"
        overlock_risk = "numeric_measurement_locked_as_law"
        confidence = 0.88
        scope_faithful_prob = 0.20
        reason = (
            "Choice locks a situational byte/port measurement as a durable rule "
            "without explicit numeric endorsement in the question or user reply. "
            "Use `--scope slice` or remove the point-in-time reserve."
        )
    elif _ONE_OFF_CHORE_RE.search(combined) and declared_scope == "durable":
        decision_type = "slice"
        overlock_risk = "bundled_extra_invariants"
        confidence = 0.85
        scope_faithful_prob = 0.25
        reason = "Choice describes a one-off branch/PR chore; use `--scope slice`."
    elif (
        user_reply
        and len(user_reply.strip()) <= 45
        and len(choice) >= 360
        and choice.count(";") >= 2
        and declared_scope == "durable"
    ):
        overlock_risk = "bundled_extra_invariants"
        confidence = 0.82
        scope_faithful_prob = 0.30
        reason = (
            "Choice bundles multiple semicolon-separated invariants onto a brief "
            "user reply; split unapproved clauses or scope to `--scope slice`."
        )

    return _adjudicate_verdict(
        declared_scope=declared_scope,
        decision_type=decision_type,
        overlock_risk=overlock_risk,
        confidence=confidence,
        scope_faithful_prob=scope_faithful_prob,
        provider="heuristic",
        model="local-rubric-v1",
        custom_reason=reason,
    )


def _adjudicate_verdict(
    *,
    declared_scope: str,
    decision_type: str,
    overlock_risk: str,
    confidence: float,
    scope_faithful_prob: float,
    provider: str,
    model: str,
    custom_reason: str | None = None,
) -> dict[str, Any]:
    recommended_scope = (
        "deferral"
        if decision_type == "deferral"
        else "slice"
        if decision_type in {"slice", "tactical"}
        else "durable"
    )

    passed = True
    if declared_scope == "durable":
        if overlock_risk != "clean" and (
            confidence >= 0.78 or scope_faithful_prob < 0.55
        ):
            passed = False
        elif (
            recommended_scope != "durable"
            and confidence >= 0.70
            and scope_faithful_prob < 0.55
        ):
            passed = False

    if custom_reason:
        reason = custom_reason
    elif passed:
        reason = (
            f"Gatekeeper ({provider}:{model}) verified scope={declared_scope} "
            f"(type={decision_type}, risk={overlock_risk})."
        )
    else:
        reason = (
            f"Gatekeeper ({provider}:{model}) rejected locking as scope='{declared_scope}': "
            f"detected decision_type='{decision_type}' and overlock_risk='{overlock_risk}' "
            f"(confidence={confidence:.2f}). Re-propose with `--scope {recommended_scope}` "
            f"(or strip unapproved clauses), or pass `--force-lock --override-reason <why>`."
        )

    return {
        "passed": passed,
        "provider": provider,
        "model": model,
        "declared_scope": declared_scope,
        "decision_type": decision_type,
        "recommended_scope": recommended_scope,
        "overlock_risk": overlock_risk,
        "confidence": round(confidence, 4),
        "scope_faithful_probability": round(scope_faithful_prob, 4),
        "reason": reason,
    }


def evaluate_decision_lock(
    *,
    decision_id: str,
    domain: str,
    question: str,
    choice: str,
    rationale: str,
    declared_scope: str = "durable",
    revisit_when: str | None = None,
    user_reply: str | None = None,
    mode: str = "auto",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    runtime_env = env if env is not None else dict(os.environ)
    effective_mode = (
        runtime_env.get("GRILLTRACK_GATE_MODE") or mode or "auto"
    ).strip().lower()
    if effective_mode not in GATE_MODES:
        effective_mode = "auto"

    state = {
        "decision_id": decision_id,
        "domain": domain,
        "declared_scope": declared_scope,
        "question": question,
        "choice": choice,
        "rationale": rationale,
        "revisit_when": revisit_when,
        "user_reply": user_reply,
    }

    if effective_mode == "off":
        return {
            "passed": True,
            "provider": "off",
            "model": "none",
            "declared_scope": declared_scope,
            "decision_type": declared_scope,
            "recommended_scope": declared_scope,
            "overlock_risk": "clean",
            "confidence": 1.0,
            "scope_faithful_probability": 1.0,
            "reason": "Gatekeeper disabled.",
        }

    if effective_mode == "heuristic":
        return evaluate_via_heuristic(state)

    if effective_mode in {"auto", "jev"}:
        jev_verdict = evaluate_via_jev(state, env=runtime_env)
        if jev_verdict is not None:
            return jev_verdict
        if effective_mode == "jev":
            return evaluate_via_heuristic(state)

    if effective_mode in {"auto", "openai"}:
        openai_verdict = evaluate_via_openai(state, env=runtime_env)
        if openai_verdict is not None:
            return openai_verdict

    return evaluate_via_heuristic(state)
