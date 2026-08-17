(() => {
  const exact = [
    "1girl 1boy",
    "2girls 1boy",
    "2boys 1girl",
    "after sex",
    "anus",
    "areola slip",
    "areolae",
    "ass focus",
    "ass grab",
    "ass",
    "bdsm",
    "bikini pull",
    "breast grab",
    "breast press",
    "breasts apart",
    "breasts",
    "cameltoe",
    "censored",
    "clothed female nude male",
    "completely nude",
    "condom",
    "cum in mouth",
    "cum on body",
    "cum on breasts",
    "cum on face",
    "cum",
    "deepthroat",
    "dildo",
    "erection",
    "explicit",
    "fellatio",
    "from behind",
    "groping",
    "handjob",
    "implied sex",
    "large breasts",
    "lingerie",
    "masturbation",
    "nip slip",
    "nipples",
    "nude",
    "open clothes",
    "open shirt",
    "panties aside",
    "pants pulled down",
    "partial nudity",
    "penis",
    "pov crotch",
    "pubic hair",
    "pussy",
    "questionable",
    "rape",
    "sex",
    "sex from behind",
    "sex toy",
    "sexually suggestive",
    "sideboob",
    "sensitive",
    "skirt lift",
    "spread legs",
    "testicles",
    "thighhighs pull",
    "topless",
    "underboob",
    "underwear only",
    "undressing",
    "vaginal",
    "very large breasts",
    "wet clothes",
    "wet shirt",
    "yuri",
  ];

  const substrings = [
    "anal",
    "anus",
    "areola",
    "bdsm",
    "breast",
    "cameltoe",
    "censored",
    "condom",
    "cum",
    "deepthroat",
    "dildo",
    "erection",
    "fellatio",
    "handjob",
    "masturbat",
    "nipple",
    "nude",
    "penis",
    "pubic",
    "pussy",
    "sex",
    "testicle",
    "topless",
    "underboob",
    "undress",
    "vaginal",
  ];

  const ratings = ["sensitive", "questionable", "explicit"];

  function normalizeTag(tag) {
    return String(tag || "")
      .trim()
      .toLowerCase()
      .replaceAll("_", " ")
      .replace(/\s+/g, " ");
  }

  function splitCaptionTags(value) {
    return String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function extractTags(payload) {
    if (Array.isArray(payload)) {
      return payload.map((item) => String(item).trim()).filter(Boolean);
    }
    if (payload && typeof payload === "object") {
      if (payload.general_display && typeof payload.general_display === "object") {
        return Object.keys(payload.general_display).map((tag) => String(tag));
      }
      if (payload.general && typeof payload.general === "object") {
        return Object.keys(payload.general).map((tag) => String(tag));
      }
      if (typeof payload.caption === "string") {
        return splitCaptionTags(payload.caption);
      }
      if (typeof payload.tags === "string") {
        return splitCaptionTags(payload.tags);
      }
    }
    if (typeof payload === "string") {
      return splitCaptionTags(payload);
    }
    return [];
  }

  function extractFlaggedRatings(payload, threshold = 0.2) {
    if (!payload || typeof payload !== "object") {
      return {};
    }
    const rating = payload.rating;
    if (!rating || typeof rating !== "object") {
      return {};
    }
    const flagged = {};
    for (const name of ratings) {
      const score = rating[name];
      if (typeof score === "number" && score >= threshold) {
        flagged[name] = Number(score.toFixed(4));
      }
    }
    return flagged;
  }

  function extractUnsuitableTags(tags) {
    const flagged = [];
    for (const tag of tags) {
      const normalized = normalizeTag(tag);
      if (exact.includes(normalized) || substrings.some((fragment) => normalized.includes(fragment))) {
        flagged.push(tag);
      }
    }
    return flagged;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function buildHighlightedTagsHtml(payload) {
    const tags = extractTags(payload);
    const flagged = new Set(extractUnsuitableTags(tags).map(normalizeTag));
    const chips = tags.map((tag) => {
      const normalized = normalizeTag(tag);
      const isFlagged = flagged.has(normalized);
      return `<span class="tag-chip ${isFlagged ? "flagged" : ""}">${escapeHtml(tag)}</span>`;
    });
    return {
      tags,
      flaggedTags: extractUnsuitableTags(tags),
      flaggedRatings: extractFlaggedRatings(payload),
      html: chips.length ? `<div class="tag-chips">${chips.join("")}</div>` : '<div class="muted">没有可展示的标签</div>',
    };
  }

  window.WDTagFlags = {
    normalizeTag,
    splitCaptionTags,
    extractTags,
    extractFlaggedRatings,
    extractUnsuitableTags,
    buildHighlightedTagsHtml,
    escapeHtml,
  };
})();
