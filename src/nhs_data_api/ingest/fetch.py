"""Polite downloading into the immutable raw archive (ADRs 0006, 0009)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .. import __version__
from ..paths import RAW_DIR

USER_AGENT = (
    f"secondthursday-ingest/{__version__} "
    "(+https://github.com/ThomUK/nhs-data-api; open-data ingestion; low request rate)"
)
MIN_INTERVAL_SECONDS = 2.0
_last_request = 0.0


class BotChallengeError(RuntimeError):
    """The source returned a bot challenge. We do not attempt to bypass these (ADR 0009)."""


@dataclass(frozen=True)
class ArchivedFile:
    path: Path
    sha256: str
    source_url: str
    already_present: bool


def _throttle() -> None:
    global _last_request
    wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def archive_url(url: str, dataset: str, publication: str, raw_dir: Path = RAW_DIR) -> ArchivedFile:
    """Download `url` into raw/<dataset>/<publication>/ unless already archived."""
    filename = Path(urlparse(url).path).name
    target = raw_dir / dataset / publication / filename
    meta_path = target.with_name(target.name + ".meta.json")
    if target.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return ArchivedFile(target, meta["sha256"], url, already_present=True)

    _throttle()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120) as c:
        resp = c.get(url)
    if resp.headers.get("x-amzn-waf-action") == "challenge":
        raise BotChallengeError(f"{url} returned a WAF challenge; add the file URL to a manifest")
    resp.raise_for_status()

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(resp.content)
    sha = hashlib.sha256(resp.content).hexdigest()
    tmp.rename(target)
    meta_path.write_text(
        json.dumps(
            {
                "source_url": url,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "sha256": sha,
                "bytes": len(resp.content),
                "content_type": resp.headers.get("content-type"),
            },
            indent=2,
        )
    )
    return ArchivedFile(target, sha, url, already_present=False)


def archive_local(path: Path, dataset: str, publication: str, source_url: str | None = None,
                  raw_dir: Path = RAW_DIR) -> ArchivedFile:
    """Copy a manually downloaded file into the raw archive, with the same metadata sidecar."""
    content = Path(path).read_bytes()
    target = raw_dir / dataset / publication / Path(path).name
    meta_path = target.with_name(target.name + ".meta.json")
    sha = hashlib.sha256(content).hexdigest()
    if target.exists() and meta_path.exists():
        return ArchivedFile(target, json.loads(meta_path.read_text())["sha256"], source_url or "",
                            already_present=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    meta_path.write_text(json.dumps({
        "source_url": source_url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "retrieval": "manual download",
        "sha256": sha,
        "bytes": len(content),
    }, indent=2))
    return ArchivedFile(target, sha, source_url or "", already_present=False)
