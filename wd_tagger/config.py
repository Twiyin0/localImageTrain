from __future__ import annotations

import platform
import sys
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
MIN_PYTHON = (3, 11)


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    cache_dir: Path
    output_dir: Path


def assert_supported_python() -> None:
    if sys.version_info >= MIN_PYTHON:
        return
    major, minor = MIN_PYTHON
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    raise RuntimeError(
        f"Python {major}.{minor}+ is required, but current interpreter is {current}: {sys.executable}"
    )


def get_default_onnx_providers() -> list[str]:
    if platform.system() == "Darwin":
        return ["CPUExecutionProvider"]
    return ["CUDAExecutionProvider", "CPUExecutionProvider"]


def get_default_torch_device() -> str:
    try:
        import torch
    except Exception:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def get_runtime_paths(project_root: str | Path | None = None) -> RuntimePaths:
    assert_supported_python()
    root = Path(project_root or Path.cwd()).resolve()
    cache_dir = root / ".cache" / "wd_tagger"
    output_dir = root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(project_root=root, cache_dir=cache_dir, output_dir=output_dir)
