import json
import subprocess

import pytest

from nhs_data_api import archive


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    remote, raw = tmp_path / "remote.git", tmp_path / "raw"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    _git(tmp_path, "clone", "-q", str(remote), str(raw))
    _git(raw, "config", "user.email", "test@example.com")
    _git(raw, "config", "user.name", "test")
    _git(raw, "checkout", "-q", "-b", "main")
    folder = raw / "rtt" / "2026-11-12"
    folder.mkdir(parents=True)
    (folder / "Full-CSV-data-file-Sep26.zip").write_bytes(b"zipdata")
    sha = archive._sha256(folder / "Full-CSV-data-file-Sep26.zip")
    (folder / "Full-CSV-data-file-Sep26.zip.meta.json").write_text(
        json.dumps({"sha256": sha, "source_url": "https://example.org/f.zip"}))
    return raw, remote


def test_push_writes_manifest_and_pushes(repo):
    raw, remote = repo
    assert "Archive" in archive.push(raw, "Archive September")
    manifest = (raw / "MANIFEST.csv").read_text()
    assert "rtt/2026-11-12/Full-CSV-data-file-Sep26.zip" in manifest
    assert "https://example.org/f.zip" in manifest
    log = subprocess.run(["git", "log", "--oneline", "main"], cwd=remote, capture_output=True,
                         text=True).stdout
    assert "Archive September" in log
    assert archive.push(raw, "again") == "nothing to commit"
    assert archive.verify(raw).ok


def test_push_refuses_changed_files(repo):
    raw, _ = repo
    archive.push(raw, "first")
    (raw / "rtt" / "2026-11-12" / "Full-CSV-data-file-Sep26.zip").write_bytes(b"tampered")
    v = archive.verify(raw)
    assert v.changed == ["rtt/2026-11-12/Full-CSV-data-file-Sep26.zip"]
    with pytest.raises(RuntimeError, match="changed"):
        archive.push(raw, "second")


def test_new_files_are_unlisted_until_pushed(repo):
    raw, _ = repo
    archive.push(raw, "first")
    (raw / "ods" / "2026-11-17").mkdir(parents=True)
    (raw / "ods" / "2026-11-17" / "organisations.jsonl").write_text("{}\n")
    assert archive.verify(raw).unlisted == ["ods/2026-11-17/organisations.jsonl"]
    archive.push(raw, "ods")
    assert archive.verify(raw).ok
