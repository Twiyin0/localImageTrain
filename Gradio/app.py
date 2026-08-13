from __future__ import annotations

import argparse
import os
import sys
from io import BytesIO
from pathlib import Path

import gradio as gr
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
)
from wd_tagger.modes import load_sources_from_dir, process_batch_type, process_single_type
from wd_tagger.service import ImageSource, PredictionOptions, TaggerService


AVAILABLE_MODELS = [
    "SmilingWolf/wd-convnext-tagger-v3",
    "SmilingWolf/wd-vit-tagger-v3",
    "SmilingWolf/wd-swinv2-tagger-v3",
    "SmilingWolf/wd-vit-large-tagger-v3",
    "SmilingWolf/wd-eva02-large-tagger-v3",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Gradio app for WD Tagger")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    return parser.parse_args()


class Predictor:
    def __init__(self) -> None:
        self.service = TaggerService()
        self.local_model_dir = os.getenv("WD_TAGGER_MODEL_DIR")

    def _options(
        self,
        repo_id: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> PredictionOptions:
        return PredictionOptions(
            repo_id=repo_id,
            model_dir=self.local_model_dir,
            general_threshold=general_threshold,
            character_threshold=character_threshold,
            general_mcut=general_mcut,
            character_mcut=character_mcut,
        )

    def process_single(
        self,
        image: Image.Image,
        repo_id: str,
        process_type: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, list | dict | None, str | None]:
        if image is None:
            return "Please provide an image.", None, None

        buffer = BytesIO()
        image.convert("RGBA").save(buffer, format="PNG")

        result = process_single_type(
            service=self.service,
            source=ImageSource(
                filename="input.png",
                image=image.convert("RGBA"),
                content_type="image/png",
                source_bytes=buffer.getvalue(),
            ),
            options=self._options(
                repo_id=repo_id,
                general_threshold=general_threshold,
                general_mcut=general_mcut,
                character_threshold=character_threshold,
                character_mcut=character_mcut,
            ),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            process_type=process_type,
        )
        if process_type == "tag":
            return str(result.body), None, None
        if process_type in {"arrary", "array"}:
            return "", result.body if isinstance(result.body, list) else [], None
        if process_type == "tagimg":
            output_dir = self.service.create_request_dir("gradio_single")
            output_path = output_dir / (result.filename or "tagged_image.png")
            output_path.write_bytes(result.body if isinstance(result.body, bytes) else b"")
            return "", {"saved_file": str(output_path)}, str(output_path)
        return "", result.body if isinstance(result.body, dict) else {}, None

    def process_batch(
        self,
        files: list[str] | None,
        input_dir: str,
        repo_id: str,
        process_type: str,
        export_format: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[dict, str | None]:
        sources = []
        if files:
            for file_path in files:
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
            return {"error": "Please upload images or provide an input directory."}, None

        result = process_batch_type(
            service=self.service,
            sources=sources,
            options=self._options(
                repo_id=repo_id,
                general_threshold=general_threshold,
                general_mcut=general_mcut,
                character_threshold=character_threshold,
                character_mcut=character_mcut,
            ),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            process_type=process_type,
            export_format=export_format,
        )
        if isinstance(result.body, dict):
            return result.body, None

        output_dir = self.service.create_request_dir("gradio_batch")
        output_path = output_dir / (result.filename or "batch_output.bin")
        data = result.body if isinstance(result.body, bytes) else str(result.body).encode("utf-8")
        output_path.write_bytes(data)
        return {"type": process_type, "saved_file": str(output_path)}, str(output_path)


def build_ui() -> gr.Blocks:
    predictor = Predictor()
    with gr.Blocks(title="Local WaifuDiffusion Tagger") as demo:
        gr.Markdown("# Local WaifuDiffusion Tagger")
        gr.Markdown("This is the preserved local Gradio frontend.")
        gr.Markdown(f"Current Python: `{sys.executable}`")
        if predictor.local_model_dir:
            gr.Markdown(f"Local model directory: `{predictor.local_model_dir}`")

        model_repo = gr.Dropdown(
            AVAILABLE_MODELS,
            value=DEFAULT_ONNX_REPO,
            label="Model",
        )
        general_threshold = gr.Slider(
            0,
            1,
            value=DEFAULT_GENERAL_THRESHOLD,
            step=0.05,
            label="General threshold",
        )
        general_mcut = gr.Checkbox(label="General use MCut")
        character_threshold = gr.Slider(
            0,
            1,
            value=DEFAULT_CHARACTER_THRESHOLD,
            step=0.05,
            label="Character threshold",
        )
        character_mcut = gr.Checkbox(label="Character use MCut")

        with gr.Tab("Single"):
            with gr.Row():
                with gr.Column():
                    image = gr.Image(type="pil", image_mode="RGBA", label="Input image")
                    process_type_single = gr.Dropdown(
                        ["tag", "arrary", "tagimg"],
                        value="tag",
                        label="Type",
                    )
                    submit_single = gr.Button("Process single", variant="primary")
                with gr.Column():
                    single_text = gr.Textbox(label="Tag output")
                    single_json = gr.JSON(label="Structured output")
                    single_file = gr.File(label="Generated file")

        with gr.Tab("Batch / Directory"):
            with gr.Row():
                with gr.Column():
                    batch_files = gr.File(
                        file_count="multiple",
                        file_types=["image"],
                        label="Upload images",
                    )
                    input_dir = gr.Textbox(
                        label="Input directory on server",
                        placeholder="e.g. /volume2/Project/images or E:\\images",
                    )
                    process_type_batch = gr.Dropdown(
                        ["json", "mulitagimg"],
                        value="json",
                        label="Type",
                    )
                    export_format = gr.Dropdown(
                        ["inline", "json", "csv", "both"],
                        value="both",
                        label="Export format for type=json",
                    )
                    submit_batch = gr.Button("Process batch", variant="primary")
                with gr.Column():
                    batch_json = gr.JSON(label="Batch result")
                    batch_file = gr.File(label="Generated file")

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
            outputs=[single_text, single_json, single_file],
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
            outputs=[batch_json, batch_file],
        )
    return demo


def main() -> None:
    args = parse_args()
    app = build_ui()
    app.queue(max_size=8)
    app.launch(server_name=args.host, server_port=args.port, share=args.share)


if __name__ == "__main__":
    main()
