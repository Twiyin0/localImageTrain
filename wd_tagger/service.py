from __future__ import annotations

import os
import platform
import resource
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from wd_tagger.config import (
    DEFAULT_CHARACTER_THRESHOLD,
    DEFAULT_GENERAL_THRESHOLD,
    DEFAULT_ONNX_REPO,
    get_runtime_paths,
)
from wd_tagger.models import OnnxTagger, mcut_threshold


@dataclass(frozen=True)
class PredictionOptions:
    repo_id: str = DEFAULT_ONNX_REPO
    model_dir: str | None = None
    general_threshold: float = DEFAULT_GENERAL_THRESHOLD
    character_threshold: float = DEFAULT_CHARACTER_THRESHOLD
    general_mcut: bool = False
    character_mcut: bool = False


def _bytes_to_mb(value: float) -> float:
    return round(value / (1024 * 1024), 2)


def _read_current_rss_bytes() -> float | None:
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


def collect_process_metrics() -> dict:
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


def localize_metrics(metrics: dict) -> dict:
    current_rss = metrics.get("process_current_rss_mb")
    peak_rss = metrics.get("process_peak_rss_mb")
    return {
        "总耗时": f"{metrics['total_elapsed_ms']} ms",
        "模型推理耗时": f"{metrics['inference_elapsed_ms']} ms",
        "本次 CPU 耗时": f"{metrics['cpu_elapsed_ms']} ms",
        "当前进程内存占用": f"{current_rss} MB" if current_rss is not None else "不可用",
        "当前进程内存峰值": f"{peak_rss} MB" if peak_rss is not None else "不可用",
        "累计用户态 CPU 时间": f"{metrics['cpu_user_time_s']} s",
        "累计内核态 CPU 时间": f"{metrics['cpu_system_time_s']} s",
    }


class TaggerService:
    def __init__(self) -> None:
        self.runtime = get_runtime_paths()
        self._cache: dict[tuple[str, str | None, tuple[str, ...]], OnnxTagger] = {}

    def _get_tagger(
        self,
        repo_id: str,
        model_dir: str | None,
        providers: list[str],
    ) -> OnnxTagger:
        key = (repo_id, model_dir, tuple(providers))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        tagger = OnnxTagger(
            repo_id=repo_id,
            cache_dir=self.runtime.cache_dir,
            providers=providers,
            local_model_dir=model_dir,
        )
        self._cache[key] = tagger
        return tagger

    def predict_from_image(
        self,
        image: Image.Image,
        options: PredictionOptions,
        providers: list[str],
    ) -> dict:
        started_at = time.perf_counter()
        cpu_started_at = time.process_time()
        tagger = self._get_tagger(
            repo_id=options.repo_id,
            model_dir=options.model_dir,
            providers=providers,
        )

        inference_started_at = time.perf_counter()
        scores = tagger.predict(image)
        inference_elapsed_ms = round((time.perf_counter() - inference_started_at) * 1000, 2)
        meta = tagger.tag_metadata
        labels = list(zip(meta.tag_names, scores.tolist()))

        rating = {labels[idx][0]: labels[idx][1] for idx in meta.rating_indexes}
        general = [labels[idx] for idx in meta.general_indexes]
        characters = [labels[idx] for idx in meta.character_indexes]

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

        selected_general = {
            name: score for name, score in general if score >= general_threshold
        }
        selected_characters = {
            name: score for name, score in characters if score >= character_threshold
        }

        ordered_general = sorted(
            selected_general.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        ordered_characters = sorted(
            selected_characters.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        metrics = collect_process_metrics()
        metrics.update(
            {
                "total_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "inference_elapsed_ms": inference_elapsed_ms,
                "cpu_elapsed_ms": round((time.process_time() - cpu_started_at) * 1000, 2),
            }
        )

        return {
            "repo_id": options.repo_id,
            "model_dir": str(Path(options.model_dir).resolve()) if options.model_dir else None,
            "providers": tagger.active_providers,
            "thresholds": {
                "general": general_threshold,
                "character": character_threshold,
            },
            "rating": rating,
            "characters": dict(ordered_characters),
            "general": dict(ordered_general),
            "caption": ", ".join(name for name, _ in ordered_general),
            "metrics": metrics,
        }
