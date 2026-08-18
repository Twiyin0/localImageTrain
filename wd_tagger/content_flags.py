from __future__ import annotations

from html import escape
from typing import Any


UNSUITABLE_EXACT_TAGS = {
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
}

UNSUITABLE_SUBSTRINGS = (
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
)

FLAGGED_RATINGS = ("sensitive", "questionable", "explicit")
DEFAULT_SENSITIVE_THRESHOLD = 0.7


def normalize_tag(tag: str) -> str:
    return " ".join(tag.strip().lower().replace("_", " ").split())


def split_caption_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def extract_tag_entries(payload: dict[str, Any] | list[Any] | str | None) -> list[dict[str, str]]:
    if isinstance(payload, dict):
        caption_display = payload.get("caption_display")
        caption_original = payload.get("caption_original")
        if isinstance(caption_display, str) and caption_display.strip():
            display_tags = split_caption_tags(caption_display)
            original_tags = split_caption_tags(caption_original) if isinstance(caption_original, str) else display_tags
            return [
                {
                    "original": str(original_tags[index] if index < len(original_tags) else tag),
                    "display": str(tag),
                }
                for index, tag in enumerate(display_tags)
            ]
        general = payload.get("general")
        if isinstance(general, dict):
            original_tags = [str(tag) for tag in general.keys()]
            general_display = payload.get("general_display")
            if isinstance(general_display, dict):
                display_tags = [str(tag) for tag in general_display.keys()]
            else:
                display_tags = original_tags
            return [
                {
                    "original": tag,
                    "display": str(display_tags[index] if index < len(display_tags) else tag),
                }
                for index, tag in enumerate(original_tags)
            ]
        caption = payload.get("caption")
        if isinstance(caption, str):
            return [{"original": tag, "display": tag} for tag in split_caption_tags(caption)]
        return []
    if isinstance(payload, list):
        return [
            {"original": str(item).strip(), "display": str(item).strip()}
            for item in payload
            if str(item).strip()
        ]
    if isinstance(payload, str):
        return [{"original": tag, "display": tag} for tag in split_caption_tags(payload)]
    return []


def extract_tags(payload: dict[str, Any] | list[Any] | str | None) -> list[str]:
    return [str(entry.get("original", "")).strip() for entry in extract_tag_entries(payload) if str(entry.get("original", "")).strip()]


def extract_flagged_ratings(
    payload: dict[str, Any] | None,
    threshold: float = DEFAULT_SENSITIVE_THRESHOLD,
) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    ratings = payload.get("rating")
    if not isinstance(ratings, dict):
        return {}

    flagged: dict[str, float] = {}
    for label in FLAGGED_RATINGS:
        score = ratings.get(label)
        if isinstance(score, (int, float)) and float(score) >= threshold:
            flagged[label] = round(float(score), 4)
    return flagged


def extract_unsuitable_tags(tags: list[str]) -> list[str]:
    flagged: list[str] = []
    for tag in tags:
        normalized = normalize_tag(tag)
        if normalized in UNSUITABLE_EXACT_TAGS or any(fragment in normalized for fragment in UNSUITABLE_SUBSTRINGS):
            flagged.append(tag)
    return flagged


def summarize_risk(
    payload: dict[str, Any] | list[Any] | str | None,
    *,
    sensitive_threshold: float = DEFAULT_SENSITIVE_THRESHOLD,
) -> dict[str, Any]:
    entries = extract_tag_entries(payload)
    original_tags = [str(entry.get("original", "")) for entry in entries if str(entry.get("original", "")).strip()]
    unsuitable_original_tags = extract_unsuitable_tags(original_tags)
    unsuitable_set = {normalize_tag(tag) for tag in unsuitable_original_tags}
    flagged_pairs = [
        {
            "original": str(entry.get("original", "")),
            "display": str(entry.get("display", entry.get("original", ""))),
        }
        for entry in entries
        if normalize_tag(str(entry.get("original", ""))) in unsuitable_set
    ]
    flagged_ratings = extract_flagged_ratings(
        payload if isinstance(payload, dict) else None,
        threshold=sensitive_threshold,
    )
    return {
        "flagged_tags": [pair["display"] for pair in flagged_pairs],
        "flagged_tags_original": [pair["original"] for pair in flagged_pairs],
        "flagged_tag_pairs": flagged_pairs,
        "flagged_tag_count": len(flagged_pairs),
        "flagged_ratings": flagged_ratings,
        "sensitive_threshold": round(float(sensitive_threshold), 4),
        "has_inappropriate_content": bool(flagged_pairs or flagged_ratings),
    }


def build_highlighted_tags_html(tags: list[str], unsuitable_tags: list[str]) -> str:
    if not tags:
        return "<div>No tags available.</div>"

    flagged_set = {normalize_tag(tag) for tag in unsuitable_tags}
    parts = [
        """
<div style="display:flex;flex-wrap:wrap;gap:8px;">
"""
    ]
    for tag in tags:
        normalized = normalize_tag(tag)
        is_flagged = normalized in flagged_set
        background = "#5b1f24" if is_flagged else "#1f3b2d"
        border = "#ff7b7b" if is_flagged else "#4da67c"
        color = "#fff5f5" if is_flagged else "#edfdf5"
        parts.append(
            f'<span style="padding:6px 10px;border-radius:999px;border:1px solid {border};'
            f'background:{background};color:{color};font-size:13px;">{escape(tag)}</span>'
        )
    parts.append("</div>")
    return "".join(parts)


def build_flagged_summary(payload: dict[str, Any] | list[Any] | str | None) -> tuple[str, dict[str, Any]]:
    entries = extract_tag_entries(payload)
    display_tags = [str(entry.get("display", "")) for entry in entries if str(entry.get("display", "")).strip()]
    summary = summarize_risk(payload)
    return build_highlighted_tags_html(display_tags, list(summary.get("flagged_tags", []))), summary
