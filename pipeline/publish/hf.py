"""Push the data/ folder to a Hugging Face Dataset.

Idempotent — re-running with the same content is a no-op (HF dedupes by hash).
Requires `HF_TOKEN` env var with `write` access to the dataset repo.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_REPO_ID = "Aramente/eu-tech-jobs"


class PublishConfigError(Exception):
    """Configuration missing (e.g. HF_TOKEN unset)."""


def push_to_hf(
    data_dir: Path,
    *,
    repo_id: str = DEFAULT_REPO_ID,
    token: str | None = None,
    commit_message: str | None = None,
) -> str:
    """Upload `data_dir` to the HF Dataset repo. Returns the commit URL."""
    token = token or os.environ.get("HF_TOKEN")
    if not token:
        raise PublishConfigError("HF_TOKEN not set; cannot push to Hugging Face.")
    try:
        from huggingface_hub import HfApi  # imported lazily — heavy dep
    except ImportError as exc:
        raise PublishConfigError(
            "huggingface_hub not installed; add to dev deps to publish."
        ) from exc
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    msg = commit_message or "chore(data): daily snapshot"
    info = api.upload_folder(
        folder_path=str(data_dir),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=msg,
        commit_description=(
            "Automated daily snapshot from github.com/Aramente/eu-tech-jobs."
        ),
    )
    logger.info("Pushed to HF: %s", info)
    return getattr(info, "commit_url", str(info))
