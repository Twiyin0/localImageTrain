(() => {
  const SETTINGS_KEY = "wd_tagger_webui_settings_v3";
  const DEFAULT_OUTPUT_TEMPLATE = "${origin_filename}_tagged${origin_ext}";
  const OUTPUT_PRESETS = [
    { label: "默认：原文件名_tagged.原后缀", value: DEFAULT_OUTPUT_TEMPLATE },
    { label: "保留原文件名", value: "${origin_filename}${origin_ext}" },
    { label: "原名_类型_序号", value: "${origin_filename}_${type}_${index}${origin_ext}" },
    { label: "原名_时间戳", value: "${origin_filename}_${timestamp}${origin_ext}" },
  ];

  const DEFAULTS = {
    outputTemplate: DEFAULT_OUTPUT_TEMPLATE,
    translationMode: "zh",
    singleType: "tag",
    batchType: "json",
    batchExportMode: "both",
    singleModel: "",
    batchModel: "",
    singleGeneral: 0.35,
    singleCharacter: 0.85,
    singleSensitive: 0.7,
    batchGeneral: 0.35,
    batchCharacter: 0.85,
    batchSensitive: 0.7,
    singleGeneralMcut: false,
    singleCharacterMcut: false,
    batchGeneralMcut: false,
    batchCharacterMcut: false,
    singleSource: "singleUpload",
    batchSource: "batchFiles",
  };

  const state = {
    models: [],
    singleDownloads: [],
    batchDownloads: [],
    singlePreviewUrl: null,
    lastSingleRequest: null,
    lastSingleTiming: null,
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

  function applyValue(selector, value) {
    const element = $(selector);
    if (element) element.value = value;
  }

  function applyChecked(selector, value) {
    const element = $(selector);
    if (element) element.checked = Boolean(value);
  }

  function syncPresetSelect(value) {
    const select = $("#outputPreset");
    if (!select) return;
    select.innerHTML = OUTPUT_PRESETS.map((preset) => (
      `<option value="${flags.escapeHtml(preset.value)}">${flags.escapeHtml(preset.label)}</option>`
    )).join("");
    select.value = OUTPUT_PRESETS.find((item) => item.value === value)?.value || "";
  }

  function syncRangeValue(input) {
    const output = $(`#${input.id}Value`);
    if (output) output.textContent = Number(input.value || 0).toFixed(2);
  }

  function syncRangeValues() {
    ["#singleGeneral", "#singleCharacter", "#singleSensitive", "#batchGeneral", "#batchCharacter", "#batchSensitive"].forEach((selector) => {
      const input = $(selector);
      if (input) syncRangeValue(input);
    });
  }

  function applySettings(settings) {
    applyValue("#outputTemplate", settings.outputTemplate);
    applyValue("#translationMode", settings.translationMode);
    applyValue("#singleType", settings.singleType);
    applyValue("#batchType", settings.batchType);
    applyValue("#batchExportMode", settings.batchExportMode);
    applyValue("#singleModel", settings.singleModel);
    applyValue("#batchModel", settings.batchModel);
    applyValue("#singleGeneral", settings.singleGeneral);
    applyValue("#singleCharacter", settings.singleCharacter);
    applyValue("#singleSensitive", settings.singleSensitive);
    applyValue("#batchGeneral", settings.batchGeneral);
    applyValue("#batchCharacter", settings.batchCharacter);
    applyValue("#batchSensitive", settings.batchSensitive);
    applyChecked("#singleGeneralMcut", settings.singleGeneralMcut);
    applyChecked("#singleCharacterMcut", settings.singleCharacterMcut);
    applyChecked("#batchGeneralMcut", settings.batchGeneralMcut);
    applyChecked("#batchCharacterMcut", settings.batchCharacterMcut);
    syncPresetSelect(settings.outputTemplate);
    syncRangeValues();
    toggleBatchExportMode();
  }

  function collectSettings() {
    return {
      outputTemplate: $("#outputTemplate").value.trim() || DEFAULT_OUTPUT_TEMPLATE,
      translationMode: $("#translationMode").value || DEFAULTS.translationMode,
      singleType: $("#singleType").value,
      batchType: $("#batchType").value,
      batchExportMode: $("#batchExportMode").value || DEFAULTS.batchExportMode,
      singleModel: $("#singleModel").value || "",
      batchModel: $("#batchModel").value || "",
      singleGeneral: Number($("#singleGeneral").value || DEFAULTS.singleGeneral),
      singleCharacter: Number($("#singleCharacter").value || DEFAULTS.singleCharacter),
      singleSensitive: Number($("#singleSensitive").value || DEFAULTS.singleSensitive),
      batchGeneral: Number($("#batchGeneral").value || DEFAULTS.batchGeneral),
      batchCharacter: Number($("#batchCharacter").value || DEFAULTS.batchCharacter),
      batchSensitive: Number($("#batchSensitive").value || DEFAULTS.batchSensitive),
      singleGeneralMcut: $("#singleGeneralMcut").checked,
      singleCharacterMcut: $("#singleCharacterMcut").checked,
      batchGeneralMcut: $("#batchGeneralMcut").checked,
      batchCharacterMcut: $("#batchCharacterMcut").checked,
      singleSource: getActiveSource("single"),
      batchSource: getActiveSource("batch"),
    };
  }

  function getActiveSource(prefix) {
    const active = $(`#${prefix}Pane .source-tab.active`);
    return active?.dataset.target || (prefix === "single" ? "singleUpload" : "batchFiles");
  }

  function setBusy(value) {
    document.body.classList.toggle("busy", value);
    ["#singleSubmit", "#batchSubmit", ".js-health-btn"].forEach((selector) => {
      $$(selector).forEach((button) => {
        button.disabled = value;
      });
    });
  }

  function emptyCard(title, text) {
    return `<div class="empty-card"><h4>${flags.escapeHtml(title)}</h4><p>${flags.escapeHtml(text)}</p></div>`;
  }

  function renderBackendStatus(payload, error = null) {
    const modelCount = Array.isArray(payload?.models) ? payload.models.length : payload?.model_count;
    const html = error
      ? `<span style="color: var(--bad);">连接失败：${flags.escapeHtml(error)}</span>`
      : [
        `<div>状态：<strong style="color: var(--ok);">${flags.escapeHtml(payload.status || "ok")}</strong></div>`,
        `<div>前端：${flags.escapeHtml(payload.frontend || "static-html")}</div>`,
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
    const options = [
      '<option value="">自动选择本地模型</option>',
      ...state.models.map((model) => {
        const label = `${model.name || model.model_dir}${model.default ? "（默认）" : ""}`;
        return `<option value="${flags.escapeHtml(model.model_dir || "")}">${flags.escapeHtml(label)}</option>`;
      }),
    ].join("");
    ["#singleModel", "#batchModel"].forEach((selector) => {
      const element = $(selector);
      if (!element) return;
      const current = element.value || saved[selector === "#singleModel" ? "singleModel" : "batchModel"] || "";
      element.innerHTML = options;
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
    const riskSummaryRaw = response.headers.get("X-WD-Risk-Summary") || response.headers.get("x-wd-risk-summary");
    let riskSummary = null;
    if (riskSummaryRaw) {
      try {
        riskSummary = JSON.parse(riskSummaryRaw);
      } catch {
        riskSummary = null;
      }
    }
    return {
      inferenceMs: response.headers.get("X-WD-Inference-Time-Ms") || response.headers.get("x-wd-inference-time-ms"),
      processMs: response.headers.get("X-WD-Backend-Process-Time-Ms") || response.headers.get("x-wd-backend-process-time-ms"),
      prepareMs: response.headers.get("X-WD-Backend-Prepare-Time-Ms") || response.headers.get("x-wd-backend-prepare-time-ms"),
      postInferenceMs: response.headers.get("X-WD-Backend-Post-Inference-Time-Ms") || response.headers.get("x-wd-backend-post-inference-time-ms"),
      totalMs: response.headers.get("X-WD-Backend-Total-Time-Ms") || response.headers.get("x-wd-backend-total-time-ms"),
      cpuElapsedMs: response.headers.get("X-WD-Cpu-Elapsed-Ms") || response.headers.get("x-wd-cpu-elapsed-ms"),
      cacheHit: response.headers.get("X-WD-Cache-Hit") || response.headers.get("x-wd-cache-hit"),
      cacheSimilarity: response.headers.get("X-WD-Cache-Similarity-Score") || response.headers.get("x-wd-cache-similarity-score"),
      riskSummary,
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
      ["前端首个请求耗时", extra.requestElapsedMs != null ? `${extra.requestElapsedMs} ms` : "-"],
      ["前端导出附加耗时", extra.exportElapsedMs != null ? `${extra.exportElapsedMs} ms` : "-"],
      ["前端端到端总耗时", extra.endToEndElapsedMs != null ? `${extra.endToEndElapsedMs} ms` : "-"],
      ["后端请求准备耗时", headers.prepareMs ? `${headers.prepareMs} ms` : "-"],
      ["后端纯推理耗时", headers.inferenceMs ? `${headers.inferenceMs} ms` : "-"],
      ["后端推理后处理耗时", headers.postInferenceMs ? `${headers.postInferenceMs} ms` : "-"],
      ["后端处理耗时", headers.processMs ? `${headers.processMs} ms` : "-"],
      ["后端总耗时", headers.totalMs ? `${headers.totalMs} ms` : "-"],
      ["导出请求后端总耗时", extra.exportBackendTotalMs != null ? `${extra.exportBackendTotalMs} ms` : "-"],
      ["缓存命中", headers.cacheHit || "-"],
      ["缓存相似度", headers.cacheSimilarity ?? "-"],
      ["本次 CPU 耗时", headers.cpuElapsedMs ? `${headers.cpuElapsedMs} ms` : "-"],
      ["当前 RSS", headers.rss ? `${headers.rss} MB` : "-"],
      ["峰值 RSS", headers.peakRss ? `${headers.peakRss} MB` : "-"],
      ["用户态 CPU", headers.cpuUser ? `${headers.cpuUser} s` : "-"],
      ["内核态 CPU", headers.cpuSys ? `${headers.cpuSys} s` : "-"],
    ];
    $(targetSelector).innerHTML = metrics.map(([name, value]) => (
      `<article class="metric-card"><h4>${flags.escapeHtml(name)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`
    )).join("");
  }

  function renderSingleExportState({ enabled = false, busy = false, hint } = {}) {
    const button = $("#singleExportGenerate");
    const hintNode = $("#singleExportHint");
    if (button) {
      button.disabled = !enabled || busy;
      button.textContent = busy ? "正在生成带 tag 图片..." : "生成带 tag 图片";
    }
    if (hintNode) {
      hintNode.textContent = hint || (enabled
        ? "识别结果已就绪；只有点这里时才会额外发起导出请求。"
        : "先执行单张识别，再按需生成导出图片。");
    }
  }

  function rememberSingleTiming(headers, requestElapsedMs) {
    state.lastSingleTiming = { headers, requestElapsedMs };
    renderTiming("#singleTimingArea", headers, {
      requestElapsedMs,
      endToEndElapsedMs: requestElapsedMs,
    });
  }

  function updateSingleTimingAfterExport(exportHeaders, exportElapsedMs) {
    if (!state.lastSingleTiming) return;
    renderTiming("#singleTimingArea", state.lastSingleTiming.headers, {
      requestElapsedMs: state.lastSingleTiming.requestElapsedMs,
      exportElapsedMs,
      endToEndElapsedMs: state.lastSingleTiming.requestElapsedMs + exportElapsedMs,
      exportBackendTotalMs: exportHeaders.totalMs,
    });
  }

  function invalidateSingleRequest(hint = "当前图片或来源已变化；如需导出，请先重新识别。") {
    state.lastSingleRequest = null;
    state.lastSingleTiming = null;
    renderSingleExportState({ enabled: false, hint });
  }

  function buildSingleSourceSnapshot(settings) {
    if (settings.singleSource === "singleUrl") {
      const url = $("#singleUrlInput").value.trim();
      if (!url) throw new Error("请先填写图片 URL");
      return { kind: "url", url };
    }
    const file = $("#singleFile").files[0];
    if (!file) throw new Error("请先选择图片");
    return { kind: "file", file };
  }

  function appendSingleSource(form, sourceSnapshot) {
    if (sourceSnapshot.kind === "url") {
      form.append("image_url", sourceSnapshot.url);
      return;
    }
    form.append("image", sourceSnapshot.file, sourceSnapshot.file.name);
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

  function renderDownload(scope, label, blob, filename) {
    $(`#${scope}DownloadArea`).innerHTML = "";
    addDownloadLink(scope, label, blob, filename);
  }

  function resultTextFromPayload(payload) {
    if (Array.isArray(payload)) return payload.join(", ");
    if (payload && typeof payload === "object") {
      return payload.caption_display || payload.caption || payload.caption_original || "";
    }
    return String(payload || "");
  }

  function renderFlagSummary(targetSelector, payload) {
    const view = flags.buildHighlightedTagsHtml(payload);
    const ratings = Object.entries(view.flaggedRatings).map(([name, score]) => `${name}: ${score}`).join(", ");
    const flaggedLabel = view.flaggedTagPairs
      .map((entry) => entry.display === entry.original ? entry.display : `${entry.display} (${entry.original})`)
      .join(", ");
    if (!view.flaggedTags.length && !ratings) {
      $(targetSelector).innerHTML = emptyCard("暂无风险提示", "没有命中明显的不合适标签。");
      return view;
    }
    $(targetSelector).innerHTML = `
      <div class="flag-grid">
        ${view.flaggedTagPairs.length ? `<article class="flag-card"><h4>不合适标签</h4><strong>${flags.escapeHtml(flaggedLabel)}</strong></article>` : ""}
        ${ratings ? `<article class="flag-card"><h4>评分提示</h4><strong>${flags.escapeHtml(ratings)}</strong></article>` : ""}
      </div>
    `;
    return view;
  }

  function renderSingleResult(payload, headers = null) {
    const displayPayload = Array.isArray(payload) || typeof payload === "string"
      ? {
        caption_display: resultTextFromPayload(payload),
        caption: resultTextFromPayload(payload),
        risk: headers?.riskSummary || null,
      }
      : payload && typeof payload === "object"
      ? payload
      : {
        caption_display: resultTextFromPayload(payload),
        caption: resultTextFromPayload(payload),
        risk: headers?.riskSummary || null,
      };
    const view = renderFlagSummary("#singleFlagArea", displayPayload);
    const text = resultTextFromPayload(payload);
    const payloadCache = payload && typeof payload === "object" ? (payload.cache || {}) : {};
    const cacheHit = payloadCache.cache_hit || headers?.cacheHit || "-";
    const cacheSimilarity = payloadCache.similarity_score ?? headers?.cacheSimilarity ?? "-";
    const cacheCards = [
      ["缓存命中", cacheHit],
      ["相似度", cacheSimilarity],
    ];
    $("#singleResultArea").innerHTML = `
      <div class="grid-stack">
        <div class="summary-card">
          <h4>标签输出</h4>
          <strong>${flags.escapeHtml(text)}</strong>
          ${view.html}
        </div>
        <div class="metric-grid">${cacheCards.map(([title, value]) => `<article class="metric-card"><h4>${flags.escapeHtml(title)}</h4><strong>${flags.escapeHtml(String(value))}</strong></article>`).join("")}</div>
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
        const flaggedLabel = view.flaggedTagPairs
          .map((entry) => entry.display === entry.original ? entry.display : `${entry.display} (${entry.original})`)
          .join(", ");
        return `<article class="flag-card"><h4>${flags.escapeHtml(item.filename || "image")}</h4><strong>${flags.escapeHtml(flaggedLabel || ratings || "命中")}</strong></article>`;
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

  function openResults(scope) {
    const details = $(`#${scope}Results`);
    if (details) details.open = true;
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
      const response = await fetch("/health", { credentials: "same-origin" });
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
    form.append("sensitive_threshold", String(settings[`${prefix}Sensitive`]));
    form.append("general_mcut", String(settings[`${prefix}GeneralMcut`]));
    form.append("character_mcut", String(settings[`${prefix}CharacterMcut`]));
    form.append("lang", settings.translationMode || "zh");
    form.append("translation_mode", settings.translationMode || "zh");
    form.append("output_filename_template", settings.outputTemplate);
    if (settings[`${prefix}Model`]) {
      form.append("model_dir", settings[`${prefix}Model`]);
    }
  }

  async function requestSingleTaggedImage(requestSnapshot) {
    $("#singleDownloadArea").innerHTML = emptyCard("正在生成导出图片", "正在把标签写入图片元数据。");
    const form = new FormData();
    form.append("type", "tagimg");
    appendCommonOptions(form, requestSnapshot.settings, "single");
    appendSingleSource(form, requestSnapshot.source);

    const response = await fetch("/process", { method: "POST", body: form, credentials: "same-origin" });
    const headers = parseHeaders(response);
    const contentType = headers.contentType.toLowerCase();
    if (!response.ok) throw new Error(await readError(response, contentType));
    if (contentType.includes("application/json") || contentType.startsWith("text/")) {
      throw new Error("后端没有返回带 tag 的图片文件。");
    }

    const blob = await response.blob();
    if (!blob.size) throw new Error("后端返回的图片文件为空。");
    const filename = extractFilename(headers.disposition, "tagged_image.png");
    renderDownload("single", "下载带 tag 图片", blob, filename);
    return { headers, filename };
  }

  async function submitSingle() {
    const settings = collectSettings();
    saveSettings(settings);
    clearDownloads("single");
    renderSingleExportState({ enabled: false, hint: "当前请求处理中，识别完成后可按需生成导出图片。" });
    state.lastSingleRequest = null;
    state.lastSingleTiming = null;
    $("#singleResultArea").innerHTML = emptyCard("处理中", "正在上传并等待后端推理结果。");
    $("#singleFlagArea").innerHTML = emptyCard("暂无风险提示", "执行后这里会显示不合适标签和评分。");
    $("#singleTimingArea").innerHTML = "";
    openResults("single");
    setBusy(true);
    const start = performance.now();
    try {
      const sourceSnapshot = buildSingleSourceSnapshot(settings);
      const form = new FormData();
      form.append("type", settings.singleType);
      appendCommonOptions(form, settings, "single");
      appendSingleSource(form, sourceSnapshot);

      const response = await fetch("/process", { method: "POST", body: form, credentials: "same-origin" });
      const headers = parseHeaders(response);
      const contentType = headers.contentType.toLowerCase();
      if (!response.ok) throw new Error(await readError(response, contentType));

      if (contentType.includes("application/json")) {
        const payload = await response.json();
        renderSingleResult(payload, headers);
      } else if (contentType.startsWith("text/plain")) {
        const text = await response.text();
        renderSingleResult(text, headers);
      } else {
        const blob = await response.blob();
        const filename = extractFilename(headers.disposition, "tagged_image.bin");
        renderDownload("single", "下载带 tag 图片", blob, filename);
        $("#singleResultArea").innerHTML = `<div class="summary-card"><h4>文件已生成</h4><strong>${flags.escapeHtml(filename)}</strong></div>`;
        $("#singleFlagArea").innerHTML = emptyCard("导出图像", "tagimg 模式由后端导出图片文件。");
      }
      const requestElapsedMs = Math.round(performance.now() - start);
      rememberSingleTiming(headers, requestElapsedMs);
      if (settings.singleType !== "tagimg") {
        state.lastSingleRequest = {
          settings: { ...settings },
          source: sourceSnapshot,
        };
        renderSingleExportState({ enabled: true });
      } else {
        renderSingleExportState({
          enabled: true,
          hint: "当前结果已经是带 metadata 的图片；如需重新生成可再次点击。",
        });
        state.lastSingleRequest = {
          settings: { ...settings, singleType: "tagimg" },
          source: sourceSnapshot,
        };
      }
      openResults("single");
    } catch (error) {
      state.lastSingleRequest = null;
      state.lastSingleTiming = null;
      renderSingleExportState({ enabled: false, hint: "识别失败，暂时不能生成导出图片。" });
      $("#singleResultArea").innerHTML = `<div class="flag-card"><h4>错误</h4><strong>${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
      openResults("single");
    } finally {
      setBusy(false);
    }
  }

  async function handleSingleExport() {
    if (!state.lastSingleRequest) {
      renderSingleExportState({ enabled: false, hint: "没有可复用的单张结果；请先重新识别。" });
      return;
    }
    openResults("single");
    setBusy(true);
    renderSingleExportState({ enabled: true, busy: true });
    const exportStarted = performance.now();
    try {
      const { headers } = await requestSingleTaggedImage(state.lastSingleRequest);
      const exportElapsedMs = Math.round(performance.now() - exportStarted);
      updateSingleTimingAfterExport(headers, exportElapsedMs);
      renderSingleExportState({
        enabled: true,
        hint: "导出完成；这次附加耗时已经单独计入，不再混进首个识别请求。",
      });
    } catch (error) {
      renderSingleExportState({
        enabled: true,
        hint: "导出失败了；可以重试，识别结果仍然保留。",
      });
      $("#singleDownloadArea").innerHTML = `<div class="flag-card"><h4>导出失败</h4><strong>${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
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
    openResults("batch");
    setBusy(true);
    const start = performance.now();
    try {
      const form = new FormData();
      form.append("type", settings.batchType);
      appendCommonOptions(form, settings, "batch");
      form.append("export_format", settings.batchType === "json" ? settings.batchExportMode : "both");

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

      const response = await fetch("/process", { method: "POST", body: form, credentials: "same-origin" });
      const headers = parseHeaders(response);
      const contentType = headers.contentType.toLowerCase();
      if (!response.ok) throw new Error(await readError(response, contentType));

      const isDownload = Boolean(headers.disposition) || contentType.includes("application/zip") || contentType.includes("text/csv") || contentType.includes("octet-stream");
      if (settings.batchType === "json" && !isDownload) {
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
        const filename = extractFilename(headers.disposition, contentType.includes("text/csv") ? "results.csv" : contentType.includes("application/json") ? "results.json" : "tagged_images.zip");
        renderDownload("batch", contentType.includes("text/csv") ? "下载 CSV" : contentType.includes("application/json") ? "下载 JSON" : "下载 ZIP", blob, filename);
        $("#batchResultArea").innerHTML = `<div class="summary-card"><h4>批量导出</h4><strong>${flags.escapeHtml(filename)}</strong></div>`;
        $("#batchFlagArea").innerHTML = emptyCard("导出结果", "文件结果由后端直接返回。");
      }
      const requestElapsedMs = Math.round(performance.now() - start);
      renderTiming("#batchTimingArea", headers, {
        requestElapsedMs,
        endToEndElapsedMs: requestElapsedMs,
      });
      openResults("batch");
    } catch (error) {
      $("#batchResultArea").innerHTML = `<div class="flag-card"><h4>错误</h4><strong>${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
      openResults("batch");
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
      button.addEventListener("click", () => {
        activateScopedTab(".source-tab", ".source-pane", button);
        if (button.closest("#singlePane")) {
          invalidateSingleRequest();
        }
      });
    });
    $$(".result-tab").forEach((button) => {
      button.addEventListener("click", () => activateScopedTab(".result-tab", ".result-pane", button));
    });
  }

  function assignFiles(input, files) {
    if (!input || !files.length) return;
    const transfer = new DataTransfer();
    files.forEach((file) => transfer.items.add(file));
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function imageFilesFromDrop(event, multiple) {
    const files = Array.from(event.dataTransfer?.files || []).filter((file) => file.type.startsWith("image/"));
    return multiple ? files : files.slice(0, 1);
  }

  function revokeSinglePreviewUrl() {
    if (state.singlePreviewUrl) {
      URL.revokeObjectURL(state.singlePreviewUrl);
      state.singlePreviewUrl = null;
    }
  }

  function updateSinglePreview() {
    const file = $("#singleFile").files[0];
    revokeSinglePreviewUrl();
    $("#singlePreview").textContent = file ? `${file.name} (${Math.round(file.size / 1024)} KB)` : "尚未选择图片";
    if (file) {
      invalidateSingleRequest();
      $("#singlePreview").classList.remove("muted");
      state.singlePreviewUrl = URL.createObjectURL(file);
      $("#singlePreview").innerHTML = `<img src="${state.singlePreviewUrl}" alt="preview" /><div class="preview-meta"><strong>${flags.escapeHtml(file.name)}</strong><span>${Math.round(file.size / 1024)} KB</span></div>`;
    } else {
      clearSingleFile();
    }
  }

  function updateBatchFileList() {
    const files = Array.from($("#batchFilesInput").files || []);
    $("#batchFileList").classList.toggle("muted", !files.length);
    $("#batchFileList").innerHTML = files.length
      ? files.map((file) => `<div class="file-row"><span>${flags.escapeHtml(file.name)}</span><b>${Math.round(file.size / 1024)} KB</b></div>`).join("")
      : "尚未选择文件";
  }

  function bindUploadCard(card) {
    const input = $(`#${card.dataset.input}`);
    if (!input) return;
    const multiple = Boolean(input.multiple);

    card.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      input.click();
    });
    ["dragenter", "dragover"].forEach((eventName) => {
      card.addEventListener(eventName, (event) => {
        event.preventDefault();
        card.classList.add("dragover");
      });
    });
    card.addEventListener("dragleave", (event) => {
      if (!card.contains(event.relatedTarget)) {
        card.classList.remove("dragover");
      }
    });
    card.addEventListener("drop", (event) => {
      event.preventDefault();
      card.classList.remove("dragover");
      const files = imageFilesFromDrop(event, multiple);
      if (files.length) assignFiles(input, files);
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
      "#translationMode",
      "#singleType",
      "#batchType",
      "#batchExportMode",
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
    $$(".upload-card").forEach(bindUploadCard);
    $("#singleClear").addEventListener("click", clearSingleFile);
    $("#batchClear").addEventListener("click", clearBatchFiles);
    $("#singleFile").addEventListener("change", updateSinglePreview);
    $("#singleUrlInput").addEventListener("input", () => invalidateSingleRequest());
    $("#singleExportGenerate").addEventListener("click", handleSingleExport);
    $("#batchFilesInput").addEventListener("change", updateBatchFileList);
    $("#backToTop").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  }

  function clearSingleFile() {
    const input = $("#singleFile");
    if (input) input.value = "";
    revokeSinglePreviewUrl();
    invalidateSingleRequest("已清空当前图片；如需导出，请重新选择并识别。");
    $("#singlePreview").classList.add("muted");
    $("#singlePreview").innerHTML = "尚未选择图片";
  }

  function clearBatchFiles() {
    const input = $("#batchFilesInput");
    if (input) input.value = "";
    $("#batchFileList").classList.add("muted");
    $("#batchFileList").innerHTML = "尚未选择文件";
  }

  function init() {
    const settings = loadSettings();
    syncPresetSelect(settings.outputTemplate);
    applySettings(settings);
    bindTabs();
    bindSettings();
    $$(".js-health-btn").forEach((button) => button.addEventListener("click", checkBackend));
    $("#singleSubmit").addEventListener("click", submitSingle);
    $("#batchSubmit").addEventListener("click", submitBatch);
    clearDownloads("single");
    clearDownloads("batch");
    renderSingleExportState({ enabled: false });
    $("#singleFlagArea").innerHTML = emptyCard("暂无风险提示", "执行后这里会显示不合适标签和评分。");
    $("#batchFlagArea").innerHTML = emptyCard("暂无风险摘要", "批量处理后这里会汇总命中风险标签的文件。");
    $("#singleTimingArea").innerHTML = emptyCard("暂无耗时数据", "请求完成后这里会显示前端和后端耗时。");
    $("#batchTimingArea").innerHTML = emptyCard("暂无耗时数据", "请求完成后这里会显示前端和后端耗时。");
    toggleBatchExportMode();
    checkBackend();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
