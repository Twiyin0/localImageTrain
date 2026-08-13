from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import gradio as gr
import httpx

from wd_tagger.config import DEFAULT_CHARACTER_THRESHOLD, DEFAULT_GENERAL_THRESHOLD, get_runtime_paths


DEFAULT_REMOTE_API_URL = os.getenv("WD_TAGGER_REMOTE_API_URL", "http://10.1.0.2:8000").strip()
DEFAULT_REMOTE_API_KEY = os.getenv("WD_TAGGER_REMOTE_API_KEY", "wdtagger-20260812-B7D9VQ2MZP4KX8R1").strip()
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("WD_TAGGER_REMOTE_TIMEOUT", "600"))

SINGLE_TYPES = ["tag", "arrary", "tagimg"]
BATCH_TYPES = ["json", "mulitagimg"]
EXPORT_FORMATS = ["inline", "json", "csv", "both"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remote Gradio client for WD Tagger NAS API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    return parser.parse_args()


@dataclass(frozen=True)
class RemoteResponse:
    content_type: str
    filename: str | None
    body: str | bytes | dict | list
    backend_process_ms: float | None
    backend_total_ms: float | None
    client_total_ms: float


class RemoteClient:
    def __init__(self) -> None:
        self.runtime = get_runtime_paths()
        self.output_root = self.runtime.output_dir / "remote_client"
        self.output_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        return base_url.strip().rstrip("/")

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        key = api_key.strip()
        if not key:
            raise ValueError("Please provide an API key.")
        return {"X-API-Key": key}

    @staticmethod
    def _parse_filename(response: httpx.Response) -> str | None:
        disposition = response.headers.get("content-disposition", "")
        marker = 'filename="'
        if marker in disposition:
            return disposition.split(marker, 1)[1].split('"', 1)[0].strip()
        return None

    @staticmethod
    def _parse_ms_header(response: httpx.Response, header_name: str) -> float | None:
        raw = response.headers.get(header_name)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _build_timing_summary(
        backend_process_ms: float | None,
        backend_total_ms: float | None,
        client_total_ms: float,
    ) -> dict[str, float | None]:
        return {
            "backend_process_ms": round(backend_process_ms, 2) if backend_process_ms is not None else None,
            "backend_total_ms": round(backend_total_ms, 2) if backend_total_ms is not None else None,
            "client_total_ms": round(client_total_ms, 2),
        }

    def _request(
        self,
        *,
        base_url: str,
        api_key: str,
        data: dict[str, Any],
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    ) -> RemoteResponse:
        normalized_base = self._normalize_base_url(base_url)
        if not normalized_base:
            raise ValueError("Please provide the remote API base URL.")

        started = perf_counter()
        with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{normalized_base}/process",
                headers=self._headers(api_key),
                data=data,
                files=files,
            )
            response.raise_for_status()
        client_total_ms = (perf_counter() - started) * 1000

        content_type = response.headers.get("content-type", "").lower()
        filename = self._parse_filename(response)
        backend_process_ms = self._parse_ms_header(response, "X-WD-Backend-Process-Time-Ms")
        backend_total_ms = self._parse_ms_header(response, "X-WD-Backend-Total-Time-Ms")

        if "application/json" in content_type:
            return RemoteResponse(
                content_type=content_type,
                filename=filename,
                body=response.json(),
                backend_process_ms=backend_process_ms,
                backend_total_ms=backend_total_ms,
                client_total_ms=client_total_ms,
            )
        if content_type.startswith("text/plain"):
            return RemoteResponse(
                content_type=content_type,
                filename=filename,
                body=response.text,
                backend_process_ms=backend_process_ms,
                backend_total_ms=backend_total_ms,
                client_total_ms=client_total_ms,
            )
        return RemoteResponse(
            content_type=content_type,
            filename=filename,
            body=response.content,
            backend_process_ms=backend_process_ms,
            backend_total_ms=backend_total_ms,
            client_total_ms=client_total_ms,
        )

    def _save_binary(self, prefix: str, filename: str | None, content: bytes) -> str:
        target_dir = self.output_root / prefix
        target_dir.mkdir(parents=True, exist_ok=True)
        target_name = filename or "download.bin"
        target_path = target_dir / target_name
        target_path.write_bytes(content)
        return str(target_path)

    @staticmethod
    def _serialize_error(exc: Exception) -> dict[str, Any]:
        if isinstance(exc, httpx.HTTPStatusError):
            detail: Any
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
            return {
                "error": f"Remote API returned HTTP {exc.response.status_code}",
                "detail": detail,
            }
        return {"error": str(exc)}

    def process_single(
        self,
        base_url: str,
        api_key: str,
        image_path: str | None,
        process_type: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, dict | list | None, str | None, dict[str, float | None]]:
        if not image_path:
            return "Please provide an image.", None, None, {}

        path = Path(image_path)
        try:
            remote = self._request(
                base_url=base_url,
                api_key=api_key,
                data={
                    "type": process_type,
                    "general_threshold": str(general_threshold),
                    "general_mcut": str(general_mcut).lower(),
                    "character_threshold": str(character_threshold),
                    "character_mcut": str(character_mcut).lower(),
                },
                files=[
                    (
                        "image",
                        (
                            path.name,
                            path.read_bytes(),
                            f"image/{path.suffix.lower().lstrip('.') or 'png'}",
                        ),
                    )
                ],
            )
        except Exception as exc:
            return "", self._serialize_error(exc), None, {}

        timing = self._build_timing_summary(
            remote.backend_process_ms,
            remote.backend_total_ms,
            remote.client_total_ms,
        )

        if process_type == "tag":
            return str(remote.body), None, None, timing
        if process_type == "arrary":
            return "", remote.body if isinstance(remote.body, list) else [], None, timing

        if isinstance(remote.body, bytes):
            output_path = self._save_binary("tagimg", remote.filename or f"{path.stem}_tagged{path.suffix or '.png'}", remote.body)
            return "", {
                "saved_file": output_path,
                "remote_content_type": remote.content_type,
                "timing": timing,
            }, output_path, timing

        return "", remote.body if isinstance(remote.body, dict) else {"error": "Unexpected response"}, None, timing

    def process_batch(
        self,
        base_url: str,
        api_key: str,
        files: list[str] | None,
        input_dir: str,
        process_type: str,
        export_format: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[dict | list, str | None, dict[str, float | None]]:
        uploads: list[tuple[str, tuple[str, bytes, str]]] = []
        for file_path in files or []:
            path = Path(file_path)
            uploads.append(
                (
                    "images",
                    (
                        path.name,
                        path.read_bytes(),
                        f"image/{path.suffix.lower().lstrip('.') or 'png'}",
                    ),
                )
            )

        try:
            remote = self._request(
                base_url=base_url,
                api_key=api_key,
                data={
                    "type": process_type,
                    "input_dir": input_dir.strip(),
                    "export_format": export_format,
                    "general_threshold": str(general_threshold),
                    "general_mcut": str(general_mcut).lower(),
                    "character_threshold": str(character_threshold),
                    "character_mcut": str(character_mcut).lower(),
                },
                files=uploads or None,
            )
        except Exception as exc:
            return self._serialize_error(exc), None, {}

        timing = self._build_timing_summary(
            remote.backend_process_ms,
            remote.backend_total_ms,
            remote.client_total_ms,
        )

        if isinstance(remote.body, (dict, list)):
            if isinstance(remote.body, dict):
                return {**remote.body, "timing": timing}, None, timing
            return remote.body, None, timing

        if isinstance(remote.body, bytes):
            prefix = "json" if process_type == "json" else "mulitagimg"
            fallback_name = "results_bundle.zip" if process_type == "json" else "tagged_images.zip"
            output_path = self._save_binary(prefix, remote.filename or fallback_name, remote.body)
            return {
                "type": process_type,
                "saved_file": output_path,
                "remote_content_type": remote.content_type,
                "timing": timing,
            }, output_path, timing

        return {"error": "Unexpected response from remote API."}, None, timing

    def health(self, base_url: str, api_key: str) -> dict[str, Any]:
        normalized_base = self._normalize_base_url(base_url)
        if not normalized_base:
            return {"error": "Please provide the remote API base URL."}

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{normalized_base}/health",
                    headers=self._headers(api_key),
                )
                response.raise_for_status()
            return response.json()
        except Exception as exc:
            return self._serialize_error(exc)


def build_ui() -> gr.Blocks:
    client = RemoteClient()

    with gr.Blocks(title="WaifuDiffusion Tagger Remote Client") as demo:
        gr.Markdown("# WaifuDiffusion Tagger Remote Client")
        gr.Markdown("This PC runs the frontend. The NAS processes images through the remote API.")
        gr.Markdown("Local preserved frontend is kept separately in `/Gradio`.")
        gr.Markdown(f"Current Python: `{sys.executable}`")
        gr.Markdown(f"Local download/output directory: `{client.output_root}`")

        with gr.Row():
            api_base_url = gr.Textbox(
                value=DEFAULT_REMOTE_API_URL,
                label="Remote API base URL",
                placeholder="http://10.1.0.2:8000",
            )
            api_key = gr.Textbox(
                value=DEFAULT_REMOTE_API_KEY,
                label="API Key",
                type="password",
            )

        with gr.Row():
            general_threshold = gr.Slider(
                0,
                1,
                value=DEFAULT_GENERAL_THRESHOLD,
                step=0.05,
                label="General threshold",
            )
            character_threshold = gr.Slider(
                0,
                1,
                value=DEFAULT_CHARACTER_THRESHOLD,
                step=0.05,
                label="Character threshold",
            )
        with gr.Row():
            general_mcut = gr.Checkbox(label="General use MCut")
            character_mcut = gr.Checkbox(label="Character use MCut")

        with gr.Tab("Connection"):
            with gr.Row():
                health_button = gr.Button("Check NAS API", variant="primary")
                health_output = gr.JSON(label="Health result")

        with gr.Tab("Single"):
            with gr.Row():
                with gr.Column():
                    image = gr.Image(type="filepath", label="Input image")
                    process_type_single = gr.Dropdown(
                        SINGLE_TYPES,
                        value="tag",
                        label="Type",
                    )
                    submit_single = gr.Button("Process single", variant="primary")
                with gr.Column():
                    single_text = gr.Textbox(label="Tag output")
                    single_json = gr.JSON(label="Structured output")
                    single_file = gr.File(label="Downloaded file")
                    single_timing = gr.JSON(label="Timing")

        with gr.Tab("Batch / Directory"):
            with gr.Row():
                with gr.Column():
                    batch_files = gr.File(
                        file_count="multiple",
                        file_types=["image"],
                        type="filepath",
                        label="Upload images to NAS",
                    )
                    input_dir = gr.Textbox(
                        label="NAS input directory",
                        placeholder="/volume2/Project/images",
                    )
                    process_type_batch = gr.Dropdown(
                        BATCH_TYPES,
                        value="json",
                        label="Type",
                    )
                    export_format = gr.Dropdown(
                        EXPORT_FORMATS,
                        value="both",
                        label="Export format for type=json",
                    )
                    submit_batch = gr.Button("Process batch", variant="primary")
                with gr.Column():
                    batch_json = gr.JSON(label="Batch result")
                    batch_file = gr.File(label="Downloaded file")
                    batch_timing = gr.JSON(label="Timing")

        health_button.click(
            client.health,
            inputs=[api_base_url, api_key],
            outputs=[health_output],
        )
        submit_single.click(
            client.process_single,
            inputs=[
                api_base_url,
                api_key,
                image,
                process_type_single,
                general_threshold,
                general_mcut,
                character_threshold,
                character_mcut,
            ],
            outputs=[single_text, single_json, single_file, single_timing],
        )
        submit_batch.click(
            client.process_batch,
            inputs=[
                api_base_url,
                api_key,
                batch_files,
                input_dir,
                process_type_batch,
                export_format,
                general_threshold,
                general_mcut,
                character_threshold,
                character_mcut,
            ],
            outputs=[batch_json, batch_file, batch_timing],
        )

    return demo


def main() -> None:
    args = parse_args()
    app = build_ui()
    app.queue(max_size=8)
    app.launch(server_name=args.host, server_port=args.port, share=args.share)


if __name__ == "__main__":
    main()
