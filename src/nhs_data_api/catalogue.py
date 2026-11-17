"""Load and validate the semantic catalogue (ADR 0007)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, HttpUrl

from .paths import CATALOGUE_DIR

Status = Literal["draft", "stable", "deprecated"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Licence(_Model):
    name: str
    url: HttpUrl


class Dimension(_Model):
    id: str
    label: str
    description: str
    codes: dict[str, str] | None = None


class Measure(_Model):
    id: str
    label: str
    unit: str
    aggregation: str
    definition: str
    standard: str | None = None
    caveat: str | None = None
    status: Status = "stable"


class Caveat(_Model):
    id: str
    applies_to: str
    text: str
    org_code: str | None = None
    period_from: date | None = None
    period_to: date | None = None


class FormatChange(_Model):
    date: date
    note: str


class LayoutNote(_Model):
    verified: date
    files: list[str]
    note: str


class Dataset(_Model):
    id: str
    title: str
    status: Status
    summary: str
    publisher: str
    source_page: HttpUrl
    licence: Licence
    attribution: str
    frequency: Literal["weekly", "monthly", "quarterly", "annual"]
    geography: str
    coverage_start: date | None
    grain: list[str]
    dimensions: list[Dimension]
    measures: list[Measure]
    caveats: list[Caveat] = []
    file_layout_notes: list[LayoutNote] = []
    known_format_changes: list[FormatChange] = []

    def measure(self, measure_id: str) -> Measure:
        for m in self.measures:
            if m.id == measure_id:
                return m
        raise KeyError(measure_id)


def load_dataset(path: Path) -> Dataset:
    return Dataset.model_validate(yaml.safe_load(path.read_text()))


@lru_cache
def load_catalogue(directory: Path = CATALOGUE_DIR) -> dict[str, Dataset]:
    datasets = {}
    for path in sorted((directory / "datasets").glob("*.yaml")):
        ds = load_dataset(path)
        if ds.id != path.stem:
            raise ValueError(f"{path.name}: id {ds.id!r} does not match filename")
        datasets[ds.id] = ds
    return datasets
