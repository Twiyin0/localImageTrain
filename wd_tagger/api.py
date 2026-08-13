from __future__ import annotations

import argparse
import os
import sys
from contextlib import asynccontextmanager
from io import BytesIO
from time import perf_counter

from fastapi import FastAPI, File, Form, HTTPException, Security, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
import uvicorn

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
)
from wd_tagger.modes import (
    ProcessResult,
    load_sources_from_dir,
    process_batch_type,
    process_single_type,
)
from wd_tagger.service import ImageSource, PredictionOptions, TaggerService


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_SCHEME = HTTPBearer(auto_error=False)
SINGLE_TYPES = {"tag", "arrary", "array", "tagimg"}
BATCH_TYPES = {"json", "mulitagimg"}


def parse_provider_env() -> list[str]:
    raw = os.getenv("WD_TAGGER_PROVIDERS", "").strip()
    if raw:
        return [provider.strip() for provider in raw.split(",") if provider.strip()]
    return ["CPUExecutionProvider"]


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


async def read_upload_image(image: UploadFile) -> tuple[Image.Image, bytes]:
    content_type = (image.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")
    try:
        content = await image.read()
        return Image.open(BytesIO(content)).convert("RGBA"), content
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc


SERVICE = TaggerService()
MODEL_REPO = os.getenv("WD_TAGGER_REPO_ID", DEFAULT_ONNX_REPO)
MODEL_DIR = os.getenv("WD_TAGGER_MODEL_DIR")
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
    version="1.2.0",
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
) -> PredictionOptions:
    return PredictionOptions(
        repo_id=MODEL_REPO,
        model_dir=MODEL_DIR,
        general_threshold=general_threshold,
        character_threshold=character_threshold,
        general_mcut=general_mcut,
        character_mcut=character_mcut,
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
        "batch_tag_endpoint": "/tag/batch",
        "process_endpoint": "/process",
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
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = perf_counter()
    pil_image, source_bytes = await read_upload_image(image)
    process_started = perf_counter()
    payload = SERVICE.predict_from_source(
        source=ImageSource(
            filename=image.filename or "image.png",
            image=pil_image,
            content_type=image.content_type or "image/png",
            source_bytes=source_bytes,
        ),
        options=build_options(general_threshold, character_threshold, general_mcut, character_mcut),
        providers=PROVIDERS,
    )
    process_ms = (perf_counter() - process_started) * 1000
    backend_total_ms = (perf_counter() - request_started) * 1000
    payload["filename"] = image.filename
    payload["content_type"] = image.content_type
    return JSONResponse(payload, headers=build_timing_headers(process_ms, backend_total_ms))


@app.post("/tag/batch", summary="Tag Images In Batch")
async def tag_images_batch(
    images: list[UploadFile] = File(..., description="Multiple image files to analyze"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = perf_counter()
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")

    sources = []
    for image in images:
        pil_image, source_bytes = await read_upload_image(image)
        sources.append(
            ImageSource(
                filename=image.filename or "image.png",
                image=pil_image,
                content_type=image.content_type or "image/png",
                source_bytes=source_bytes,
            )
        )

    process_started = perf_counter()
    result = process_batch_type(
        service=SERVICE,
        sources=sources,
        options=build_options(general_threshold, character_threshold, general_mcut, character_mcut),
        providers=PROVIDERS,
        process_type="json",
        export_format="inline",
    )
    process_ms = (perf_counter() - process_started) * 1000
    backend_total_ms = (perf_counter() - request_started) * 1000
    assert isinstance(result.body, dict)
    return JSONResponse(result.body, headers=build_timing_headers(process_ms, backend_total_ms))


@app.post("/process", summary="Unified Process Endpoint")
async def process_endpoint(
    type: str = Form(..., description="tag | arrary | tagimg | json | mulitagimg"),
    image: UploadFile | None = File(None, description="Single image"),
    images: list[UploadFile] | None = File(None, description="Multiple images"),
    input_dir: str | None = Form(None, description="Server-side directory path for batch processing"),
    export_format: str = Form("both", description="inline | json | csv | both"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    _: str = Security(require_api_key),
) -> Response:
    request_started = perf_counter()
    options = build_options(general_threshold, character_threshold, general_mcut, character_mcut)

    if type in SINGLE_TYPES:
        if image is None:
            raise HTTPException(status_code=400, detail="single-image types require the image field")
        pil_image, source_bytes = await read_upload_image(image)
        process_started = perf_counter()
        result = process_single_type(
            service=SERVICE,
            source=ImageSource(
                filename=image.filename or "image.png",
                image=pil_image,
                content_type=image.content_type or "image/png",
                source_bytes=source_bytes,
            ),
            options=options,
            providers=PROVIDERS,
            process_type=type,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        return build_response(result, process_ms=process_ms, backend_total_ms=backend_total_ms)

    if type in BATCH_TYPES:
        sources = []
        if images:
            for upload in images:
                pil_image, source_bytes = await read_upload_image(upload)
                sources.append(
                    ImageSource(
                        filename=upload.filename or "image.png",
                        image=pil_image,
                        content_type=upload.content_type or "image/png",
                        source_bytes=source_bytes,
                    )
                )
        if input_dir and input_dir.strip():
            try:
                sources.extend(load_sources_from_dir(input_dir.strip()))
            except FileNotFoundError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not sources:
            raise HTTPException(status_code=400, detail="batch types require images or input_dir")

        process_started = perf_counter()
        result = process_batch_type(
            service=SERVICE,
            sources=sources,
            options=options,
            providers=PROVIDERS,
            process_type=type,
            export_format=export_format,
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
