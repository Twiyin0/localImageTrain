from __future__ import annotations

import argparse
import threading
import json
import os
import sys
import csv
from io import BytesIO
from pathlib import Path
from time import perf_counter

import gradio as gr
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wd_tagger.config import DEFAULT_CHARACTER_THRESHOLD, DEFAULT_GENERAL_THRESHOLD, get_default_onnx_providers
from wd_tagger.content_flags import build_flagged_summary, extract_tags
from wd_tagger.modes import load_sources_from_dir, process_batch_type
from wd_tagger.service import ImageSource, PredictionOptions, TaggerService, localize_metrics


DEFAULT_PROVIDERS = get_default_onnx_providers()
LOCAL_MODELS_DIR = PROJECT_ROOT / "models"


def discover_local_models() -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    if not LOCAL_MODELS_DIR.exists():
        return choices
    for model_dir in sorted(LOCAL_MODELS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        if (model_dir / "model.onnx").exists() and (model_dir / "selected_tags.csv").exists():
            choices.append((model_dir.name, str(model_dir)))
    return choices


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Gradio app for WD Tagger")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    return parser.parse_args()


class Predictor:
    def __init__(self) -> None:
        self.service = TaggerService()
        self.local_model_dir = os.getenv("WD_TAGGER_MODEL_DIR") or self._default_local_model_dir()
        self._warmup_lock = threading.Lock()
        self._warmup_status: dict[str, str | float | None] = {
            "status": "not_started",
            "model_dir": self.local_model_dir,
            "providers": "",
            "elapsed_ms": None,
            "error": None,
        }

    @staticmethod
    def _default_local_model_dir() -> str | None:
        models = discover_local_models()
        return models[0][1] if models else None

    def _options(
        self,
        model_dir: str | None,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> PredictionOptions:
        return PredictionOptions(
            model_dir=model_dir or self.local_model_dir,
            general_threshold=general_threshold,
            character_threshold=character_threshold,
            general_mcut=general_mcut,
            character_mcut=character_mcut,
        )

    @staticmethod
    def _payload_metrics(payload: dict) -> dict:
        metrics = localize_metrics(payload.get("metrics"))
        metrics["Actual providers"] = ", ".join(str(provider) for provider in payload.get("providers", []))
        cache = payload.get("cache", {}) if isinstance(payload.get("cache"), dict) else {}
        metrics["Cache hit"] = str(cache.get("cache_hit", "unknown"))
        return metrics

    @staticmethod
    def _batch_metrics(payload: dict, metrics_payload: dict | None) -> dict:
        metrics = localize_metrics(metrics_payload)
        metrics["Actual providers"] = ", ".join(str(provider) for provider in payload.get("providers", []))
        cache_stats = payload.get("cache_stats", {}) if isinstance(payload.get("cache_stats"), dict) else {}
        metrics["Cache stats"] = str(cache_stats)
        return metrics

    def _set_warmup_status(self, **updates: str | float | None) -> None:
        with self._warmup_lock:
            self._warmup_status.update(updates)

    def warmup_status(self) -> dict[str, str | float | None]:
        with self._warmup_lock:
            return dict(self._warmup_status)

    def warmup(self, model_dir: str | None = None) -> dict[str, str | float | None]:
        selected_model_dir = model_dir or self.local_model_dir
        if not selected_model_dir:
            self._set_warmup_status(status="skipped", error="No local model found.")
            return self.warmup_status()

        self._set_warmup_status(
            status="warming",
            model_dir=selected_model_dir,
            providers="",
            elapsed_ms=None,
            error=None,
        )
        started = perf_counter()
        try:
            self.service.exact_cache_enabled = False
            self.service.similar_cache_enabled = False
            image = Image.new("RGBA", (448, 448), (255, 255, 255, 255))
            payload = self.service.predict_from_source(
                source=ImageSource(
                    filename="warmup.png",
                    image=image,
                    content_type="image/png",
                ),
                options=self._options(
                    model_dir=selected_model_dir,
                    general_threshold=DEFAULT_GENERAL_THRESHOLD,
                    general_mcut=False,
                    character_threshold=DEFAULT_CHARACTER_THRESHOLD,
                    character_mcut=False,
                ),
                providers=DEFAULT_PROVIDERS,
            )
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            self._set_warmup_status(
                status="ready",
                providers=", ".join(str(provider) for provider in payload.get("providers", [])),
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            self._set_warmup_status(status="failed", elapsed_ms=elapsed_ms, error=str(exc))
        finally:
            self.service.exact_cache_enabled = os.getenv("WD_TAGGER_EXACT_CACHE_ENABLED", "1") != "0"
            self.service.similar_cache_enabled = os.getenv("WD_TAGGER_SIMILAR_CACHE_ENABLED", "1") != "0"
        return self.warmup_status()

    def warmup_async(self, model_dir: str | None = None) -> dict[str, str | float | None]:
        if self.warmup_status().get("status") == "warming":
            return self.warmup_status()
        thread = threading.Thread(target=self.warmup, args=(model_dir,), daemon=True)
        thread.start()
        return self.warmup_status()

    def process_single(
        self,
        image: Image.Image,
        model_dir: str,
        process_type: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, list | dict | None, str, dict | None, str | None, dict | None]:
        if image is None:
            return "Please provide an image.", None, "", None, None, None

        buffer = BytesIO()
        rgba = image.convert("RGBA")
        rgba.save(buffer, format="PNG")
        source = ImageSource(
            filename="input.png",
            image=rgba,
            content_type="image/png",
            source_bytes=buffer.getvalue(),
        )
        payload = self.service.predict_from_source(
            source=source,
            options=self._options(
                model_dir=model_dir,
                general_threshold=general_threshold,
                general_mcut=general_mcut,
                character_threshold=character_threshold,
                character_mcut=character_mcut,
            ),
            providers=DEFAULT_PROVIDERS,
        )
        highlighted_html, flagged_summary = build_flagged_summary(payload)
        metrics = self._payload_metrics(payload)
        tags = extract_tags(payload)

        if process_type == "tag":
            return str(payload.get("caption", "")), None, highlighted_html, flagged_summary, None, metrics
        if process_type in {"arrary", "array"}:
            return "", tags, highlighted_html, flagged_summary, None, metrics

        output_dir = self.service.create_request_dir("gradio_single")
        output_path = self.service.write_tagged_image(output_dir, source, payload)
        return "", payload, highlighted_html, flagged_summary, str(output_path), metrics

    def process_batch(
        self,
        files: list[str] | None,
        input_dir: str,
        model_dir: str,
        process_type: str,
        export_format: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[dict, str, list[dict[str, object]], str | None, str | None, str | None, dict | None]:
        sources: list[ImageSource] = []
        for file_path in files or []:
            path = Path(file_path)
            sources.append(
                ImageSource(
                    filename=path.name,
                    image=Image.open(path).convert("RGBA"),
                    content_type=f"image/{path.suffix.lower().lstrip('.') or 'png'}",
                    source_path=str(path),
                    source_bytes=path.read_bytes(),
                )
            )
        if input_dir.strip():
            sources.extend(load_sources_from_dir(input_dir.strip()))
        if not sources:
            return {"error": "Please upload images or provide an input directory."}, "", [], None, None, None, None

        request_export_format = "inline" if process_type == "json" and export_format == "both" else export_format

        result = process_batch_type(
            service=self.service,
            sources=sources,
            options=self._options(
                model_dir=model_dir,
                general_threshold=general_threshold,
                general_mcut=general_mcut,
                character_threshold=character_threshold,
                character_mcut=character_mcut,
            ),
            providers=DEFAULT_PROVIDERS,
            process_type=process_type,
            export_format=request_export_format,
        )

        if isinstance(result.body, dict):
            payload = dict(result.body)
            items = payload.get("items", []) if isinstance(payload.get("items", []), list) else []
            flagged_items: list[dict[str, object]] = []
            cards: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                _, summary = build_flagged_summary(item)
                flagged_tags = list(summary.get("flagged_tags", []))
                flagged_ratings = dict(summary.get("flagged_ratings", {}))
                flagged_items.append(
                    {
                        "filename": item.get("filename"),
                        "flagged_tags": flagged_tags,
                        "flagged_ratings": flagged_ratings,
                        "has_inappropriate_content": summary.get("has_inappropriate_content", False),
                    }
                )
                if flagged_tags or flagged_ratings:
                    details = ", ".join(flagged_tags) if flagged_tags else "rating only"
                    cards.append(
                        "<div style='margin-bottom:8px;padding:8px 10px;border:1px solid #ff7b7b;"
                        "border-radius:10px;background:#5b1f24;color:#fff5f5;'>"
                        f"<b>{item.get('filename') or 'image'}</b>: {details}</div>"
                    )
            payload["flagged_items"] = flagged_items
            json_file = None
            csv_file = None
            if process_type == "json":
                output_dir = self.service.create_request_dir("gradio_batch_json")
                json_path = output_dir / "results.json"
                json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                json_file = str(json_path)

                csv_path = output_dir / "results.csv"
                rows = self.service.build_batch_rows(items)
                with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
                    writer = csv.DictWriter(
                        file,
                        fieldnames=["filename", "ok", "caption", "tags", "cache_hit", "similarity_score", "error"],
                    )
                    writer.writeheader()
                    writer.writerows(rows)
                csv_file = str(csv_path)

            return (
                payload,
                "".join(cards) or "<div>No flagged tags.</div>",
                flagged_items,
                json_file,
                csv_file,
                None,
                self._batch_metrics(payload, result.metrics),
            )

        output_dir = self.service.create_request_dir("gradio_batch")
        output_path = output_dir / (result.filename or "batch_output.bin")
        data = result.body if isinstance(result.body, bytes) else str(result.body).encode("utf-8")
        output_path.write_bytes(data)
        return (
            {"type": process_type, "saved_file": str(output_path)},
            "<div>No flagged tags.</div>",
            [],
            None,
            None,
            str(output_path),
            localize_metrics(result.metrics),
        )


def build_ui() -> gr.Blocks:
    predictor = Predictor()
    local_models = discover_local_models()
    predictor.warmup_async()

    with gr.Blocks(title="Local WaifuDiffusion Tagger") as demo:
        gr.Markdown("# Local WaifuDiffusion Tagger")
        gr.Markdown("This is the preserved local Gradio frontend.")
        gr.Markdown(f"Current Python: `{sys.executable}`")
        if predictor.local_model_dir:
            gr.Markdown(f"Local model directory: `{predictor.local_model_dir}`")

        model_repo = gr.Dropdown(
            local_models,
            value=predictor.local_model_dir,
            label="Local model",
        )
        general_threshold = gr.Slider(0, 1, value=DEFAULT_GENERAL_THRESHOLD, step=0.05, label="General threshold")
        general_mcut = gr.Checkbox(label="General use MCut")
        character_threshold = gr.Slider(0, 1, value=DEFAULT_CHARACTER_THRESHOLD, step=0.05, label="Character threshold")
        character_mcut = gr.Checkbox(label="Character use MCut")
        with gr.Row():
            warmup_button = gr.Button("Warm up CUDA / model", variant="secondary")
            warmup_output = gr.JSON(label="Warmup status", value=predictor.warmup_status())

        with gr.Tab("Single"):
            with gr.Row():
                with gr.Column():
                    image = gr.Image(type="pil", image_mode="RGBA", label="Input image")
                    process_type_single = gr.Dropdown(["tag", "arrary", "tagimg"], value="tag", label="Type")
                    submit_single = gr.Button("Process single", variant="primary")
                with gr.Column():
                    single_text = gr.Textbox(label="Tag output")
                    single_json = gr.JSON(label="Structured output")
                    single_highlight = gr.HTML(label="Highlighted tags")
                    single_flagged = gr.JSON(label="Flagged tags")
                    single_file = gr.File(label="Generated file")
                    single_metrics = gr.JSON(label="Metrics")

        with gr.Tab("Batch / Directory"):
            with gr.Row():
                with gr.Column():
                    batch_files = gr.File(file_count="multiple", file_types=["image"], label="Upload images")
                    input_dir = gr.Textbox(
                        label="Input directory on server",
                        placeholder="e.g. /volume2/Project/images or E:\\images",
                    )
                    process_type_batch = gr.Dropdown(["json", "mulitagimg"], value="json", label="Type")
                    export_format = gr.Dropdown(["inline", "json", "csv", "both"], value="both", label="Export format")
                    submit_batch = gr.Button("Process batch", variant="primary")
                with gr.Column():
                    batch_json = gr.JSON(label="Batch result")
                    batch_highlight = gr.HTML(label="Highlighted tags")
                    batch_flagged = gr.JSON(label="Flagged tags")
                    batch_json_file = gr.File(label="Generated JSON")
                    batch_csv_file = gr.File(label="Generated CSV")
                    batch_file = gr.File(label="Generated archive / file")
                    batch_metrics = gr.JSON(label="Metrics")

        submit_single.click(
            predictor.process_single,
            inputs=[
                image,
                model_repo,
                process_type_single,
                general_threshold,
                general_mcut,
                character_threshold,
                character_mcut,
            ],
            outputs=[single_text, single_json, single_highlight, single_flagged, single_file, single_metrics],
        )
        submit_batch.click(
            predictor.process_batch,
            inputs=[
                batch_files,
                input_dir,
                model_repo,
                process_type_batch,
                export_format,
                general_threshold,
                general_mcut,
                character_threshold,
                character_mcut,
            ],
            outputs=[batch_json, batch_highlight, batch_flagged, batch_json_file, batch_csv_file, batch_file, batch_metrics],
        )
        warmup_button.click(
            predictor.warmup,
            inputs=[model_repo],
            outputs=[warmup_output],
        )
        demo.load(
            predictor.warmup_status,
            outputs=[warmup_output],
        )
    return demo


def main() -> None:
    args = parse_args()
    app = build_ui()
    app.queue(max_size=8)
    app.launch(server_name=args.host, server_port=args.port, share=args.share)


if __name__ == "__main__":
    main()
