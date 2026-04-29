"""Mistral-powered job tagger with three-layer hallucination defense.

Layers:
  1. Scrape-time: drop boilerplate "About us / D&I" sections before sending
     the description to the LLM.
  2. Prompt directive: explicit instruction to emit `null` rather than guess.
  3. Grounding backstop: every extracted `stack` / `language` token must
     appear as a substring in the source description.

Cache by `Job.id` — only diff jobs hit the LLM. Steady-state: ~50–500 LLM
calls/day at ~€0.001 each.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pipeline.models import Job, RoleFamily, Seniority

logger = logging.getLogger(__name__)


_BOILERPLATE_PATTERNS = [
    r"(?is)about\s+(?:us|the\s+team|the\s+company)\b.*?(?=^##|\Z)",
    r"(?is)(equal\s+opportunity|diversity\s+and\s+inclusion|d&i)\b.*?(?=^##|\Z)",
    r"(?is)benefits?\b.*?(?=^##|\Z)",
    r"(?is)why\s+work\s+(?:with|at)\s+us\b.*?(?=^##|\Z)",
]


def strip_boilerplate(description_md: str) -> str:
    """Layer 1: remove company-marketing sections before sending to LLM."""
    if not description_md:
        return ""
    out = description_md
    for pattern in _BOILERPLATE_PATTERNS:
        out = re.sub(pattern, "", out, flags=re.MULTILINE)
    return out.strip()


_VALID_SENIORITY: set[Seniority] = {  # type: ignore[arg-type]
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "exec",
}
_VALID_ROLE: set[RoleFamily] = {  # type: ignore[arg-type]
    "engineering",
    "ml-ai",
    "data",
    "product",
    "design",
    "sales",
    "marketing",
    "ops",
    "support",
    "finance",
    "legal",
    "hr",
    "research",
    "other",
}


def build_prompt(job: Job, stripped: str) -> str:
    """Construct the user prompt. Title + cleaned description only."""
    return (
        "Extract structured fields from this job posting. "
        "Return JSON with keys: seniority, role_family, remote_policy, "
        "visa_sponsorship, stack (list), languages (list — human languages, ISO 639-1 codes). "
        "If a field is not stated, return null. Do NOT infer values.\n\n"
        f"Title: {job.title}\n\n"
        f"Description:\n{stripped[:6000]}"
    )


def _ground(values: list[str], source: str) -> list[str]:
    """Layer 3: drop values that don't appear (case-insensitive) in source."""
    if not values:
        return []
    lower = source.lower()
    return [v for v in values if v and v.lower() in lower]


def normalize_response(raw: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Validate + ground the LLM's structured output."""
    out: dict[str, Any] = {}
    sen = raw.get("seniority")
    out["seniority"] = sen if sen in _VALID_SENIORITY else None
    role = raw.get("role_family")
    out["role_family"] = role if role in _VALID_ROLE else None
    rp = raw.get("remote_policy")
    out["remote_policy"] = rp if rp in {
        "onsite", "hybrid", "remote", "remote-eu", "remote-global"
    } else None
    visa = raw.get("visa_sponsorship")
    out["visa_sponsorship"] = visa if isinstance(visa, bool) else None
    stack_raw = raw.get("stack") or []
    out["stack"] = _ground([s for s in stack_raw if isinstance(s, str)], source_text)
    langs_raw = raw.get("languages") or []
    out["languages"] = _ground(
        [lang for lang in langs_raw if isinstance(lang, str)], source_text
    )
    return out


# ----- runtime LLM call (lazy import keeps tests fast) -----

_SYSTEM = (
    "You extract structured fields from job postings. "
    "You output ONLY JSON, no commentary. "
    "If a field is not stated explicitly in the posting, the value MUST be null. "
    "Never invent stack/language entries that are not in the source text."
)


class TaggerConfigError(Exception):
    pass


# Provider selection: DeepSeek is preferred (~10x cheaper than Mistral on
# structured extraction with comparable quality). Falls back to Mistral when
# DEEPSEEK_API_KEY is unset and MISTRAL_API_KEY is set. Both APIs are
# OpenAI-compatible so we use the official `openai` SDK pointed at the right
# base URL — keeps the call site identical.
_PROVIDERS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "mistral": {
        "env_key": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
    },
}


def selected_provider() -> str | None:
    """Return the active provider name, or None if no key is set."""
    for name, cfg in _PROVIDERS.items():
        if os.environ.get(cfg["env_key"]):
            return name
    return None


def is_configured() -> bool:
    return selected_provider() is not None


def call_llm(prompt: str, *, model: str | None = None) -> dict[str, Any]:
    """Call the configured LLM provider (DeepSeek or Mistral). Lazy SDK import."""
    provider = selected_provider()
    if not provider:
        raise TaggerConfigError(
            "No LLM provider configured. Set DEEPSEEK_API_KEY (preferred) or "
            "MISTRAL_API_KEY."
        )
    cfg = _PROVIDERS[provider]
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise TaggerConfigError(
            "openai SDK not installed; add to deps to enable the tagger."
        ) from exc
    client = OpenAI(
        api_key=os.environ[cfg["env_key"]],
        base_url=cfg["base_url"],
    )
    resp = client.chat.completions.create(
        model=model or cfg["model"],
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    return json.loads(content if isinstance(content, str) else "{}")


# Backwards-compat alias (was Mistral-only).
call_mistral = call_llm


def tag_job(job: Job) -> Job:
    """Tag a single job in place. No-op when no LLM provider is configured."""
    if not is_configured():
        return job
    stripped = strip_boilerplate(job.description_md)
    if not stripped:
        return job
    prompt = build_prompt(job, stripped)
    try:
        raw = call_llm(prompt)
    except Exception as exc:  # noqa: BLE001 — never break the run on tagger errors
        logger.warning("tagger error for %s: %s", job.id, exc)
        return job
    fields = normalize_response(raw, stripped)
    return job.model_copy(update=fields)
