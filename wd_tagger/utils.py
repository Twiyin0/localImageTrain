from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def ensure_dir(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def write_json(path: str | Path, payload: dict) -> None:
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def read_tag_list(path: str | Path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def normalize_tag_text(tags: Iterable[str]) -> list[str]:
    normalized = []
    for tag in tags:
        clean = tag.strip().replace(" ", "_")
        if clean:
            normalized.append(clean)
    return normalized
