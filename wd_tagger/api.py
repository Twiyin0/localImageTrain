from __future__ import annotations

import argparse
import os
import sys
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
import uvicorn

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    assert_supported_python,
    get_default_onnx_providers,
)
from wd_tagger.service import PredictionOptions, TaggerService


def parse_provider_env() -> list[str]:
    raw = os.getenv("WD_TAGGER_PROVIDERS", "").strip()
    if raw:
        return [provider.strip() for provider in raw.split(",") if provider.strip()]
    return get_default_onnx_providers()


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
        "Upload an image and return WD Tagger labels. "
        "This API is designed for NAS CPU Docker deployment by default."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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
    }


@app.get("/health", summary="Health Check")
def health() -> dict:
    return {
        "status": "ok",
        "python": sys.executable,
        "repo_id": MODEL_REPO,
        "model_dir": MODEL_DIR,
        "providers": PROVIDERS,
    }


@app.post("/tag", summary="Tag Image")
async def tag_image(
    image: UploadFile = File(..., description="Image file to analyze"),
    general_threshold: float = Form(DEFAULT_GENERAL_THRESHOLD),
    character_threshold: float = Form(DEFAULT_CHARACTER_THRESHOLD),
    general_mcut: bool = Form(False),
    character_mcut: bool = Form(False),
) -> JSONResponse:
    content_type = (image.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    try:
        content = await image.read()
        pil_image = Image.open(BytesIO(content)).convert("RGBA")
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc

    payload = SERVICE.predict_from_image(
        image=pil_image,
        options=PredictionOptions(
            repo_id=MODEL_REPO,
            model_dir=MODEL_DIR,
            general_threshold=general_threshold,
            character_threshold=character_threshold,
            general_mcut=general_mcut,
            character_mcut=character_mcut,
        ),
        providers=PROVIDERS,
    )
    payload["filename"] = image.filename
    payload["content_type"] = image.content_type
    return JSONResponse(payload)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WD Tagger FastAPI server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    assert_supported_python()
    args = build_arg_parser().parse_args()
    uvicorn.run("wd_tagger.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
