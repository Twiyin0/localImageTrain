(() => {
  const SETTINGS_KEY = "wd_tagger_webui_settings_v2";
  const DEFAULT_OUTPUT_TEMPLATE = "${origin_filename}_tagged${origin_ext}";
  const OUTPUT_PRESETS = [
    { label: "默认：原文件名_tagged.原后缀", value: DEFAULT_OUTPUT_TEMPLATE },
    { label: "保留原文件名", value: "${origin_filename}${origin_ext}" },
    { label: "原名_类型_序号", value: "${origin_filename}_${type}_${index}${origin_ext}" },
    { label: "原名_时间戳", value: "${origin_filename}_${timestamp}${origin_ext}" },
  ];

  const DEFAULTS = {
    outputTemplate: DEFAULT_OUTPUT_TEMPLATE,
    singleType: "tag",
    batchType: "json",
    batchExportMode: "both",
    singleLang: "zh",
    batchLang: "zh",
    singleModel: "",
    batchModel: "",
    singleGeneral: 0.35,
    singleCharacter: 0.85,
    batchGeneral: 0.35,
    batchCharacter: 0.85,
    singleGeneralMcut: false,
    singleCharacterMcut: false,
    batchGeneralMcut: false,
    batchCharacterMcut: false,
  };

  const state = {
    singleDownloads: [],
    batchDownloads: [],
    models: [],
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const flags = window.WDTagFlags;

  function loadSettings() {
    try {
      return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") || {}) };
    } catch {
      return { ...DEFAULTS };
    }
  }

  function saveSettings(settings = collectSettings()) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }

  function syncPresetSelect(value) {
    const select = $("#outputPreset");
    select.innerHTML = OUTPUT_PRESETS.map((preset) => (
      `<option value="${flags.escapeHtml(preset.value)}">${flags.escapeHtml(preset.label)}</option>`
    )).join("");
    select.value = OUTPUT_PRESETS.find((item) => item.value === value)?.value || "";
  }

  function setValue(selector, value) {
    const element = $(selector);
    if (element) element.value = value;
  }

  function setChecked(selector, value) {
    const element = $(selector);
    if (element) element.checked = Boolean(value);
  }

  function applySettingsToForm(settings) {
    setValue("#outputTemplate", settings.outputTemplate);
    setValue("#singleType", settings.singleType);
    setValue("#batchType", settings.batchType);
    setValue("#batchExportMode", settings.batchExportMode);
    setValue("#singleLang", settings.singleLang);
    setValue("#batchLang", settings.batchLang);
    setValue("#singleModel", settings.singleModel);
    setValue("#batchModel", settings.batchModel);
    setValue("#singleGeneral", settings.singleGeneral);
    setValue("#singleCharacter", settings.singleCharacter);
    setValue("#batchGeneral", settings.batchGeneral);
    setValue("#batchCharacter", settings.batchCharacter);
    setChecked("#singleGeneralMcut", settings.singleGeneralMcut);
    setChecked("#singleCharacterMcut", settings.singleCharacterMcut);
    setChecked("#batchGeneralMcut", settings.batchGeneralMcut);
    setChecked("#batchCharacterMcut", settings.batchCharacterMcut);
    syncPresetSelect(settings.outputTemplate);
    syncRangeValues();
    toggleBatchExportMode();
  }

  function getActiveSource(prefix) {
    const button = $(`#${prefix}Pane .source-tab.active`);
    return button?.dataset.target || (prefix === "single" ? "singleUpload" : "batchFiles");
  }

  function collectSettings() {
    return {
      outputTemplate: $("#outputTemplate").value.trim() || DEFAULTS.outputTemplate,
      singleType: $("#singleType").value,
      batchType: $("#batchType").value,
      batchExportMode: $("#batchExportMode")?.value || DEFAULTS.batchExportMode,
      singleLang: $("#singleLang").value,
      batchLang: $("#batchLang").value,
      singleModel: $("#singleModel")?.value || "",
      batchModel: $("#batchModel")?.value || "",
      singleGeneral: Number($("#singleGeneral").value || DEFAULTS.singleGeneral),
      singleCharacter: Number($("#singleCharacter").value || DEFAULTS.singleCharacter),
      batchGeneral: Number($("#batchGeneral").value || DEFAULTS.batchGeneral),
      batchCharacter: Number($("#batchCharacter").value || DEFAULTS.batchCharacter),
      singleGeneralMcut: $("#singleGeneralMcut").checked,
      singleCharacterMcut: $("#singleCharacterMcut").checked,
      batchGeneralMcut: $("#batchGeneralMcut").checked,
      batchCharacterMcut: $("#batchCharacterMcut").checked,
      singleSource: getActiveSource("single"),
      batchSource: getActiveSource("batch"),
    };
  }

  function setBusy(value) {
    document.body.classList.toggle("busy", value);
    ["#singleSubmit", "#batchSubmit"].forEach((selector) => {
      const element = $(selector);
      if (element) element.disabled = value;
    });
    $$(".js-health-btn").forEach((button) => {
      button.disabled = value;
    });
  }

  function renderBackendStatus(payload, error = null) {
    const modelCount = Array.isArray(payload?.models) ? payload.models.length : payload?.model_count;
    const html = error
      ? `<span style="color: var(--bad);">连接失败：${flags.escapeHtml(error)}</span>`
      : [
        `<div>状态：<strong style="color: var(--ok);">${flags.escapeHtml(payload.status || "ok")}</strong></div>`,
        `<div>模型：${flags.escapeHtml(payload.model_dir || "-")}</div>`,
        `<div>本地模型数：${flags.escapeHtml(modelCount ?? "-")}</div>`,
        `<div>Provider：${flags.escapeHtml(Array.isArray(payload.providers) ? payload.providers.join(", ") : String(payload.providers || "-"))}</div>`,
        `<div>鉴权：${payload.auth_enabled ? "已开启" : "未开启"}</div>`,
      ].join("");
    $$(".backend-status").forEach((target) => {
      target.innerHTML = html;
    });
    if (Array.isArray(payload?.models)) {
      updateModelOptions(payload.models, payload.model_dir);
    }
  }

  function updateModelOptions(models, defaultModelDir = "") {
    state.models = Array.isArray(models) ? models : [];
    const saved = loadSettings();
    const modelOptions = [
      '<option value="">自动选择本地模型</option>',
      ...state.models.map((model) => {
        const label = `${model.name || model.model_dir}${model.default ? "（默认）" : ""}`;
        return `<option value="${flags.escapeHtml(model.model_dir || "")}">${flags.escapeHtml(label)}</option>`;
      }),
    ].join("");
    ["#singleModel", "#batchModel"].forEach((selector) => {
      const element = $(selector);
      if (!element) return;
      const current = element.value || saved[selector.includes("single") ? "singleModel" : "batchModel"] || "";
      element.innerHTML = modelOptions;
      element.value = state.models.some((item) => item.model_dir === current) ? current : "";
    });

    const modelList = $("#modelList");
    if (!modelList) return;
    if (!state.models.length) {
      modelList.innerHTML = emptyCard("未发现本地模型", "请把完整模型目录放到 models/，目录内需要 model.onnx 和 selected_tags.csv。");
      return;
    }
    modelList.innerHTML = state.models.map((model) => `
      <article class="model-card ${model.model_dir === defaultModelDir || model.default ? "selected" : ""}">
        <h4>${flags.escapeHtml(model.name || "local model")}</h4>
        <p>${flags.escapeHtml(model.model_dir || "")}</p>
      </article>
    `).join("");
  }

  function parseHeaders(response) {
    return {
      processMs: response.headers.get("X-WD-Backend-Process-Time-Ms") || response.headers.get("x-wd-backend-process-time-ms"),
      totalMs: response.headers.get("X-WD-Backend-Total-Time-Ms") || response.headers.get("x-wd-backend-total-time-ms"),
      rss: response.headers.get("X-WD-Process-Current-Rss-Mb") || response.headers.get("x-wd-process-current-rss-mb"),
      peakRss: response.headers.get("X-WD-Process-Peak-Rss-Mb") || response.headers.get("x-wd-process-peak-rss-mb"),
      cpuUser: response.headers.get("X-WD-Process-Cpu-User-Time-S") || response.headers.get("x-wd-process-cpu-user-time-s"),
      cpuSys: response.headers.get("X-WD-Process-Cpu-System-Time-S") || response.headers.get("x-wd-process-cpu-system-time-s"),
      contentType: response.headers.get("content-type") || "",
      disposition: response.headers.get("content-disposition") || "",
    };
  }

  function renderTiming(targetSelector, headers, extra = {}) {
    const metrics = [
      ["后端模型耗时", headers.processMs ? `${headers.processMs} ms` : "-"],
      ["后端总耗时", headers.totalMs ? `${headers.totalMs} ms` : "-"],
      ["当前 RSS", headers.rss ? `${headers.rss} MB` : "-"],
      ["峰值 RSS", headers.peakRss ? `${headers.peakRss} MB` : "-"],
      ["用户态 CPU", headers.cpuUser ? `${headers.cpuUser} s` : "-"],
      ["内核态 CPU", headers.cpuSys ? `${headers.cpuSys} s` : "-"],
    ];
    if (extra.totalElapsedMs != null) metrics.unshift(["前端总耗时", `${extra.totalElapsedMs} ms`]);
    $(targetSelector).innerHTML = metrics.map(([name, value]) => (
      `<article class="metric-card"><h4>${flags.escapeHtml(name)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`
    )).join("");
  }

  function clearDownloads(scope) {
    const key = scope === "single" ? "singleDownloads" : "batchDownloads";
    for (const url of state[key]) URL.revokeObjectURL(url);
    state[key] = [];
    $(`#${scope}DownloadArea`).innerHTML = '<div class="empty-card"><h4>暂无导出文件</h4><p>处理完成后这里会显示下载入口。</p></div>';
  }

  function addDownloadLink(scope, label, blob, filename) {
    const url = URL.createObjectURL(blob);
    const key = scope === "single" ? "singleDownloads" : "batchDownloads";
    state[key].push(url);
    const link = document.createElement("a");
    link.className = "download-link";
    link.href = url;
    link.download = filename;
    link.textContent = `${label}: ${filename}`;
    $(`#${scope}DownloadArea`).appendChild(link);
  }

  function emptyCard(title, text) {
    return `<div class="empty-card"><h4>${flags.escapeHtml(title)}</h4><p>${flags.escapeHtml(text)}</p></div>`;
  }

  function renderFlagSummary(targetSelector, payload) {
    const view = flags.buildHighlightedTagsHtml(payload);
    const ratings = Object.entries(view.flaggedRatings).map(([name, score]) => `${name}: ${score}`).join(", ");
    if (!view.flaggedTags.length && !ratings) {
      $(targetSelector).innerHTML = emptyCard("暂无风险提示", "没有命中明显的不合适标签。");
      return view;
    }
    $(targetSelector).innerHTML = `
      <div class="flag-grid">
        ${view.flaggedTags.length ? `<article class="flag-card"><h4>不合适标签</h4><strong>${flags.escapeHtml(view.flaggedTags.join(", "))}</strong></article>` : ""}
        ${ratings ? `<article class="flag-card"><h4>评分提示</h4><strong>${flags.escapeHtml(ratings)}</strong></article>` : ""}
      </div>
    `;
    return view;
  }

  function renderSingleTags(payload) {
    const view = renderFlagSummary("#singleFlagArea", payload);
    $("#singleResultArea").innerHTML = `
      <div class="summary-card">
        <h4>标签输出</h4>
        <strong>${flags.escapeHtml(Array.isArray(payload) ? payload.join(", ") : String(payload || ""))}</strong>
        ${view.html}
      </div>
    `;
  }

  function renderBatchSummary(payload) {
    const items = Array.isArray(payload.items) ? payload.items : [];
    const cacheStats = payload.cache_stats || {};
    const metrics = payload.metrics || {};
    const summaryCards = [
      ["总图片数", String(items.length)],
      ["成功数", String(payload.success_count ?? items.length)],
      ["失败数", String(payload.error_count ?? 0)],
      ["精确命中", String(cacheStats.exact ?? 0)],
      ["近似命中", String(cacheStats.similar ?? 0)],
      ["未命中", String(cacheStats.miss ?? 0)],
    ];
    const metricCards = [
      ["模型累计耗时", metrics.inference_elapsed_ms != null ? `${metrics.inference_elapsed_ms} ms` : "-"],
      ["后端处理总耗时", metrics.total_elapsed_ms != null ? `${metrics.total_elapsed_ms} ms` : "-"],
      ["CPU 耗时", metrics.cpu_elapsed_ms != null ? `${metrics.cpu_elapsed_ms} ms` : "-"],
    ];
    $("#batchResultArea").innerHTML = `
      <div class="grid-stack">
        <div class="metric-grid">${summaryCards.map(([title, value]) => `<article class="summary-card"><h4>${flags.escapeHtml(title)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`).join("")}</div>
        <div class="metric-grid">${metricCards.map(([title, value]) => `<article class="metric-card"><h4>${flags.escapeHtml(title)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`).join("")}</div>
        ${items.slice(0, 24).map((item) => {
          const cache = item.cache || {};
          const tagView = flags.buildHighlightedTagsHtml(item);
          return `
            <article class="item-card">
              <h4>${flags.escapeHtml(item.filename || "image")}</h4>
              <strong>${flags.escapeHtml(item.caption || "")}</strong>
              <div class="muted" style="margin-top:6px;">cache: ${flags.escapeHtml(cache.cache_hit || "-")} / similarity: ${flags.escapeHtml(cache.similarity_score ?? "-")}</div>
              ${tagView.html}
            </article>
          `;
        }).join("")}
      </div>
    `;

    const flaggedItems = items
      .map((item) => {
        const view = flags.buildHighlightedTagsHtml(item);
        if (!view.flaggedTags.length && !Object.keys(view.flaggedRatings).length) return "";
        const ratings = Object.entries(view.flaggedRatings).map(([k, v]) => `${k}: ${v}`).join(", ");
        return `<article class="flag-card"><h4>${flags.escapeHtml(item.filename || "image")}</h4><strong>${flags.escapeHtml(view.flaggedTags.join(", ") || ratings || "命中")}</strong></article>`;
      })
      .filter(Boolean)
      .join("");
    $("#batchFlagArea").innerHTML = flaggedItems ? `<div class="flag-grid">${flaggedItems}</div>` : emptyCard("暂无风险摘要", "批量任务没有命中明显的不合适标签。");
  }

  function csvEscape(value) {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  function buildBatchCsv(payload) {
    const rows = [["filename", "ok", "caption", "tags", "cache_hit", "similarity_score", "error"]];
    for (const item of Array.isArray(payload.items) ? payload.items : []) {
      const cache = item.cache || {};
      rows.push([
        item.filename || "",
        item.ok === false ? "false" : "true",
        item.caption || "",
        flags.extractTags(item).join("|"),
        cache.cache_hit || "",
        cache.similarity_score ?? "",
        item.error || "",
      ]);
    }
    return rows.map((row) => row.map(csvEscape).join(",")).join("\n");
  }

  function extractFilename(disposition, fallback) {
    const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
    if (utf8?.[1]) return decodeURIComponent(utf8[1]);
    const quoted = /filename="?([^"]+)"?/i.exec(disposition || "");
    return quoted?.[1] || fallback;
  }

  function toggleBatchExportMode() {
    const row = $("#batchExportModeRow");
    const select = $("#batchExportMode");
    const isJson = $("#batchType").value === "json";
    if (row) row.style.display = isJson ? "block" : "none";
    if (select) select.disabled = !isJson;
  }

  function syncRangeValue(input) {
    const output = $(`#${input.id}Value`);
    if (output) output.textContent = Number(input.value || 0).toFixed(2);
  }

  function syncRangeValues() {
    ["#singleGeneral", "#singleCharacter", "#batchGeneral", "#batchCharacter"].forEach((selector) => {
      const input = $(selector);
      if (input) syncRangeValue(input);
    });
  }

  function clearSingleFile() {
    const input = $("#singleFile");
    if (input) input.value = "";
    $("#singlePreview").classList.add("muted");
    $("#singlePreview").innerHTML = "尚未选择图片";
  }

  function clearBatchFiles() {
    const input = $("#batchFilesInput");
    if (input) input.value = "";
    $("#batchFileList").classList.add("muted");
    $("#batchFileList").innerHTML = "尚未选择文件";
  }

  async function readError(response, contentType) {
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      return payload.detail || payload.error || JSON.stringify(payload);
    }
    return await response.text();
  }

  async function checkBackend() {
    setBusy(true);
    try {
      const response = await fetch("/api/health");
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      renderBackendStatus(await response.json());
    } catch (error) {
      renderBackendStatus(null, error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  function appendCommonOptions(form, settings, prefix) {
    form.append("general_threshold", String(settings[`${prefix}General`]));
    form.append("character_threshold", String(settings[`${prefix}Character`]));
    form.append("general_mcut", String(settings[`${prefix}GeneralMcut`]));
    form.append("character_mcut", String(settings[`${prefix}CharacterMcut`]));
    form.append("lang", settings[`${prefix}Lang`]);
    form.append("translation_mode", settings[`${prefix}Lang`]);
    form.append("output_filename_template", settings.outputTemplate);
    if (settings[`${prefix}Model`]) {
      form.append("model_dir", settings[`${prefix}Model`]);
    }
  }

  async function submitSingle() {
    const settings = collectSettings();
    saveSettings(settings);
    clearDownloads("single");
    $("#singleResultArea").innerHTML = emptyCard("处理中", "正在上传并等待后端推理结果。");
    $("#singleFlagArea").innerHTML = emptyCard("暂无风险提示", "执行后这里会显示不合适标签和评分。");
    $("#singleTimingArea").innerHTML = "";
    setBusy(true);
    const start = performance.now();
    try {
      const form = new FormData();
      form.append("type", settings.singleType);
      appendCommonOptions(form, settings, "single");

      if (settings.singleSource === "singleUrl") {
        const url = $("#singleUrlInput").value.trim();
        if (!url) throw new Error("请先填写图片 URL");
        form.append("image_url", url);
      } else {
        const file = $("#singleFile").files[0];
        if (!file) throw new Error("请先选择图片");
        form.append("image", file, file.name);
      }

      const response = await fetch("/api/process", { method: "POST", body: form });
      const headers = parseHeaders(response);
      const contentType = headers.contentType.toLowerCase();
      if (!response.ok) throw new Error(await readError(response, contentType));

      if (contentType.includes("application/json")) {
        const payload = await response.json();
        renderSingleTags(settings.singleType === "arrary" ? payload : payload.caption || payload);
      } else if (contentType.startsWith("text/plain")) {
        renderSingleTags(await response.text());
      } else {
        const blob = await response.blob();
        const filename = extractFilename(headers.disposition, "tagged_image.bin");
        $("#singleDownloadArea").innerHTML = "";
        addDownloadLink("single", "下载图片", blob, filename);
        $("#singleResultArea").innerHTML = `<div class="summary-card"><h4>文件已生成</h4><strong>${flags.escapeHtml(filename)}</strong></div>`;
        $("#singleFlagArea").innerHTML = emptyCard("导出图像", "tagimg 模式由后端导出图片文件。");
      }
      renderTiming("#singleTimingArea", headers, { totalElapsedMs: Math.round(performance.now() - start) });
    } catch (error) {
      $("#singleResultArea").innerHTML = `<div class="flag-card"><h4>错误</h4><strong>${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
    } finally {
      setBusy(false);
    }
  }

  async function submitBatch() {
    const settings = collectSettings();
    saveSettings(settings);
    clearDownloads("batch");
    $("#batchResultArea").innerHTML = emptyCard("处理中", "正在上传批量任务并等待后端处理。");
    $("#batchFlagArea").innerHTML = emptyCard("暂无风险摘要", "批量处理后这里会汇总命中风险标签的文件。");
    $("#batchTimingArea").innerHTML = "";
    setBusy(true);
    const start = performance.now();
    try {
      const form = new FormData();
      form.append("type", settings.batchType);
      appendCommonOptions(form, settings, "batch");
      form.append("export_format", "inline");

      if (settings.batchSource === "batchFiles") {
        const files = Array.from($("#batchFilesInput").files || []);
        if (!files.length) throw new Error("请先选择批量图片");
        files.forEach((file) => form.append("images", file, file.name));
      } else if (settings.batchSource === "batchUrls") {
        const urls = $("#batchUrlInput").value
          .split(/[\n,;|]+/)
          .map((item) => item.trim())
          .filter(Boolean);
        if (!urls.length) throw new Error("请先填写批量图片 URL");
        form.append("image_urls", urls.join(";"));
      } else {
        const dir = $("#batchDirInput").value.trim();
        if (!dir) throw new Error("请先填写服务端目录路径");
        form.append("input_dir", dir);
      }

      const response = await fetch("/api/process", { method: "POST", body: form });
      const headers = parseHeaders(response);
      const contentType = headers.contentType.toLowerCase();
      if (!response.ok) throw new Error(await readError(response, contentType));

      if (settings.batchType === "json") {
        const payload = await response.json();
        renderBatchSummary(payload);
        $("#batchDownloadArea").innerHTML = "";
        const jsonBlob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
        const csvBlob = new Blob([buildBatchCsv(payload)], { type: "text/csv;charset=utf-8" });
        if (settings.batchExportMode === "json" || settings.batchExportMode === "both") addDownloadLink("batch", "JSON", jsonBlob, "results.json");
        if (settings.batchExportMode === "csv" || settings.batchExportMode === "both") addDownloadLink("batch", "CSV", csvBlob, "results.csv");
        if (settings.batchExportMode === "inline") clearDownloads("batch");
      } else {
        const blob = await response.blob();
        const filename = extractFilename(headers.disposition, "tagged_images.zip");
        $("#batchDownloadArea").innerHTML = "";
        addDownloadLink("batch", "下载 ZIP", blob, filename);
        $("#batchResultArea").innerHTML = `<div class="summary-card"><h4>批量导出</h4><strong>${flags.escapeHtml(filename)}</strong></div>`;
        $("#batchFlagArea").innerHTML = emptyCard("ZIP 结果", "ZIP 结果由后端直接返回。");
      }
      renderTiming("#batchTimingArea", headers, { totalElapsedMs: Math.round(performance.now() - start) });
    } catch (error) {
      $("#batchResultArea").innerHTML = `<div class="flag-card"><h4>错误</h4><strong>${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
    } finally {
      setBusy(false);
    }
  }

  function activateScopedTab(buttonSelector, paneSelector, button) {
    const root = button.closest(".main-pane") || document;
    $$(buttonSelector, root).forEach((item) => item.classList.remove("active"));
    $$(paneSelector, root).forEach((pane) => pane.classList.remove("active"));
    button.classList.add("active");
    $(`#${button.dataset.target}`).classList.add("active");
  }

  function bindTabs() {
    $$(".main-tab").forEach((button) => {
      button.addEventListener("click", () => {
        $$(".main-tab").forEach((item) => item.classList.remove("active"));
        $$(".main-pane").forEach((pane) => pane.classList.remove("active"));
        button.classList.add("active");
        $(`#${button.dataset.target}`).classList.add("active");
      });
    });
    $$(".source-tab").forEach((button) => {
      button.addEventListener("click", () => activateScopedTab(".source-tab", ".source-pane", button));
    });
    $$(".result-tab").forEach((button) => {
      button.addEventListener("click", () => activateScopedTab(".result-tab", ".result-pane", button));
    });
  }

  function bindSettings() {
    $("#outputPreset").addEventListener("change", (event) => {
      if (event.target.value) {
        $("#outputTemplate").value = event.target.value;
        saveSettings();
      }
    });
    [
      "#outputTemplate",
      "#singleType",
      "#batchType",
      "#batchExportMode",
      "#singleLang",
      "#batchLang",
      "#singleModel",
      "#batchModel",
      "#singleGeneral",
      "#singleCharacter",
      "#batchGeneral",
      "#batchCharacter",
      "#singleGeneralMcut",
      "#singleCharacterMcut",
      "#batchGeneralMcut",
      "#batchCharacterMcut",
    ].forEach((selector) => {
      const element = $(selector);
      if (element) element.addEventListener("change", () => saveSettings());
    });
    ["#singleGeneral", "#singleCharacter", "#batchGeneral", "#batchCharacter"].forEach((selector) => {
      const element = $(selector);
      if (!element) return;
      element.addEventListener("input", () => syncRangeValue(element));
      element.addEventListener("change", () => {
        syncRangeValue(element);
        saveSettings();
      });
    });
    $("#batchType").addEventListener("change", toggleBatchExportMode);
    $$(".upload-card").forEach((card) => {
      card.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        const input = $(`#${card.dataset.input}`);
        if (input) input.click();
      });
    });
    $("#singleClear").addEventListener("click", clearSingleFile);
    $("#batchClear").addEventListener("click", clearBatchFiles);
    $("#singleFile").addEventListener("change", () => {
      const file = $("#singleFile").files[0];
      $("#singlePreview").textContent = file ? `${file.name} (${Math.round(file.size / 1024)} KB)` : "尚未选择图片";
      if (file) {
        $("#singlePreview").classList.remove("muted");
        const reader = new FileReader();
        reader.onload = () => {
          $("#singlePreview").innerHTML = `<img src="${reader.result}" alt="preview" /><div class="preview-meta"><strong>${flags.escapeHtml(file.name)}</strong><span>${Math.round(file.size / 1024)} KB</span></div>`;
        };
        reader.readAsDataURL(file);
      } else {
        clearSingleFile();
      }
    });
    $("#batchFilesInput").addEventListener("change", () => {
      const files = Array.from($("#batchFilesInput").files || []);
      $("#batchFileList").classList.toggle("muted", !files.length);
      $("#batchFileList").innerHTML = files.length
        ? files.map((file) => `<div class="file-row"><span>${flags.escapeHtml(file.name)}</span><b>${Math.round(file.size / 1024)} KB</b></div>`).join("")
        : "尚未选择文件";
    });
  }

  function init() {
    const settings = loadSettings();
    syncPresetSelect(settings.outputTemplate);
    applySettingsToForm(settings);
    bindTabs();
    bindSettings();
    $$(".js-health-btn").forEach((button) => button.addEventListener("click", checkBackend));
    $("#singleSubmit").addEventListener("click", submitSingle);
    $("#batchSubmit").addEventListener("click", submitBatch);
    clearDownloads("single");
    clearDownloads("batch");
    $("#singleFlagArea").innerHTML = emptyCard("暂无风险提示", "执行后这里会显示不合适标签和评分。");
    $("#batchFlagArea").innerHTML = emptyCard("暂无风险摘要", "批量处理后这里会汇总命中风险标签的文件。");
    $("#singleTimingArea").innerHTML = emptyCard("暂无耗时数据", "请求完成后这里会显示前端和后端耗时。");
    $("#batchTimingArea").innerHTML = emptyCard("暂无耗时数据", "请求完成后这里会显示前端和后端耗时。");
    toggleBatchExportMode();
    checkBackend();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
