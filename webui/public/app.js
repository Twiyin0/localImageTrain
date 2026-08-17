(() => {
  const SETTINGS_KEY = "wd_tagger_webui_settings_v1";
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
    lastDownloads: [],
    busy: false,
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

  function setSelectValue(selector, value) {
    const element = $(selector);
    if (element) element.value = value;
  }

  function setInputValue(selector, value) {
    const element = $(selector);
    if (element) element.value = value;
  }

  function setChecked(selector, value) {
    const element = $(selector);
    if (element) element.checked = Boolean(value);
  }

  function syncPresetSelect(value) {
    const select = $("#outputPreset");
    select.innerHTML = OUTPUT_PRESETS.map((preset) => (
      `<option value="${flags.escapeHtml(preset.value)}">${flags.escapeHtml(preset.label)}</option>`
    )).join("");
    select.value = OUTPUT_PRESETS.find((item) => item.value === value)?.value || "";
  }

  function applySettingsToForm(settings) {
    setInputValue("#outputTemplate", settings.outputTemplate);
    setSelectValue("#singleType", settings.singleType);
    setSelectValue("#batchType", settings.batchType);
    setSelectValue("#batchExportMode", settings.batchExportMode);
    setSelectValue("#singleLang", settings.singleLang);
    setSelectValue("#batchLang", settings.batchLang);
    setInputValue("#singleGeneral", settings.singleGeneral);
    setInputValue("#singleCharacter", settings.singleCharacter);
    setInputValue("#batchGeneral", settings.batchGeneral);
    setInputValue("#batchCharacter", settings.batchCharacter);
    setChecked("#singleGeneralMcut", settings.singleGeneralMcut);
    setChecked("#singleCharacterMcut", settings.singleCharacterMcut);
    setChecked("#batchGeneralMcut", settings.batchGeneralMcut);
    setChecked("#batchCharacterMcut", settings.batchCharacterMcut);
    syncPresetSelect(settings.outputTemplate);
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
    state.busy = value;
    document.body.classList.toggle("busy", value);
    $("#singleSubmit").disabled = value;
    $("#batchSubmit").disabled = value;
    $("#healthBtn").disabled = value;
  }

  function renderBackendStatus(payload, error = null) {
    const target = $("#backendStatus");
    if (error) {
      target.innerHTML = `<span style="color: var(--bad);">连接失败：${flags.escapeHtml(error)}</span>`;
      return;
    }
    const providers = Array.isArray(payload.providers) ? payload.providers.join(", ") : String(payload.providers || "-");
    target.innerHTML = [
      `<div>状态：<strong style="color: var(--good);">${flags.escapeHtml(payload.status || "ok")}</strong></div>`,
      `<div>模型：${flags.escapeHtml(payload.model_dir || "-")}</div>`,
      `<div>Provider：${flags.escapeHtml(providers)}</div>`,
      `<div>鉴权：${payload.auth_enabled ? "已开启" : "未开启"}</div>`,
    ].join("");
  }

  function clearDownloads() {
    for (const url of state.lastDownloads) URL.revokeObjectURL(url);
    state.lastDownloads = [];
    $("#downloadArea").innerHTML = "";
  }

  function addDownloadLink(label, blob, filename) {
    const url = URL.createObjectURL(blob);
    state.lastDownloads.push(url);
    const link = document.createElement("a");
    link.className = "download-link";
    link.href = url;
    link.download = filename;
    link.textContent = `${label}: ${filename}`;
    $("#downloadArea").appendChild(link);
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

  function renderTiming(headers, extra = {}) {
    const metrics = [
      ["后端模型耗时", headers.processMs ? `${headers.processMs} ms` : "-"],
      ["后端总耗时", headers.totalMs ? `${headers.totalMs} ms` : "-"],
      ["当前 RSS", headers.rss ? `${headers.rss} MB` : "-"],
      ["峰值 RSS", headers.peakRss ? `${headers.peakRss} MB` : "-"],
      ["用户态 CPU", headers.cpuUser ? `${headers.cpuUser} s` : "-"],
      ["内核态 CPU", headers.cpuSys ? `${headers.cpuSys} s` : "-"],
    ];
    if (extra.totalElapsedMs != null) metrics.unshift(["前端总耗时", `${extra.totalElapsedMs} ms`]);
    $("#timingArea").innerHTML = metrics.map(([name, value]) => (
      `<article class="metric-card"><h4>${flags.escapeHtml(name)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`
    )).join("");
  }

  function renderFlagSummary(view) {
    $("#flagArea").innerHTML = `
      <div class="summary-card">
        <h4>不合适标签</h4>
        <strong>${flags.escapeHtml(view.flaggedTags.join(", ") || "无")}</strong>
      </div>
    `;
  }

  function renderSingleTags(payload) {
    const view = flags.buildHighlightedTagsHtml(payload);
    renderFlagSummary(view);
    $("#resultArea").innerHTML = `
      <div class="summary-card">
        <h4>标签结果</h4>
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
    const metricHtml = summaryCards.map(([title, value]) => (
      `<article class="summary-card"><h4>${flags.escapeHtml(title)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`
    )).join("");
    const extraHtml = [
      ["模型累计耗时", metrics.inference_elapsed_ms != null ? `${metrics.inference_elapsed_ms} ms` : "-"],
      ["后端处理总耗时", metrics.total_elapsed_ms != null ? `${metrics.total_elapsed_ms} ms` : "-"],
      ["CPU 耗时", metrics.cpu_elapsed_ms != null ? `${metrics.cpu_elapsed_ms} ms` : "-"],
    ].map(([title, value]) => (
      `<article class="metric-card"><h4>${flags.escapeHtml(title)}</h4><strong>${flags.escapeHtml(value)}</strong></article>`
    )).join("");
    const flaggedItems = items
      .map((item) => {
        const view = flags.buildHighlightedTagsHtml(item);
        if (!view.flaggedTags.length && !Object.keys(view.flaggedRatings).length) return "";
        const ratings = Object.entries(view.flaggedRatings).map(([k, v]) => `${k}: ${v}`).join(", ");
        return `
          <article class="flag-card">
            <h4>${flags.escapeHtml(item.filename || "image")}</h4>
            <strong>${flags.escapeHtml(view.flaggedTags.join(", ") || "无")}</strong>
            <div class="muted" style="margin-top:6px;">评分：${flags.escapeHtml(ratings || "-")}</div>
          </article>
        `;
      })
      .filter(Boolean)
      .join("");
    $("#flagArea").innerHTML = flaggedItems || '<div class="summary-card"><h4>不合适标签</h4><strong>本次没有命中明显的不合适标签</strong></div>';
    $("#resultArea").innerHTML = `
      <div class="grid-stack">
        <div class="grid-2">${metricHtml}</div>
        <div class="grid-2">${extraHtml}</div>
        <div class="summary-card">
          <h4>批量明细</h4>
          <strong>${flags.escapeHtml(`输入 ${items.length} 张，输出 ${payload.success_count ?? items.length} 张`)}</strong>
        </div>
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
  }

  async function submitSingle() {
    const settings = collectSettings();
    saveSettings(settings);
    clearDownloads();
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
        addDownloadLink("下载图片", blob, filename);
        $("#flagArea").innerHTML = '<div class="summary-card"><h4>不合适标签</h4><strong>tagimg 模式由后端导出图片文件</strong></div>';
        $("#resultArea").innerHTML = `<div class="summary-card"><h4>文件已生成</h4><strong>${flags.escapeHtml(filename)}</strong></div>`;
      }
      renderTiming(headers, { totalElapsedMs: Math.round(performance.now() - start) });
    } catch (error) {
      $("#resultArea").innerHTML = `<div class="summary-card"><h4>错误</h4><strong style="color: var(--bad);">${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
    } finally {
      setBusy(false);
    }
  }

  async function submitBatch() {
    const settings = collectSettings();
    saveSettings(settings);
    clearDownloads();
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
        const jsonBlob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
        const csvBlob = new Blob([buildBatchCsv(payload)], { type: "text/csv;charset=utf-8" });
        if (settings.batchExportMode === "json" || settings.batchExportMode === "both") addDownloadLink("JSON", jsonBlob, "results.json");
        if (settings.batchExportMode === "csv" || settings.batchExportMode === "both") addDownloadLink("CSV", csvBlob, "results.csv");
      } else {
        const blob = await response.blob();
        const filename = extractFilename(headers.disposition, "tagged_images.zip");
        addDownloadLink("下载 ZIP", blob, filename);
        $("#flagArea").innerHTML = '<div class="summary-card"><h4>不合适标签</h4><strong>ZIP 结果由后端直接返回</strong></div>';
        $("#resultArea").innerHTML = `<div class="summary-card"><h4>批量导出</h4><strong>${flags.escapeHtml(filename)}</strong></div>`;
      }
      renderTiming(headers, { totalElapsedMs: Math.round(performance.now() - start) });
    } catch (error) {
      $("#resultArea").innerHTML = `<div class="summary-card"><h4>错误</h4><strong style="color: var(--bad);">${flags.escapeHtml(error instanceof Error ? error.message : String(error))}</strong></div>`;
    } finally {
      setBusy(false);
    }
  }

  function bindTabs() {
    $$(".tab").forEach((button) => {
      button.addEventListener("click", () => {
        $$(".tab").forEach((item) => item.classList.remove("active"));
        $$(".pane").forEach((pane) => pane.classList.remove("active"));
        button.classList.add("active");
        $(`#${button.dataset.target}`).classList.add("active");
      });
    });
    $$(".source-tab").forEach((button) => {
      button.addEventListener("click", () => {
        const group = button.closest(".pane");
        $$(".source-tab", group).forEach((item) => item.classList.remove("active"));
        $$(".source-pane", group).forEach((pane) => pane.classList.remove("active"));
        button.classList.add("active");
        $(`#${button.dataset.target}`, group).classList.add("active");
      });
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
    $("#batchType").addEventListener("change", toggleBatchExportMode);
    $("#singleFile").addEventListener("change", () => {
      const file = $("#singleFile").files[0];
      $("#singlePreview").textContent = file ? `${file.name} (${Math.round(file.size / 1024)} KB)` : "尚未选择图片";
      if (file) {
        const reader = new FileReader();
        reader.onload = () => {
          $("#singlePreview").innerHTML = `<img src="${reader.result}" alt="preview" style="max-width:100%;max-height:260px;border-radius:14px;display:block;" />`;
        };
        reader.readAsDataURL(file);
      }
    });
    $("#batchFilesInput").addEventListener("change", () => {
      const files = Array.from($("#batchFilesInput").files || []);
      $("#batchFileList").innerHTML = files.length
        ? files.map((file) => `<div>${flags.escapeHtml(file.name)} <span class="muted">(${Math.round(file.size / 1024)} KB)</span></div>`).join("")
        : "尚未选择文件";
    });
  }

  function init() {
    const settings = loadSettings();
    syncPresetSelect(settings.outputTemplate);
    applySettingsToForm(settings);
    bindTabs();
    bindSettings();
    $("#healthBtn").addEventListener("click", checkBackend);
    $("#singleSubmit").addEventListener("click", submitSingle);
    $("#batchSubmit").addEventListener("click", submitBatch);
    toggleBatchExportMode();
    checkBackend();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
