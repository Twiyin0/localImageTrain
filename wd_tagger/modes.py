from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, process_time
from typing import Literal

from PIL import Image

from wd_tagger.service import (
    ImageSource,
    PredictionOptions,
    TaggerService,
    collect_process_metrics,
)

ProcessType = Literal["tag", "arrary", "array", "tagimg", "json", "mulitagimg"]
ExportFormat = Literal["inline", "json", "csv", "both"]


@dataclass(frozen=True)
class ProcessResult:
    type: str
    media_type: str
    body: str | bytes | dict | list
    filename: str | None = None
    metrics: dict | None = None


def normalize_type(value: str) -> str:
    return "arrary" if value == "array" else value


def load_sources_from_dir(input_dir: str | Path) -> list[ImageSource]:
    root = Path(input_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"input directory not found: {root}")

    sources: list[ImageSource] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            continue
        source_bytes = path.read_bytes()
        image = Image.open(path).convert("RGBA")
        sources.append(
            ImageSource(
                filename=path.name,
                image=image,
                content_type=f"image/{path.suffix.lower().lstrip('.')}",
                source_path=str(path),
                source_bytes=source_bytes,
            )
        )
    return sources


def process_single_type(
    service: TaggerService,
    source: ImageSource,
    options: PredictionOptions,
    providers: list[str],
    process_type: str,
) -> ProcessResult:
    started_at = perf_counter()
    cpu_started_at = process_time()
    payload = service.predict_from_source(
        source,
        options=options,
        providers=providers,
        allow_similar=False,
    )
    payload["filename"] = source.filename
    payload["content_type"] = source.content_type
    payload["source_path"] = source.source_path

    normalized = normalize_type(process_type)
    if normalized == "tag":
        metrics = dict(payload.get("metrics", {}))
        metrics.update(
            {
                "total_elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                "inference_elapsed_ms": metrics.get("inference_elapsed_ms"),
                "cpu_elapsed_ms": round((process_time() - cpu_started_at) * 1000, 2),
            }
        )
        return ProcessResult(
            type="tag",
            media_type="text/plain; charset=utf-8",
            body=payload["caption"],
            metrics=metrics,
        )
    if normalized == "arrary":
        metrics = dict(payload.get("metrics", {}))
        metrics.update(
            {
                "total_elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                "inference_elapsed_ms": metrics.get("inference_elapsed_ms"),
                "cpu_elapsed_ms": round((process_time() - cpu_started_at) * 1000, 2),
            }
        )
        return ProcessResult(
            type="arrary",
            media_type="application/json",
            body=service.extract_tag_array(payload),
            metrics=metrics,
        )
    if normalized == "tagimg":
        output_dir = service.create_request_dir("tagimg")
        tagged_path = service.write_tagged_image(output_dir, source, payload)
        metrics = dict(payload.get("metrics", {}))
        metrics.update(
            {
                "total_elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                "inference_elapsed_ms": metrics.get("inference_elapsed_ms"),
                "cpu_elapsed_ms": round((process_time() - cpu_started_at) * 1000, 2),
            }
        )
        return ProcessResult(
            type="tagimg",
            media_type="application/octet-stream",
            body=tagged_path.read_bytes(),
            filename=tagged_path.name,
            metrics=metrics,
        )
    return ProcessResult(type="json", media_type="application/json", body=payload, metrics=payload.get("metrics"))


def process_batch_type(
    service: TaggerService,
    sources: list[ImageSource],
    options: PredictionOptions,
    providers: list[str],
    process_type: str,
    export_format: str,
) -> ProcessResult:
    normalized = normalize_type(process_type)
    items: list[dict] = []
    tagged_files: list[Path] = []
    output_dir = service.create_request_dir(normalized)
    started_at = perf_counter()
    cpu_started_at = process_time()
    inference_total_ms = 0.0

    for source in sources:
        payload = service.predict_from_source(
            source,
            options=options,
            providers=providers,
            allow_similar=True,
        )
        payload["filename"] = source.filename
        payload["content_type"] = source.content_type
        payload["source_path"] = source.source_path
        payload["ok"] = True
        items.append(payload)
        inference_total_ms += float(payload.get("metrics", {}).get("inference_elapsed_ms", 0.0))
        if normalized == "mulitagimg":
            tagged_files.append(service.write_tagged_image(output_dir, source, payload))

    summary = {
        "repo_id": options.repo_id,
        "model_dir": options.model_dir,
        "providers": items[0]["providers"] if items else providers,
        "requested_count": len(sources),
        "success_count": len(items),
        "error_count": 0,
        "cache_stats": {
            "miss": sum(1 for item in items if item.get("cache", {}).get("cache_hit") == "miss"),
            "exact": sum(1 for item in items if item.get("cache", {}).get("cache_hit") == "exact"),
            "similar": sum(1 for item in items if item.get("cache", {}).get("cache_hit") == "similar"),
        },
        "items": items,
        "metrics": {
            **collect_process_metrics(),
            "total_elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
            "inference_elapsed_ms": round(inference_total_ms, 2),
            "cpu_elapsed_ms": round((process_time() - cpu_started_at) * 1000, 2),
        },
    }

    if normalized == "mulitagimg":
        manifest = service.write_batch_json(output_dir, summary)
        zip_path = service.zip_paths(output_dir, "tagged_images.zip", tagged_files + [manifest])
        return ProcessResult(
            type="mulitagimg",
            media_type="application/zip",
            body=zip_path.read_bytes(),
            filename=zip_path.name,
            metrics=summary["metrics"],
        )

    rows = service.build_batch_rows(items)
    json_path, csv_path, zip_path = service.package_json_and_csv(output_dir, summary, rows)
    if export_format == "inline":
        return ProcessResult(type="json", media_type="application/json", body=summary, metrics=summary["metrics"])
    if export_format == "json":
        return ProcessResult(
            type="json",
            media_type="application/json",
            body=json_path.read_bytes(),
            filename=json_path.name,
            metrics=summary["metrics"],
        )
    if export_format == "csv":
        return ProcessResult(
            type="json",
            media_type="text/csv; charset=utf-8",
            body=csv_path.read_bytes(),
            filename=csv_path.name,
            metrics=summary["metrics"],
        )
    return ProcessResult(
        type="json",
        media_type="application/zip",
        body=zip_path.read_bytes(),
        filename=zip_path.name,
        metrics=summary["metrics"],
    )
