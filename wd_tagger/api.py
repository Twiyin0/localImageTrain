from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import zipfile
from contextlib import asynccontextmanager
from io import BytesIO
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, Security, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
import uvicorn

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    find_local_model_dir,
    get_default_onnx_providers,
)
from wd_tagger.modes import (
    ProcessResult,
    load_sources_from_dir,
    load_sources_from_urls,
    process_batch_type,
    process_single_type,
)
from wd_tagger.service import DEFAULT_OUTPUT_FILENAME_TEMPLATE, ImageSource, PredictionOptions, TaggerService


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_SCHEME = HTTPBearer(auto_error=False)
SINGLE_TYPES = {"tag", "arrary", "array", "tagimg"}
BATCH_TYPES = {"json", "mulitagimg"}
STREAM_CHUNK_SIZE = 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def parse_provider_env() -> list[str]:
    raw = os.getenv("WD_TAGGER_PROVIDERS", "").strip()
    if raw:
        return [provider.strip() for provider in raw.split(",") if provider.strip()]
    return get_default_onnx_providers()


def get_expected_api_key() -> str:
    return os.getenv("WD_TAGGER_API_KEY", "").strip()


def require_api_key(
    x_api_key: str | None = Security(API_KEY_HEADER),
    bearer: HTTPAuthorizationCredentials | None = Security(BEARER_SCHEME),
) -> str:
    expected = get_expected_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured on the server")

    provided = x_api_key
    if not provided and bearer is not None:
        provided = bearer.credentials
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return provided


def normalize_image_content_type(content_type: str | None, filename: str | None = None) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in {"", "application/octet-stream"} and filename:
        guessed, _ = mimetypes.guess_type(filename)
        normalized = (guessed or normalized).lower()
    if not normalized.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")
    return normalized


def decode_image(content: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(content)) as image_file:
            return image_file.convert("RGBA")
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc


async def read_request_stream_bytes(request: Request) -> bytes:
    chunks = bytearray()
    async for chunk in request.stream():
        if chunk:
            chunks.extend(chunk)
    content = bytes(chunks)
    if not content:
        raise HTTPException(status_code=400, detail="Request body is empty")
    return content


async def read_upload_bytes(image: UploadFile) -> bytes:
    chunks = bytearray()
    while True:
        chunk = await image.read(STREAM_CHUNK_SIZE)
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


async def read_upload_image(image: UploadFile) -> ImageSource:
    content_type = normalize_image_content_type(image.content_type, image.filename)
    content = await read_upload_bytes(image)
    return ImageSource(
        filename=image.filename or "image.png",
        image=decode_image(content),
        content_type=content_type,
        source_bytes=content,
    )


async def read_stream_image(
    request: Request,
    *,
    filename: str | None,
    content_type: str | None,
) -> ImageSource:
    normalized_type = normalize_image_content_type(content_type or request.headers.get("content-type"), filename)
    content = await read_request_stream_bytes(request)
    return ImageSource(
        filename=filename or "stream_image.png",
        image=decode_image(content),
        content_type=normalized_type,
        source_bytes=content,
    )


def is_zip_content(content_type: str | None, filename: str | None = None) -> bool:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    return normalized in {"application/zip", "application/x-zip-compressed"} or (filename or "").lower().endswith(".zip")


async def read_stream_zip_sources(
    request: Request,
    *,
    filename: str | None,
    content_type: str | None,
) -> list[ImageSource]:
    if not is_zip_content(content_type or request.headers.get("content-type"), filename):
        raise HTTPException(status_code=400, detail="batch stream requires an application/zip request body")

    archive_bytes = await read_request_stream_bytes(request)
    sources: list[ImageSource] = []
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                entry_name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                if not entry_name:
                    continue
                if not any(entry_name.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    continue
                guessed_type = normalize_image_content_type(None, entry_name)
                source_bytes = archive.read(info)
                sources.append(
                    ImageSource(
                        filename=entry_name,
                        image=decode_image(source_bytes),
                        content_type=guessed_type,
                        source_bytes=source_bytes,
                    )
                )
    except HTTPException:
        raise
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid zip stream") from exc

    if not sources:
        raise HTTPException(status_code=400, detail="zip stream does not contain supported image files")
    return sources


MODEL_REPO = os.getenv("WD_TAGGER_REPO_ID", DEFAULT_ONNX_REPO)
SERVICE = TaggerService()
MODEL_DIR = os.getenv("WD_TAGGER_MODEL_DIR") or find_local_model_dir(
    repo_id=MODEL_REPO,
    project_root=SERVICE.runtime.project_root,
)
PROVIDERS = parse_provider_env()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="WaifuDiffusion Tagger API",
    description=(
        "Upload images or point to a directory and process them in multiple modes. "
        "Supports API key authentication and offline NAS deployment."
    ),
    version="1.3.3",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


def build_timing_headers(process_ms: float, backend_total_ms: float) -> dict[str, str]:
    return {
        "X-WD-Backend-Process-Time-Ms": f"{process_ms:.2f}",
        "X-WD-Backend-Total-Time-Ms": f"{backend_total_ms:.2f}",
    }


def build_response(result: ProcessResult, *, process_ms: float, backend_total_ms: float) -> Response:
    headers = build_timing_headers(process_ms, backend_total_ms)
    metrics = result.metrics if isinstance(result.metrics, dict) else None
    if metrics is not None:
        headers["X-WD-Process-Current-Rss-Mb"] = str(metrics.get("process_current_rss_mb"))
        headers["X-WD-Process-Peak-Rss-Mb"] = str(metrics.get("process_peak_rss_mb"))
        headers["X-WD-Process-Cpu-User-Time-S"] = str(metrics.get("cpu_user_time_s"))
        headers["X-WD-Process-Cpu-System-Time-S"] = str(metrics.get("cpu_system_time_s"))
    if result.type == "tag":
        return PlainTextResponse(str(result.body), headers=headers)
    if isinstance(result.body, dict):
        return JSONResponse(result.body, headers=headers)
    if isinstance(result.body, list):
        return JSONResponse(result.body, headers=headers)
    if isinstance(result.body, bytes):
        if result.filename:
            headers["Content-Disposition"] = f'attachment; filename="{result.filename}"'
        return Response(content=result.body, media_type=result.media_type, headers=headers)
    return PlainTextResponse(str(result.body), headers=headers)


def build_options(
    general_threshold: float,
    character_threshold: float,
    general_mcut: bool,
    character_mcut: bool,
    lang: Literal["zh", "en"] | None = None,
    translation_mode: str = "zh",
) -> PredictionOptions:
    return PredictionOptions(
        repo_id=MODEL_REPO,
        model_dir=MODEL_DIR,
        general_threshold=general_threshold,
        character_threshold=character_threshold,
        general_mcut=general_mcut,
        character_mcut=character_mcut,
        lang=lang,
        translation_mode=translation_mode,
    )


@app.get("/", summary="API Info")
def index() -> dict:
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "tag_endpoint": "/tag",
        "tag_stream_endpoint": "/tag/stream",
        "batch_tag_endpoint": "/tag/batch",
        "batch_tag_stream_endpoint": "/tag/batch/stream",
        "process_endpoint": "/process",
        "process_stream_endpoint": "/process/stream",
    }


@app.get("/health", summary="Health Check")
def health() -> dict:
    return {
        "status": "ok",
        "python": sys.executable,
        "repo_id": MODEL_REPO,
        "model_dir": MODEL_DIR,
        "providers": PROVIDERS,
        "auth_enabled": bool(get_expected_api_key()),
    }


@app.post("/tag", summary="Tag Image")
async def tag_image(
    image: UploadFile = File(..., description="Image file to analyze"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    lang: Literal["zh", "en"] | None = Form(None),
    translation_mode: str = Form("zh"),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = perf_counter()
    source = await read_upload_image(image)
    process_started = perf_counter()
    payload = SERVICE.predict_from_source(
        source=source,
        options=build_options(
            general_threshold,
            character_threshold,
            general_mcut,
            character_mcut,
            lang,
            translation_mode,
        ),
        providers=PROVIDERS,
    )
    process_ms = (perf_counter() - process_started) * 1000
    backend_total_ms = (perf_counter() - request_started) * 1000
    payload["filename"] = source.filename
    payload["content_type"] = source.content_type
    return JSONResponse(payload, headers=build_timing_headers(process_ms, backend_total_ms))


@app.post("/tag/stream", summary="Tag Image From Raw Stream")
async def tag_image_stream(
    request: Request,
    filename: str | None = Query(None, description="Original filename, used for type inference and response metadata"),
    general_threshold: float = Query(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Query(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Query(False),
    character_mcut: bool = Query(False),
    lang: Literal["zh", "en"] | None = Query(None),
    translation_mode: str = Query("zh"),
    content_type: str | None = Header(None),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = perf_counter()
    source = await read_stream_image(request, filename=filename, content_type=content_type)
    process_started = perf_counter()
    payload = SERVICE.predict_from_source(
        source=source,
        options=build_options(
            general_threshold,
            character_threshold,
            general_mcut,
            character_mcut,
            lang,
            translation_mode,
        ),
        providers=PROVIDERS,
    )
    process_ms = (perf_counter() - process_started) * 1000
    backend_total_ms = (perf_counter() - request_started) * 1000
    payload["filename"] = source.filename
    payload["content_type"] = source.content_type
    return JSONResponse(payload, headers=build_timing_headers(process_ms, backend_total_ms))


@app.post("/tag/batch", summary="Tag Images In Batch")
async def tag_images_batch(
    images: list[UploadFile] = File(..., description="Multiple image files to analyze"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    lang: Literal["zh", "en"] | None = Form(None),
    translation_mode: str = Form("zh"),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = perf_counter()
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")

    sources = []
    for image in images:
        sources.append(await read_upload_image(image))

    process_started = perf_counter()
    result = process_batch_type(
        service=SERVICE,
        sources=sources,
        options=build_options(
            general_threshold,
            character_threshold,
            general_mcut,
            character_mcut,
            lang,
            translation_mode,
        ),
        providers=PROVIDERS,
        process_type="json",
        export_format="inline",
    )
    process_ms = (perf_counter() - process_started) * 1000
    backend_total_ms = (perf_counter() - request_started) * 1000
    assert isinstance(result.body, dict)
    return JSONResponse(result.body, headers=build_timing_headers(process_ms, backend_total_ms))


@app.post("/tag/batch/stream", summary="Tag Zip Image Batch From Raw Stream")
async def tag_images_batch_stream(
    request: Request,
    filename: str | None = Query(None, description="Zip filename, optional"),
    general_threshold: float = Query(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Query(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Query(False),
    character_mcut: bool = Query(False),
    lang: Literal["zh", "en"] | None = Query(None),
    translation_mode: str = Query("zh"),
    content_type: str | None = Header(None),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = perf_counter()
    sources = await read_stream_zip_sources(request, filename=filename, content_type=content_type)
    process_started = perf_counter()
    result = process_batch_type(
        service=SERVICE,
        sources=sources,
        options=build_options(
            general_threshold,
            character_threshold,
            general_mcut,
            character_mcut,
            lang,
            translation_mode,
        ),
        providers=PROVIDERS,
        process_type="json",
        export_format="inline",
    )
    process_ms = (perf_counter() - process_started) * 1000
    backend_total_ms = (perf_counter() - request_started) * 1000
    assert isinstance(result.body, dict)
    return JSONResponse(result.body, headers=build_timing_headers(process_ms, backend_total_ms))


@app.post("/process/stream", summary="Unified Process Endpoint From Raw Stream")
async def process_stream_endpoint(
    request: Request,
    type: str = Query(..., description="tag | arrary | array | tagimg | json | mulitagimg"),
    filename: str | None = Query(None, description="Original image filename or zip filename"),
    export_format: str = Query("both", description="inline | json | csv | both; used by type=json"),
    output_filename_template: str = Query(
        DEFAULT_OUTPUT_FILENAME_TEMPLATE,
        description=(
            "Output filename template. Variables: ${origin_filename}, ${origin_ext}, "
            "${origin_basename}, ${type}, ${index}. Default: ${origin_filename}_tagged${origin_ext}"
        ),
    ),
    general_threshold: float = Query(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Query(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Query(False),
    character_mcut: bool = Query(False),
    lang: Literal["zh", "en"] | None = Query(None),
    translation_mode: str = Query("zh"),
    content_type: str | None = Header(None),
    _: str = Security(require_api_key),
) -> Response:
    request_started = perf_counter()
    options = build_options(
        general_threshold,
        character_threshold,
        general_mcut,
        character_mcut,
        lang,
        translation_mode,
    )

    if type in SINGLE_TYPES:
        source = await read_stream_image(request, filename=filename, content_type=content_type)
        process_started = perf_counter()
        result = process_single_type(
            service=SERVICE,
            source=source,
            options=options,
            providers=PROVIDERS,
            process_type=type,
            output_filename_template=output_filename_template,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        return build_response(result, process_ms=process_ms, backend_total_ms=backend_total_ms)

    if type in BATCH_TYPES:
        sources = await read_stream_zip_sources(request, filename=filename, content_type=content_type)
        process_started = perf_counter()
        result = process_batch_type(
            service=SERVICE,
            sources=sources,
            options=options,
            providers=PROVIDERS,
            process_type=type,
            export_format=export_format,
            output_filename_template=output_filename_template,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        return build_response(result, process_ms=process_ms, backend_total_ms=backend_total_ms)

    raise HTTPException(status_code=400, detail="Unsupported type")


@app.post("/process", summary="Unified Process Endpoint")
async def process_endpoint(
    type: str = Form(..., description="tag | arrary | tagimg | json | mulitagimg"),
    image: UploadFile | None = File(None, description="Single image"),
    images: list[UploadFile] | None = File(None, description="Multiple images"),
    image_url: str | None = Form(None, description="Single image URL"),
    image_urls: str | None = Form(None, description="Multiple image URLs split by comma, semicolon, pipe, or newline"),
    input_dir: str | None = Form(None, description="Server-side directory path for batch processing"),
    export_format: str = Form("both", description="inline | json | csv | both"),
    output_filename_template: str = Form(
        DEFAULT_OUTPUT_FILENAME_TEMPLATE,
        description=(
            "Output filename template. Variables: ${origin_filename}, ${origin_ext}, "
            "${origin_basename}, ${type}, ${index}. Default: ${origin_filename}_tagged${origin_ext}"
        ),
    ),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    lang: Literal["zh", "en"] | None = Form(None),
    translation_mode: str = Form("zh"),
    _: str = Security(require_api_key),
) -> Response:
    request_started = perf_counter()
    options = build_options(
        general_threshold,
        character_threshold,
        general_mcut,
        character_mcut,
        lang,
        translation_mode,
    )

    if type in SINGLE_TYPES:
        if image is not None:
            source = await read_upload_image(image)
        elif image_url and image_url.strip():
            try:
                source = load_sources_from_urls(image_url.strip())[0]
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            raise HTTPException(status_code=400, detail="single-image types require image or image_url")
        process_started = perf_counter()
        result = process_single_type(
            service=SERVICE,
            source=source,
            options=options,
            providers=PROVIDERS,
            process_type=type,
            output_filename_template=output_filename_template,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        return build_response(result, process_ms=process_ms, backend_total_ms=backend_total_ms)

    if type in BATCH_TYPES:
        sources = []
        if images:
            for upload in images:
                sources.append(await read_upload_image(upload))
        if input_dir and input_dir.strip():
            try:
                sources.extend(load_sources_from_dir(input_dir.strip()))
            except FileNotFoundError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if image_urls and image_urls.strip():
            try:
                sources.extend(load_sources_from_urls(image_urls))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not sources:
            raise HTTPException(status_code=400, detail="batch types require images, image_urls, or input_dir")

        process_started = perf_counter()
        result = process_batch_type(
            service=SERVICE,
            sources=sources,
            options=options,
            providers=PROVIDERS,
            process_type=type,
            export_format=export_format,
            output_filename_template=output_filename_template,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        return build_response(result, process_ms=process_ms, backend_total_ms=backend_total_ms)

    raise HTTPException(status_code=400, detail="Unsupported type")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WD Tagger FastAPI server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    uvicorn.run("wd_tagger.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
