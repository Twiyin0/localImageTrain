from __future__ import annotations

import argparse
import json
from pathlib import Path

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    get_runtime_paths,
)
from wd_tagger.service import ImageSource, PredictionOptions, TaggerService
from wd_tagger.utils import write_json


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local WD Tagger inference")
    parser.add_argument("image", help="Input image path")
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_ONNX_REPO,
        help="Hugging Face model repo, default is the lighter convnext v3 model",
    )
    parser.add_argument(
        "--model-dir",
        help="Local directory that already contains model.onnx and selected_tags.csv",
    )
    parser.add_argument(
        "--general-threshold",
        type=float,
        default=DEFAULT_GENERAL_THRESHOLD,
    )
    parser.add_argument(
        "--character-threshold",
        type=float,
        default=DEFAULT_CHARACTER_THRESHOLD,
    )
    parser.add_argument("--general-mcut", action="store_true")
    parser.add_argument("--character-mcut", action="store_true")
    parser.add_argument("--json-out", help="Optional JSON output path")
    return parser


def run_inference(args: argparse.Namespace) -> dict:
    runtime = get_runtime_paths()
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    service = TaggerService()
    image_path = Path(args.image).resolve()
    source_bytes = image_path.read_bytes()
    source = ImageSource.from_bytes(
        filename=image_path.name,
        content_type=f"image/{image_path.suffix.lower().lstrip('.') or 'png'}",
        source_bytes=source_bytes,
        source_path=str(image_path),
    )
    payload = service.predict_from_source(
        source=source,
        options=PredictionOptions(
            repo_id=args.repo_id,
            model_dir=args.model_dir,
            general_threshold=args.general_threshold,
            character_threshold=args.character_threshold,
            general_mcut=args.general_mcut,
            character_mcut=args.character_mcut,
        ),
        providers=providers,
    )
    payload["image"] = str(image_path)
    if args.json_out:
        write_json(args.json_out, payload)
    return payload


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = run_inference(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
