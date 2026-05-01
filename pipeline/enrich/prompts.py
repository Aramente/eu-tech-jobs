"""Prompt variants for the LLM tagger.

Three variants designed around the failure mode observed in production
(2026-04-29 first DeepSeek run): classifications under-tagged because the
single all-strict prompt treated "infer the role family from a posting"
the same way as "extract a tech-stack token". They are different jobs.

- V0_CURRENT: baseline. The prompt that's currently deployed. All-strict.
- V1_DIFFERENTIATED: classifications (role_family, seniority,
  remote_policy) are inferred from title+description by closest-match;
  extractions (stack, languages, visa_sponsorship) stay strict.
- V2_FEW_SHOT: V1 + three worked examples covering the dominant edge
  cases (rich description, title-only, ambiguous title).

Each variant is a (system_prompt, user_prompt_builder) pair. The builder
takes (title, description) and returns the user message string.

Run scripts/eval_tagger.py to compare on a stratified sample of real
jobs and pick the empirical winner.
"""

from __future__ import annotations

from collections.abc import Callable

UserBuilder = Callable[[str, str], str]


# ----- V0: current (baseline) -----------------------------------------

_V0_SYSTEM = (
    "You extract structured fields from job postings. "
    "You output ONLY JSON, no commentary. "
    "If a field is not stated explicitly in the posting, the value MUST be null. "
    "Never invent stack/language entries that are not in the source text."
)


def _v0_user(title: str, description: str) -> str:
    desc = description[:6000] if description else ""
    return (
        "Extract structured fields from this job posting. "
        "Return JSON with keys: seniority, role_family, remote_policy, "
        "visa_sponsorship, stack (list), languages (list — human languages, "
        "ISO 639-1 codes). If a field is not stated, return null. Do NOT "
        f"infer values.\n\nTitle: {title}\n\nDescription:\n{desc}"
    )


# ----- V1: differentiated (classifications vs extractions) ------------

_V1_SYSTEM = (
    "You analyze job postings and output ONLY JSON, no commentary. There are "
    "two kinds of fields:\n\n"
    "1. CLASSIFICATIONS (role_family, seniority, remote_policy): infer the "
    "closest match from the allowed list using the job title and the "
    "description. Pick the most likely category even when it's not stated "
    "verbatim. Return null only when there's really no signal.\n\n"
    "2. EXTRACTIONS (stack, languages, visa_sponsorship): only return values "
    "that appear (case-insensitively) in the source text. Never invent."
)


_V1_FIELD_SPEC = (
    "Output JSON with these keys exactly:\n"
    '  - "role_family": one of "engineering", "ml-ai", "data", "product", '
    '"design", "sales", "marketing", "ops", "support", "finance", "legal", '
    '"hr", "research", "other", or null\n'
    '  - "seniority": one of "intern", "junior", "mid", "senior", "staff", '
    '"principal", "exec", or null\n'
    '  - "remote_policy": one of "onsite", "hybrid", "remote", "remote-eu", '
    '"remote-global", or null\n'
    '  - "visa_sponsorship": true, false, or null (only if mentioned)\n'
    '  - "stack": list of technologies/tools that appear verbatim in the '
    'text (e.g. ["Python", "PyTorch", "Kubernetes"]). Empty list if none.\n'
    '  - "languages": list of human-language ISO 639-1 codes that appear '
    'in the text (e.g. ["en", "fr", "de"]). Empty list if none.\n'
    '  - "salary_min": numeric lower bound of the disclosed pay range (no '
    'currency symbols, no thousands separators), or null if not disclosed.\n'
    '  - "salary_max": numeric upper bound, or null if not disclosed (or '
    'equal to salary_min when only one value given).\n'
    '  - "salary_currency": ISO 4217 code ("EUR", "GBP", "USD", "PLN", '
    '"CHF", "SEK", "DKK", "NOK") inferred from the symbol or text, or null.\n'
    '  - "salary_period": one of "year", "month", "day", "hour", or null. '
    'Default to "year" when "/yr" or "p.a." is shown but unit is implicit.\n\n'
    "Notes:\n"
    "- ml-ai = machine learning, AI/LLM, applied data science roles.\n"
    "- research = pure research scientist roles (PhD-track, publishing).\n"
    "- hr = recruiting, talent acquisition, people ops, people partner.\n"
    "- engineering = software/backend/frontend/full-stack/devops roles.\n"
    "- remote-eu = remote restricted to Europe; remote-global = remote, no "
    "country restriction; remote = unspecified scope.\n"
    "- Salary: only extract when actually shown in the text. NEVER guess "
    'from market norms. "DOE / competitive / negotiable" → null.\n'
)


def _v1_user(title: str, description: str) -> str:
    desc_block = (
        description[:6000]
        if description
        else "(no description provided — infer from title alone where possible)"
    )
    return (
        f"{_V1_FIELD_SPEC}\n\n"
        f"Title: {title}\n\n"
        f"Description:\n{desc_block}"
    )


# ----- V2: V1 + few-shot examples -------------------------------------

_V2_SYSTEM = _V1_SYSTEM


_V2_EXAMPLES = (
    "Examples:\n\n"
    "Title: Senior Machine Learning Engineer\n"
    "Description: Build LLM-powered features. Python, PyTorch, AWS. Remote "
    "within EU. €80,000 — €110,000 / year.\n"
    "Output: {\"role_family\": \"ml-ai\", \"seniority\": \"senior\", "
    "\"remote_policy\": \"remote-eu\", \"visa_sponsorship\": null, \"stack\": "
    "[\"Python\", \"PyTorch\", \"AWS\"], \"languages\": [], \"salary_min\": "
    "80000, \"salary_max\": 110000, \"salary_currency\": \"EUR\", "
    "\"salary_period\": \"year\"}\n\n"
    "Title: Account Executive (DACH)\n"
    "Description: (no description provided — infer from title alone where "
    "possible)\n"
    "Output: {\"role_family\": \"sales\", \"seniority\": null, "
    "\"remote_policy\": null, \"visa_sponsorship\": null, \"stack\": [], "
    "\"languages\": [\"de\"], \"salary_min\": null, \"salary_max\": null, "
    "\"salary_currency\": null, \"salary_period\": null}\n\n"
    "Title: Junior UX Designer — Berlin office\n"
    "Description: Help design our consumer app. On-site only. Visa "
    "sponsorship available. Compensation is competitive.\n"
    "Output: {\"role_family\": \"design\", \"seniority\": \"junior\", "
    "\"remote_policy\": \"onsite\", \"visa_sponsorship\": true, \"stack\": "
    "[], \"languages\": [], \"salary_min\": null, \"salary_max\": null, "
    "\"salary_currency\": null, \"salary_period\": null}\n"
)


def _v2_user(title: str, description: str) -> str:
    desc_block = (
        description[:5500]  # leave room for examples
        if description
        else "(no description provided — infer from title alone where possible)"
    )
    return (
        f"{_V1_FIELD_SPEC}\n\n"
        f"{_V2_EXAMPLES}\n"
        "Now process this posting:\n\n"
        f"Title: {title}\n\n"
        f"Description:\n{desc_block}"
    )


# ----- registry -------------------------------------------------------

VARIANTS: dict[str, tuple[str, UserBuilder]] = {
    "v0_current": (_V0_SYSTEM, _v0_user),
    "v1_differentiated": (_V1_SYSTEM, _v1_user),
    "v2_few_shot": (_V2_SYSTEM, _v2_user),
}

DEFAULT_VARIANT = "v2_few_shot"


def build_messages(
    variant: str, title: str, description: str
) -> list[dict[str, str]]:
    """Return OpenAI-format chat messages for a given variant."""
    if variant not in VARIANTS:
        raise ValueError(
            f"Unknown variant '{variant}'. Available: {sorted(VARIANTS)}"
        )
    system, user_builder = VARIANTS[variant]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_builder(title, description)},
    ]
