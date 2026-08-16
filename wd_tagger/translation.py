from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAG_TRANSLATION_CSV_PATH = PROJECT_ROOT / "datasets" / "selected_tags_cn.csv"

TAG_TRANSLATION_OVERRIDES = {
    "1girl": "1个女孩",
    "1boy": "1个男孩",
    "2girls": "2个女孩",
    "multiple girls": "多个女孩",
    "solo": "单人",
    "socks": "袜",
    "white socks": "白丝",
    "stockings": "长筒袜",
    "white stockings": "白丝",
    "thighhighs": "过膝袜",
    "white thighhighs": "白丝",
    "pantyhose": "连裤袜",
    "white pantyhose": "白丝",
    "white legwear": "白丝",
    "no shoes": "没穿鞋",
    "barefoot": "赤足",
    "feet": "足",
    "foot focus": "足部特写",
    "toes": "足趾",
    "soles": "足底",
    "legs": "腿",
    "bare legs": "裸腿",
    "thighs": "大腿",
    "knees": "膝盖",
    "shoes": "鞋子",
    "footwear": "鞋",
    "black footwear": "黑鞋",
    "close-up": "特写",
    "indoors": "室内",
    "outdoors": "户外",
    "lower body": "下半身",
    "unworn shoes": "未穿的鞋子",
    "wand": "魔杖",
    "holding wand": "手持魔杖",
    "holding": "手持",
    "sitting": "坐着",
    "standing": "站立",
    "dress": "连衣裙",
    "blue dress": "蓝色连衣裙",
    "skirt": "裙子",
    "capelet": "披肩",
    "long hair": "长发",
    "bow": "蝴蝶结",
    "hair bow": "发饰蝴蝶结",
    "black bow": "黑色蝴蝶结",
    "looking at viewer": "看向观众",
    "blonde hair": "金毛",
    "white hair": "白毛",
    "black hair": "黑毛",
    "brown hair": "棕毛",
    "blue hair": "蓝毛",
    "pink hair": "粉毛",
    "red hair": "红毛",
    "green hair": "绿毛",
    "purple hair": "紫毛",
    "silver hair": "银毛",
    "grey hair": "灰毛",
    "gray hair": "灰毛",
    "multicolored hair": "多色发",
    "short hair": "短发",
    "medium hair": "中长发",
    "antenna hair": "触角发",
    "ahoge": "呆毛",
    "realistic": "写实",
    "full body": "全身",
    "phone": "手机",
    "cellphone": "手机",
    "smartphone": "智能手机",
    "holding phone": "手持手机",
    "selfie": "自拍",
    "black pantyhose": "黑丝",
    "black stockings": "黑丝",
    "black socks": "黑袜",
    "jewelry": "首饰",
    "necklace": "项链",
    "door": "门",
    "mirror": "镜子",
    "virtual youtuber": "虚拟主播",
}

def _normalize_tag_key(text: str) -> str:
    return " ".join(text.strip().lower().replace("_", " ").split())


@lru_cache(maxsize=1)
def load_selected_tag_translations() -> dict[str, str]:
    if not TAG_TRANSLATION_CSV_PATH.exists():
        return {}

    translations: dict[str, str] = {}
    try:
        with TAG_TRANSLATION_CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                name = str(row.get("name", "")).strip()
                translated_name = str(row.get("translatedname", "")).strip()
                if name and translated_name:
                    translations[_normalize_tag_key(name)] = translated_name
    except Exception:
        return {}
    return translations


def lookup_tag_translation(text: str) -> str | None:
    key = _normalize_tag_key(text)
    return load_selected_tag_translations().get(key) or TAG_TRANSLATION_OVERRIDES.get(key)


def translate_terms_from_table(texts: Sequence[str]) -> list[str]:
    clean_texts = [str(text).strip() for text in texts]
    if not clean_texts:
        return []

    translated: list[str] = []
    for text in clean_texts:
        translated.append(lookup_tag_translation(text) or text)
    return translated
