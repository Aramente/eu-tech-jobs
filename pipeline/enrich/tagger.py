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

from pipeline.enrich.prompts import DEFAULT_VARIANT, VARIANTS, build_messages
from pipeline.models import Job, RoleFamily, SalaryBand, Seniority

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


# Defensive synonym mapping — DeepSeek occasionally returns close-but-not-
# canonical values ("engineer" vs "engineering"). Mapping these to the
# canonical form *before* the strict allowlist check recovers data that
# would otherwise be nulled.
_ROLE_SYNONYMS = {
    "engineer": "engineering",
    "developer": "engineering",
    "dev": "engineering",
    "swe": "engineering",
    "software engineering": "engineering",
    "software": "engineering",
    "devops": "engineering",
    "ml": "ml-ai",
    "ai": "ml-ai",
    "ml/ai": "ml-ai",
    "ai/ml": "ml-ai",
    "machine learning": "ml-ai",
    "machine-learning": "ml-ai",
    "ai engineering": "ml-ai",
    "data engineering": "data",
    "data science": "data",
    "data engineer": "data",
    "data scientist": "data",
    "analytics": "data",
    "product management": "product",
    "pm": "product",
    "designer": "design",
    "ux": "design",
    "ui": "design",
    "ux/ui": "design",
    "graphic design": "design",
    "ae": "sales",
    "sdr": "sales",
    "bdr": "sales",
    "account executive": "sales",
    "business development": "sales",
    "growth": "marketing",
    "operations": "ops",
    "customer success": "support",
    "cs": "support",
    "accounting": "finance",
    "compliance": "legal",
    "people": "hr",
    "talent": "hr",
    "recruiting": "hr",
    "recruiter": "hr",
    "people operations": "hr",
    "researcher": "research",
}


def _canon_role(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in _VALID_ROLE:
        return v
    if v in _ROLE_SYNONYMS:
        return _ROLE_SYNONYMS[v]
    return None


def build_prompt(job: Job, stripped: str) -> str:
    """Backwards-compat shim — emits the V0 user prompt for old call sites."""
    from pipeline.enrich.prompts import VARIANTS as _V

    _, builder = _V["v0_current"]
    return builder(job.title, stripped)


def _ground(values: list[str], source: str) -> list[str]:
    """Layer 3: drop values that don't appear (case-insensitive) in source."""
    if not values:
        return []
    lower = source.lower()
    return [v for v in values if v and v.lower() in lower]


def normalize_response(raw: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Validate + ground the LLM's structured output.

    For classifications (seniority, role_family, remote_policy): map case
    variants and common synonyms to the canonical allowlist. Unknown values
    fall back to null. For extractions (stack, languages): keep the
    case-insensitive substring grounding check unchanged.
    """
    out: dict[str, Any] = {}
    sen = raw.get("seniority")
    if isinstance(sen, str) and sen.strip().lower() in _VALID_SENIORITY:
        out["seniority"] = sen.strip().lower()
    else:
        out["seniority"] = None
    out["role_family"] = _canon_role(raw.get("role_family"))
    rp = raw.get("remote_policy")
    valid_rp = {"onsite", "hybrid", "remote", "remote-eu", "remote-global"}
    if isinstance(rp, str) and rp.strip().lower() in valid_rp:
        out["remote_policy"] = rp.strip().lower()
    else:
        out["remote_policy"] = None
    visa = raw.get("visa_sponsorship")
    out["visa_sponsorship"] = visa if isinstance(visa, bool) else None
    stack_raw = raw.get("stack") or []
    out["stack"] = _ground([s for s in stack_raw if isinstance(s, str)], source_text)
    langs_raw = raw.get("languages") or []
    out["languages"] = _ground(
        [lang for lang in langs_raw if isinstance(lang, str)], source_text
    )

    # Salary canonicalisation. Drop the band entirely if any required
    # field is missing or implausible — better null than wrong.
    out["salary"] = _canon_salary(raw, source_text)
    return out


_VALID_CCY = {"EUR", "GBP", "USD", "PLN", "CHF", "SEK", "DKK", "NOK", "CZK", "HUF", "RON", "BGN"}
_VALID_PERIOD = {"year", "month", "day", "hour"}


def _canon_salary(raw: dict[str, Any], source_text: str) -> dict[str, Any] | None:
    """Pull salary_min/max/currency/period from the LLM payload, sanity-check
    against source-text grounding to reduce hallucination, return a SalaryBand
    dict or None."""
    smin = raw.get("salary_min")
    smax = raw.get("salary_max")
    ccy = raw.get("salary_currency")
    per = raw.get("salary_period")
    # Coerce numerics
    try:
        smin = float(smin) if smin is not None else None
    except (TypeError, ValueError):
        smin = None
    try:
        smax = float(smax) if smax is not None else None
    except (TypeError, ValueError):
        smax = None
    if smin is None and smax is None:
        return None
    if smin is None and smax is not None:
        smin = smax
    if smax is None and smin is not None:
        smax = smin
    # Range sanity
    if smin <= 0 or smax <= 0 or smax < smin:
        return None
    # Currency
    if not isinstance(ccy, str) or ccy.strip().upper() not in _VALID_CCY:
        return None
    ccy = ccy.strip().upper()
    # Period
    if not isinstance(per, str) or per.strip().lower() not in _VALID_PERIOD:
        return None
    per = per.strip().lower()
    # Layer-3 grounding: at least one of {currency symbol, currency code,
    # the rough min, the rough max} must appear in source. Reduces
    # hallucinated salaries on jobs that didn't disclose anything.
    src = source_text.lower() if source_text else ""
    sym = {"EUR": "€", "GBP": "£", "USD": "$"}
    grounded = (
        ccy.lower() in src
        or sym.get(ccy, "").lower() in src
        or any(str(int(v))[:3] in src for v in (smin, smax))
        or "salary" in src
        or "compensation" in src
    )
    if not grounded:
        return None
    try:
        return SalaryBand(min=smin, max=smax, currency=ccy, period=per)
    except Exception:
        return None


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


def call_llm(
    title: str,
    description: str,
    *,
    variant: str = DEFAULT_VARIANT,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Call the configured LLM provider (DeepSeek or Mistral) with one of the
    prompt variants. Returns (parsed_json, token_usage_dict).

    Lazy SDK import keeps tests fast.
    """
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
    messages = build_messages(variant, title, description)
    resp = client.chat.completions.create(
        model=model or cfg["model"],
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    parsed = json.loads(content if isinstance(content, str) else "{}")
    usage = {
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(resp.usage, "total_tokens", 0) or 0,
    }
    return parsed, usage


# Backwards-compat shim — old call signature `call_mistral(prompt_str)`.
def call_mistral(prompt: str, *, model: str | None = None) -> dict[str, Any]:
    """Legacy entrypoint. Splits the prompt into title+description heuristically.

    Prefer call_llm(title, description, variant=...) in new code.
    """
    title = ""
    description = prompt
    if "Title: " in prompt:
        head, _, tail = prompt.partition("Title: ")
        if "\n\n" in tail:
            title_line, _, after = tail.partition("\n\n")
            title = title_line.strip()
            if after.startswith("Description:"):
                description = after[len("Description:"):].strip()
            else:
                description = after
    parsed, _ = call_llm(title, description, variant="v0_current", model=model)
    return parsed


class TaggerFatalError(Exception):
    """Raised on auth / payment / quota errors that won't recover by retry —
    the calling loop should abort instead of silently no-opping every job."""


def _is_fatal_provider_error(exc: BaseException) -> bool:
    """Recognize HTTP 401 / 402 / 403 / 429 from the OpenAI SDK or its
    underlying httpx error hierarchy. These won't recover by retrying the
    next job — they mean credentials/balance/quota — so the whole run
    should crash loudly rather than producing a 'succeeded with 0 tags' run.
    """
    code = (
        getattr(exc, "status_code", None)
        or getattr(getattr(exc, "response", None), "status_code", None)
    )
    if code in (401, 402, 403, 429):
        return True
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in (
            "payment required",
            "insufficient balance",
            "invalid api key",
            "authentication",
            "quota",
            "rate limit",
        )
    )


def tag_job(job: Job, *, variant: str = DEFAULT_VARIANT) -> Job:
    """Tag a single job in place. No-op when no LLM provider is configured.

    Unlike the previous version, we DO call the LLM even when the description
    is empty — many sources (Ashby, JustJoin.it, aggregators) ship title-only,
    and a title alone like "Senior ML Engineer" is enough to classify
    role_family + seniority. The V1/V2 prompts handle the empty-description
    case explicitly.

    Per-job exceptions (parse errors, transient 5xx) are swallowed and the
    job is returned unchanged — one bad job shouldn't kill the run. But
    auth/payment/quota errors (HTTP 401/402/403/429) are RAISED as
    TaggerFatalError so the run aborts loudly instead of silently producing
    a "succeeded" workflow with 0 tags.
    """
    if not is_configured() or variant not in VARIANTS:
        return job
    stripped = strip_boilerplate(job.description_md)
    if not job.title.strip():
        return job  # nothing to work with at all
    try:
        raw, _usage = call_llm(job.title, stripped, variant=variant)
    except Exception as exc:  # noqa: BLE001
        if _is_fatal_provider_error(exc):
            raise TaggerFatalError(
                f"LLM provider rejected the call (likely auth/balance): {exc}"
            ) from exc
        logger.warning("tagger error for %s: %s", job.id, exc)
        return job
    # Grounding source: original description (LLM might cite words from it).
    fields = normalize_response(raw, stripped)
    return job.model_copy(update=fields)
