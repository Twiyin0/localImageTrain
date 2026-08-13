from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
from html import escape
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

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

APP_CSS = """
#local-shell {
  --bg: #0b0f15;
  --panel: rgba(16, 22, 31, 0.94);
  --panel-2: rgba(22, 29, 41, 0.98);
  --border: rgba(130, 148, 176, 0.18);
  --text: #eef4ff;
  --muted: #99abc6;
  --accent: #ff7a18;
  --accent-2: #ff9a52;
  --ok: #31c48d;
  --warn: #ffb454;
  --bad: #ff7b7b;
}

#local-shell.gradio-container {
  max-width: 1580px !important;
  padding: 16px 24px 40px !important;
  background: #0b0f15;
  color: var(--text);
  font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif !important;
}

#local-shell .block {
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: var(--panel) !important;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.22);
}

#local-shell .status-card,
#local-shell .note-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(13, 18, 27, 0.94);
  padding: 12px 14px;
}

#local-shell .status-card p {
  margin: 0;
}

#local-shell .status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

#local-shell .status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

#local-shell .status-pill b {
  color: white;
}

#local-shell .status-ok { border-color: rgba(49, 196, 141, 0.28); }
#local-shell .status-warn { border-color: rgba(255, 180, 84, 0.28); }
#local-shell .status-bad { border-color: rgba(255, 123, 123, 0.28); }

#local-shell .tabs {
  gap: 12px;
}

#local-shell .tabs > .tab-nav {
  padding: 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
}

#local-shell .tabs > .tab-nav button {
  min-height: 44px;
  border-radius: 6px !important;
  padding: 0 18px;
  color: var(--muted);
  font-weight: 700;
}

#local-shell .tabs > .tab-nav button.selected {
  background: var(--accent) !important;
  color: white !important;
  box-shadow: 0 12px 26px rgba(255, 122, 24, 0.22);
}

#local-shell .result-tabs > .tab-nav {
  justify-content: flex-start;
}

#local-shell .result-tabs .tabitem {
  padding-top: 14px !important;
}

#local-shell .metric-grid,
#local-shell .flag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

#local-shell .metric-card,
#local-shell .flag-card,
#local-shell .empty-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  padding: 16px;
}

#local-shell .metric-card h4,
#local-shell .flag-card h4,
#local-shell .empty-card h4 {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

#local-shell .metric-card strong,
#local-shell .flag-card strong {
  display: block;
  color: white;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.45;
}

#local-shell .flag-card {
  border-color: rgba(255, 123, 123, 0.24);
  background: rgba(64, 22, 29, 0.78);
}

#local-shell .empty-card {
  text-align: center;
  color: var(--muted);
}

#local-shell .empty-card h4 {
  color: var(--text);
  text-transform: none;
  letter-spacing: 0;
  font-size: 16px;
}

#local-shell .primary-action button {
  min-height: 54px;
  border-radius: 8px !important;
  border: none !important;
  background: #f56d16 !important;
  color: white !important;
  font-size: 18px !important;
  font-weight: 800 !important;
  box-shadow: 0 18px 38px rgba(255, 122, 24, 0.24);
}

#local-shell .secondary-action button {
  min-height: 46px;
  border-radius: 8px !important;
}

#local-shell .gr-json,
#local-shell textarea {
  min-height: 250px !important;
}

#local-shell .results-file {
  min-height: 160px;
}
"""


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
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--share", action="store_true")
    return parser.parse_args()


def render_empty_card(title: str, message: str) -> str:
    return (
        "<div class='empty-card'>"
        f"<h4>{escape(title)}</h4>"
        f"<p>{escape(message)}</p>"
        "</div>"
    )


def render_metrics_html(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return render_empty_card("等待结果", "执行一次识别后，这里会显示推理耗时、内存和缓存命中信息。")

    parts = ["<div class='metric-grid'>"]
    for key, value in metrics.items():
        safe_value = "-" if value in {None, ""} else escape(str(value))
        parts.append(
            "<div class='metric-card'>"
            f"<h4>{escape(str(key))}</h4>"
            f"<strong>{safe_value}</strong>"
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_flagged_html(summary: dict[str, Any] | None) -> str:
    if not summary:
        return render_empty_card("暂无风险提示", "处理完成后，这里会显示命中的敏感标签和评分。")

    flagged_tags = list(summary.get("flagged_tags", []))
    flagged_ratings = dict(summary.get("flagged_ratings", {}))
    if not flagged_tags and not flagged_ratings:
        return render_empty_card("未发现明显风险标签", "当前结果没有命中敏感评分或风险标签。")

    cards: list[str] = ["<div class='flag-grid'>"]
    if flagged_tags:
        cards.append(
            "<div class='flag-card'>"
            "<h4>命中标签</h4>"
            f"<strong>{escape(', '.join(str(tag) for tag in flagged_tags))}</strong>"
            "</div>"
        )
    if flagged_ratings:
        cards.append(
            "<div class='flag-card'>"
            "<h4>命中评分</h4>"
            f"<strong>{escape(', '.join(f'{name}: {score}' for name, score in flagged_ratings.items()))}</strong>"
            "</div>"
        )
    cards.append("</div>")
    return "".join(cards)


def render_batch_flagged_html(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return render_empty_card("暂无风险摘要", "批量任务完成后，这里会汇总命中风险标签的文件。")

    cards: list[str] = ["<div class='flag-grid'>"]
    flagged_count = 0
    for item in items:
        flagged_tags = list(item.get("flagged_tags", []))
        flagged_ratings = dict(item.get("flagged_ratings", {}))
        if not flagged_tags and not flagged_ratings:
            continue
        flagged_count += 1
        details: list[str] = []
        if flagged_tags:
            details.append(", ".join(str(tag) for tag in flagged_tags))
        if flagged_ratings:
            details.append(", ".join(f"{name}: {score}" for name, score in flagged_ratings.items()))
        cards.append(
            "<div class='flag-card'>"
            f"<h4>{escape(str(item.get('filename') or 'image'))}</h4>"
            f"<strong>{escape(' | '.join(details))}</strong>"
            "</div>"
        )
    cards.append("</div>")
    if flagged_count == 0:
        return render_empty_card("未发现明显风险标签", "这次批量处理没有命中需要特别提醒的文件。")
    return "".join(cards)


def render_batch_summary_html(payload: dict[str, Any] | None) -> str:
    if not payload:
        return render_empty_card("等待批量结果", "执行批量处理后，这里会显示总数、成功数和缓存统计。")

    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    total = len(items)
    success = sum(1 for item in items if isinstance(item, dict) and item.get("ok", True))
    cache_stats = payload.get("cache_stats", {}) if isinstance(payload.get("cache_stats"), dict) else {}
    return render_metrics_html(
        {
            "总文件数": total,
            "成功处理": success,
            "失败数量": max(total - success, 0),
            "精确缓存": cache_stats.get("exact", 0),
            "近似缓存": cache_stats.get("similar", 0),
            "未命中": cache_stats.get("miss", 0),
        }
    )


def render_warmup_status_html(status: dict[str, str | float | None]) -> str:
    state = str(status.get("status") or "not_started")
    tone = {
        "ready": "status-ok",
        "warming": "status-warn",
        "failed": "status-bad",
        "skipped": "status-warn",
    }.get(state, "")
    label = {
        "ready": "模型已就绪",
        "warming": "模型预热中",
        "failed": "预热失败",
        "skipped": "未发现本地模型",
        "not_started": "尚未预热",
    }.get(state, state)

    parts = [
        f"<span class='status-pill {tone}'><b>状态</b>{escape(label)}</span>",
        f"<span class='status-pill'><b>Provider</b>{escape(str(status.get('providers') or ', '.join(DEFAULT_PROVIDERS)))}</span>",
    ]
    if status.get("model_dir"):
        parts.append(f"<span class='status-pill'><b>模型</b>{escape(Path(str(status['model_dir'])).name)}</span>")
    if status.get("elapsed_ms") is not None:
        parts.append(f"<span class='status-pill'><b>耗时</b>{escape(str(status['elapsed_ms']))} ms</span>")
    if status.get("error"):
        parts.append(f"<span class='status-pill status-bad'><b>错误</b>{escape(str(status['error']))}</span>")
    return "<div class='status-strip'>" + "".join(parts) + "</div>"


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
    def _payload_metrics(payload: dict) -> dict[str, Any]:
        metrics = localize_metrics(payload.get("metrics"))
        metrics["实际 Provider"] = ", ".join(str(provider) for provider in payload.get("providers", []))
        cache = payload.get("cache", {}) if isinstance(payload.get("cache"), dict) else {}
        metrics["缓存命中"] = str(cache.get("cache_hit", "unknown"))
        if cache.get("similarity_score") is not None:
            metrics["相似度得分"] = cache.get("similarity_score")
        return metrics

    @staticmethod
    def _batch_metrics(payload: dict, metrics_payload: dict | None) -> dict[str, Any]:
        metrics = localize_metrics(metrics_payload)
        metrics["实际 Provider"] = ", ".join(str(provider) for provider in payload.get("providers", []))
        cache_stats = payload.get("cache_stats", {}) if isinstance(payload.get("cache_stats"), dict) else {}
        metrics["缓存统计"] = cache_stats
        return metrics

    def _set_warmup_status(self, **updates: str | float | None) -> None:
        with self._warmup_lock:
            self._warmup_status.update(updates)

    def warmup_status(self) -> dict[str, str | float | None]:
        with self._warmup_lock:
            return dict(self._warmup_status)

    def warmup_status_html(self) -> str:
        return render_warmup_status_html(self.warmup_status())

    def warmup(self, model_dir: str | None = None) -> str:
        selected_model_dir = model_dir or self.local_model_dir
        if not selected_model_dir:
            self._set_warmup_status(status="skipped", error="No local model found.")
            return self.warmup_status_html()

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
        return self.warmup_status_html()

    def warmup_async(self, model_dir: str | None = None) -> None:
        if self.warmup_status().get("status") == "warming":
            return
        thread = threading.Thread(target=self.warmup, args=(model_dir,), daemon=True)
        thread.start()

    def process_single(
        self,
        image: Image.Image,
        model_dir: str,
        process_type: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, dict | list | None, str, str, str | None, str]:
        if image is None:
            return (
                "请先提供一张图像。",
                None,
                render_empty_card("等待结果", "上传图像后，这里会显示标签高亮视图。"),
                render_empty_card("暂无风险提示", "执行后这里会显示敏感标签和评分。"),
                None,
                render_empty_card("暂无指标", "执行后这里会显示推理耗时、内存和缓存信息。"),
            )

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
        metrics_html = render_metrics_html(self._payload_metrics(payload))
        flagged_html = render_flagged_html(flagged_summary)
        tags = extract_tags(payload)

        if process_type == "tag":
            return str(payload.get("caption", "")), payload, highlighted_html, flagged_html, None, metrics_html
        if process_type in {"arrary", "array"}:
            return ", ".join(tags), tags, highlighted_html, flagged_html, None, metrics_html

        output_dir = self.service.create_request_dir("gradio_single")
        output_path = self.service.write_tagged_image(output_dir, source, payload)
        return "", payload, highlighted_html, flagged_html, str(output_path), metrics_html

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
    ) -> tuple[dict, str, str, str | None, str | None, str | None, str]:
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
            empty = render_empty_card("等待批量任务", "上传文件或填写目录后再开始处理。")
            return {"error": "Please upload images or provide an input directory."}, empty, empty, None, None, None, empty

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
            items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
            flagged_items: list[dict[str, object]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                _, summary = build_flagged_summary(item)
                flagged_items.append(
                    {
                        "filename": item.get("filename"),
                        "flagged_tags": list(summary.get("flagged_tags", [])),
                        "flagged_ratings": dict(summary.get("flagged_ratings", {})),
                    }
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
                render_batch_summary_html(payload),
                render_batch_flagged_html(flagged_items),
                json_file,
                csv_file,
                None,
                render_metrics_html(self._batch_metrics(payload, result.metrics)),
            )

        output_dir = self.service.create_request_dir("gradio_batch")
        output_path = output_dir / (result.filename or "batch_output.bin")
        data = result.body if isinstance(result.body, bytes) else str(result.body).encode("utf-8")
        output_path.write_bytes(data)
        return (
            {"type": process_type, "saved_file": str(output_path)},
            render_empty_card("文件已生成", "批量处理已经完成，可以在导出页签中下载结果文件。"),
            render_empty_card("暂无风险摘要", "当前导出结果没有附带风险明细。"),
            None,
            None,
            str(output_path),
            render_metrics_html(localize_metrics(result.metrics)),
        )


def build_ui() -> gr.Blocks:
    predictor = Predictor()
    local_models = discover_local_models()
    predictor.warmup_async()

    with gr.Blocks(title="Local WaifuDiffusion Tagger", elem_id="local-shell") as demo:
        with gr.Tabs():
            with gr.Tab("单张处理"):
                with gr.Row():
                    with gr.Column(scale=11, min_width=500):
                        image = gr.Image(type="pil", image_mode="RGBA", label="输入图像")
                        single_model = gr.Dropdown(local_models, value=predictor.local_model_dir, label="本地模型")
                        process_type_single = gr.Dropdown(
                            choices=[
                                ("仅返回标签文本", "tag"),
                                ("返回标签数组", "arrary"),
                                ("导出写回标签图像", "tagimg"),
                            ],
                            value="tag",
                            label="返回类型",
                        )
                        with gr.Row():
                            single_general_threshold = gr.Slider(0, 1, value=DEFAULT_GENERAL_THRESHOLD, step=0.05, label="通用标签阈值")
                            single_character_threshold = gr.Slider(0, 1, value=DEFAULT_CHARACTER_THRESHOLD, step=0.05, label="角色标签阈值")
                        with gr.Row():
                            single_general_mcut = gr.Checkbox(label="通用标签自动阈值（MCut）")
                            single_character_mcut = gr.Checkbox(label="角色标签自动阈值（MCut）")
                        submit_single = gr.Button("开始处理单张图像", variant="primary", elem_classes=["primary-action"])

                    with gr.Column(scale=9, min_width=420):
                        with gr.Accordion("结果与详情", open=False):
                            with gr.Tabs(elem_classes=["result-tabs"]):
                                with gr.Tab("标签结果"):
                                    single_text = gr.Textbox(label="标签输出", lines=5, max_lines=10)
                                    single_highlight = gr.HTML(value=render_empty_card("等待结果", "处理完成后，这里会显示标签高亮视图。"))
                                with gr.Tab("结构化结果"):
                                    single_json = gr.JSON(label="结构化结果")
                                with gr.Tab("风险提示"):
                                    single_flagged = gr.HTML(value=render_empty_card("暂无风险提示", "执行后这里会显示敏感标签和评分。"))
                                with gr.Tab("导出文件"):
                                    single_file = gr.File(label="生成文件", elem_classes=["results-file"])
                                with gr.Tab("资源指标"):
                                    single_metrics = gr.HTML(value=render_empty_card("暂无指标", "执行后这里会显示推理耗时、内存和缓存信息。"))

            with gr.Tab("批量处理"):
                with gr.Row():
                    with gr.Column(scale=11, min_width=500):
                        batch_files = gr.File(file_count="multiple", file_types=["image"], type="filepath", label="批量上传图像")
                        batch_input_dir = gr.Textbox(label="本地目录路径", placeholder="/Users/you/images")
                        batch_model = gr.Dropdown(local_models, value=predictor.local_model_dir, label="本地模型")
                        process_type_batch = gr.Dropdown(
                            choices=[("生成 JSON 结果", "json"), ("导出写回标签图像", "mulitagimg")],
                            value="json",
                            label="批量模式",
                        )
                        export_format = gr.Dropdown(
                            choices=[("仅内联结果", "inline"), ("仅 JSON 文件", "json"), ("仅 CSV 文件", "csv"), ("JSON + CSV", "both")],
                            value="both",
                            label="导出格式",
                        )
                        with gr.Row():
                            batch_general_threshold = gr.Slider(0, 1, value=DEFAULT_GENERAL_THRESHOLD, step=0.05, label="通用标签阈值")
                            batch_character_threshold = gr.Slider(0, 1, value=DEFAULT_CHARACTER_THRESHOLD, step=0.05, label="角色标签阈值")
                        with gr.Row():
                            batch_general_mcut = gr.Checkbox(label="通用标签自动阈值（MCut）")
                            batch_character_mcut = gr.Checkbox(label="角色标签自动阈值（MCut）")
                        submit_batch = gr.Button("开始批量处理", variant="primary", elem_classes=["primary-action"])

                    with gr.Column(scale=9, min_width=420):
                        with gr.Accordion("结果与详情", open=False):
                            with gr.Tabs(elem_classes=["result-tabs"]):
                                with gr.Tab("处理摘要"):
                                    batch_summary = gr.HTML(value=render_empty_card("等待批量结果", "执行批量处理后，这里会显示总数、成功数和缓存统计。"))
                                with gr.Tab("结构化结果"):
                                    batch_json = gr.JSON(label="批量结果")
                                with gr.Tab("风险摘要"):
                                    batch_flagged = gr.HTML(value=render_empty_card("暂无风险摘要", "批量任务完成后，这里会汇总命中风险标签的文件。"))
                                with gr.Tab("导出文件"):
                                    batch_json_file = gr.File(label="JSON 文件", elem_classes=["results-file"])
                                    batch_csv_file = gr.File(label="CSV 文件", elem_classes=["results-file"])
                                    batch_file = gr.File(label="归档 / 导出文件", elem_classes=["results-file"])
                                with gr.Tab("资源指标"):
                                    batch_metrics = gr.HTML(value=render_empty_card("暂无指标", "批量任务完成后，这里会显示耗时、内存和缓存统计。"))

            with gr.Tab("运行状态"):
                with gr.Row():
                    warmup_status = gr.HTML(value=predictor.warmup_status_html(), elem_classes=["status-card"])
                    warmup_button = gr.Button("刷新模型状态", variant="secondary", elem_classes=["secondary-action"])

        submit_single.click(
            predictor.process_single,
            inputs=[
                image,
                single_model,
                process_type_single,
                single_general_threshold,
                single_general_mcut,
                single_character_threshold,
                single_character_mcut,
            ],
            outputs=[single_text, single_json, single_highlight, single_flagged, single_file, single_metrics],
        )
        submit_batch.click(
            predictor.process_batch,
            inputs=[
                batch_files,
                batch_input_dir,
                batch_model,
                process_type_batch,
                export_format,
                batch_general_threshold,
                batch_general_mcut,
                batch_character_threshold,
                batch_character_mcut,
            ],
            outputs=[batch_json, batch_summary, batch_flagged, batch_json_file, batch_csv_file, batch_file, batch_metrics],
        )
        warmup_button.click(
            predictor.warmup,
            inputs=[single_model],
            outputs=[warmup_status],
        )
        demo.load(
            predictor.warmup_status_html,
            outputs=[warmup_status],
        )
    return demo


def main() -> None:
    args = parse_args()
    predictor = Predictor()
    print(f"[local-mode] Python: {sys.executable}")
    print(f"[local-mode] Providers: {', '.join(DEFAULT_PROVIDERS)}")
    print(f"[local-mode] Model directory: {predictor.local_model_dir or 'auto-discover / auto-download'}")
    app = build_ui()
    app.queue(max_size=8)
    app.launch(server_name=args.host, server_port=args.port, share=args.share, css=APP_CSS)


if __name__ == "__main__":
    main()
