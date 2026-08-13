from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import huggingface_hub
import numpy as np
import onnxruntime as ort
import pandas as pd
from PIL import Image

from wd_tagger.config import (
    DEFAULT_ONNX_REPO,
    LABEL_FILENAME,
    ONNX_FILENAME,
)


KAOMOJIS = {
    "0_0",
    "(o)_(o)",
    "+_+",
    "+_-",
    "._.",
    "<o>_<o>",
    "<|>_<|>",
    "=_=",
    ">_<",
    "3_3",
    "6_9",
    ">_o",
    "@_@",
    "^_^",
    "o_o",
    "u_u",
    "x_x",
    "|_|",
    "||_||",
}


@dataclass
class TagMetadata:
    tag_names: list[str]
    rating_indexes: list[int]
    general_indexes: list[int]
    character_indexes: list[int]


def preload_cuda_runtime() -> None:
    # ONNX Runtime can reuse CUDA/cuDNN DLLs bundled with PyTorch when both
    # stacks target the same CUDA/cuDNN major versions.
    try:
        import torch  # noqa: F401
    except Exception:
        pass

    preload = getattr(ort, "preload_dlls", None)
    if callable(preload):
        try:
            preload()
        except Exception:
            pass


def load_tag_metadata(csv_path: str | Path) -> TagMetadata:
    frame = pd.read_csv(csv_path)
    names = frame["name"].map(
        lambda value: value if value in KAOMOJIS else value.replace("_", " ")
    )
    return TagMetadata(
        tag_names=names.tolist(),
        rating_indexes=list(np.where(frame["category"] == 9)[0]),
        general_indexes=list(np.where(frame["category"] == 0)[0]),
        character_indexes=list(np.where(frame["category"] == 4)[0]),
    )


def pad_square_rgb(image: Image.Image, target_size: int) -> np.ndarray:
    rgba = image.convert("RGBA")
    white_canvas = Image.new("RGBA", rgba.size, (255, 255, 255))
    white_canvas.alpha_composite(rgba)
    rgb = white_canvas.convert("RGB")

    width, height = rgb.size
    max_side = max(width, height)
    square = Image.new("RGB", (max_side, max_side), (255, 255, 255))
    square.paste(rgb, ((max_side - width) // 2, (max_side - height) // 2))

    if max_side != target_size:
        square = square.resize((target_size, target_size), Image.BICUBIC)

    array = np.asarray(square, dtype=np.float32)
    return np.expand_dims(array[:, :, ::-1], axis=0)


def mcut_threshold(probabilities: Sequence[float]) -> float:
    sorted_probs = np.sort(np.asarray(probabilities))[::-1]
    if sorted_probs.size < 2:
        return 0.5
    differences = sorted_probs[:-1] - sorted_probs[1:]
    index = int(np.argmax(differences))
    return float((sorted_probs[index] + sorted_probs[index + 1]) / 2)


class OnnxTagger:
    def __init__(
        self,
        repo_id: str = DEFAULT_ONNX_REPO,
        cache_dir: str | Path | None = None,
        providers: list[str] | None = None,
        local_model_dir: str | Path | None = None,
    ) -> None:
        self.repo_id = repo_id
        self.cache_dir = str(Path(cache_dir).resolve()) if cache_dir else None
        self.providers = providers
        preload_cuda_runtime()
        if local_model_dir:
            model_dir = Path(local_model_dir).resolve()
            self.model_path = str((model_dir / ONNX_FILENAME).resolve())
            self.csv_path = str((model_dir / LABEL_FILENAME).resolve())
        else:
            self.model_path = huggingface_hub.hf_hub_download(
                repo_id=repo_id,
                filename=ONNX_FILENAME,
                cache_dir=self.cache_dir,
            )
            self.csv_path = huggingface_hub.hf_hub_download(
                repo_id=repo_id,
                filename=LABEL_FILENAME,
                cache_dir=self.cache_dir,
            )
        self.tag_metadata = load_tag_metadata(self.csv_path)
        self.session = ort.InferenceSession(self.model_path, providers=providers)
        self.active_providers = self.session.get_providers()
        _, self.target_height, self.target_width, _ = self.session.get_inputs()[0].shape
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def predict(self, image: Image.Image) -> np.ndarray:
        batch = pad_square_rgb(image, self.target_height)
        outputs = self.session.run([self.output_name], {self.input_name: batch})[0]
        return outputs[0].astype(float)
