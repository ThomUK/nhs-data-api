"""Durable raw archive (ADR 0012): manifest, verification and git push.

The raw archive directory is a checkout of a private git repository. Every file is listed in
MANIFEST.csv with its SHA-256; files are never modified once archived (ADR 0006).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

MANIFEST = "MANIFEST.csv"
README = "README.md"
IGNORED = {MANIFEST, README, ".gitattributes"}
FIELDS = ["path", "bytes", "sha256", "source_url", "retrieved_at", "retrieval"]

README_TEXT = """# NHS data raw archive

Immutable copies of every source file ingested by the NHS data API, exactly as downloaded,
laid out as `<dataset>/<publication date>/<original file name>`. Each file has a
`.meta.json` sidecar (source URL, retrieval time, SHA-256) where one was recorded, and
`MANIFEST.csv` lists every file with its checksum.

Files are never edited or deleted. Revised publications are archived under the release that
republished them. Regenerate the processed layer from this archive with `nda rebuild-rtt`.

Source data: NHS England, Open Government Licence v3.0.
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archived_files(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.rglob("*")
                  if p.is_file() and ".git" not in p.relative_to(raw_dir).parts
                  and p.name not in IGNORED and not p.name.endswith((".meta.json", ".part")))


def build_manifest(raw_dir: Path) -> list[dict]:
    rows = []
    for p in archived_files(raw_dir):
        meta_path = p.with_name(p.name + ".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        rows.append({"path": p.relative_to(raw_dir).as_posix(), "bytes": p.stat().st_size,
                     "sha256": _sha256(p), "source_url": meta.get("source_url") or "",
                     "retrieved_at": meta.get("retrieved_at") or "",
                     "retrieval": meta.get("retrieval") or ""})
    return rows


def write_manifest(raw_dir: Path) -> Path:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(build_manifest(raw_dir))
    (raw_dir / MANIFEST).write_text(buf.getvalue())
    if not (raw_dir / README).exists():
        (raw_dir / README).write_text(README_TEXT)
    return raw_dir / MANIFEST


@dataclass
class Verification:
    checked: int
    missing: list[str]
    changed: list[str]
    unlisted: list[str]

    @property
    def ok(self) -> bool:
        return not (self.missing or self.changed or self.unlisted)


def verify(raw_dir: Path) -> Verification:
    """Check every file against MANIFEST.csv and its .meta.json checksum."""
    listed = {}
    manifest = raw_dir / MANIFEST
    if manifest.exists():
        listed = {r["path"]: r["sha256"] for r in csv.DictReader(manifest.open())}
    missing, changed = [], []
    for rel, sha in listed.items():
        p = raw_dir / rel
        if not p.exists():
            missing.append(rel)
        elif _sha256(p) != sha:
            changed.append(rel)
    present = {p.relative_to(raw_dir).as_posix() for p in archived_files(raw_dir)}
    for p in archived_files(raw_dir):  # sidecar checksums, where recorded
        meta = p.with_name(p.name + ".meta.json")
        if meta.exists():
            rel = p.relative_to(raw_dir).as_posix()
            if json.loads(meta.read_text()).get("sha256") not in (None, _sha256(p)) \
                    and rel not in changed:
                changed.append(rel)
    return Verification(len(listed), sorted(missing), sorted(changed),
                        sorted(present - set(listed)))


def _git(raw_dir: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=raw_dir, check=True, capture_output=True,
                          text=True).stdout.strip()


def push(raw_dir: Path, message: str, remote: str = "origin", branch: str = "main") -> str:
    """Refresh the manifest, refuse if any archived file changed, then commit and push."""
    if not (raw_dir / ".git").exists():
        raise RuntimeError(f"{raw_dir} is not a git checkout; clone the archive repository "
                           "there or set NDA_RAW_DIR to its checkout")
    before = verify(raw_dir)
    if before.changed or before.missing:
        raise RuntimeError(f"archived files changed or missing: {before.changed + before.missing}")
    write_manifest(raw_dir)
    _git(raw_dir, "add", "-A")
    if not _git(raw_dir, "status", "--porcelain"):
        return "nothing to commit"
    _git(raw_dir, "commit", "-q", "-m", message)
    _git(raw_dir, "push", "-q", "-u", remote, branch)
    return _git(raw_dir, "log", "--oneline", "-1")
