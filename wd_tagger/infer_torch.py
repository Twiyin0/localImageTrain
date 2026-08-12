from __future__ import annotations

import argparse
import json
from pathlib import Path

import timm
import torch
from PIL import Image
from timm.data import create_transform, resolve_model_data_config

from wd_tagger.config import assert_supported_python, get_default_torch_device


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inference for fine-tuned WD Tagger checkpoints")
    parser.add_argument("image", help="Input image path")
    parser.add_argument("--checkpoint", required=True, help="Path to best.pt from training")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--device", default=get_default_torch_device())
    parser.add_argument("--json-out", help="Optional JSON output path")
    return parser


def replace_classifier(model: torch.nn.Module, num_classes: int) -> None:
    if hasattr(model, "reset_classifier"):
        model.reset_classifier(num_classes=num_classes)
        return
    classifier = getattr(model, "head", None)
    if isinstance(classifier, torch.nn.Linear):
        model.head = torch.nn.Linear(classifier.in_features, num_classes)
        return
    raise RuntimeError("Unsupported model head, cannot reset classifier")


def run_inference(args: argparse.Namespace) -> dict:
    checkpoint_path = Path(args.checkpoint).resolve()
    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    base_model = checkpoint["base_model"]
    tags = checkpoint["tags"]
    threshold = args.threshold if args.threshold is not None else checkpoint.get("threshold", 0.35)

    model = timm.create_model(f"hf_hub:{base_model}", pretrained=False)
    replace_classifier(model, num_classes=len(tags))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    device = args.device
    model.to(device)

    data_config = resolve_model_data_config(model)
    transform = create_transform(**data_config, is_training=False)
    image = Image.open(args.image).convert("RGB")
    tensor = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(tensor)
        scores = torch.sigmoid(logits)[0].detach().cpu().tolist()

    selected = {
        tag: score
        for tag, score in sorted(
            zip(tags, scores),
            key=lambda item: item[1],
            reverse=True,
        )
        if score >= threshold
    }

    payload = {
        "image": str(Path(args.image).resolve()),
        "checkpoint": str(checkpoint_path),
        "base_model": base_model,
        "threshold": threshold,
        "tags": selected,
        "caption": ", ".join(selected.keys()),
    }
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return payload


def main() -> None:
    assert_supported_python()
    args = build_arg_parser().parse_args()
    payload = run_inference(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
