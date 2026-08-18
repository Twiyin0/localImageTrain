from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import zipfile
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from time import perf_counter, time
from typing import Literal
from uuid import uuid4

from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, Query, Request, Security, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
import uvicorn

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    discover_local_model_dirs,
    find_local_model_dir,
    get_default_onnx_providers,
)
from wd_tagger.content_flags import DEFAULT_SENSITIVE_THRESHOLD
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
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_env_file() -> None:
    env_path = PROJECT_ROOT / ".env.nas"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


load_local_env_file()


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
    api_key_cookie: str | None = Cookie(default=None, alias="wd_tagger_api_key"),
) -> str:
    expected = get_expected_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="API key is not configured on the server")

    provided = x_api_key
    if not provided and bearer is not None:
        provided = bearer.credentials
    if not provided:
        provided = api_key_cookie
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


async def read_request_stream_payload(request: Request) -> tuple[bytes, str]:
    chunks = bytearray()
    digest = hashlib.md5()
    async for chunk in request.stream():
        if not chunk:
            continue
        chunks.extend(chunk)
        digest.update(chunk)
    content = bytes(chunks)
    if not content:
        raise HTTPException(status_code=400, detail="Request body is empty")
    return content, digest.hexdigest()


async def read_upload_bytes(image: UploadFile) -> bytes:
    chunks = bytearray()
    while True:
        chunk = await image.read(STREAM_CHUNK_SIZE)
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


async def read_upload_payload(image: UploadFile) -> tuple[bytes, str]:
    chunks = bytearray()
    digest = hashlib.md5()
    while True:
        chunk = await image.read(STREAM_CHUNK_SIZE)
        if not chunk:
            break
        chunks.extend(chunk)
        digest.update(chunk)
    return bytes(chunks), digest.hexdigest()


async def read_upload_image(image: UploadFile) -> ImageSource:
    content_type = normalize_image_content_type(image.content_type, image.filename)
    content, content_md5 = await read_upload_payload(image)
    return ImageSource.from_bytes(
        filename=image.filename or "image.png",
        content_type=content_type,
        source_bytes=content,
        source_md5=content_md5,
    )


async def read_stream_image(
    request: Request,
    *,
    filename: str | None,
    content_type: str | None,
) -> ImageSource:
    normalized_type = normalize_image_content_type(content_type or request.headers.get("content-type"), filename)
    content, content_md5 = await read_request_stream_payload(request)
    return ImageSource.from_bytes(
        filename=filename or "stream_image.png",
        content_type=normalized_type,
        source_bytes=content,
        source_md5=content_md5,
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
                    ImageSource.from_bytes(
                        filename=entry_name,
                        content_type=guessed_type,
                        source_bytes=source_bytes,
                        source_md5=hashlib.md5(source_bytes).hexdigest(),
                    )
                )
    except HTTPException:
        raise
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid zip stream") from exc

    if not sources:
        raise HTTPException(status_code=400, detail="zip stream does not contain supported image files")
    return sources


def close_image_source(source: ImageSource | None) -> None:
    if source is None:
        return
    source.close()


def close_image_sources(sources: list[ImageSource] | None) -> None:
    if not sources:
        return
    for source in sources:
        source.close()


MODEL_REPO = os.getenv("WD_TAGGER_REPO_ID", DEFAULT_ONNX_REPO)
SERVICE = TaggerService()
MODEL_DIR = os.getenv("WD_TAGGER_MODEL_DIR") or find_local_model_dir(
    repo_id=MODEL_REPO,
    project_root=SERVICE.runtime.project_root,
)
PROVIDERS = parse_provider_env()
WEBUI_DIR = SERVICE.runtime.project_root / "webui" / "public"
WEBUI_INDEX = WEBUI_DIR / "index.html"
WEBUI_ASSETS = {
    "styles.css": WEBUI_DIR / "styles.css",
    "app.js": WEBUI_DIR / "app.js",
    "flags.js": WEBUI_DIR / "flags.js",
}


def list_local_models() -> list[dict[str, str | bool]]:
    models = []
    default_dir = str(Path(MODEL_DIR).resolve()) if MODEL_DIR else None
    for model_dir in discover_local_model_dirs(project_root=SERVICE.runtime.project_root):
        resolved = str(model_dir.resolve())
        models.append(
            {
                "name": model_dir.name,
                "model_dir": resolved,
                "repo_id": f"SmilingWolf/{model_dir.name}" if model_dir.name.startswith("wd-") else MODEL_REPO,
                "default": resolved == default_dir,
            }
        )
    if default_dir and not any(item["model_dir"] == default_dir for item in models):
        models.insert(
            0,
            {
                "name": Path(default_dir).name,
                "model_dir": default_dir,
                "repo_id": MODEL_REPO,
                "default": True,
            },
        )
    return models


def resolve_requested_model(model_dir: str | None = None, repo_id: str | None = None) -> tuple[str, str | None]:
    selected_repo = (repo_id or MODEL_REPO).strip() or MODEL_REPO
    requested_dir = (model_dir or "").strip()
    if not requested_dir:
        return selected_repo, MODEL_DIR

    requested_path = Path(requested_dir).expanduser()
    try:
        resolved_requested = str(requested_path.resolve())
    except OSError:
        raise HTTPException(status_code=400, detail="Invalid model_dir")

    allowed_dirs = {str(Path(item["model_dir"]).resolve()) for item in list_local_models() if item.get("model_dir")}
    if resolved_requested not in allowed_dirs:
        raise HTTPException(status_code=400, detail="model_dir must be one of the discovered local models")

    matched = next((item for item in list_local_models() if item["model_dir"] == resolved_requested), None)
    selected_repo = str(matched.get("repo_id") or selected_repo) if matched else selected_repo
    return selected_repo, resolved_requested


UPLOAD_ROOT = SERVICE.runtime.cache_dir / "webui_uploads"
UPLOAD_TTL_SECONDS = max(60, int(os.getenv("WD_TAGGER_UPLOAD_TTL_SECONDS", "86400")))
UPLOAD_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def ensure_upload_root() -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return UPLOAD_ROOT


def cleanup_upload_root(*, max_age_seconds: int = UPLOAD_TTL_SECONDS) -> None:
    root = ensure_upload_root()
    now = time()
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        try:
            if now - entry.stat().st_mtime > max_age_seconds:
                shutil.rmtree(entry, ignore_errors=True)
        except FileNotFoundError:
            continue


def _validate_upload_id(upload_id: str) -> str:
    upload_id = upload_id.strip()
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload reference")
    return upload_id


def _resolve_uploaded_file(upload_id: str) -> Path:
    upload_dir = ensure_upload_root() / _validate_upload_id(upload_id)
    if not upload_dir.is_dir():
        raise HTTPException(status_code=404, detail="Upload reference not found")
    files = [path for path in upload_dir.iterdir() if path.is_file()]
    if len(files) != 1:
        raise HTTPException(status_code=404, detail="Upload reference is invalid")
    return files[0]


def _load_source_from_path(path: Path) -> ImageSource:
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Upload file not found")
    content = path.read_bytes()
    content_type = normalize_image_content_type(None, path.name)
    return ImageSource.from_bytes(
        filename=path.name,
        content_type=content_type,
        source_bytes=content,
        source_path=str(path),
    )


def load_uploaded_source(upload_id: str) -> ImageSource:
    return _load_source_from_path(_resolve_uploaded_file(upload_id))


def load_uploaded_sources(upload_ids: str | list[str] | None) -> list[ImageSource]:
    if upload_ids is None:
        return []
    if isinstance(upload_ids, str):
        parts = [part.strip() for part in upload_ids.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in upload_ids if str(part).strip()]
    if not parts:
        return []
    return [load_uploaded_source(upload_id) for upload_id in parts]


async def save_uploaded_file(image: UploadFile) -> dict[str, object]:
    ensure_upload_root()
    upload_id = uuid4().hex
    upload_dir = UPLOAD_ROOT / upload_id
    upload_dir.mkdir(parents=True, exist_ok=False)
    filename = Path(image.filename or "upload.png").name or "upload.png"
    content_type = normalize_image_content_type(image.content_type, filename)
    target = upload_dir / filename
    digest = hashlib.md5()
    size = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await image.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    return {
        "upload_id": upload_id,
        "filename": filename,
        "content_type": content_type,
        "size": size,
        "md5": digest.hexdigest(),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    cleanup_upload_root()
    yield


app = FastAPI(
    title="WaifuDiffusion Tagger API",
    description=(
        "Upload images or point to a directory and process them in multiple modes. "
        "Supports API key authentication and offline NAS deployment."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


@app.middleware("http")
async def capture_request_started_at(request: Request, call_next):
    request.state.request_started_at = perf_counter()
    return await call_next(request)


def get_request_started_at(request: Request | None) -> float:
    started_at = getattr(getattr(request, "state", None), "request_started_at", None)
    if isinstance(started_at, (int, float)):
        return float(started_at)
    return perf_counter()


def build_timing_headers(process_ms: float, backend_total_ms: float) -> dict[str, str]:
    prepare_ms = max(backend_total_ms - process_ms, 0.0)
    return {
        "X-WD-Backend-Process-Time-Ms": f"{process_ms:.2f}",
        "X-WD-Backend-Total-Time-Ms": f"{backend_total_ms:.2f}",
        "X-WD-Backend-Prepare-Time-Ms": f"{prepare_ms:.2f}",
    }


def build_response(result: ProcessResult, *, process_ms: float, backend_total_ms: float) -> Response:
    headers = build_timing_headers(process_ms, backend_total_ms)
    metrics = result.metrics if isinstance(result.metrics, dict) else None
    cache = result.cache if isinstance(result.cache, dict) else None
    risk = result.risk if isinstance(result.risk, dict) else None
    if metrics is not None:
        inference_ms = metrics.get("inference_elapsed_ms")
        cpu_elapsed_ms = metrics.get("cpu_elapsed_ms")
        if inference_ms is not None:
            headers["X-WD-Inference-Time-Ms"] = str(inference_ms)
            headers["X-WD-Backend-Post-Inference-Time-Ms"] = f"{max(process_ms - float(inference_ms), 0.0):.2f}"
        if cpu_elapsed_ms is not None:
            headers["X-WD-Cpu-Elapsed-Ms"] = str(cpu_elapsed_ms)
        headers["X-WD-Process-Current-Rss-Mb"] = str(metrics.get("process_current_rss_mb"))
        headers["X-WD-Process-Peak-Rss-Mb"] = str(metrics.get("process_peak_rss_mb"))
        headers["X-WD-Process-Cpu-User-Time-S"] = str(metrics.get("cpu_user_time_s"))
        headers["X-WD-Process-Cpu-System-Time-S"] = str(metrics.get("cpu_system_time_s"))
    if cache is not None:
        cache_hit = cache.get("cache_hit")
        similarity_score = cache.get("similarity_score")
        if cache_hit is not None:
            headers["X-WD-Cache-Hit"] = str(cache_hit)
        if similarity_score is not None:
            headers["X-WD-Cache-Similarity-Score"] = str(similarity_score)
    if risk is not None:
        headers["X-WD-Risk-Summary"] = json.dumps(risk, ensure_ascii=True, separators=(",", ":"))
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
    sensitive_threshold: float,
    general_mcut: bool,
    character_mcut: bool,
    lang: Literal["zh", "en"] | None = None,
    translation_mode: str = "zh",
    model_dir: str | None = None,
    repo_id: str | None = None,
) -> PredictionOptions:
    selected_repo, selected_model_dir = resolve_requested_model(model_dir=model_dir, repo_id=repo_id)
    return PredictionOptions(
        repo_id=selected_repo,
        model_dir=selected_model_dir,
        general_threshold=general_threshold,
        character_threshold=character_threshold,
        sensitive_threshold=sensitive_threshold,
        general_mcut=general_mcut,
        character_mcut=character_mcut,
        lang=lang,
        translation_mode=translation_mode,
    )

def serve_webui_file(path: Path, *, media_type: str) -> FileResponse:
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@app.get("/", summary="Web UI")
def index() -> Response:
    if not WEBUI_INDEX.is_file():
        raise HTTPException(status_code=404, detail="Web UI is not available")
    html = WEBUI_INDEX.read_text(encoding="utf-8")
    response = HTMLResponse(html, headers={"Cache-Control": "no-store"})
    api_key = get_expected_api_key()
    if api_key:
        response.set_cookie(
            key="wd_tagger_api_key",
            value=api_key,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
    return response


@app.get("/styles.css", include_in_schema=False)
def styles_css() -> Response:
    return serve_webui_file(WEBUI_ASSETS["styles.css"], media_type="text/css; charset=utf-8")


@app.get("/app.js", include_in_schema=False)
def app_js() -> Response:
    return serve_webui_file(WEBUI_ASSETS["app.js"], media_type="application/javascript; charset=utf-8")


@app.get("/flags.js", include_in_schema=False)
def flags_js() -> Response:
    return serve_webui_file(WEBUI_ASSETS["flags.js"], media_type="application/javascript; charset=utf-8")


@app.get("/health", summary="Health Check")
def health() -> dict:
    models = list_local_models()
    return {
        "status": "ok",
        "version": app.version,
        "frontend": "static-html",
        "python": sys.executable,
        "repo_id": MODEL_REPO,
        "model_dir": MODEL_DIR,
        "providers": PROVIDERS,
        "auth_enabled": bool(get_expected_api_key()),
        "models": models,
        "model_count": len(models),
    }


@app.get("/models", summary="List Local Models")
def models(_: str = Security(require_api_key)) -> dict:
    return {
        "default_model_dir": MODEL_DIR,
        "repo_id": MODEL_REPO,
        "models": list_local_models(),
    }


@app.post("/uploads/image", summary="Upload Image To Temporary Cache")
async def upload_image(image: UploadFile = File(..., description="Image file to cache for later processing"), _: str = Security(require_api_key)) -> dict[str, object]:
    payload = await save_uploaded_file(image)
    cleanup_upload_root()
    return payload


@app.post("/tag", summary="Tag Image")
async def tag_image(
    request: Request,
    image: UploadFile | None = File(None, description="Image file to analyze"),
    image_ref: str | None = Form(None, description="Temporary upload reference returned by /uploads/image"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    sensitive_threshold: float = Form(DEFAULT_SENSITIVE_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    lang: Literal["zh", "en"] | None = Form(None),
    translation_mode: str = Form("zh"),
    model_dir: str | None = Form(None),
    repo_id: str | None = Form(None),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = get_request_started_at(request)
    if image_ref and image_ref.strip():
        source = load_uploaded_source(image_ref)
    elif image is not None:
        source = await read_upload_image(image)
    else:
        raise HTTPException(status_code=400, detail="Either image or image_ref is required")
    try:
        process_started = perf_counter()
        payload = SERVICE.predict_from_source(
            source=source,
            options=build_options(
                general_threshold,
                character_threshold,
                sensitive_threshold,
                general_mcut,
                character_mcut,
                lang,
                translation_mode,
                model_dir,
                repo_id,
            ),
            providers=PROVIDERS,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        payload["filename"] = source.filename
        payload["content_type"] = source.content_type
        return JSONResponse(payload, headers=build_timing_headers(process_ms, backend_total_ms))
    finally:
        close_image_source(source)


@app.post("/tag/stream", summary="Tag Image From Raw Stream")
async def tag_image_stream(
    request: Request,
    filename: str | None = Query(None, description="Original filename, used for type inference and response metadata"),
    general_threshold: float = Query(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Query(DEFAULT_CHARACTER_THRESHOLD),
    sensitive_threshold: float = Query(DEFAULT_SENSITIVE_THRESHOLD),
    general_mcut: bool = Query(False),
    character_mcut: bool = Query(False),
    lang: Literal["zh", "en"] | None = Query(None),
    translation_mode: str = Query("zh"),
    model_dir: str | None = Query(None),
    repo_id: str | None = Query(None),
    content_type: str | None = Header(None),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = get_request_started_at(request)
    source = await read_stream_image(request, filename=filename, content_type=content_type)
    try:
        process_started = perf_counter()
        payload = SERVICE.predict_from_source(
            source=source,
            options=build_options(
                general_threshold,
                character_threshold,
                sensitive_threshold,
                general_mcut,
                character_mcut,
                lang,
                translation_mode,
                model_dir,
                repo_id,
            ),
            providers=PROVIDERS,
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        payload["filename"] = source.filename
        payload["content_type"] = source.content_type
        return JSONResponse(payload, headers=build_timing_headers(process_ms, backend_total_ms))
    finally:
        close_image_source(source)


@app.post("/tag/batch", summary="Tag Images In Batch")
async def tag_images_batch(
    request: Request,
    images: list[UploadFile] | None = File(None, description="Multiple image files to analyze"),
    image_refs: str | None = Form(None, description="Comma-separated temporary upload references"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    sensitive_threshold: float = Form(DEFAULT_SENSITIVE_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    lang: Literal["zh", "en"] | None = Form(None),
    translation_mode: str = Form("zh"),
    model_dir: str | None = Form(None),
    repo_id: str | None = Form(None),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = get_request_started_at(request)
    if not images and not (image_refs and image_refs.strip()):
        raise HTTPException(status_code=400, detail="At least one image is required")

    sources = []
    try:
        if image_refs and image_refs.strip():
            sources.extend(load_uploaded_sources(image_refs))
        for image in images or []:
            sources.append(await read_upload_image(image))

        process_started = perf_counter()
        result = process_batch_type(
            service=SERVICE,
            sources=sources,
            options=build_options(
                general_threshold,
                character_threshold,
                sensitive_threshold,
                general_mcut,
                character_mcut,
                lang,
                translation_mode,
                model_dir,
                repo_id,
            ),
            providers=PROVIDERS,
            process_type="json",
            export_format="inline",
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        assert isinstance(result.body, dict)
        return JSONResponse(result.body, headers=build_timing_headers(process_ms, backend_total_ms))
    finally:
        close_image_sources(sources)


@app.post("/tag/batch/stream", summary="Tag Zip Image Batch From Raw Stream")
async def tag_images_batch_stream(
    request: Request,
    filename: str | None = Query(None, description="Zip filename, optional"),
    general_threshold: float = Query(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Query(DEFAULT_CHARACTER_THRESHOLD),
    sensitive_threshold: float = Query(DEFAULT_SENSITIVE_THRESHOLD),
    general_mcut: bool = Query(False),
    character_mcut: bool = Query(False),
    lang: Literal["zh", "en"] | None = Query(None),
    translation_mode: str = Query("zh"),
    model_dir: str | None = Query(None),
    repo_id: str | None = Query(None),
    content_type: str | None = Header(None),
    _: str = Security(require_api_key),
) -> JSONResponse:
    request_started = get_request_started_at(request)
    sources = await read_stream_zip_sources(request, filename=filename, content_type=content_type)
    try:
        process_started = perf_counter()
        result = process_batch_type(
            service=SERVICE,
            sources=sources,
            options=build_options(
                general_threshold,
                character_threshold,
                sensitive_threshold,
                general_mcut,
                character_mcut,
                lang,
                translation_mode,
                model_dir,
                repo_id,
            ),
            providers=PROVIDERS,
            process_type="json",
            export_format="inline",
        )
        process_ms = (perf_counter() - process_started) * 1000
        backend_total_ms = (perf_counter() - request_started) * 1000
        assert isinstance(result.body, dict)
        return JSONResponse(result.body, headers=build_timing_headers(process_ms, backend_total_ms))
    finally:
        close_image_sources(sources)


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
    sensitive_threshold: float = Query(DEFAULT_SENSITIVE_THRESHOLD),
    general_mcut: bool = Query(False),
    character_mcut: bool = Query(False),
    lang: Literal["zh", "en"] | None = Query(None),
    translation_mode: str = Query("zh"),
    model_dir: str | None = Query(None),
    repo_id: str | None = Query(None),
    content_type: str | None = Header(None),
    _: str = Security(require_api_key),
) -> Response:
    request_started = get_request_started_at(request)
    options = build_options(
        general_threshold,
        character_threshold,
        sensitive_threshold,
        general_mcut,
        character_mcut,
        lang,
        translation_mode,
        model_dir,
        repo_id,
    )

    if type in SINGLE_TYPES:
        source = await read_stream_image(request, filename=filename, content_type=content_type)
        try:
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
        finally:
            close_image_source(source)

    if type in BATCH_TYPES:
        sources = await read_stream_zip_sources(request, filename=filename, content_type=content_type)
        try:
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
        finally:
            close_image_sources(sources)

    raise HTTPException(status_code=400, detail="Unsupported type")


@app.post("/process", summary="Unified Process Endpoint")
async def process_endpoint(
    request: Request,
    type: str = Form(..., description="tag | arrary | tagimg | json | mulitagimg"),
    image: UploadFile | None = File(None, description="Single image"),
    images: list[UploadFile] | None = File(None, description="Multiple images"),
    image_ref: str | None = Form(None, description="Temporary upload reference returned by /uploads/image"),
    image_refs: str | None = Form(None, description="Comma-separated temporary upload references"),
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
    sensitive_threshold: float = Form(DEFAULT_SENSITIVE_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
    lang: Literal["zh", "en"] | None = Form(None),
    translation_mode: str = Form("zh"),
    model_dir: str | None = Form(None),
    repo_id: str | None = Form(None),
    _: str = Security(require_api_key),
) -> Response:
    request_started = get_request_started_at(request)
    options = build_options(
        general_threshold,
        character_threshold,
        sensitive_threshold,
        general_mcut,
        character_mcut,
        lang,
        translation_mode,
        model_dir,
        repo_id,
    )

    if type in SINGLE_TYPES:
        if image_ref and image_ref.strip():
            source = load_uploaded_source(image_ref)
        elif image is not None:
            source = await read_upload_image(image)
        elif image_url and image_url.strip():
            try:
                source = load_sources_from_urls(image_url.strip())[0]
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            raise HTTPException(status_code=400, detail="single-image types require image or image_url")
        try:
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
        finally:
            close_image_source(source)

    if type in BATCH_TYPES:
        sources = []
        try:
            if image_refs and image_refs.strip():
                sources.extend(load_uploaded_sources(image_refs))
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
        finally:
            close_image_sources(sources)

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
