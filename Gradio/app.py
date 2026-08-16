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

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    discover_local_model_dirs,
    get_default_onnx_providers,
)
from wd_tagger.content_flags import build_flagged_summary, extract_tags
from wd_tagger.modes import load_sources_from_dir, load_sources_from_urls, process_batch_type
from wd_tagger.service import (
    DEFAULT_OUTPUT_FILENAME_TEMPLATE,
    ImageSource,
    PredictionOptions,
    TaggerService,
    localize_metrics,
)


DEFAULT_PROVIDERS = get_default_onnx_providers()
LOCAL_MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_TRANSLATION_MODE = os.getenv("WD_TAGGER_TRANSLATION_MODE", "original").strip() or "original"
DEFAULT_TRANSLATION_API_URL = os.getenv("WD_TAGGER_TRANSLATION_API_URL", "").strip()
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
            "tab.single": "单张处理",
            "tab.batch": "批量处理",
            "tab.status": "运行状态",
            "tab.upload": "上传图片",
            "tab.url": "网络 URL",
            "tab.tag_result": "标签结果",
            "tab.structured": "结构化结果",
            "tab.flags": "风险提示",
            "tab.flag_summary": "风险摘要",
            "tab.export": "导出文件",
            "tab.metrics": "资源指标",
            "tab.batch_summary": "处理摘要",
            "button.single": "开始处理单张图像",
            "button.batch": "开始批量处理",
            "button.refresh_status": "刷新模型状态",
            "label.image": "输入图像",
            "label.image_url": "图像 URL",
            "label.batch_urls": "批量图像 URL",
            "label.input_dir": "本地目录路径",
            "label.local_model": "本地模型",
            "label.translation_mode": "翻译模式",
            "label.translation_api_url": "翻译 API 地址",
            "label.return_type": "返回类型",
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
            "label.json_file": "JSON 文件",
            "label.csv_file": "CSV 文件",
            "label.archive_file": "归档 / 导出文件",
            "accordion.results": "结果与详情",
            "accordion.translation": "翻译设置",
            "markdown.export_hint": "文件名规则在右下角原生 `settings` 中修改。默认：`${origin_filename}_tagged${origin_ext}`。",
            "placeholder.image_url": "https://example.com/image.png",
            "placeholder.translation_api_url": "http://your-translator:8001",
            "placeholder.batch_urls": "多个 URL 可用逗号、分号、竖线或换行分割",
            "placeholder.input_dir": r"E:\images",
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
            "tab.single": "Single Image",
            "tab.batch": "Batch",
            "tab.status": "Runtime Status",
            "tab.upload": "Upload Image",
            "tab.url": "Image URL",
            "tab.tag_result": "Tags",
            "tab.structured": "Structured Result",
            "tab.flags": "Flagged Tags",
            "tab.flag_summary": "Flag Summary",
            "tab.export": "Exports",
            "tab.metrics": "Resource Metrics",
            "tab.batch_summary": "Batch Summary",
            "button.single": "Process Single Image",
            "button.batch": "Start Batch Processing",
            "button.refresh_status": "Refresh Model Status",
            "label.image": "Input Image",
            "label.image_url": "Image URL",
            "label.batch_urls": "Batch Image URLs",
            "label.input_dir": "Local Directory",
            "label.local_model": "Local Model",
            "label.translation_mode": "Translation Mode",
            "label.translation_api_url": "Translation API URL",
            "label.return_type": "Return Type",
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
            "label.json_file": "JSON File",
            "label.csv_file": "CSV File",
            "label.archive_file": "Archive / Export File",
            "accordion.results": "Results and Details",
            "accordion.translation": "Translation Settings",
            "markdown.export_hint": "Edit the filename rule in the native `settings` link at the bottom-right. Default: `${origin_filename}_tagged${origin_ext}`.",
            "placeholder.image_url": "https://example.com/image.png",
            "placeholder.translation_api_url": "http://your-translator:8001",
            "placeholder.batch_urls": "Separate multiple URLs with comma, semicolon, pipe, or newline",
            "placeholder.input_dir": r"E:\images",
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

#local-input-image {
  max-height: 460px;
  overflow: hidden;
}

#local-input-image .image-container,
#local-input-image .image-frame,
#local-input-image img,
#local-input-image canvas {
  max-height: 390px !important;
  object-fit: contain !important;
}

#local-back-to-top {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1000;
  width: 56px;
  height: 56px;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  filter: none !important;
  cursor: pointer;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

#local-back-to-top:hover {
  transform: scale(1.12);
}

#local-back-to-top button {
  width: 56px;
  height: 56px;
  padding: 0 !important;
  border-radius: 50% !important;
  border: none !important;
  background: linear-gradient(135deg, #f56d16, #ff8a3c) !important;
  color: white !important;
  font-size: 20px !important;
  font-weight: 600 !important;
  box-shadow:
    0 0 0 4px rgba(245, 109, 22, 0.15),
    0 8px 32px rgba(245, 109, 22, 0.4),
    0 4px 16px rgba(0, 0, 0, 0.1) !important;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  line-height: 1;
  position: relative;
}

#local-back-to-top button::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(245, 109, 22, 0.2), rgba(255, 138, 60, 0.05));
  filter: blur(12px);
  z-index: -1;
  animation: pulse-glow 2s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.08); }
}

#local-back-to-top button:hover {
  transform: translateY(-2px);
  box-shadow:
    0 0 0 6px rgba(245, 109, 22, 0.2),
    0 12px 40px rgba(245, 109, 22, 0.5),
    0 6px 20px rgba(0, 0, 0, 0.15) !important;
}

#local-back-to-top button:active {
  transform: scale(0.92);
}

#local-back-to-top .arrow {
  display: block;
  font-size: 18px;
  line-height: 1;
  margin-top: -2px;
}

#local-back-to-top .label {
  display: block;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  line-height: 1;
  margin-top: 1px;
}

#local-output-settings-state {
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
  #local-shell.gradio-container { padding: 10px 10px 72px !important; }
  #local-input-image { max-height: 360px; }
  #local-input-image .image-container,
  #local-input-image .image-frame,
  #local-input-image img,
  #local-input-image canvas { max-height: 290px !important; }
  #local-back-to-top { right: 14px; bottom: 14px; }
}
"""


def build_settings_injection_js(scope: str) -> str:
    storage_key = f"wd_tagger_{scope}_output_filename_template"
    translation_storage_key = f"wd_tagger_{scope}_translation_api_url"
    textbox_selector = f"#{scope}-output-filename-template textarea, #{scope}-output-filename-template input"
    translation_selector = f"#{scope}-translation-api-url textarea, #{scope}-translation-api-url input"
    payload = {
        "storageKey": storage_key,
        "translationStorageKey": translation_storage_key,
        "textboxSelector": textbox_selector,
        "translationSelector": translation_selector,
        "defaultTemplate": DEFAULT_OUTPUT_FILENAME_TEMPLATE,
        "defaultTranslationApiUrl": DEFAULT_TRANSLATION_API_URL,
        "presets": OUTPUT_TEMPLATE_PRESETS,
        "zh": {
            "title": "导出文件名规则",
            "description": "这里会同步到图像导出、JSON/CSV、ZIP 打包文件名。默认 ${origin_filename}_tagged${origin_ext}，.xxx 会按导出类型自动替换。",
            "preset": "文件名模板预设",
            "custom": "自定义文件名模板",
            "help": "可用变量：${origin_filename}, ${origin_basename}, ${origin_ext}, ${type}, ${index}, ${date}, ${time}, ${timestamp}",
            "save": "保存导出规则",
            "saved": "已保存",
            "translationTitle": "翻译 API 设置",
            "translationDescription": "这里会同步到翻译请求使用的 API 地址。留空时会自动回退为原文。",
            "translationLabel": "翻译 API 地址",
            "translationPlaceholder": "http://your-translator:8001",
            "translationHelp": "建议填写翻译服务的 Base URL，保存后会同步到主界面设置。",
            "translationSave": "保存翻译设置",
        },
        "en": {
            "title": "Export Filename Rule",
            "description": "This is used for tagged images, JSON/CSV files, and ZIP archives. Default is ${origin_filename}_tagged${origin_ext}; the extension is replaced for each export type.",
            "preset": "Filename Template Preset",
            "custom": "Custom Filename Template",
            "help": "Variables: ${origin_filename}, ${origin_basename}, ${origin_ext}, ${type}, ${index}, ${date}, ${time}, ${timestamp}",
            "save": "Save Export Rule",
            "saved": "Saved",
            "translationTitle": "Translation API Settings",
            "translationDescription": "This value is used for translation requests. Leave it empty to keep the original text.",
            "translationLabel": "Translation API URL",
            "translationPlaceholder": "http://your-translator:8001",
            "translationHelp": "Set the translation service base URL here; it will sync back to the main page input.",
            "translationSave": "Save Translation Setting",
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

  function syncTranslationTextbox(value) {{
    const textbox = document.querySelector(config.translationSelector);
    setNativeValue(textbox, value || config.defaultTranslationApiUrl || "");
  }}

  function getStoredTemplate() {{
    return localStorage.getItem(config.storageKey) || config.defaultTemplate;
  }}

  function getStoredTranslationUrl() {{
    return localStorage.getItem(config.translationStorageKey) || config.defaultTranslationApiUrl || "";
  }}

  function findSettingsRoot() {{
    const banner = document.querySelector(".banner-wrap");
    return banner?.parentElement || null;
  }}

  function renderPanel(panel) {{
    const locale = currentLocale();
    const t = config[locale] || config.zh;
    const current = getStoredTemplate();
    const currentTranslation = getStoredTranslationUrl();
    if (panel.dataset.rendered === "1" && panel.dataset.locale === locale) {{
      syncHiddenTextbox(current);
      syncTranslationTextbox(currentTranslation);
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
      <h2 style="margin-top: 22px;">${{t.translationTitle}}</h2>
      <p>${{t.translationDescription}}</p>
      <label for="${{config.translationStorageKey}}-input">${{t.translationLabel}}</label>
      <input id="${{config.translationStorageKey}}-input" value="${{currentTranslation.replaceAll('"', "&quot;")}}" placeholder="${{t.translationPlaceholder}}" />
      <p>${{t.translationHelp}}</p>
      <button type="button" id="${{config.translationStorageKey}}-save">${{t.translationSave}}</button>
      <span class="wd-settings-status" id="${{config.translationStorageKey}}-status"></span>
    `;
    const preset = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-preset`);
    const input = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-input`);
    const save = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-save`);
    const status = panel.querySelector(`#${{CSS.escape(config.storageKey)}}-status`);
    const translationInput = panel.querySelector(`#${{CSS.escape(config.translationStorageKey)}}-input`);
    const translationSave = panel.querySelector(`#${{CSS.escape(config.translationStorageKey)}}-save`);
    const translationStatus = panel.querySelector(`#${{CSS.escape(config.translationStorageKey)}}-status`);
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
    translationSave.addEventListener("click", () => {{
      const value = translationInput.value.trim() || "";
      localStorage.setItem(config.translationStorageKey, value);
      syncTranslationTextbox(value);
      translationStatus.textContent = t.saved;
      window.setTimeout(() => (translationStatus.textContent = ""), 1600);
    }});
    syncTranslationTextbox(currentTranslation);
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


APP_JS = build_settings_injection_js("local")


def discover_local_models() -> list[tuple[str, str]]:
    return [
        (model_dir.name, str(model_dir))
        for model_dir in discover_local_model_dirs(project_root=PROJECT_ROOT)
    ]


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


def apply_template_preset(value: str) -> str:
    return value or DEFAULT_OUTPUT_FILENAME_TEMPLATE


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
        translation_mode: str,
        translation_api_url: str,
    ) -> PredictionOptions:
        return PredictionOptions(
            model_dir=model_dir or self.local_model_dir,
            general_threshold=general_threshold,
            character_threshold=character_threshold,
            general_mcut=general_mcut,
            character_mcut=character_mcut,
            translation_mode=translation_mode,
            translation_api_url=translation_api_url.strip(),
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
                    translation_mode=DEFAULT_TRANSLATION_MODE,
                    translation_api_url=DEFAULT_TRANSLATION_API_URL,
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
        image: str | Image.Image | None,
        image_url: str,
        model_dir: str,
        translation_mode: str,
        translation_api_url: str,
        process_type: str,
        output_filename_template: str,
        general_threshold: float,
        general_mcut: bool,
        character_threshold: float,
        character_mcut: bool,
    ) -> tuple[str, dict | list | None, str, str, str | None, str]:
        if image is None and not image_url.strip():
            return (
                "请先提供一张图像。",
                None,
                render_empty_card("等待结果", "上传图像后，这里会显示标签高亮视图。"),
                render_empty_card("暂无风险提示", "执行后这里会显示敏感标签和评分。"),
                None,
                render_empty_card("暂无指标", "执行后这里会显示推理耗时、内存和缓存信息。"),
            )

        if image is not None:
            if isinstance(image, str):
                path = Path(image)
                source = ImageSource(
                    filename=path.name,
                    image=Image.open(path).convert("RGBA"),
                    content_type=f"image/{path.suffix.lower().lstrip('.') or 'png'}",
                    source_path=str(path),
                    source_bytes=path.read_bytes(),
                )
            else:
                buffer = BytesIO()
                rgba = image.convert("RGBA")
                rgba.save(buffer, format="PNG")
                source = ImageSource(
                    filename="input.png",
                    image=rgba,
                    content_type="image/png",
                    source_bytes=buffer.getvalue(),
                )
        else:
            try:
                source = load_sources_from_urls(image_url)[0]
            except Exception as exc:
                empty = render_empty_card("URL 加载失败", str(exc))
                return "", {"error": str(exc)}, empty, empty, None, render_empty_card("暂无指标", "URL 加载失败，未执行推理。")

        payload = self.service.predict_from_source(
            source=source,
            options=self._options(
                model_dir=model_dir,
                general_threshold=general_threshold,
                general_mcut=general_mcut,
                character_threshold=character_threshold,
                character_mcut=character_mcut,
                translation_mode=translation_mode,
                translation_api_url=translation_api_url,
            ),
            providers=DEFAULT_PROVIDERS,
        )
        highlighted_html, flagged_summary = build_flagged_summary(payload)
        metrics_html = render_metrics_html(self._payload_metrics(payload))
        flagged_html = render_flagged_html(flagged_summary)
        tags = extract_tags(payload)
        output_dir = self.service.create_request_dir("gradio_single")
        output_path = self.service.write_tagged_image(output_dir, source, payload, output_filename_template)

        if process_type == "tag":
            return str(payload.get("caption", "")), payload, highlighted_html, flagged_html, str(output_path), metrics_html
        if process_type in {"arrary", "array"}:
            return ", ".join(tags), tags, highlighted_html, flagged_html, str(output_path), metrics_html

        return "", payload, highlighted_html, flagged_html, str(output_path), metrics_html

    def process_batch(
        self,
        files: list[str] | None,
        image_urls: str,
        input_dir: str,
        model_dir: str,
        translation_mode: str,
        translation_api_url: str,
        process_type: str,
        export_format: str,
        output_filename_template: str,
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
        if image_urls.strip():
            sources.extend(load_sources_from_urls(image_urls))
        if not sources:
            empty = render_empty_card("等待批量任务", "上传文件、输入 URL 或填写目录后再开始处理。")
            return {"error": "Please upload images, provide URLs, or provide an input directory."}, empty, empty, None, None, None, empty

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
                translation_mode=translation_mode,
                translation_api_url=translation_api_url,
            ),
            providers=DEFAULT_PROVIDERS,
            process_type=process_type,
            export_format=request_export_format,
            output_filename_template=output_filename_template,
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
                from wd_tagger.service import render_output_filename

                json_path = output_dir / render_output_filename(
                    output_filename_template or "${origin_filename}${origin_ext}",
                    origin_name="results.json",
                    default_ext=".json",
                    process_type="json",
                )
                json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                json_file = str(json_path)

                csv_path = output_dir / render_output_filename(
                    output_filename_template or "${origin_filename}${origin_ext}",
                    origin_name="results.csv",
                    default_ext=".csv",
                    process_type="json",
                )
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
    t = APP_I18N

    with gr.Blocks(title="Local WaifuDiffusion Tagger", elem_id="local-shell") as demo:
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
                elem_id="local-translation-api-url",
            )
        with gr.Tabs() as main_tabs:
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
                                    elem_id="local-input-image",
                                )
                            with gr.Tab(t("tab.url")):
                                single_image_url = gr.Textbox(
                                    label=t("label.image_url"),
                                    placeholder=t("placeholder.image_url"),
                                    lines=3,
                                )
                        single_model = gr.Dropdown(local_models, value=predictor.local_model_dir, label=t("label.local_model"))
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
                            single_general_threshold = gr.Slider(0, 1, value=DEFAULT_GENERAL_THRESHOLD, step=0.05, label=t("label.general_threshold"))
                            single_character_threshold = gr.Slider(0, 1, value=DEFAULT_CHARACTER_THRESHOLD, step=0.05, label=t("label.character_threshold"))
                        with gr.Row():
                            single_general_mcut = gr.Checkbox(label=t("label.general_mcut"))
                            single_character_mcut = gr.Checkbox(label=t("label.character_mcut"))
                    with gr.Column(scale=9, min_width=420):
                        with gr.Accordion(t("accordion.results"), open=False) as single_results:
                            with gr.Tabs(elem_classes=["result-tabs"]):
                                with gr.Tab(t("tab.tag_result")):
                                    single_text = gr.Textbox(label=t("label.tag_output"), lines=5, max_lines=10)
                                    single_highlight = gr.HTML(value=render_empty_card("等待结果", "处理完成后，这里会显示标签高亮视图。"))
                                with gr.Tab(t("tab.structured")):
                                    single_json = gr.JSON(label=t("label.structured_result"))
                                with gr.Tab(t("tab.flags")):
                                    single_flagged = gr.HTML(value=render_empty_card("暂无风险提示", "执行后这里会显示敏感标签和评分。"))
                                with gr.Tab(t("tab.export")):
                                    gr.Markdown(t("markdown.export_hint"))
                                    single_file = gr.File(label=t("label.tagged_image"), elem_classes=["results-file"])
                                with gr.Tab(t("tab.metrics")):
                                    single_metrics = gr.HTML(value=render_empty_card("暂无指标", "执行后这里会显示推理耗时、内存和缓存信息。"))

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
                        batch_input_dir = gr.Textbox(label=t("label.input_dir"), placeholder=t("placeholder.input_dir"))
                        batch_model = gr.Dropdown(local_models, value=predictor.local_model_dir, label=t("label.local_model"))
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
                                    batch_summary = gr.HTML(value=render_empty_card("等待批量结果", "执行批量处理后，这里会显示总数、成功数和缓存统计。"))
                                with gr.Tab(t("tab.structured")):
                                    batch_json = gr.JSON(label=t("label.batch_result"))
                                with gr.Tab(t("tab.flag_summary")):
                                    batch_flagged = gr.HTML(value=render_empty_card("暂无风险摘要", "批量任务完成后，这里会汇总命中风险标签的文件。"))
                                with gr.Tab(t("tab.export")):
                                    gr.Markdown(t("markdown.export_hint"))
                                    batch_json_file = gr.File(label=t("label.json_file"), elem_classes=["results-file"])
                                    batch_csv_file = gr.File(label=t("label.csv_file"), elem_classes=["results-file"])
                                    batch_file = gr.File(label=t("label.archive_file"), elem_classes=["results-file"])
                                with gr.Tab(t("tab.metrics")):
                                    batch_metrics = gr.HTML(value=render_empty_card("暂无指标", "批量任务完成后，这里会显示耗时、内存和缓存统计。"))

            with gr.Tab(t("tab.status")):
                with gr.Row():
                    warmup_status = gr.HTML(value=predictor.warmup_status_html(), elem_classes=["status-card"])
                    warmup_button = gr.Button(t("button.refresh_status"), variant="secondary", elem_classes=["secondary-action"])

        with gr.Group(elem_id="local-output-settings-state"):
            output_filename_template = gr.Textbox(
                value=DEFAULT_OUTPUT_FILENAME_TEMPLATE,
                label="output filename template",
                elem_id="local-output-filename-template",
            )

        back_to_top = gr.Button("↑", elem_id="local-back-to-top", size="sm")

        single_event = submit_single.click(
            predictor.process_single,
            inputs=[
                image,
                single_image_url,
                single_model,
                translation_mode,
                translation_api_url,
                process_type_single,
                output_filename_template,
                single_general_threshold,
                single_general_mcut,
                single_character_threshold,
                single_character_mcut,
            ],
            outputs=[single_text, single_json, single_highlight, single_flagged, single_file, single_metrics],
        )
        single_event.then(lambda: gr.Accordion(open=True), outputs=single_results, queue=False)
        batch_event = submit_batch.click(
            predictor.process_batch,
            inputs=[
                batch_files,
                batch_image_urls,
                batch_input_dir,
                batch_model,
                translation_mode,
                translation_api_url,
                process_type_batch,
                export_format,
                output_filename_template,
                batch_general_threshold,
                batch_general_mcut,
                batch_character_threshold,
                batch_character_mcut,
            ],
            outputs=[batch_json, batch_summary, batch_flagged, batch_json_file, batch_csv_file, batch_file, batch_metrics],
        )
        batch_event.then(lambda: gr.Accordion(open=True), outputs=batch_results, queue=False)
        back_to_top.click(
            None,
            js="() => window.scrollTo({ top: 0, behavior: 'smooth' })",
            queue=False,
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
