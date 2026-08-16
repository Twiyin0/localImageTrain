from __future__ import annotations

import json
import re
from typing import Sequence
from urllib import request


TAG_TRANSLATION_OVERRIDES = {
    "1girl": "1个女孩",
    "solo": "单人",
    "socks": "袜子",
    "white socks": "白袜",
    "no shoes": "没穿鞋",
    "feet": "脚",
    "foot focus": "脚部特写",
    "shoes": "鞋子",
    "close-up": "特写",
    "indoors": "室内",
    "outdoors": "户外",
    "lower body": "下半身",
    "unworn shoes": "未穿的鞋子",
    "white pantyhose": "白色连裤袜",
    "pantyhose": "连裤袜",
    "wand": "魔杖",
    "holding wand": "手持魔杖",
    "holding": "手持",
    "sitting": "坐着",
    "dress": "连衣裙",
    "blue dress": "蓝色连衣裙",
    "long hair": "长发",
    "bow": "蝴蝶结",
    "hair bow": "发饰蝴蝶结",
    "black bow": "黑色蝴蝶结",
    "looking at viewer": "看向观众",
    "blonde hair": "金发",
    "white hair": "白发",
    "antenna hair": "触角发",
    "ahoge": "呆毛",
    "realistic": "写实",
    "full body": "全身",
}

REPEATED_LEADING_CJK = re.compile(r"^([\u4e00-\u9fff])\1+")


def _normalize_translate_url(endpoint: str) -> str:
    cleaned = endpoint.strip().rstrip("/")
    if cleaned.endswith("/translate"):
        return cleaned
    return f"{cleaned}/translate"


def _normalize_health_url(endpoint: str) -> str:
    cleaned = endpoint.strip().rstrip("/")
    if cleaned.endswith("/health"):
        return cleaned
    return f"{cleaned}/health"


def translate_texts(
    endpoint: str | None,
    texts: Sequence[str],
    *,
    source_lang: str | None = None,
    target_lang: str | None = None,
    beam_size: int = 1,
    max_decoding_length: int = 128,
    timeout_s: float = 8.0,
) -> list[str] | None:
    if not endpoint:
        return None

    clean_texts = [str(text).strip() for text in texts]
    if not clean_texts:
        return []

    payload_data: dict[str, object] = {
        "text": clean_texts,
        "beam_size": beam_size,
        "max_decoding_length": max_decoding_length,
    }
    if source_lang:
        payload_data["source_lang"] = source_lang
    if target_lang:
        payload_data["target_lang"] = target_lang

    payload = json.dumps(payload_data, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        _normalize_translate_url(endpoint),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    translations = data.get("translations")
    if not isinstance(translations, list) or len(translations) != len(clean_texts):
        return None
    return [str(item) for item in translations]


def _normalize_tag_key(text: str) -> str:
    return " ".join(text.strip().lower().replace("_", " ").split())


def _clean_translated_term(text: str) -> str:
    cleaned = str(text).strip()
    parts = cleaned.split()
    if parts and all(part == parts[0] for part in parts):
        cleaned = parts[0]
    if len(cleaned) % 2 == 0:
        midpoint = len(cleaned) // 2
        if cleaned[:midpoint] == cleaned[midpoint:]:
            cleaned = cleaned[:midpoint]
    return REPEATED_LEADING_CJK.sub(r"\1", cleaned)


def translate_terms_one_by_one(
    endpoint: str | None,
    texts: Sequence[str],
    *,
    source_lang: str | None = None,
    target_lang: str | None = None,
    beam_size: int = 1,
    max_decoding_length: int = 64,
    timeout_s: float = 8.0,
) -> list[str] | None:
    if not endpoint:
        return None

    clean_texts = [str(text).strip() for text in texts]
    if not clean_texts:
        return []

    translated: list[str] = []
    for text in clean_texts:
        override = TAG_TRANSLATION_OVERRIDES.get(_normalize_tag_key(text))
        if override:
            translated.append(override)
            continue
        result = translate_texts(
            endpoint,
            [text],
            source_lang=source_lang,
            target_lang=target_lang,
            beam_size=beam_size,
            max_decoding_length=max_decoding_length,
            timeout_s=timeout_s,
        )
        translated.append(_clean_translated_term(result[0]) if result and len(result) == 1 else text)
    return translated


def translation_api_is_healthy(endpoint: str | None, timeout_s: float = 3.0) -> bool:
    if not endpoint:
        return False

    req = request.Request(_normalize_health_url(endpoint), method="GET")
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            if not 200 <= int(getattr(resp, "status", 200)) < 300:
                return False
            body = resp.read().decode("utf-8").strip()
    except Exception:
        return False

    if not body:
        return True
    try:
        data = json.loads(body)
    except Exception:
        return True
    return str(data.get("status", "")).lower() == "ok"
