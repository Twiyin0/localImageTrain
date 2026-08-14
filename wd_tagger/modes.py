from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from time import perf_counter, process_time
from typing import Literal
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import mimetypes
import re

from PIL import Image

from wd_tagger.service import (
    DEFAULT_BATCH_ARCHIVE_TEMPLATE,
    ImageSource,
    PredictionOptions,
    TaggerService,
    collect_process_metrics,
    render_output_filename,
)

ProcessType = Literal["tag", "arrary", "array", "tagimg", "json", "mulitagimg"]
ExportFormat = Literal["inline", "json", "csv", "both"]
URL_SPLIT_PATTERN = re.compile(r"[\n,;|]+")
MAX_URL_IMAGE_BYTES = 25 * 1024 * 1024


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


def split_image_urls(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in URL_SPLIT_PATTERN.split(value) if part.strip()]


def _filename_from_url(url: str, content_type: str, index: int) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    suffix = Path(name).suffix
    if not suffix:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        suffix = guessed or ".png"
    stem = Path(name).stem or f"url_image_{index}"
    return f"{stem}{suffix}"


def load_source_from_url(url: str, index: int = 1) -> ImageSource:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported image URL scheme: {url}")

    request = Request(url, headers={"User-Agent": "WD-Tagger/1.0"})
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "image/png")
        content_length = response.headers.get("Content-Length")
        try:
            if content_length and int(content_length) > MAX_URL_IMAGE_BYTES:
                raise ValueError(f"image URL is too large: {url}")
        except ValueError:
            if content_length and content_length.isdigit():
                raise
        source_bytes = response.read(MAX_URL_IMAGE_BYTES + 1)
    if len(source_bytes) > MAX_URL_IMAGE_BYTES:
        raise ValueError(f"image URL is too large: {url}")
    if not content_type.lower().startswith("image/"):
        guessed_type, _ = mimetypes.guess_type(url)
        content_type = guessed_type or content_type
    image = Image.open(BytesIO(source_bytes)).convert("RGBA")
    return ImageSource(
        filename=_filename_from_url(url, content_type, index),
        image=image,
        content_type=content_type,
        source_path=url,
        source_bytes=source_bytes,
    )


def load_sources_from_urls(urls: str | None) -> list[ImageSource]:
    return [load_source_from_url(url, index) for index, url in enumerate(split_image_urls(urls), start=1)]


def process_single_type(
    service: TaggerService,
    source: ImageSource,
    options: PredictionOptions,
    providers: list[str],
    process_type: str,
    output_filename_template: str | None = None,
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
        tagged_path = service.write_tagged_image(output_dir, source, payload, output_filename_template)
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
    output_filename_template: str | None = None,
) -> ProcessResult:
    normalized = normalize_type(process_type)
    items: list[dict] = []
    tagged_files: list[Path] = []
    output_dir = service.create_request_dir(normalized)
    started_at = perf_counter()
    cpu_started_at = process_time()
    inference_total_ms = 0.0

    for index, source in enumerate(sources, start=1):
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
            tagged_files.append(service.write_tagged_image(output_dir, source, payload, output_filename_template, index))

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
        archive_name = render_output_filename(
            output_filename_template or DEFAULT_BATCH_ARCHIVE_TEMPLATE,
            origin_name="batch.zip",
            default_ext=".zip",
            process_type="mulitagimg",
        )
        zip_path = service.zip_paths(output_dir, archive_name, tagged_files + [manifest])
        return ProcessResult(
            type="mulitagimg",
            media_type="application/zip",
            body=zip_path.read_bytes(),
            filename=zip_path.name,
            metrics=summary["metrics"],
        )

    rows = service.build_batch_rows(items)
    json_path, csv_path, zip_path = service.package_json_and_csv(output_dir, summary, rows, output_filename_template)
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
