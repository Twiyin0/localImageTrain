from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


HF_SPACE_URL = "https://huggingface.co/spaces/SmilingWolf/wd-tagger"
HF_VIT_URL = "https://huggingface.co/SmilingWolf/wd-vit-tagger-v3"
HF_CONVNEXT_URL = "https://huggingface.co/SmilingWolf/wd-convnext-tagger-v3"

DEFAULT_ONNX_REPO = "SmilingWolf/wd-convnext-tagger-v3"
DEFAULT_TRAIN_REPO = "SmilingWolf/wd-vit-tagger-v3"
DEFAULT_GENERAL_THRESHOLD = 0.35
DEFAULT_CHARACTER_THRESHOLD = 0.85
LABEL_FILENAME = "selected_tags.csv"
ONNX_FILENAME = "model.onnx"
MODELS_DIR_ENV = "WD_TAGGER_MODELS_DIR"
MODEL_DIR_ENV = "WD_TAGGER_MODEL_DIR"


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


def is_complete_model_dir(model_dir: str | Path) -> bool:
    path = Path(model_dir).expanduser()
    return (path / ONNX_FILENAME).is_file() and (path / LABEL_FILENAME).is_file()


def _iter_model_roots(project_root: str | Path | None = None) -> list[Path]:
    roots: list[Path] = []
    env_roots = os.getenv(MODELS_DIR_ENV)
    if env_roots:
        roots.extend(Path(raw).expanduser() for raw in env_roots.split(os.pathsep) if raw.strip())

    root = Path(project_root or Path.cwd()).resolve()
    roots.append(root / "models")

    seen: set[str] = set()
    unique_roots: list[Path] = []
    for candidate in roots:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_roots.append(candidate)
    return unique_roots


def discover_local_model_dirs(
    repo_id: str | None = None,
    project_root: str | Path | None = None,
) -> list[Path]:
    repo_name = (repo_id or "").split("/")[-1].lower()
    candidates: list[Path] = []

    for root in _iter_model_roots(project_root):
        if is_complete_model_dir(root):
            candidates.append(root.resolve())
        if not root.is_dir():
            continue
        for model_dir in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if model_dir.is_dir() and is_complete_model_dir(model_dir):
                candidates.append(model_dir.resolve())

    def sort_key(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if repo_name and name == repo_name:
            return (0, str(path))
        if repo_name and repo_name in name:
            return (1, str(path))
        return (2, str(path))

    return sorted(dict.fromkeys(candidates), key=sort_key)


def find_local_model_dir(
    repo_id: str | None = None,
    project_root: str | Path | None = None,
) -> str | None:
    explicit_model_dir = os.getenv(MODEL_DIR_ENV)
    if explicit_model_dir and is_complete_model_dir(explicit_model_dir):
        return str(Path(explicit_model_dir).expanduser().resolve())

    models = discover_local_model_dirs(repo_id=repo_id, project_root=project_root)
    return str(models[0]) if models else None


def get_default_onnx_providers() -> list[str]:
    if sys.platform == "win32":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]
