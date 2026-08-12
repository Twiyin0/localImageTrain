from __future__ import annotations

import argparse
from contextlib import nullcontext
import math
from pathlib import Path

import timm
import torch
from sklearn.metrics import f1_score
from timm.data import create_transform, resolve_model_data_config
from torch import nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm

from wd_tagger.config import (
    DEFAULT_TRAIN_REPO,
    assert_supported_python,
    get_default_torch_device,
    get_runtime_paths,
)
from wd_tagger.data import ManifestRow, MultiLabelImageDataset, load_manifest
from wd_tagger.utils import ensure_dir, write_json


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="4GB-friendly WD Tagger fine-tuning")
    parser.add_argument("--manifest", required=True, help="CSV with image,tags columns")
    parser.add_argument("--output-dir", default="outputs/finetune")
    parser.add_argument("--base-model", default=DEFAULT_TRAIN_REPO)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--unfreeze-backbone", action="store_true")
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument("--device", default=get_default_torch_device())
    return parser


def autocast_context(device: str):
    if device.startswith("cuda"):
        return torch.autocast(device_type="cuda")
    return nullcontext()


def replace_classifier(model: nn.Module, num_classes: int) -> None:
    if hasattr(model, "reset_classifier"):
        model.reset_classifier(num_classes=num_classes)
        return

    classifier = getattr(model, "head", None)
    if isinstance(classifier, nn.Linear):
        model.head = nn.Linear(classifier.in_features, num_classes)
        return

    raise RuntimeError("Unsupported model head, cannot reset classifier")


def freeze_backbone(model: nn.Module) -> None:
    for name, parameter in model.named_parameters():
        parameter.requires_grad = False
        if "head" in name or "fc" in name or "classifier" in name:
            parameter.requires_grad = True


def compute_macro_f1(logits: torch.Tensor, targets: torch.Tensor, threshold: float) -> float:
    predictions = (torch.sigmoid(logits) >= threshold).to(torch.int32).cpu().numpy()
    truth = targets.to(torch.int32).cpu().numpy()
    return float(f1_score(truth, predictions, average="macro", zero_division=0))


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: str,
    threshold: float,
) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    total_f1 = 0.0
    batches = 0
    with torch.no_grad():
        for images, targets in loader:
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            logits = model(images)
            loss = criterion(logits, targets)
            total_loss += loss.item()
            total_f1 += compute_macro_f1(logits, targets, threshold)
            batches += 1
    if batches == 0:
        return 0.0, 0.0
    return total_loss / batches, total_f1 / batches


def build_subset_dataset(
    rows: list[ManifestRow],
    tags: list[str],
    indices: list[int],
    transform,
) -> MultiLabelImageDataset:
    subset_rows = [rows[index] for index in indices]
    return MultiLabelImageDataset(rows=subset_rows, tags=tags, transform=transform)


def main() -> None:
    assert_supported_python()
    args = build_arg_parser().parse_args()
    runtime = get_runtime_paths()
    output_dir = ensure_dir(args.output_dir)

    rows, tags = load_manifest(args.manifest)
    model = timm.create_model(f"hf_hub:{args.base_model}", pretrained=True)
    if args.gradient_checkpointing and hasattr(model, "set_grad_checkpointing"):
        model.set_grad_checkpointing(True)

    data_config = resolve_model_data_config(model)
    train_transform = create_transform(**data_config, is_training=True)
    eval_transform = create_transform(**data_config, is_training=False)
    base_dataset = MultiLabelImageDataset(rows=rows, tags=tags, transform=train_transform)

    val_size = max(1, math.floor(len(base_dataset) * args.val_split)) if len(base_dataset) > 1 else 0
    train_size = len(base_dataset) - val_size
    if train_size <= 0:
        raise ValueError("dataset is too small, need at least 2 images for train/val split")
    if val_size > 0:
        train_subset, val_subset = random_split(base_dataset, [train_size, val_size])
        train_dataset = build_subset_dataset(rows, tags, list(train_subset.indices), train_transform)
        val_dataset = build_subset_dataset(rows, tags, list(val_subset.indices), eval_transform)
    else:
        train_dataset, val_dataset = base_dataset, None

    replace_classifier(model, num_classes=len(tags))
    if not args.unfreeze_backbone:
        freeze_backbone(model)

    device = args.device
    model.to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=args.lr,
        weight_decay=args.weight_decay,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.startswith("cuda"))

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=device.startswith("cuda"),
    )
    val_loader = (
        DataLoader(
            val_dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.num_workers,
            pin_memory=device.startswith("cuda"),
        )
        if val_dataset is not None
        else None
    )

    best_f1 = -1.0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        optimizer.zero_grad(set_to_none=True)

        progress = tqdm(train_loader, desc=f"epoch {epoch}/{args.epochs}", leave=False)
        for step, (images, targets) in enumerate(progress, start=1):
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            with autocast_context(device):
                logits = model(images)
                loss = criterion(logits, targets) / args.grad_accum

            scaler.scale(loss).backward()
            if step % args.grad_accum == 0 or step == len(train_loader):
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)

            running_loss += loss.item() * args.grad_accum
            progress.set_postfix(loss=f"{running_loss / step:.4f}")

        metrics = {"epoch": epoch, "train_loss": running_loss / max(1, len(train_loader))}
        if val_loader is not None:
            val_loss, val_f1 = evaluate(model, val_loader, criterion, device, args.threshold)
            metrics["val_loss"] = val_loss
            metrics["val_macro_f1"] = val_f1
            if val_f1 > best_f1:
                best_f1 = val_f1
                torch.save(
                    {
                        "model_state_dict": model.state_dict(),
                        "tags": tags,
                        "base_model": args.base_model,
                        "threshold": args.threshold,
                    },
                    output_dir / "best.pt",
                )
        else:
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "tags": tags,
                    "base_model": args.base_model,
                    "threshold": args.threshold,
                },
                output_dir / "best.pt",
            )
        history.append(metrics)
        print(metrics)

    write_json(
        output_dir / "train_summary.json",
        {
            "manifest": str(Path(args.manifest).resolve()),
            "base_model": args.base_model,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "device": args.device,
            "tags": tags,
            "history": history,
            "cache_dir": str(runtime.cache_dir),
        },
    )


if __name__ == "__main__":
    main()
