from __future__ import annotations

import json
from typing import Sequence
from urllib import request


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
