from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    assert_supported_python,
    get_default_onnx_providers,
    get_runtime_paths,
)
from wd_tagger.models import OnnxTagger, mcut_threshold
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
    providers = get_default_onnx_providers()
    tagger = OnnxTagger(
        repo_id=args.repo_id,
        cache_dir=runtime.cache_dir,
        providers=providers,
        local_model_dir=args.model_dir,
    )
    image = Image.open(args.image)
    scores = tagger.predict(image)
    meta = tagger.tag_metadata
    labels = list(zip(meta.tag_names, scores.tolist()))

    rating = {labels[idx][0]: labels[idx][1] for idx in meta.rating_indexes}
    general = [labels[idx] for idx in meta.general_indexes]
    characters = [labels[idx] for idx in meta.character_indexes]

    general_threshold = (
        mcut_threshold([score for _, score in general])
        if args.general_mcut
        else args.general_threshold
    )
    character_threshold = (
        max(0.15, mcut_threshold([score for _, score in characters]))
        if args.character_mcut
        else args.character_threshold
    )

    selected_general = {
        name: score for name, score in general if score >= general_threshold
    }
    selected_characters = {
        name: score for name, score in characters if score >= character_threshold
    }

    ordered_tags = ", ".join(
        name
        for name, _ in sorted(
            selected_general.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )

    payload = {
        "repo_id": args.repo_id,
        "model_dir": str(Path(args.model_dir).resolve()) if args.model_dir else None,
        "image": str(Path(args.image).resolve()),
        "providers": tagger.active_providers,
        "thresholds": {
            "general": general_threshold,
            "character": character_threshold,
        },
        "rating": rating,
        "characters": selected_characters,
        "general": selected_general,
        "caption": ordered_tags,
    }
    if args.json_out:
        write_json(args.json_out, payload)
    return payload


def main() -> None:
    assert_supported_python()
    args = build_arg_parser().parse_args()
    payload = run_inference(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
