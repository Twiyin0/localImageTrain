from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import torch
from PIL import Image
from torch.utils.data import Dataset

from wd_tagger.utils import normalize_tag_text


@dataclass(frozen=True)
class ManifestRow:
    image_path: Path
    tags: list[str]


def load_manifest(manifest_path: str | Path) -> tuple[list[ManifestRow], list[str]]:
    manifest = pd.read_csv(manifest_path)
    required = {"image", "tags"}
    if not required.issubset(set(manifest.columns)):
        missing = ", ".join(sorted(required - set(manifest.columns)))
        raise ValueError(f"manifest missing columns: {missing}")

    rows: list[ManifestRow] = []
    vocab: set[str] = set()
    parent = Path(manifest_path).resolve().parent

    for row in manifest.itertuples(index=False):
        tags = normalize_tag_text(str(row.tags).split(","))
        image_path = Path(row.image)
        if not image_path.is_absolute():
            image_path = (parent / image_path).resolve()
        rows.append(ManifestRow(image_path=image_path, tags=tags))
        vocab.update(tags)

    return rows, sorted(vocab)


class MultiLabelImageDataset(Dataset):
    def __init__(
        self,
        rows: list[ManifestRow],
        tags: list[str],
        transform,
    ) -> None:
        self.rows = rows
        self.tags = tags
        self.transform = transform
        self.tag_to_index = {tag: idx for idx, tag in enumerate(tags)}

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        row = self.rows[index]
        image = Image.open(row.image_path).convert("RGB")
        tensor = self.transform(image)

        target = torch.zeros(len(self.tags), dtype=torch.float32)
        for tag in row.tags:
            tag_index = self.tag_to_index.get(tag)
            if tag_index is not None:
                target[tag_index] = 1.0
        return tensor, target
