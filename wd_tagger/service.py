from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import os
import sqlite3
import platform
import threading
import subprocess
import sys
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from time import perf_counter, process_time, time
from typing import Any
from uuid import uuid4
import zipfile

import numpy as np
from PIL import ExifTags, Image, PngImagePlugin

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    find_local_model_dir,
    get_runtime_paths,
)
from wd_tagger.models import OnnxTagger, mcut_threshold
from wd_tagger.translation import translate_terms_from_table
from wd_tagger.utils import ensure_dir

IMAGE_DESCRIPTION_TAG = ExifTags.Base.ImageDescription
USER_COMMENT_TAG = 37510
SQLITE_CACHE_FILENAME = "prediction_cache.sqlite3"
DEFAULT_OUTPUT_FILENAME_TEMPLATE = "${origin_filename}_tagged${origin_ext}"
DEFAULT_BATCH_ARCHIVE_TEMPLATE = "${origin_filename}_tagged.zip"
WINDOWS_FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _bytes_to_mb(value: float) -> float:
    return round(value / (1024 * 1024), 2)


def sanitize_output_filename(filename: str, fallback: str = "output") -> str:
    cleaned = WINDOWS_FORBIDDEN_FILENAME_CHARS.sub("_", Path(filename).name.strip())
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def render_output_filename(
    template: str | None,
    *,
    origin_name: str,
    default_ext: str,
    process_type: str,
    index: int | None = None,
) -> str:
    raw_template = (template or DEFAULT_OUTPUT_FILENAME_TEMPLATE).strip() or DEFAULT_OUTPUT_FILENAME_TEMPLATE
    origin_path = Path(origin_name or "output")
    now = datetime.now()
    origin_ext = origin_path.suffix or default_ext
    if not origin_ext.startswith("."):
        origin_ext = f".{origin_ext}"
    origin_filename = origin_path.stem or "output"
    values = {
        "origin_filename": origin_filename,
        "origin_stem": origin_filename,
        "origin_basename": origin_path.name or f"{origin_filename}{origin_ext}",
        "origin_ext": origin_ext,
        "ext": origin_ext,
        "type": process_type,
        "index": str(index or 1),
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
        "timestamp": now.strftime("%Y%m%d_%H%M%S"),
    }
    rendered = raw_template
    for key, value in values.items():
        rendered = rendered.replace("${" + key + "}", value)
    if rendered.endswith(".xxx"):
        rendered = rendered[:-4] + origin_ext
    rendered = sanitize_output_filename(rendered)
    if not Path(rendered).suffix:
        rendered = f"{rendered}{default_ext}"
    return rendered


def _read_macos_current_rss_bytes() -> float | None:
    class TimeValue(ctypes.Structure):
        _fields_ = [("seconds", ctypes.c_int32), ("microseconds", ctypes.c_int32)]

    class MachTaskBasicInfo(ctypes.Structure):
        _fields_ = [
            ("virtual_size", ctypes.c_uint64),
            ("resident_size", ctypes.c_uint64),
            ("resident_size_max", ctypes.c_uint64),
            ("user_time", TimeValue),
            ("system_time", TimeValue),
            ("policy", ctypes.c_int32),
            ("suspend_count", ctypes.c_int32),
        ]

    try:
        libsystem = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        libsystem.mach_task_self.restype = ctypes.c_uint32
        libsystem.task_info.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        info = MachTaskBasicInfo()
        count = ctypes.c_uint32(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_int))
        result = libsystem.task_info(
            libsystem.mach_task_self(),
            20,  # MACH_TASK_BASIC_INFO
            ctypes.cast(ctypes.byref(info), ctypes.POINTER(ctypes.c_int)),
            ctypes.byref(count),
        )
        return float(info.resident_size) if result == 0 else None
    except Exception:
        return None


def _read_current_rss_bytes() -> float | None:
    if sys.platform == "darwin":
        return _read_macos_current_rss_bytes()
    if sys.platform.startswith("linux"):
        status_path = Path("/proc/self/status")
        if status_path.exists():
            for line in status_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return float(parts[1]) * 1024
    try:
        output = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            text=True,
        ).strip()
        if output:
            return float(output) * 1024
    except Exception:
        return None
    return None


def collect_process_metrics() -> dict[str, float | None]:
    if os.name == "nt":
        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32),
            ]

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        def filetime_to_seconds(value: FILETIME) -> float:
            raw = (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)
            return raw / 10_000_000.0

        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        handle = kernel32.GetCurrentProcess()
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        current_rss = None
        peak_rss = None
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            current_rss = float(counters.WorkingSetSize)
            peak_rss = float(counters.PeakWorkingSetSize)
        creation_time = FILETIME()
        exit_time = FILETIME()
        kernel_time = FILETIME()
        user_time = FILETIME()
        cpu_user_time = None
        cpu_system_time = None
        if kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation_time),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            cpu_user_time = filetime_to_seconds(user_time)
            cpu_system_time = filetime_to_seconds(kernel_time)
        return {
            "process_current_rss_mb": _bytes_to_mb(current_rss) if current_rss is not None else None,
            "process_peak_rss_mb": _bytes_to_mb(peak_rss) if peak_rss is not None else None,
            "cpu_user_time_s": round(cpu_user_time, 4) if cpu_user_time is not None else None,
            "cpu_system_time_s": round(cpu_system_time, 4) if cpu_system_time is not None else None,
        }

    try:
        import resource
    except Exception:
        return {
            "process_current_rss_mb": None,
            "process_peak_rss_mb": None,
            "cpu_user_time_s": None,
            "cpu_system_time_s": None,
        }

    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss_value = float(usage.ru_maxrss)
    if platform.system() != "Darwin":
        rss_value *= 1024
    current_rss_bytes = _read_current_rss_bytes()
    return {
        "process_current_rss_mb": (
            _bytes_to_mb(current_rss_bytes) if current_rss_bytes is not None else None
        ),
        "process_peak_rss_mb": _bytes_to_mb(rss_value),
        "cpu_user_time_s": round(float(usage.ru_utime), 4),
        "cpu_system_time_s": round(float(usage.ru_stime), 4),
    }


def localize_metrics(metrics: dict[str, Any] | None) -> dict[str, str]:
    if not metrics:
        return {}
    current_rss = metrics.get("process_current_rss_mb")
    peak_rss = metrics.get("process_peak_rss_mb")
    return {
        "总耗时": f"{metrics.get('total_elapsed_ms')} ms",
        "模型推理耗时": f"{metrics.get('inference_elapsed_ms')} ms",
        "本次 CPU 耗时": f"{metrics.get('cpu_elapsed_ms')} ms",
        "当前进程内存占用": f"{current_rss} MB" if current_rss is not None else "不可用",
        "当前进程内存峰值": f"{peak_rss} MB" if peak_rss is not None else "不可用",
        "累计用户态 CPU 时间": f"{metrics.get('cpu_user_time_s')} s",
        "累计内核态 CPU 时间": f"{metrics.get('cpu_system_time_s')} s",
    }


@dataclass(frozen=True)
class ImageSource:
    filename: str
    image: Image.Image
    content_type: str
    source_path: str | None = None
    source_bytes: bytes | None = None

    @classmethod
    def from_bytes(
        cls,
        *,
        filename: str,
        content_type: str,
        source_bytes: bytes,
        source_path: str | None = None,
    ) -> ImageSource:
        return cls(
            filename=filename,
            image=Image.open(BytesIO(source_bytes)).convert("RGBA"),
            content_type=content_type,
            source_path=source_path,
            source_bytes=source_bytes,
        )


@dataclass(frozen=True)
class PredictionOptions:
    repo_id: str = DEFAULT_ONNX_REPO
    model_dir: str | None = None
    general_threshold: float = DEFAULT_GENERAL_THRESHOLD
    character_threshold: float = DEFAULT_CHARACTER_THRESHOLD
    general_mcut: bool = False
    character_mcut: bool = False
    lang: str | None = None
    translation_mode: str = "zh"


class TaggerService:
    def __init__(self) -> None:
        self.runtime = get_runtime_paths()
        self._tagger_cache: dict[tuple[str, str | None, tuple[str, ...]], OnnxTagger] = {}
        self.export_root = ensure_dir(self.runtime.output_dir / "api_exports")

        self.exact_cache_enabled = os.getenv("WD_TAGGER_EXACT_CACHE_ENABLED", "1") != "0"
        self.similar_cache_enabled = os.getenv("WD_TAGGER_SIMILAR_CACHE_ENABLED", "1") != "0"
        self.similarity_threshold = float(os.getenv("WD_TAGGER_SIMILARITY_THRESHOLD", "0.985"))
        self.similar_candidate_limit = max(1, int(os.getenv("WD_TAGGER_SIMILAR_CANDIDATE_LIMIT", "128")))
        self.cache_max_entries = max(1, int(os.getenv("WD_TAGGER_CACHE_MAX_ENTRIES", "5000")))
        self.memory_cache_size = max(1, int(os.getenv("WD_TAGGER_MEMORY_CACHE_SIZE", "512")))

        self.cache_db_path = self.runtime.cache_dir / SQLITE_CACHE_FILENAME
        self._db_lock = threading.Lock()
        self._db = sqlite3.connect(self.cache_db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_db()

        self._exact_memory_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()

    def _init_db(self) -> None:
        with self._db_lock:
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS prediction_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_key TEXT NOT NULL,
                    source_md5 TEXT NOT NULL,
                    pixel_md5 TEXT NOT NULL,
                    signature_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    filename TEXT,
                    source_path TEXT,
                    created_ts REAL NOT NULL,
                    last_used_ts REAL NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_cache_model_source ON prediction_cache(model_key, source_md5)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_prediction_cache_model_pixel ON prediction_cache(model_key, pixel_md5)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_prediction_cache_model_last_used ON prediction_cache(model_key, last_used_ts DESC)"
            )
            self._db.commit()

    def _get_tagger(
        self,
        repo_id: str,
        model_dir: str | None,
        providers: list[str],
    ) -> OnnxTagger:
        resolved_model_dir = self._resolve_model_dir(repo_id, model_dir)
        key = (repo_id, resolved_model_dir, tuple(providers))
        cached = self._tagger_cache.get(key)
        if cached is not None:
            return cached

        tagger = OnnxTagger(
            repo_id=repo_id,
            cache_dir=self.runtime.cache_dir,
            providers=providers,
            local_model_dir=resolved_model_dir,
        )
        self._tagger_cache[key] = tagger
        return tagger

    @staticmethod
    def _resolved_model_dir(model_dir: str | None) -> str | None:
        return str(Path(model_dir).resolve()) if model_dir else None

    def _resolve_model_dir(self, repo_id: str, model_dir: str | None) -> str | None:
        return self._resolved_model_dir(model_dir) or find_local_model_dir(
            repo_id=repo_id,
            project_root=self.runtime.project_root,
        )

    def _build_model_key(
        self,
        repo_id: str,
        model_dir: str | None,
        providers: list[str],
    ) -> str:
        provider_key = ",".join(str(provider) for provider in providers)
        return f"{repo_id}|{self._resolved_model_dir(model_dir) or ''}|{provider_key}"

    @staticmethod
    def _cache_key(model_key: str, hash_value: str) -> tuple[str, str]:
        return model_key, hash_value

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "model_key": str(row["model_key"]),
            "source_md5": str(row["source_md5"]),
            "pixel_md5": str(row["pixel_md5"]),
            "signature": json.loads(str(row["signature_json"])),
            "raw": json.loads(str(row["raw_json"])),
            "filename": row["filename"],
            "source_path": row["source_path"],
            "created_ts": float(row["created_ts"]),
            "last_used_ts": float(row["last_used_ts"]),
            "hits": int(row["hits"]),
        }

    def _remember_exact_entry(self, entry: dict[str, Any]) -> None:
        for hash_value in {entry.get("source_md5"), entry.get("pixel_md5")}:
            if not hash_value:
                continue
            key = self._cache_key(str(entry["model_key"]), str(hash_value))
            self._exact_memory_cache[key] = entry
            self._exact_memory_cache.move_to_end(key)

        while len(self._exact_memory_cache) > self.memory_cache_size:
            self._exact_memory_cache.popitem(last=False)

    def _get_exact_from_memory(self, model_key: str, hashes: list[str]) -> dict[str, Any] | None:
        for hash_value in hashes:
            entry = self._exact_memory_cache.get(self._cache_key(model_key, hash_value))
            if entry is not None:
                self._exact_memory_cache.move_to_end(self._cache_key(model_key, hash_value))
                return entry
        return None

    def _fetch_exact_from_db(self, model_key: str, source_md5: str, pixel_md5: str) -> dict[str, Any] | None:
        with self._db_lock:
            row = self._db.execute(
                """
                SELECT * FROM prediction_cache
                WHERE model_key = ? AND source_md5 = ?
                LIMIT 1
                """,
                (model_key, source_md5),
            ).fetchone()

            if row is None and pixel_md5 != source_md5:
                row = self._db.execute(
                    """
                    SELECT * FROM prediction_cache
                    WHERE model_key = ? AND pixel_md5 = ?
                    ORDER BY last_used_ts DESC
                    LIMIT 1
                    """,
                    (model_key, pixel_md5),
                ).fetchone()

        if row is None:
            return None
        entry = self._row_to_entry(row)
        self._remember_exact_entry(entry)
        return entry

    def _update_entry_usage(self, entry_id: int) -> None:
        now = time()
        with self._db_lock:
            self._db.execute(
                """
                UPDATE prediction_cache
                SET last_used_ts = ?, hits = hits + 1
                WHERE id = ?
                """,
                (now, entry_id),
            )
            self._db.commit()

    def _trim_db(self) -> None:
        with self._db_lock:
            count_row = self._db.execute("SELECT COUNT(*) AS count FROM prediction_cache").fetchone()
            total = int(count_row["count"]) if count_row is not None else 0
            excess = total - self.cache_max_entries
            if excess <= 0:
                return

            rows = self._db.execute(
                """
                SELECT id, model_key, source_md5, pixel_md5
                FROM prediction_cache
                ORDER BY last_used_ts ASC
                LIMIT ?
                """,
                (excess,),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if not ids:
                return

            placeholders = ",".join("?" for _ in ids)
            self._db.execute(f"DELETE FROM prediction_cache WHERE id IN ({placeholders})", ids)
            self._db.commit()

            removed_keys = {
                self._cache_key(str(row["model_key"]), str(hash_value))
                for row in rows
                for hash_value in (row["source_md5"], row["pixel_md5"])
                if hash_value
            }
            for key in removed_keys:
                self._exact_memory_cache.pop(key, None)

    def _store_entry(
        self,
        *,
        model_key: str,
        source_md5: str,
        pixel_md5: str,
        signature: dict[str, Any],
        raw: dict[str, Any],
        source: ImageSource,
    ) -> dict[str, Any]:
        now = time()
        with self._db_lock:
            self._db.execute(
                """
                INSERT INTO prediction_cache (
                    model_key, source_md5, pixel_md5, signature_json, raw_json,
                    filename, source_path, created_ts, last_used_ts, hits
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(model_key, source_md5) DO UPDATE SET
                    pixel_md5 = excluded.pixel_md5,
                    signature_json = excluded.signature_json,
                    raw_json = excluded.raw_json,
                    filename = excluded.filename,
                    source_path = excluded.source_path,
                    last_used_ts = excluded.last_used_ts
                """,
                (
                    model_key,
                    source_md5,
                    pixel_md5,
                    json.dumps(signature, ensure_ascii=False),
                    json.dumps(raw, ensure_ascii=False),
                    source.filename,
                    source.source_path,
                    now,
                    now,
                ),
            )
            self._db.commit()

            row = self._db.execute(
                """
                SELECT * FROM prediction_cache
                WHERE model_key = ? AND source_md5 = ?
                LIMIT 1
                """,
                (model_key, source_md5),
            ).fetchone()

        assert row is not None
        entry = self._row_to_entry(row)
        self._remember_exact_entry(entry)
        self._trim_db()
        return entry

    @staticmethod
    def _hash_bytes(payload: bytes) -> str:
        return hashlib.md5(payload).hexdigest()

    @staticmethod
    def _image_to_png_bytes(image: Image.Image) -> bytes:
        buffer = BytesIO()
        image.convert("RGBA").save(buffer, format="PNG")
        return buffer.getvalue()

    def _get_source_bytes(self, source: ImageSource) -> bytes:
        if source.source_bytes is not None:
            return source.source_bytes
        if source.source_path:
            path = Path(source.source_path)
            if path.exists() and path.is_file():
                return path.read_bytes()
        return self._image_to_png_bytes(source.image)

    @staticmethod
    def _compute_dhash(image: Image.Image) -> str:
        grayscale = image.convert("L").resize((9, 8), Image.Resampling.BICUBIC)
        pixels = np.asarray(grayscale, dtype=np.int16)
        bits = pixels[:, 1:] > pixels[:, :-1]
        value = 0
        for bit in bits.flatten():
            value = (value << 1) | int(bool(bit))
        return f"{value:016x}"

    @staticmethod
    def _compute_visual_signature(image: Image.Image) -> dict[str, Any]:
        rgb = image.convert("RGB")
        grayscale_thumb = rgb.convert("L").resize((8, 8), Image.Resampling.BICUBIC)
        thumb = np.asarray(grayscale_thumb, dtype=np.uint8).flatten().tolist()
        mean_rgb = np.asarray(rgb.resize((1, 1), Image.Resampling.BICUBIC), dtype=np.uint8).reshape(-1).tolist()
        width, height = rgb.size
        return {
            "thumb": thumb,
            "dhash": TaggerService._compute_dhash(rgb),
            "mean_rgb": mean_rgb,
            "aspect_ratio": round(width / max(height, 1), 6),
            "size": [width, height],
        }

    @staticmethod
    def _hamming_distance(left: str, right: str) -> int:
        return (int(left, 16) ^ int(right, 16)).bit_count()

    @staticmethod
    def _cosine_similarity(left: list[int], right: list[int]) -> float:
        left_array = np.asarray(left, dtype=np.float32)
        right_array = np.asarray(right, dtype=np.float32)
        left_norm = float(np.linalg.norm(left_array))
        right_norm = float(np.linalg.norm(right_array))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return float(np.dot(left_array, right_array) / (left_norm * right_norm))

    @staticmethod
    def _mean_rgb_similarity(left: list[int], right: list[int]) -> float:
        diff = np.mean(np.abs(np.asarray(left, dtype=np.float32) - np.asarray(right, dtype=np.float32)))
        return max(0.0, 1.0 - float(diff / 255.0))

    @staticmethod
    def _aspect_similarity(left: float, right: float) -> float:
        maximum = max(abs(left), abs(right), 1e-6)
        return max(0.0, 1.0 - abs(left - right) / maximum)

    def _similarity_components(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
        thumb_score = self._cosine_similarity(
            list(left.get("thumb", [])),
            list(right.get("thumb", [])),
        )
        dhash_score = 1.0 - self._hamming_distance(
            str(left.get("dhash", "0")),
            str(right.get("dhash", "0")),
        ) / 64.0
        color_score = self._mean_rgb_similarity(
            list(left.get("mean_rgb", [0, 0, 0])),
            list(right.get("mean_rgb", [0, 0, 0])),
        )
        aspect_score = self._aspect_similarity(
            float(left.get("aspect_ratio", 1.0)),
            float(right.get("aspect_ratio", 1.0)),
        )
        combined = thumb_score * 0.55 + dhash_score * 0.25 + color_score * 0.1 + aspect_score * 0.1
        return {
            "combined": round(combined, 6),
            "thumb": round(thumb_score, 6),
            "dhash": round(dhash_score, 6),
            "color": round(color_score, 6),
            "aspect": round(aspect_score, 6),
        }

    def _fetch_recent_candidates(self, model_key: str) -> list[dict[str, Any]]:
        with self._db_lock:
            rows = self._db.execute(
                """
                SELECT * FROM prediction_cache
                WHERE model_key = ?
                ORDER BY last_used_ts DESC
                LIMIT ?
                """,
                (model_key, self.similar_candidate_limit),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def _find_similar_entry(
        self,
        model_key: str,
        signature: dict[str, Any],
        excluded_hashes: set[str],
    ) -> tuple[dict[str, Any] | None, dict[str, float] | None]:
        if not self.similar_cache_enabled:
            return None, None

        best_entry: dict[str, Any] | None = None
        best_components: dict[str, float] | None = None
        for entry in self._fetch_recent_candidates(model_key):
            if entry.get("source_md5") in excluded_hashes or entry.get("pixel_md5") in excluded_hashes:
                continue

            components = self._similarity_components(signature, dict(entry.get("signature", {})))
            if components["combined"] < self.similarity_threshold:
                continue
            if components["thumb"] < 0.995 or components["dhash"] < 0.95 or components["aspect"] < 0.97:
                continue

            if best_components is None or components["combined"] > best_components["combined"]:
                best_entry = entry
                best_components = components

        return best_entry, best_components

    @staticmethod
    def _build_raw_prediction(
        *,
        repo_id: str,
        model_dir: str | None,
        providers: list[str],
        rating: dict[str, float],
        general: list[tuple[str, float]],
        characters: list[tuple[str, float]],
    ) -> dict[str, Any]:
        return {
            "repo_id": repo_id,
            "model_dir": model_dir,
            "providers": providers,
            "rating": rating,
            "general_scores": [[name, float(score)] for name, score in general],
            "character_scores": [[name, float(score)] for name, score in characters],
        }

    @staticmethod
    def _normalize_translation_mode(mode: str | None) -> str:
        normalized = (mode or "original").strip().lower()
        if normalized in {"zh", "zh-cn", "cn", "chinese", "translate"}:
            return "zh"
        return "original"

    @staticmethod
    def _normalize_output_lang(lang: str | None) -> str | None:
        normalized = (lang or "").strip().lower()
        if normalized in {"zh", "zh-cn", "cn", "chinese"}:
            return "zh"
        if normalized in {"en", "en-us", "english"}:
            return "en"
        return None

    def _resolve_output_lang(self, options: PredictionOptions) -> tuple[str, bool]:
        explicit_lang = self._normalize_output_lang(options.lang)
        if explicit_lang is not None:
            return explicit_lang, explicit_lang == "zh"

        legacy_mode = self._normalize_translation_mode(options.translation_mode)
        if legacy_mode == "original":
            return "en", False
        return "zh", True

    def _predict_raw_from_source(
        self,
        source: ImageSource,
        options: PredictionOptions,
        providers: list[str],
        *,
        allow_similar: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        model_dir = self._resolve_model_dir(options.repo_id, options.model_dir)
        model_key = self._build_model_key(options.repo_id, model_dir, providers)
        source_md5 = self._hash_bytes(self._get_source_bytes(source))
        pixel_md5 = self._hash_bytes(self._image_to_png_bytes(source.image))
        signature = self._compute_visual_signature(source.image)

        if self.exact_cache_enabled:
            entry = self._get_exact_from_memory(model_key, [source_md5, pixel_md5])
            if entry is None:
                entry = self._fetch_exact_from_db(model_key, source_md5, pixel_md5)
            if entry is not None:
                self._update_entry_usage(int(entry["id"]))
                self._remember_exact_entry(entry)
                return dict(entry["raw"]), {
                    "cache_hit": "exact",
                    "source_md5": source_md5,
                    "pixel_md5": pixel_md5,
                    "matched_source_md5": entry.get("source_md5"),
                    "matched_pixel_md5": entry.get("pixel_md5"),
                    "similarity_score": 1.0,
                }

        if allow_similar:
            similar_entry, similarity_components = self._find_similar_entry(
                model_key,
                signature,
                {source_md5, pixel_md5},
            )
            if similar_entry is not None and similarity_components is not None:
                self._update_entry_usage(int(similar_entry["id"]))
                self._store_entry(
                    model_key=model_key,
                    source_md5=source_md5,
                    pixel_md5=pixel_md5,
                    signature=signature,
                    raw=dict(similar_entry["raw"]),
                    source=source,
                )
                return dict(similar_entry["raw"]), {
                    "cache_hit": "similar",
                    "source_md5": source_md5,
                    "pixel_md5": pixel_md5,
                    "matched_source_md5": similar_entry.get("source_md5"),
                    "matched_pixel_md5": similar_entry.get("pixel_md5"),
                    "similarity_score": similarity_components["combined"],
                    "similarity_components": similarity_components,
                }

        tagger = self._get_tagger(
            repo_id=options.repo_id,
            model_dir=model_dir,
            providers=providers,
        )
        scores = tagger.predict(source.image)
        meta = tagger.tag_metadata
        labels = list(zip(meta.tag_names, scores.tolist()))

        rating = {labels[idx][0]: labels[idx][1] for idx in meta.rating_indexes}
        general = [labels[idx] for idx in meta.general_indexes]
        characters = [labels[idx] for idx in meta.character_indexes]
        raw = self._build_raw_prediction(
            repo_id=options.repo_id,
            model_dir=model_dir,
            providers=tagger.active_providers,
            rating=rating,
            general=general,
            characters=characters,
        )
        self._store_entry(
            model_key=model_key,
            source_md5=source_md5,
            pixel_md5=pixel_md5,
            signature=signature,
            raw=raw,
            source=source,
        )
        return raw, {
            "cache_hit": "miss",
            "source_md5": source_md5,
            "pixel_md5": pixel_md5,
            "matched_source_md5": None,
            "matched_pixel_md5": None,
            "similarity_score": None,
        }

    def _finalize_payload(self, raw: dict[str, Any], options: PredictionOptions, cache_info: dict[str, Any]) -> dict[str, Any]:
        general = [(str(name), float(score)) for name, score in raw.get("general_scores", [])]
        characters = [(str(name), float(score)) for name, score in raw.get("character_scores", [])]
        rating = {str(name): float(score) for name, score in dict(raw.get("rating", {})).items()}

        general_threshold = (
            mcut_threshold([score for _, score in general])
            if options.general_mcut
            else options.general_threshold
        )
        character_threshold = (
            max(0.15, mcut_threshold([score for _, score in characters]))
            if options.character_mcut
            else options.character_threshold
        )

        ordered_general = sorted(
            [(name, score) for name, score in general if score >= general_threshold],
            key=lambda item: item[1],
            reverse=True,
        )
        ordered_characters = sorted(
            [(name, score) for name, score in characters if score >= character_threshold],
            key=lambda item: item[1],
            reverse=True,
        )

        caption_original = ", ".join(name for name, _ in ordered_general)
        translation_mode = self._normalize_translation_mode(options.translation_mode)
        output_lang, translation_requested = self._resolve_output_lang(options)
        display_general = ordered_general
        display_characters = ordered_characters
        translated = False
        if output_lang == "zh":
            general_names = [name for name, _ in ordered_general]
            character_names = [name for name, _ in ordered_characters]
            translated_names = translate_terms_from_table([*general_names, *character_names])
            if translated_names and len(translated_names) == len(general_names) + len(character_names):
                translated = True
                translated_general_names = translated_names[: len(general_names)]
                translated_character_names = translated_names[len(general_names) :]
                display_general = [
                    (name, score)
                    for name, (_, score) in zip(translated_general_names, ordered_general, strict=True)
                ]
                display_characters = [
                    (name, score)
                    for name, (_, score) in zip(translated_character_names, ordered_characters, strict=True)
                ]
        caption_display = ", ".join(name for name, _ in display_general)

        return {
            "repo_id": raw.get("repo_id", options.repo_id),
            "model_dir": raw.get("model_dir"),
            "providers": raw.get("providers", []),
            "thresholds": {
                "general": general_threshold,
                "character": character_threshold,
            },
            "rating": rating,
            "characters": dict(ordered_characters),
            "general": dict(ordered_general),
            "characters_display": dict(display_characters),
            "general_display": dict(display_general),
            "caption": caption_display if translated else caption_original,
            "caption_original": caption_original,
            "caption_display": caption_display if translated else caption_original,
            "translation": {
                "lang": output_lang,
                "mode": translation_mode,
                "source": "datasets/selected_tags_cn.csv" if translated else None,
                "available": translated,
                "requested": translation_requested,
            },
            "cache": cache_info,
        }

    def predict_from_source(
        self,
        source: ImageSource,
        options: PredictionOptions,
        providers: list[str],
        *,
        allow_similar: bool = False,
    ) -> dict:
        started_at = perf_counter()
        cpu_started_at = process_time()
        inference_started_at = perf_counter()
        raw, cache_info = self._predict_raw_from_source(
            source,
            options=options,
            providers=providers,
            allow_similar=allow_similar,
        )
        inference_elapsed_ms = round((perf_counter() - inference_started_at) * 1000, 2)
        payload = self._finalize_payload(raw, options, cache_info)
        metrics = collect_process_metrics()
        metrics.update(
            {
                "total_elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                "inference_elapsed_ms": inference_elapsed_ms,
                "cpu_elapsed_ms": round((process_time() - cpu_started_at) * 1000, 2),
            }
        )
        payload["metrics"] = metrics
        return payload

    def predict_from_image(
        self,
        image: Image.Image,
        options: PredictionOptions,
        providers: list[str],
        *,
        allow_similar: bool = False,
    ) -> dict:
        return self.predict_from_source(
            ImageSource(
                filename="image.png",
                image=image.convert("RGBA"),
                content_type="image/png",
            ),
            options=options,
            providers=providers,
            allow_similar=allow_similar,
        )

    def create_request_dir(self, prefix: str) -> Path:
        return ensure_dir(self.export_root / f"{prefix}_{uuid4().hex[:12]}")

    @staticmethod
    def extract_tag_array(payload: dict) -> list[str]:
        display_general = payload.get("general_display")
        if isinstance(display_general, dict) and display_general:
            return list(display_general.keys())
        return list(payload.get("general", {}).keys())

    @staticmethod
    def build_batch_rows(items: list[dict]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in items:
            cache = item.get("cache", {}) if isinstance(item.get("cache"), dict) else {}
            rows.append(
                {
                    "filename": item.get("filename"),
                    "ok": item.get("ok", True),
                    "caption": item.get("caption", ""),
                    "tags": "|".join(TaggerService.extract_tag_array(item)) if item.get("ok", True) else "",
                    "cache_hit": cache.get("cache_hit", ""),
                    "similarity_score": cache.get("similarity_score", ""),
                    "error": item.get("error", ""),
                }
            )
        return rows

    def write_batch_json(self, output_dir: Path, payload: dict, output_template: str | None = None) -> Path:
        filename = render_output_filename(
            output_template or "${origin_filename}${origin_ext}",
            origin_name="results.json",
            default_ext=".json",
            process_type="json",
        )
        path = ensure_unique_path(output_dir / filename)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_batch_csv(self, output_dir: Path, rows: list[dict[str, Any]], output_template: str | None = None) -> Path:
        filename = render_output_filename(
            output_template or "${origin_filename}${origin_ext}",
            origin_name="results.csv",
            default_ext=".csv",
            process_type="json",
        )
        path = ensure_unique_path(output_dir / filename)
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["filename", "ok", "caption", "tags", "cache_hit", "similarity_score", "error"],
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_tagged_image(
        self,
        output_dir: Path,
        source: ImageSource,
        payload: dict,
        output_template: str | None = None,
        index: int | None = None,
    ) -> Path:
        suffix = Path(source.filename).suffix.lower()
        safe_suffix = suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
        output_filename = render_output_filename(
            output_template,
            origin_name=source.filename,
            default_ext=safe_suffix,
            process_type="tagimg",
            index=index,
        )
        output_path = ensure_unique_path(output_dir / output_filename)
        safe_suffix = output_path.suffix.lower()
        if safe_suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            safe_suffix = ".png"
            output_path = ensure_unique_path(output_path.with_suffix(".png"))

        caption = payload["caption"]
        tags = self.extract_tag_array(payload)
        metadata_text = json.dumps(
            {
                "caption": caption,
                "tags": tags,
                "rating": payload.get("rating", {}),
                "characters": payload.get("characters", {}),
                "cache": payload.get("cache", {}),
            },
            ensure_ascii=False,
        )

        image = source.image.copy()
        if safe_suffix == ".png":
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("Caption", caption)
            png_info.add_text("Tags", ", ".join(tags))
            png_info.add_text("WDTagger", metadata_text)
            image.save(output_path, pnginfo=png_info)
            return output_path

        save_image = image.convert("RGB") if safe_suffix in {".jpg", ".jpeg"} else image
        exif = save_image.getexif()
        exif[IMAGE_DESCRIPTION_TAG] = caption
        try:
            exif[USER_COMMENT_TAG] = metadata_text
        except Exception:
            pass
        try:
            save_image.save(output_path, exif=exif.tobytes())
            return output_path
        except Exception:
            fallback = ensure_unique_path(output_path.with_suffix(".png"))
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("Caption", caption)
            png_info.add_text("Tags", ", ".join(tags))
            png_info.add_text("WDTagger", metadata_text)
            image.save(fallback, pnginfo=png_info)
            return fallback

    def zip_paths(self, output_dir: Path, archive_name: str, files: list[Path]) -> Path:
        zip_path = ensure_unique_path(output_dir / sanitize_output_filename(archive_name, "archive.zip"))
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, arcname=file.name)
        return zip_path

    def zip_tagged_images(self, output_dir: Path, tagged_files: list[Path]) -> Path:
        return self.zip_paths(output_dir, "tagged_images.zip", tagged_files)

    def package_json_and_csv(
        self,
        output_dir: Path,
        payload: dict,
        rows: list[dict[str, Any]],
        output_template: str | None = None,
    ) -> tuple[Path, Path, Path]:
        json_path = self.write_batch_json(output_dir, payload, output_template)
        csv_path = self.write_batch_csv(output_dir, rows, output_template)
        archive_name = render_output_filename(
            output_template or "${origin_filename}_bundle${origin_ext}",
            origin_name="results.zip",
            default_ext=".zip",
            process_type="json",
        )
        zip_path = self.zip_paths(output_dir, archive_name, [json_path, csv_path])
        return json_path, csv_path, zip_path
