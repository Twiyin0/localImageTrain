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


def normalize_tag(tag: str) -> str:
    return " ".join(tag.strip().lower().replace("_", " ").split())


def split_caption_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def extract_tags(payload: dict[str, Any] | list[Any] | str | None) -> list[str]:
    if isinstance(payload, dict):
        general = payload.get("general")
        if isinstance(general, dict):
            return [str(tag) for tag in general.keys()]
        caption = payload.get("caption")
        if isinstance(caption, str):
            return split_caption_tags(caption)
        return []
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    if isinstance(payload, str):
        return split_caption_tags(payload)
    return []


def extract_flagged_ratings(payload: dict[str, Any] | None, threshold: float = 0.2) -> dict[str, float]:
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
    tags = extract_tags(payload)
    unsuitable_tags = extract_unsuitable_tags(tags)
    flagged_ratings = extract_flagged_ratings(payload if isinstance(payload, dict) else None)
    summary = {
        "flagged_tags": unsuitable_tags,
        "flagged_tag_count": len(unsuitable_tags),
        "flagged_ratings": flagged_ratings,
        "has_inappropriate_content": bool(unsuitable_tags or flagged_ratings),
    }
    return build_highlighted_tags_html(tags, unsuitable_tags), summary
