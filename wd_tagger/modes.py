from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

from wd_tagger.service import ImageSource, PredictionOptions, TaggerService

ProcessType = Literal["tag", "arrary", "array", "tagimg", "json", "mulitagimg"]
ExportFormat = Literal["inline", "json", "csv", "both"]


@dataclass(frozen=True)
class ProcessResult:
    type: str
    media_type: str
    body: str | bytes | dict | list
    filename: str | None = None


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
        image = Image.open(path).convert("RGBA")
        sources.append(
            ImageSource(
                filename=path.name,
                image=image,
                content_type=f"image/{path.suffix.lower().lstrip('.')}",
                source_path=str(path),
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
    payload = service.predict_from_image(source.image, options=options, providers=providers)
    payload["filename"] = source.filename
    payload["content_type"] = source.content_type
    payload["source_path"] = source.source_path

    normalized = normalize_type(process_type)
    if normalized == "tag":
        return ProcessResult(type="tag", media_type="text/plain; charset=utf-8", body=payload["caption"])
    if normalized == "arrary":
        return ProcessResult(type="arrary", media_type="application/json", body=service.extract_tag_array(payload))
    if normalized == "tagimg":
        output_dir = service.create_request_dir("tagimg")
        tagged_path = service.write_tagged_image(output_dir, source, payload)
        return ProcessResult(
            type="tagimg",
            media_type="application/octet-stream",
            body=tagged_path.read_bytes(),
            filename=tagged_path.name,
        )
    return ProcessResult(type="json", media_type="application/json", body=payload)


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

    for source in sources:
        payload = service.predict_from_image(source.image, options=options, providers=providers)
        payload["filename"] = source.filename
        payload["content_type"] = source.content_type
        payload["source_path"] = source.source_path
        payload["ok"] = True
        items.append(payload)
        if normalized == "mulitagimg":
            tagged_files.append(service.write_tagged_image(output_dir, source, payload))

    summary = {
        "repo_id": options.repo_id,
        "model_dir": options.model_dir,
        "providers": items[0]["providers"] if items else providers,
        "requested_count": len(sources),
        "success_count": len(items),
        "error_count": 0,
        "items": items,
    }

    if normalized == "mulitagimg":
        manifest = service.write_batch_json(output_dir, summary)
        zip_path = service.zip_paths(output_dir, "tagged_images.zip", tagged_files + [manifest])
        return ProcessResult(
            type="mulitagimg",
            media_type="application/zip",
            body=zip_path.read_bytes(),
            filename=zip_path.name,
        )

    rows = service.build_batch_rows(items)
    json_path, csv_path, zip_path = service.package_json_and_csv(output_dir, summary, rows)
    if export_format == "inline":
        return ProcessResult(type="json", media_type="application/json", body=summary)
    if export_format == "json":
        return ProcessResult(
            type="json",
            media_type="application/json",
            body=json_path.read_bytes(),
            filename=json_path.name,
        )
    if export_format == "csv":
        return ProcessResult(
            type="json",
            media_type="text/csv; charset=utf-8",
            body=csv_path.read_bytes(),
            filename=csv_path.name,
        )
    return ProcessResult(
        type="json",
        media_type="application/zip",
        body=zip_path.read_bytes(),
        filename=zip_path.name,
    )
