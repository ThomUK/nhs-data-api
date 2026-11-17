"""Filesystem layout (ADR 0006, ADR 0012).

NDA_DATA_DIR sets the data root (default: data/ in the repository). NDA_RAW_DIR points the
raw archive somewhere else, typically a checkout of the private archive repository.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_DIR = REPO_ROOT / "catalogue"
DATA_DIR = Path(os.environ.get("NDA_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = Path(os.environ.get("NDA_RAW_DIR", DATA_DIR / "raw"))
PROCESSED_DIR = DATA_DIR / "processed"
