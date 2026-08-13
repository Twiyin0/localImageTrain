from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


HF_SPACE_URL = "https://huggingface.co/spaces/SmilingWolf/wd-tagger"
HF_VIT_URL = "https://huggingface.co/SmilingWolf/wd-vit-tagger-v3"
HF_CONVNEXT_URL = "https://huggingface.co/SmilingWolf/wd-convnext-tagger-v3"

DEFAULT_ONNX_REPO = "SmilingWolf/wd-convnext-tagger-v3"
DEFAULT_TRAIN_REPO = "SmilingWolf/wd-vit-tagger-v3"
DEFAULT_GENERAL_THRESHOLD = 0.35
DEFAULT_CHARACTER_THRESHOLD = 0.85
LABEL_FILENAME = "selected_tags.csv"
ONNX_FILENAME = "model.onnx"


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    cache_dir: Path
    output_dir: Path


def get_runtime_paths(project_root: str | Path | None = None) -> RuntimePaths:
    root = Path(project_root or Path.cwd()).resolve()
    cache_dir = root / ".cache" / "wd_tagger"
    output_dir = root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(project_root=root, cache_dir=cache_dir, output_dir=output_dir)
