from __future__ import annotations

import argparse
import os
import sys

import gradio as gr
from PIL import Image

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    assert_supported_python,
    get_default_onnx_providers,
)
from wd_tagger.service import PredictionOptions, TaggerService, localize_metrics


AVAILABLE_MODELS = [
    "SmilingWolf/wd-convnext-tagger-v3",
    "SmilingWolf/wd-vit-tagger-v3",
    "SmilingWolf/wd-swinv2-tagger-v3",
    "SmilingWolf/wd-vit-large-tagger-v3",
    "SmilingWolf/wd-eva02-large-tagger-v3",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gradio app for local WD Tagger")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    return parser.parse_args()


class Predictor:
    def __init__(self) -> None:
        self.service = TaggerService()
        self.local_model_dir = os.getenv("WD_TAGGER_MODEL_DIR")

    def predict(
        self,
        image: Image.Image,
        repo_id: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, dict, dict, dict, dict]:
        payload = self.service.predict_from_image(
            image=image,
            options=PredictionOptions(
                repo_id=repo_id,
                model_dir=self.local_model_dir,
                general_threshold=general_threshold,
                character_threshold=character_threshold,
                general_mcut=general_mcut,
                character_mcut=character_mcut,
            ),
            providers=get_default_onnx_providers(),
        )
        return (
            payload["caption"],
            payload["rating"],
            payload["characters"],
            payload["general"],
            localize_metrics(payload["metrics"]),
        )


def build_ui() -> gr.Blocks:
    predictor = Predictor()
    with gr.Blocks(title="Local WaifuDiffusion Tagger") as demo:
        gr.Markdown("# Local WaifuDiffusion Tagger")
        gr.Markdown("适配 4GB 显存：默认使用 ONNX 推理，首次运行会自动下载模型。")
        gr.Markdown(f"当前 Python: `{sys.executable}`")
        if predictor.local_model_dir:
            gr.Markdown(f"当前使用本地模型目录: `{predictor.local_model_dir}`")
        with gr.Row():
            with gr.Column():
                image = gr.Image(type="pil", image_mode="RGBA", label="Input")
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
                submit = gr.Button("Run", variant="primary")
            with gr.Column():
                caption = gr.Textbox(label="Caption")
                rating = gr.Label(label="Rating")
                characters = gr.Label(label="Characters")
                general = gr.Label(label="Tags")
                metrics = gr.JSON(label="推理与资源信息")

        submit.click(
            predictor.predict,
            inputs=[
                image,
                model_repo,
                general_threshold,
                general_mcut,
                character_threshold,
                character_mcut,
            ],
            outputs=[caption, rating, characters, general, metrics],
        )
    return demo


def main() -> None:
    assert_supported_python()
    args = parse_args()
    app = build_ui()
    app.queue(max_size=8)
    app.launch(server_name=args.host, server_port=args.port, share=args.share)


if __name__ == "__main__":
    main()
