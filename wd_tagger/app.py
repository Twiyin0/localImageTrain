from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path
from time import perf_counter
from typing import Any

import gradio as gr
import httpx

from wd_tagger.config import DEFAULT_CHARACTER_THRESHOLD, DEFAULT_GENERAL_THRESHOLD, get_runtime_paths
from wd_tagger.content_flags import build_flagged_summary
from wd_tagger.service import DEFAULT_OUTPUT_FILENAME_TEMPLATE, localize_metrics


DEFAULT_REMOTE_API_URL = os.getenv("WD_TAGGER_REMOTE_API_URL", "http://10.1.0.2:8000").strip()
DEFAULT_REMOTE_API_KEY = os.getenv("WD_TAGGER_REMOTE_API_KEY", "wdtagger-20260812-B7D9VQ2MZP4KX8R1").strip()
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("WD_TAGGER_REMOTE_TIMEOUT", "600"))
DEFAULT_TRANSLATION_MODE = os.getenv("WD_TAGGER_TRANSLATION_MODE", "original").strip() or "original"
DEFAULT_TRANSLATION_API_URL = os.getenv("WD_TAGGER_TRANSLATION_API_URL", "").strip()

SINGLE_TYPES = ["tag", "arrary", "tagimg"]
BATCH_TYPES = ["json", "mulitagimg"]
EXPORT_FORMATS = ["inline", "json", "csv", "both"]
OUTPUT_TEMPLATE_CHOICES = [
    ("默认：原名_tagged.原后缀", DEFAULT_OUTPUT_FILENAME_TEMPLATE),
    ("保留原名", "${origin_filename}${origin_ext}"),
    ("原名_类型_序号", "${origin_filename}_${type}_${index}${origin_ext}"),
    ("原名_时间戳", "${origin_filename}_${timestamp}${origin_ext}"),
]
OUTPUT_TEMPLATE_PRESETS = [
    {"label_zh": label, "label_en": label_en, "value": value}
    for (label, value), label_en in zip(
        OUTPUT_TEMPLATE_CHOICES,
        [
            "Default: original_tagged.ext",
            "Keep original filename",
            "Original_type_index",
            "Original_timestamp",
        ],
        strict=True,
    )
]

APP_I18N = gr.I18n(
    **{
        "zh-CN": {
            "tab.connection": "连接设置",
            "tab.single": "单张处理",
            "tab.batch": "批量处理",
            "tab.upload": "上传图片",
            "tab.url": "网络 URL",
            "tab.tag_result": "标签结果",
            "tab.structured": "结构化结果",
            "tab.flags": "风险提示",
            "tab.flag_summary": "风险摘要",
            "tab.export": "导出文件",
            "tab.timing": "耗时指标",
            "tab.batch_summary": "处理摘要",
            "button.health": "检测远程连接",
            "button.single": "开始处理单张图像",
            "button.batch": "开始批量处理",
            "label.api_url": "远程 API 地址",
            "label.api_key": "API Key",
            "label.health_result": "健康检查结果",
            "label.image": "输入图像",
            "label.image_url": "图像 URL",
            "label.batch_urls": "批量图像 URL",
            "label.remote_dir": "远程目录路径",
            "label.return_type": "返回类型",
            "label.translation_mode": "翻译模式",
            "label.translation_api_url": "翻译 API 地址",
            "label.batch_mode": "批量模式",
            "label.export_format": "导出格式",
            "label.general_threshold": "通用标签阈值",
            "label.character_threshold": "角色标签阈值",
            "label.general_mcut": "通用标签自动阈值（MCut）",
            "label.character_mcut": "角色标签自动阈值（MCut）",
            "label.tag_output": "标签输出",
            "label.structured_result": "结构化结果",
            "label.batch_result": "批量结果",
            "label.tagged_image": "带标签元数据的图像",
            "label.download_file": "下载文件",
            "accordion.connection": "连接详情",
            "accordion.translation": "翻译设置",
            "accordion.results": "结果与详情",
            "markdown.export_hint": "文件名规则在右下角原生 `settings` 中修改。默认：`${origin_filename}_tagged${origin_ext}`。",
            "placeholder.api_url": "http://your-nas:8000",
            "placeholder.translation_api_url": "http://your-translator:8001",
            "placeholder.image_url": "https://example.com/image.png",
            "placeholder.batch_urls": "多个 URL 可用逗号、分号、竖线或换行分割；URL 会由远程 API 下载处理",
            "placeholder.remote_dir": "/volume2/Project/images",
            "choice.tag": "仅返回标签文本",
            "choice.arrary": "返回标签数组",
            "choice.tagimg": "导出写回标签图像",
            "choice.original": "保留原文",
            "choice.translate_zh": "翻译为中文",
            "choice.json": "生成 JSON 结果",
            "choice.mulitagimg": "导出写回标签图像",
            "choice.inline": "仅内联结果",
            "choice.json_file": "仅 JSON 文件",
            "choice.csv_file": "仅 CSV 文件",
            "choice.both": "JSON + CSV",
        },
        "en": {
            "tab.connection": "Connection",
            "tab.single": "Single Image",
            "tab.batch": "Batch",
            "tab.upload": "Upload Image",
            "tab.url": "Image URL",
            "tab.tag_result": "Tags",
            "tab.structured": "Structured Result",
            "tab.flags": "Flagged Tags",
            "tab.flag_summary": "Flag Summary",
            "tab.export": "Exports",
            "tab.timing": "Timing Metrics",
            "tab.batch_summary": "Batch Summary",
            "button.health": "Check Remote Connection",
            "button.single": "Process Single Image",
            "button.batch": "Start Batch Processing",
            "label.api_url": "Remote API URL",
            "label.api_key": "API Key",
            "label.health_result": "Health Check Result",
            "label.image": "Input Image",
            "label.image_url": "Image URL",
            "label.batch_urls": "Batch Image URLs",
            "label.remote_dir": "Remote Directory",
            "label.return_type": "Return Type",
            "label.translation_mode": "Translation Mode",
            "label.translation_api_url": "Translation API URL",
            "label.batch_mode": "Batch Mode",
            "label.export_format": "Export Format",
            "label.general_threshold": "General Tag Threshold",
            "label.character_threshold": "Character Tag Threshold",
            "label.general_mcut": "Auto General Threshold (MCut)",
            "label.character_mcut": "Auto Character Threshold (MCut)",
            "label.tag_output": "Tag Output",
            "label.structured_result": "Structured Result",
            "label.batch_result": "Batch Result",
            "label.tagged_image": "Image with Metadata",
            "label.download_file": "Download File",
            "accordion.connection": "Connection Details",
            "accordion.translation": "Translation Settings",
            "accordion.results": "Results and Details",
            "markdown.export_hint": "Edit the filename rule in the native `settings` link at the bottom-right. Default: `${origin_filename}_tagged${origin_ext}`.",
            "placeholder.api_url": "http://your-nas:8000",
            "placeholder.translation_api_url": "http://your-translator:8001",
            "placeholder.image_url": "https://example.com/image.png",
            "placeholder.batch_urls": "Separate multiple URLs with comma, semicolon, pipe, or newline; URLs are fetched by the remote API",
            "placeholder.remote_dir": "/volume2/Project/images",
            "choice.tag": "Return tag text only",
            "choice.arrary": "Return tag array",
            "choice.tagimg": "Export image with metadata",
            "choice.original": "Keep original",
            "choice.translate_zh": "Translate to Chinese",
            "choice.json": "Generate JSON result",
            "choice.mulitagimg": "Export tagged images",
            "choice.inline": "Inline result only",
            "choice.json_file": "JSON file only",
            "choice.csv_file": "CSV file only",
            "choice.both": "JSON + CSV",
        },
    }
)

APP_CSS = """
#remote-shell {
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

#remote-shell.gradio-container {
  max-width: 1580px !important;
  padding: 16px 24px 40px !important;
  background: #0b0f15;
  color: var(--text);
  font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif !important;
}

#remote-shell .block {
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: var(--panel) !important;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.22);
}

#remote-shell .status-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(13, 18, 27, 0.94);
  padding: 12px 14px;
}

#remote-shell .tabs {
  gap: 12px;
}

#remote-shell .tabs > .tab-nav {
  padding: 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
}

#remote-shell .tabs > .tab-nav button {
  min-height: 44px;
  border-radius: 6px !important;
  padding: 0 18px;
  color: var(--muted);
  font-weight: 700;
}

#remote-shell .tabs > .tab-nav button.selected {
  background: var(--accent) !important;
  color: white !important;
  box-shadow: 0 12px 26px rgba(255, 122, 24, 0.22);
}

#remote-shell .result-tabs > .tab-nav {
  justify-content: flex-start;
}

#remote-shell .result-tabs .tabitem {
  padding-top: 14px !important;
}

#remote-shell .metric-grid,
#remote-shell .flag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

#remote-shell .metric-card,
#remote-shell .flag-card,
#remote-shell .empty-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  padding: 16px;
}

#remote-shell .metric-card h4,
#remote-shell .flag-card h4,
#remote-shell .empty-card h4 {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

#remote-shell .metric-card strong,
#remote-shell .flag-card strong {
  display: block;
  color: white;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.45;
}

#remote-shell .flag-card {
  border-color: rgba(255, 123, 123, 0.24);
  background: rgba(64, 22, 29, 0.78);
}

#remote-shell .empty-card {
  text-align: center;
  color: var(--muted);
}

#remote-shell .empty-card h4 {
  color: var(--text);
  text-transform: none;
  letter-spacing: 0;
  font-size: 16px;
}

#remote-shell .status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

#remote-shell .status-pill {
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

#remote-shell .status-pill b { color: white; }
#remote-shell .status-ok { border-color: rgba(49, 196, 141, 0.28); }
#remote-shell .status-bad { border-color: rgba(255, 123, 123, 0.28); }
#remote-shell .status-warn { border-color: rgba(255, 180, 84, 0.28); }

#remote-shell .primary-action button {
  min-height: 54px;
  border-radius: 8px !important;
  border: none !important;
  background: #f56d16 !important;
  color: white !important;
  font-size: 18px !important;
  font-weight: 800 !important;
  box-shadow: 0 18px 38px rgba(255, 122, 24, 0.24);
}

#remote-shell .secondary-action button {
  min-height: 46px;
  border-radius: 14px !important;
}

#remote-shell .gr-json,
#remote-shell textarea {
  min-height: 250px !important;
}

#remote-shell .results-file {
  min-height: 160px;
}

#remote-input-image {
  max-height: 460px;
  overflow: hidden;
}

#remote-input-image .image-container,
#remote-input-image .image-frame,
#remote-input-image img,
#remote-input-image canvas {
  max-height: 390px !important;
  object-fit: contain !important;
}

#remote-back-to-top {
  position: fixed;
  right: 24px;
  z-index: 1000;
  height: 44px;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  filter: drop-shadow(0 18px 28px rgba(0, 0, 0, 0.42));
}

#remote-back-to-top {
  bottom: 24px;
  width: 44px;
  min-width: 44px !important;
}

#remote-back-to-top button {
  width: 44px;
  min-width: 44px !important;
  height: 44px;
  padding: 0 !important;
  border-radius: 50% !important;
  border: 1px solid var(--border) !important;
  background: #f56d16 !important;
  color: white !important;
  font-size: 22px !important;
  box-shadow:
    0 18px 38px rgba(0, 0, 0, 0.46),
    0 8px 18px rgba(245, 109, 22, 0.34) !important;
}

#remote-output-settings-state {
  display: none !important;
}

.wd-settings-panel {
  border: 1px solid rgba(130, 148, 176, 0.22);
  border-radius: 12px;
  margin: 12px 0;
  padding: 16px;
  background: rgba(255, 255, 255, 0.04);
}

.wd-settings-panel h2 {
  margin: 0 0 10px;
  font-size: 18px;
}

.wd-settings-panel p {
  margin: 0 0 12px;
  color: var(--body-text-color-subdued, #99abc6);
  line-height: 1.55;
}

.wd-settings-panel label {
  display: block;
  margin: 10px 0 6px;
  font-weight: 700;
}

.wd-settings-panel select,
.wd-settings-panel input {
  width: 100%;
  min-height: 38px;
  border: 1px solid rgba(130, 148, 176, 0.32);
  border-radius: 8px;
  padding: 8px 10px;
  color: var(--body-text-color, #eef4ff);
  background: var(--input-background-fill, rgba(255, 255, 255, 0.06));
}

.wd-settings-panel button {
  margin-top: 12px;
  min-height: 38px;
  border: 0;
  border-radius: 8px;
  padding: 0 14px;
  background: #f56d16;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}

.wd-settings-panel .wd-settings-status {
  display: inline-block;
  margin-left: 10px;
  color: var(--body-text-color-subdued, #99abc6);
  font-size: 13px;
}

@media (max-width: 768px) {
  #remote-shell.gradio-container { padding: 10px 10px 72px !important; }
  #remote-input-image { max-height: 360px; }
  #remote-input-image .image-container,
  #remote-input-image .image-frame,
  #remote-input-image img,
  #remote-input-image canvas { max-height: 290px !important; }
  #remote-back-to-top { right: 14px; bottom: 14px; }
}
"""


def build_settings_injection_js(scope: str) -> str:
    storage_key = f"wd_tagger_{scope}_output_filename_template"
    textbox_selector = f"#{scope}-output-filename-template textarea, #{scope}-output-filename-template input"
    payload = {
        "storageKey": storage_key,
        "textboxSelector": textbox_selector,
        "defaultTemplate": DEFAULT_OUTPUT_FILENAME_TEMPLATE,
        "presets": OUTPUT_TEMPLATE_PRESETS,
        "zh": {
            "title": "导出文件名规则",
            "description": "这里会同步到图像导出、JSON/CSV、ZIP 打包文件名。默认 ${origin_filename}_tagged${origin_ext}，.xxx 会按导出类型自动替换。",
            "preset": "文件名模板预设",
            "custom": "自定义文件名模板",
            "help": "可用变量：${origin_filename}, ${origin_basename}, ${origin_ext}, ${type}, ${index}, ${date}, ${time}, ${timestamp}",
            "save": "保存导出规则",
            "saved": "已保存",
        },
        "en": {
            "title": "Export Filename Rule",
            "description": "This is used for tagged images, JSON/CSV files, and ZIP archives. Default is ${origin_filename}_tagged${origin_ext}; the extension is replaced for each export type.",
            "preset": "Filename Template Preset",
            "custom": "Custom Filename Template",
            "help": "Variables: ${origin_filename}, ${origin_basename}, ${origin_ext}, ${type}, ${index}, ${date}, ${time}, ${timestamp}",
            "save": "Save Export Rule",
            "saved": "Saved",
        },
    }
    config = json.dumps(payload, ensure_ascii=False)
    return f"""
(() => {{
  const config = {config};

  function currentLocale() {{
    const settingsText = Array.from(document.querySelectorAll("h2, label, button"))
      .map((node) => node.textContent || "")
      .join(" ");
    if (/设置|语言|显示主题/.test(settingsText)) return "zh";
    if ((navigator.language || "").toLowerCase().startsWith("zh")) return "zh";
    return "en";
  }}

  function setNativeValue(element, value) {{
    if (!element) return;
    const proto = element.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(element, value);
    else element.value = value;
    element.dispatchEvent(new Event("input", {{ bubbles: true }}));
    element.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}

  function syncHiddenTextbox(value) {{
    const textbox = document.querySelector(config.textboxSelector);
    setNativeValue(textbox, value || config.defaultTemplate);
  }}

  function getStoredTemplate() {{
    return localStorage.getItem(config.storageKey) || config.defaultTemplate;
  }}

  function findSettingsRoot() {{
    const banner = document.querySelector(".banner-wrap");
    return banner?.parentElement || null;
  }}

  function renderPanel(panel) {{
    const locale = currentLocale();
    const t = config[locale] || config.zh;
    const current = getStoredTemplate();
    if (panel.dataset.rendered === "1" && panel.dataset.locale === locale) {{
      syncHiddenTextbox(current);
      return;
    }}
    panel.dataset.rendered = "1";
    panel.dataset.locale = locale;
    panel.innerHTML = `
      <h2>${{t.title}}</h2>
      <p>${{t.description}}</p>
      <label for="${{config.storageKey}}-preset">${{t.preset}}</label>
      <select id="${{config.storageKey}}-preset">
        ${{config.presets.map((item) => `<option value="${{item.value.replaceAll('"', "&quot;")}}">${{locale === "zh" ? item.label_zh : item.label_en}}</option>`).join("")}}
      </select>
      <label for="${{config.storageKey}}-input">${{t.custom}}</label>
      <input id="${{config.storageKey}}-input" value="${{current.replaceAll('"', "&quot;")}}" />
      <p>${{t.help}}</p>
      <button type="button" id="${{config.storageKey}}-save">${{t.save}}</button>
      <span class="wd-settings-status" id="${{config.storageKey}}-status"></span>
    `;
    const preset = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-preset`);
    const input = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-input`);
    const save = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-save`);
    const status = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-status`);
    const matched = config.presets.find((item) => item.value === current);
    preset.value = matched ? matched.value : "";
    preset.addEventListener("change", () => {{
      input.value = preset.value || config.defaultTemplate;
    }});
    save.addEventListener("click", () => {{
      const value = input.value.trim() || config.defaultTemplate;
      localStorage.setItem(config.storageKey, value);
      syncHiddenTextbox(value);
      status.textContent = t.saved;
      window.setTimeout(() => (status.textContent = ""), 1600);
    }});
    syncHiddenTextbox(current);
  }}

  function inject() {{
    const root = findSettingsRoot();
    if (!root) return;
    let panel = root.querySelector(".wd-settings-panel[data-scope='{scope}']");
    if (!panel) {{
      panel = document.createElement("div");
      panel.className = "wd-settings-panel";
      panel.dataset.scope = "{scope}";
      const firstBanner = root.querySelector(".banner-wrap");
      root.insertBefore(panel, firstBanner?.nextSibling || root.firstChild);
    }}
    renderPanel(panel);
  }}

  syncHiddenTextbox(getStoredTemplate());
  const observer = new MutationObserver(() => inject());
  observer.observe(document.body, {{ childList: true, subtree: true }});
  window.setInterval(inject, 800);
}})();
"""


APP_JS = build_settings_injection_js("remote")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remote Gradio client for WD Tagger NAS API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
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
        return render_empty_card("等待结果", "这里会显示推理耗时、资源占用和连接相关指标。")
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


def render_timing_html(timing: dict[str, Any] | None) -> str:
    if not timing:
        return render_empty_card("暂无耗时数据", "请求完成后，这里会显示前端耗时和后端处理耗时。")
    localized = {
        "后端处理耗时 (ms)": timing.get("backend_process_ms"),
        "后端总耗时 (ms)": timing.get("backend_total_ms"),
        "前端请求总耗时 (ms)": timing.get("client_total_ms"),
    }
    return render_metrics_html(localized)


def render_flagged_html(payload: dict[str, Any] | list[Any] | str | None) -> str:
    _, summary = build_flagged_summary(payload)
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
        return render_empty_card("暂无风险摘要", "批量处理后，这里会汇总命中风险标签的文件。")

    cards: list[str] = ["<div class='flag-grid'>"]
    flagged_count = 0
    for item in items:
        _, summary = build_flagged_summary(item)
        flagged_tags = list(summary.get("flagged_tags", []))
        flagged_ratings = dict(summary.get("flagged_ratings", {}))
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
        return render_empty_card("未发现明显风险标签", "当前批量结果没有命中需要特别提醒的文件。")
    return "".join(cards)


def apply_template_preset(value: str) -> str:
    return value or DEFAULT_OUTPUT_FILENAME_TEMPLATE


def render_health_html(payload: dict[str, Any] | None) -> str:
    if not payload:
        return render_empty_card("等待检测", "点击连接检测后，这里会显示远程 API 状态。")
    if payload.get("error"):
        return (
            "<div class='status-strip'>"
            f"<span class='status-pill status-bad'><b>连接失败</b>{escape(str(payload.get('error')))}</span>"
            "</div>"
        )
    pills = [
        "<span class='status-pill status-ok'><b>状态</b>连接正常</span>",
        f"<span class='status-pill'><b>Repo</b>{escape(str(payload.get('repo_id') or '-'))}</span>",
        f"<span class='status-pill'><b>Provider</b>{escape(', '.join(str(item) for item in payload.get('providers', [])) or '-')}</span>",
        f"<span class='status-pill'><b>鉴权</b>{'已开启' if payload.get('auth_enabled') else '未开启'}</span>",
    ]
    return "<div class='status-strip'>" + "".join(pills) + "</div>"


@dataclass(frozen=True)
class RemoteResponse:
    content_type: str
    filename: str | None
    body: str | bytes | dict | list
    backend_process_ms: float | None
    backend_total_ms: float | None
    client_total_ms: float
    metrics: dict[str, Any] | None


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
    def _parse_metrics(response: httpx.Response) -> dict[str, Any] | None:
        metrics = {
            "process_current_rss_mb": response.headers.get("X-WD-Process-Current-Rss-Mb"),
            "process_peak_rss_mb": response.headers.get("X-WD-Process-Peak-Rss-Mb"),
            "cpu_user_time_s": response.headers.get("X-WD-Process-Cpu-User-Time-S"),
            "cpu_system_time_s": response.headers.get("X-WD-Process-Cpu-System-Time-S"),
        }
        if all(value is None for value in metrics.values()):
            return None
        try:
            return {
                "process_current_rss_mb": float(metrics["process_current_rss_mb"]) if metrics["process_current_rss_mb"] not in {None, "None"} else None,
                "process_peak_rss_mb": float(metrics["process_peak_rss_mb"]) if metrics["process_peak_rss_mb"] not in {None, "None"} else None,
                "cpu_user_time_s": float(metrics["cpu_user_time_s"]) if metrics["cpu_user_time_s"] not in {None, "None"} else None,
                "cpu_system_time_s": float(metrics["cpu_system_time_s"]) if metrics["cpu_system_time_s"] not in {None, "None"} else None,
            }
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
        metrics = self._parse_metrics(response)

        if "application/json" in content_type:
            body: str | bytes | dict | list = response.json()
        elif content_type.startswith("text/plain"):
            body = response.text
        else:
            body = response.content

        return RemoteResponse(
            content_type=content_type,
            filename=filename,
            body=body,
            backend_process_ms=backend_process_ms,
            backend_total_ms=backend_total_ms,
            client_total_ms=client_total_ms,
            metrics=metrics,
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
            try:
                detail: Any = exc.response.json()
            except Exception:
                detail = exc.response.text
            return {"error": f"Remote API returned HTTP {exc.response.status_code}", "detail": detail}
        return {"error": str(exc)}

    def process_single(
        self,
        base_url: str,
        api_key: str,
        translation_mode: str,
        translation_api_url: str,
        image_path: str | None,
        image_url: str,
        process_type: str,
        output_filename_template: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, dict | list | None, str, str, str | None, str, str]:
        if not image_path and not image_url.strip():
            empty = render_empty_card("等待结果", "选择图像后再开始处理。")
            return "请先提供一张图像或 URL。", None, empty, empty, None, empty, empty

        request_data = {
            "general_threshold": str(general_threshold),
            "general_mcut": str(general_mcut).lower(),
            "character_threshold": str(character_threshold),
            "character_mcut": str(character_mcut).lower(),
            "output_filename_template": output_filename_template or DEFAULT_OUTPUT_FILENAME_TEMPLATE,
            "translation_mode": translation_mode,
            "translation_api_url": translation_api_url.strip(),
        }
        upload = None
        fallback_name = "url_image_tagged.png"
        if image_path:
            path = Path(image_path)
            source_bytes = path.read_bytes()
            fallback_name = f"{path.stem}_tagged{path.suffix or '.png'}"
            upload = [("image", (path.name, source_bytes, f"image/{path.suffix.lower().lstrip('.') or 'png'}"))]
        else:
            request_data["image_url"] = image_url.strip()
        try:
            remote = self._request(
                base_url=base_url,
                api_key=api_key,
                data={**request_data, "type": process_type},
                files=upload,
            )
            tagged_response = remote
            if process_type != "tagimg":
                tagged_response = self._request(
                    base_url=base_url,
                    api_key=api_key,
                    data={**request_data, "type": "tagimg"},
                    files=upload,
                )
            if not isinstance(tagged_response.body, bytes):
                raise ValueError("Remote API did not return a tagged image file.")
            output_path = self._save_binary(
                "tagimg",
                tagged_response.filename or fallback_name,
                tagged_response.body,
            )
        except Exception as exc:
            payload = self._serialize_error(exc)
            empty = render_empty_card("请求失败", "请检查远程地址、API Key 或远程服务状态。")
            return "", payload, empty, empty, None, empty, empty

        timing = self._build_timing_summary(remote.backend_process_ms, remote.backend_total_ms, remote.client_total_ms)
        metrics_html = render_metrics_html(localize_metrics(remote.metrics))
        timing_html = render_timing_html(timing)

        if process_type == "tag":
            flagged_html = render_flagged_html(str(remote.body))
            return str(remote.body), {"caption": remote.body}, render_empty_card("处理完成", "标签文本和带标签元数据的图像均已生成。"), flagged_html, output_path, timing_html, metrics_html
        if process_type == "arrary":
            flagged_html = render_flagged_html(remote.body if isinstance(remote.body, list) else [])
            return "", remote.body if isinstance(remote.body, list) else [], render_empty_card("处理完成", "标签数组和带标签元数据的图像均已生成。"), flagged_html, output_path, timing_html, metrics_html
        if isinstance(remote.body, bytes):
            payload = {
                "saved_file": output_path,
                "remote_content_type": remote.content_type,
                "timing": timing,
                "metrics": remote.metrics,
            }
            return "", payload, render_empty_card("文件模式", "结果已写入本地文件，可在导出页签下载。"), render_empty_card("文件模式", "此模式主要返回写回标签后的图像文件。"), output_path, timing_html, metrics_html

        payload = remote.body if isinstance(remote.body, dict) else {"error": "Unexpected response"}
        flagged_html = render_flagged_html(payload)
        return "", payload, render_empty_card("结构化结果", "此模式返回结构化内容，请查看 JSON 页签。"), flagged_html, None, timing_html, metrics_html

    def process_batch(
        self,
        base_url: str,
        api_key: str,
        translation_mode: str,
        translation_api_url: str,
        files: list[str] | None,
        image_urls: str,
        input_dir: str,
        process_type: str,
        export_format: str,
        output_filename_template: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[dict | list, str, str, str | None, str, str]:
        uploads: list[tuple[str, tuple[str, bytes, str]]] = []
        for file_path in files or []:
            path = Path(file_path)
            uploads.append(("images", (path.name, path.read_bytes(), f"image/{path.suffix.lower().lstrip('.') or 'png'}")))

        try:
            remote = self._request(
                base_url=base_url,
                api_key=api_key,
                data={
                    "type": process_type,
                    "input_dir": input_dir.strip(),
                    "image_urls": image_urls.strip(),
                    "export_format": export_format,
                    "output_filename_template": output_filename_template or DEFAULT_OUTPUT_FILENAME_TEMPLATE,
                    "general_threshold": str(general_threshold),
                    "general_mcut": str(general_mcut).lower(),
                    "character_threshold": str(character_threshold),
                    "character_mcut": str(character_mcut).lower(),
                    "translation_mode": translation_mode,
                    "translation_api_url": translation_api_url.strip(),
                },
                files=uploads or None,
            )
        except Exception as exc:
            payload = self._serialize_error(exc)
            empty = render_empty_card("请求失败", "请检查远程地址、API Key 或远程服务状态。")
            return payload, empty, empty, None, empty, empty

        timing = self._build_timing_summary(remote.backend_process_ms, remote.backend_total_ms, remote.client_total_ms)
        timing_html = render_timing_html(timing)
        metrics_html = render_metrics_html(localize_metrics(remote.metrics))

        if isinstance(remote.body, dict):
            payload = {**remote.body, "timing": timing, "metrics": remote.metrics}
            items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
            return payload, render_metrics_html({
                "总文件数": len(items),
                "成功处理": sum(1 for item in items if isinstance(item, dict) and item.get("ok", True)),
                "批量模式": process_type,
            }), render_batch_flagged_html(items), None, timing_html, metrics_html

        if isinstance(remote.body, list):
            payload = {"items": remote.body, "timing": timing}
            return payload, render_empty_card("列表结果", "请查看 JSON 页签了解详细条目。"), render_empty_card("暂无风险摘要", "当前返回的是列表结构。"), None, timing_html, metrics_html

        if isinstance(remote.body, bytes):
            prefix = "json" if process_type == "json" else "mulitagimg"
            fallback_name = "results_bundle.zip" if process_type == "json" else "tagged_images.zip"
            output_path = self._save_binary(prefix, remote.filename or fallback_name, remote.body)
            payload = {
                "type": process_type,
                "saved_file": output_path,
                "remote_content_type": remote.content_type,
                "timing": timing,
                "metrics": remote.metrics,
            }
            return payload, render_empty_card("文件已生成", "批量结果已经保存到本地导出目录。"), render_empty_card("导出模式", "此模式主要返回下载文件。"), output_path, timing_html, metrics_html

        payload = {"error": "Unexpected response from remote API."}
        empty = render_empty_card("结果异常", "远程接口返回了未预期的内容。")
        return payload, empty, empty, None, timing_html, metrics_html

    def health(self, base_url: str, api_key: str) -> tuple[dict[str, Any], str]:
        normalized_base = self._normalize_base_url(base_url)
        if not normalized_base:
            payload = {"error": "Please provide the remote API base URL."}
            return payload, render_health_html(payload)

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(f"{normalized_base}/health", headers=self._headers(api_key))
                response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            payload = self._serialize_error(exc)
        return payload, render_health_html(payload)


def build_ui() -> gr.Blocks:
    client = RemoteClient()
    t = APP_I18N

    with gr.Blocks(title="WaifuDiffusion Tagger Remote Client", elem_id="remote-shell") as demo:
        with gr.Tabs() as main_tabs:
            with gr.Tab(t("tab.connection")):
                with gr.Row():
                    with gr.Column(scale=11, min_width=520):
                        api_base_url = gr.Textbox(value=DEFAULT_REMOTE_API_URL, label=t("label.api_url"), placeholder=t("placeholder.api_url"))
                        api_key = gr.Textbox(value=DEFAULT_REMOTE_API_KEY, label=t("label.api_key"), type="password")
                        health_button = gr.Button(t("button.health"), variant="primary", elem_classes=["primary-action"])
                    with gr.Column(scale=9, min_width=420):
                        with gr.Accordion(t("accordion.connection"), open=False):
                            health_status = gr.HTML(value=render_empty_card("等待检测", "点击连接检测后，这里会显示远程 API 状态。"))
                            health_output = gr.JSON(label=t("label.health_result"))
                        with gr.Accordion(t("accordion.translation"), open=False):
                            translation_mode = gr.Radio(
                                choices=[
                                    (t("choice.original"), "original"),
                                    (t("choice.translate_zh"), "zh"),
                                ],
                                value=DEFAULT_TRANSLATION_MODE,
                                label=t("label.translation_mode"),
                            )
                            translation_api_url = gr.Textbox(
                                value=DEFAULT_TRANSLATION_API_URL,
                                label=t("label.translation_api_url"),
                                placeholder=t("placeholder.translation_api_url"),
                            )

            with gr.Tab(t("tab.single")):
                with gr.Row():
                    with gr.Column(scale=11, min_width=500):
                        submit_single = gr.Button(t("button.single"), variant="primary", elem_classes=["primary-action"])
                        with gr.Tabs(elem_classes=["result-tabs"]):
                            with gr.Tab(t("tab.upload")):
                                image = gr.Image(
                                    type="filepath",
                                    label=t("label.image"),
                                    height=390,
                                    elem_id="remote-input-image",
                                )
                            with gr.Tab(t("tab.url")):
                                single_image_url = gr.Textbox(
                                    label=t("label.image_url"),
                                    placeholder=t("placeholder.image_url"),
                                    lines=3,
                                )
                        process_type_single = gr.Dropdown(
                            choices=[
                                (t("choice.tag"), "tag"),
                                (t("choice.arrary"), "arrary"),
                                (t("choice.tagimg"), "tagimg"),
                            ],
                            value="tag",
                            label=t("label.return_type"),
                        )
                        with gr.Row():
                            general_threshold = gr.Slider(0, 1, value=DEFAULT_GENERAL_THRESHOLD, step=0.05, label=t("label.general_threshold"))
                            character_threshold = gr.Slider(0, 1, value=DEFAULT_CHARACTER_THRESHOLD, step=0.05, label=t("label.character_threshold"))
                        with gr.Row():
                            general_mcut = gr.Checkbox(label=t("label.general_mcut"))
                            character_mcut = gr.Checkbox(label=t("label.character_mcut"))
                    with gr.Column(scale=9, min_width=420):
                        with gr.Accordion(t("accordion.results"), open=False) as single_results:
                            with gr.Tabs(elem_classes=["result-tabs"]):
                                with gr.Tab(t("tab.tag_result")):
                                    single_text = gr.Textbox(label=t("label.tag_output"), lines=5, max_lines=10)
                                    single_summary = gr.HTML(value=render_empty_card("等待结果", "处理完成后，这里会显示当前模式的结果说明。"))
                                with gr.Tab(t("tab.structured")):
                                    single_json = gr.JSON(label=t("label.structured_result"))
                                with gr.Tab(t("tab.flags")):
                                    single_flagged = gr.HTML(value=render_empty_card("暂无风险提示", "执行后这里会显示敏感标签和评分。"))
                                with gr.Tab(t("tab.export")):
                                    gr.Markdown(t("markdown.export_hint"))
                                    single_file = gr.File(label=t("label.tagged_image"), elem_classes=["results-file"])
                                with gr.Tab(t("tab.timing")):
                                    single_timing = gr.HTML(value=render_empty_card("暂无耗时数据", "请求完成后，这里会显示前端和后端耗时。"))
                                    single_metrics = gr.HTML(value=render_empty_card("暂无资源指标", "请求完成后，这里会显示远端返回的资源指标。"))

            with gr.Tab(t("tab.batch")):
                with gr.Row():
                    with gr.Column(scale=11, min_width=500):
                        with gr.Tabs(elem_classes=["result-tabs"]):
                            with gr.Tab(t("tab.upload")):
                                batch_files = gr.File(file_count="multiple", file_types=["image"], type="filepath", label=t("label.image"))
                            with gr.Tab(t("tab.url")):
                                batch_image_urls = gr.Textbox(
                                    label=t("label.batch_urls"),
                                    placeholder=t("placeholder.batch_urls"),
                                    lines=5,
                                )
                        input_dir = gr.Textbox(label=t("label.remote_dir"), placeholder=t("placeholder.remote_dir"))
                        process_type_batch = gr.Dropdown(
                            choices=[(t("choice.json"), "json"), (t("choice.mulitagimg"), "mulitagimg")],
                            value="json",
                            label=t("label.batch_mode"),
                        )
                        export_format = gr.Dropdown(
                            choices=[(t("choice.inline"), "inline"), (t("choice.json_file"), "json"), (t("choice.csv_file"), "csv"), (t("choice.both"), "both")],
                            value="both",
                            label=t("label.export_format"),
                        )
                        with gr.Row():
                            batch_general_threshold = gr.Slider(0, 1, value=DEFAULT_GENERAL_THRESHOLD, step=0.05, label=t("label.general_threshold"))
                            batch_character_threshold = gr.Slider(0, 1, value=DEFAULT_CHARACTER_THRESHOLD, step=0.05, label=t("label.character_threshold"))
                        with gr.Row():
                            batch_general_mcut = gr.Checkbox(label=t("label.general_mcut"))
                            batch_character_mcut = gr.Checkbox(label=t("label.character_mcut"))
                        submit_batch = gr.Button(t("button.batch"), variant="primary", elem_classes=["primary-action"])

                    with gr.Column(scale=9, min_width=420):
                        with gr.Accordion(t("accordion.results"), open=False) as batch_results:
                            with gr.Tabs(elem_classes=["result-tabs"]):
                                with gr.Tab(t("tab.batch_summary")):
                                    batch_summary = gr.HTML(value=render_empty_card("等待批量结果", "执行批量处理后，这里会显示处理摘要。"))
                                with gr.Tab(t("tab.structured")):
                                    batch_json = gr.JSON(label=t("label.batch_result"))
                                with gr.Tab(t("tab.flag_summary")):
                                    batch_flagged = gr.HTML(value=render_empty_card("暂无风险摘要", "批量处理后，这里会汇总命中风险标签的文件。"))
                                with gr.Tab(t("tab.export")):
                                    gr.Markdown(t("markdown.export_hint"))
                                    batch_file = gr.File(label=t("label.download_file"), elem_classes=["results-file"])
                                with gr.Tab(t("tab.timing")):
                                    batch_timing = gr.HTML(value=render_empty_card("暂无耗时数据", "请求完成后，这里会显示前端和后端耗时。"))
                                    batch_metrics = gr.HTML(value=render_empty_card("暂无资源指标", "请求完成后，这里会显示远端返回的资源指标。"))

        with gr.Group(elem_id="remote-output-settings-state"):
            output_filename_template = gr.Textbox(
                value=DEFAULT_OUTPUT_FILENAME_TEMPLATE,
                label="output filename template",
                elem_id="remote-output-filename-template",
            )

        back_to_top = gr.Button("↑", elem_id="remote-back-to-top", size="sm")

        health_button.click(
            client.health,
            inputs=[api_base_url, api_key],
            outputs=[health_output, health_status],
        )
        single_event = submit_single.click(
            client.process_single,
            inputs=[
                api_base_url,
                api_key,
                translation_mode,
                translation_api_url,
                image,
                single_image_url,
                process_type_single,
                output_filename_template,
                general_threshold,
                general_mcut,
                character_threshold,
                character_mcut,
            ],
            outputs=[single_text, single_json, single_summary, single_flagged, single_file, single_timing, single_metrics],
        )
        single_event.then(lambda: gr.Accordion(open=True), outputs=single_results, queue=False)
        batch_event = submit_batch.click(
            client.process_batch,
            inputs=[
                api_base_url,
                api_key,
                translation_mode,
                translation_api_url,
                batch_files,
                batch_image_urls,
                input_dir,
                process_type_batch,
                export_format,
                output_filename_template,
                batch_general_threshold,
                batch_general_mcut,
                batch_character_threshold,
                batch_character_mcut,
            ],
            outputs=[batch_json, batch_summary, batch_flagged, batch_file, batch_timing, batch_metrics],
        )
        batch_event.then(lambda: gr.Accordion(open=True), outputs=batch_results, queue=False)
        back_to_top.click(
            None,
            js="() => window.scrollTo({ top: 0, behavior: 'smooth' })",
            queue=False,
        )

    return demo


def main() -> None:
    args = parse_args()
    client = RemoteClient()
    print(f"[client-api] Python: {sys.executable}")
    print(f"[client-api] Output directory: {client.output_root}")
    print(f"[client-api] Default remote API: {DEFAULT_REMOTE_API_URL}")
    app = build_ui()
    app.queue(max_size=8)
    app.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        css=APP_CSS,
        js=APP_JS,
        i18n=APP_I18N,
        footer_links=["api", "gradio", "settings"],
    )


if __name__ == "__main__":
    main()
