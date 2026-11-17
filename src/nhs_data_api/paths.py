"""Filesystem layout (ADR 0006). Override the root with NDA_DATA_DIR."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_DIR = REPO_ROOT / "catalogue"
DATA_DIR = Path(os.environ.get("NDA_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
