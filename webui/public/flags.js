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
    "insertion",
    "large breasts",
    "lingerie",
    "masturbation",
    "no panties",
    "nip slip",
    "nipples",
    "nude",
    "object insertion",
    "open clothes",
    "open shirt",
    "panties aside",
    "panties",
    "pants pulled down",
    "partial nudity",
    "penis",
    "pantyshot",
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
    "spread pussy",
    "testicles",
    "thighhighs pull",
    "topless",
    "underboob",
    "underwear only",
    "undressing",
    "unsafe for work",
    "vaginal",
    "vibrator",
    "very large breasts",
    "wet clothes",
    "wet shirt",
    "yuri",
    "not safe for work",
    "nsfw",
    "不适合工作场合",
    "敏感",
    "擦边",
    "露骨",
    "成人",
    "裸露",
    "裸体",
    "全裸",
    "胸部",
    "巨乳",
    "乳头",
    "内衣",
    "胖次",
    "阴部",
    "下体",
    "私处",
    "性玩具",
    "插入",
    "自慰",
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
    "crotch",
    "cum",
    "deepthroat",
    "dildo",
    "erection",
    "fellatio",
    "genital",
    "groin",
    "handjob",
    "insertion",
    "labia",
    "masturbat",
    "nipple",
    "nude",
    "object insertion",
    "panties",
    "pantyshot",
    "penis",
    "pubic",
    "pussy",
    "sex",
    "testicle",
    "topless",
    "underboob",
    "undress",
    "unsafe for work",
    "vaginal",
    "vagina",
    "vibrator",
    "vulva",
    "nsfw",
    "不适合",
    "敏感",
    "擦边",
    "露骨",
    "裸",
    "胸",
    "乳",
    "内衣",
    "胖次",
    "阴部",
    "下体",
    "私处",
    "性玩具",
    "插入",
    "自慰",
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
    return extractTagEntries(payload).map((entry) => entry.display);
  }

  function extractOriginalTags(payload) {
    return extractTagEntries(payload).map((entry) => entry.original);
  }

  function extractTagEntries(payload) {
    if (Array.isArray(payload)) {
      return payload
        .map((item) => String(item).trim())
        .filter(Boolean)
        .map((tag) => ({ display: tag, original: tag }));
    }
    if (payload && typeof payload === "object") {
      const captionDisplay = typeof payload.caption_display === "string"
        ? payload.caption_display
        : typeof payload.caption === "string" ? payload.caption : "";
      if (captionDisplay) {
        const displayTags = splitCaptionTags(captionDisplay);
        const originalTags = typeof payload.caption_original === "string"
          ? splitCaptionTags(payload.caption_original)
          : displayTags;
        return displayTags.map((tag, index) => ({ display: tag, original: originalTags[index] || tag }));
      }
      if (payload.general && typeof payload.general === "object") {
        const originalTags = Object.keys(payload.general).map((tag) => String(tag));
        const displayTags = payload.general_display && typeof payload.general_display === "object"
          ? Object.keys(payload.general_display).map((tag) => String(tag))
          : originalTags;
        return originalTags.map((tag, index) => ({ display: displayTags[index] || tag, original: tag }));
      }
      if (payload.general_display && typeof payload.general_display === "object") {
        return Object.keys(payload.general_display)
          .map((tag) => String(tag))
          .map((tag) => ({ display: tag, original: tag }));
      }
      if (typeof payload.tags === "string") {
        return splitCaptionTags(payload.tags).map((tag) => ({ display: tag, original: tag }));
      }
    }
    if (typeof payload === "string") {
      return splitCaptionTags(payload).map((tag) => ({ display: tag, original: tag }));
    }
    return [];
  }

  function extractFlaggedRatings(payload, threshold = 0.2) {
    if (!payload || typeof payload !== "object") {
      return {};
    }
    if (payload.risk && typeof payload.risk === "object" && payload.risk.flagged_ratings && typeof payload.risk.flagged_ratings === "object") {
      return payload.risk.flagged_ratings;
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
      if (isUnsuitableTag(tag)) {
        flagged.push(tag);
      }
    }
    return flagged;
  }

  function isUnsuitableTag(tag) {
    const normalized = normalizeTag(tag);
    return exact.includes(normalized) || substrings.some((fragment) => normalized.includes(fragment));
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
    const entries = extractTagEntries(payload);
    const flaggedRatings = extractFlaggedRatings(payload);
    const riskPairs = payload && typeof payload === "object" && payload.risk && typeof payload.risk === "object" && Array.isArray(payload.risk.flagged_tag_pairs)
      ? payload.risk.flagged_tag_pairs
      : null;
    const flaggedOriginalSet = riskPairs
      ? new Set(riskPairs.map((entry) => normalizeTag(entry.original)))
      : null;
    const flaggedDisplaySet = riskPairs
      ? new Set(riskPairs.map((entry) => normalizeTag(entry.display || entry.original)))
      : null;
    const flaggedEntries = entries.map((entry) => (
      flaggedOriginalSet
        ? flaggedOriginalSet.has(normalizeTag(entry.original)) || flaggedDisplaySet.has(normalizeTag(entry.display))
        : isUnsuitableTag(entry.original) || isUnsuitableTag(entry.display)
    ));
    const chips = entries.map((entry, index) => {
      const isFlagged = flaggedEntries[index];
      return `<span class="tag-chip ${isFlagged ? "flagged" : ""}" title="${escapeHtml(entry.original)}">${escapeHtml(entry.display)}</span>`;
    });
    if (Object.keys(flaggedRatings).length && !entries.some((entry) => normalizeTag(entry.original) === "nsfw" || normalizeTag(entry.display) === "nsfw")) {
      chips.unshift('<span class="tag-chip flagged" title="rating">NSFW</span>');
    }
    return {
      tags: entries.map((entry) => entry.display),
      originalTags: entries.map((entry) => entry.original),
      flaggedTagPairs: riskPairs
        ? riskPairs.map((entry) => ({ original: String(entry.original || ""), display: String(entry.display || entry.original || "") }))
        : entries
          .filter((entry, index) => flaggedEntries[index])
          .map((entry) => ({ original: entry.original, display: entry.display })),
      flaggedTags: entries
        .filter((entry, index) => flaggedEntries[index])
        .map((entry) => entry.display),
      flaggedRatings,
      html: chips.length ? `<div class="tag-chips">${chips.join("")}</div>` : '<div class="muted">没有可展示的标签</div>',
    };
  }

  window.WDTagFlags = {
    normalizeTag,
    splitCaptionTags,
    extractTags,
    extractOriginalTags,
    extractFlaggedRatings,
    extractUnsuitableTags,
    isUnsuitableTag,
    buildHighlightedTagsHtml,
    escapeHtml,
  };
})();
