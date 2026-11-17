"""Publication calendar: expected publication dates and files received (catalogue/calendar.yaml)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, HttpUrl

from .paths import CATALOGUE_DIR, RAW_DIR

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileSpec(_Model):
    id: str
    label: str
    pattern: str
    role: Literal["ingest", "validate", "reference"]
    required: bool
    purpose: str


class DatasetSchedule(_Model):
    title: str
    rule: Literal["second_thursday", "unknown"]
    data_lag_months: int | None
    rule_status: Literal["confirmed", "unconfirmed"]
    rule_note: str
    confirmed: dict[date, str]
    overrides: dict[date, date]  # generated date -> actual date
    source_page: HttpUrl
    files: list[FileSpec]


@lru_cache
def load_schedules(path: Path = CATALOGUE_DIR / "calendar.yaml") -> dict[str, DatasetSchedule]:
    raw = yaml.safe_load(path.read_text())["datasets"]
    return {k: DatasetSchedule.model_validate(v) for k, v in raw.items()}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def file_pattern(spec: FileSpec, data_month: date) -> re.Pattern[str]:
    name = MONTHS[data_month.month - 1]
    text = spec.pattern.format(mon=name[:3], month=name, yy=f"{data_month.year % 100:02d}",
                               yyyy=data_month.year)
    return re.compile(text, re.IGNORECASE)


def received_files(raw_dir: Path, dataset: str, publication: date) -> list[str]:
    folder = raw_dir / dataset / publication.isoformat()
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir()
                  if p.is_file() and not p.name.endswith((".meta.json", ".part")))


def publications(start: date, end: date, raw_dir: Path = RAW_DIR) -> list[dict]:
    """Every expected publication between start and end (inclusive), with file status."""
    out = []
    for dataset, sched in load_schedules().items():
        if sched.rule != "second_thursday":
            continue
        month = date(start.year, start.month, 1)
        while month <= end:
            generated = nth_weekday(month.year, month.month, 3, 2)  # Thursday = 3
            pub = sched.overrides.get(generated, generated)
            if start <= pub <= end:
                data_month = add_months(month, -(sched.data_lag_months or 0))
                present = received_files(raw_dir, dataset, pub)
                files = []
                for spec in sched.files:
                    pattern = file_pattern(spec, data_month)
                    matches = [f for f in present if pattern.search(f)]
                    files.append({**spec.model_dump(), "received": matches})
                out.append({
                    "dataset": dataset,
                    "title": sched.title,
                    "publication_date": pub.isoformat(),
                    "data_period": data_month.isoformat(),
                    "date_status": "confirmed" if pub in sched.confirmed else "expected",
                    "date_note": sched.confirmed.get(pub),
                    "rule_status": sched.rule_status,
                    "source_page": str(sched.source_page),
                    "files": files,
                    "unmatched_files": [f for f in present
                                        if not any(f in x["received"] for x in files)],
                })
            month = add_months(month, 1)
    return sorted(out, key=lambda p: (p["publication_date"], p["dataset"]))


def unscheduled() -> list[dict]:
    return [{"dataset": k, "title": s.title, "rule_note": s.rule_note,
             "source_page": str(s.source_page)}
            for k, s in load_schedules().items() if s.rule == "unknown"]
