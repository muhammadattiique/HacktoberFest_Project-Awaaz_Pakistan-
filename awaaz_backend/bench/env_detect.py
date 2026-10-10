"""Phase 0 baseline: target hardware / environment detection.

Writes results/baseline/env.json describing CPU, RAM, GPU/CUDA, OS, Python,
the configured Whisper model, and whether the configured Ollama model is present.

Run from the awaaz_backend directory with the baseline venv:
    python bench/env_detect.py

Only reads configuration; never touches the real awaaz.db.
"""
import json
import os
import platform
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
OUT = HERE / "results" / "baseline" / "env.json"
sys.path[:0] = [str(HERE), str(BACKEND)]

# Strip any app-setting overrides inherited from the caller's shell (e.g. a
# WHISPER_MODEL=tiny or DATABASE_URL left over from the UI-baseline step) so
# env.json reflects the repository defaults, not the current terminal session.
from _common import clean_app_env  # noqa: E402

_clean_env, _removed_overrides, _explicit = clean_app_env()
os.environ.clear()
os.environ.update(_clean_env)


def _safe(fn, default="NOT MEASURED"):
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - best-effort probe
        return f"{default}: {exc}"


def cpu_info() -> dict:
    info = {
        "processor": platform.processor() or "unknown",
        "machine": platform.machine(),
    }
    try:
        import psutil

        info["physical_cores"] = psutil.cpu_count(logical=False)
        info["logical_cores"] = psutil.cpu_count(logical=True)
    except Exception as exc:
        info["cores_error"] = str(exc)
    # Windows: richer CPU name via registry/env
    info["processor_identifier"] = os.environ.get("PROCESSOR_IDENTIFIER", "unknown")
    info["num_processors_env"] = os.environ.get("NUMBER_OF_PROCESSORS", "unknown")
    return info


def ram_info() -> dict:
    try:
        import psutil

        vm = psutil.virtual_memory()
        return {
            "total_bytes": vm.total,
            "total_gib": round(vm.total / (1024 ** 3), 2),
            "available_gib": round(vm.available / (1024 ** 3), 2),
        }
    except Exception as exc:
        return {"error": f"NOT MEASURED: {exc}"}


def gpu_info() -> dict:
    out = {}
    try:
        import torch

        out["torch_version"] = torch.__version__
        out["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            out["cuda_device_count"] = torch.cuda.device_count()
            out["cuda_device_name"] = torch.cuda.get_device_name(0)
            out["cuda_version"] = torch.version.cuda
        else:
            out["note"] = "CUDA not available; torch is CPU build."
    except Exception as exc:
        out["torch_error"] = f"NOT MEASURED: {exc}"
    return out


def whisper_config() -> dict:
    try:
        from config import settings

        return {
            "whisper_model": settings.WHISPER_MODEL,
            "whisper_device": settings.WHISPER_DEVICE,
            "audio_max_duration_seconds": settings.AUDIO_MAX_DURATION_SECONDS,
            "upload_max_bytes": settings.UPLOAD_MAX_BYTES,
            "ollama_model_configured": settings.OLLAMA_MODEL,
            "ollama_base_url": settings.OLLAMA_BASE_URL,
        }
    except Exception as exc:
        return {"error": f"NOT MEASURED: {exc}"}


def ollama_models(base_url: str) -> dict:
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name") for m in data.get("models", [])]
        return {"reachable": True, "url": url, "models": names, "raw": data.get("models", [])}
    except Exception as exc:
        return {"reachable": False, "url": url, "error": f"NOT MEASURED: {exc}"}


def main() -> None:
    cfg = whisper_config()
    base_url = cfg.get("ollama_base_url", "http://localhost:11434") if isinstance(cfg, dict) else "http://localhost:11434"
    tags = ollama_models(base_url)
    configured_model = cfg.get("ollama_model_configured") if isinstance(cfg, dict) else None
    model_present = None
    if tags.get("reachable"):
        names = tags.get("models", [])
        model_present = configured_model in names
        # also check loose base name (qwen2.5:1.5b vs qwen2.5:1.5b-instruct)
        if not model_present and configured_model:
            base = configured_model.split("-")[0]
            model_present = any(n.startswith(base) for n in names)

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "platform": platform.platform(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "cpu": cpu_info(),
        "ram": ram_info(),
        "gpu": gpu_info(),
        "whisper": {k: v for k, v in cfg.items() if k.startswith("whisper") or k.startswith("audio") or k.startswith("upload")} if isinstance(cfg, dict) else cfg,
        "ollama": {
            **tags,
            "configured_model": configured_model,
            "configured_model_present": model_present,
        },
        "inherited_shell_overrides_ignored": _removed_overrides,
        "notes": [
            "psutil installed into the temporary baseline venv only; requirements.txt unchanged.",
            "Whisper model name is read from config.settings.WHISPER_MODEL (defaults to 'base').",
            "App-setting env vars inherited from the shell were cleared before reading config so this reflects repo defaults.",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
