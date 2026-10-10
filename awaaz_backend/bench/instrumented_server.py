"""Run the real Awaaz FastAPI app under uvicorn with stage-timing probes.

The probes are monkeypatches applied *in this process only*; no application
source is modified. For each request to ``POST /api/complaints/voice`` one JSON
line is appended to ``$BENCH_STAGE_LOG`` with:

* ``receive_parse_s``  ASGI entry -> handler starts copying the upload (body
                       receive + multipart parsing + dependency setup)
* ``save_s``           ``shutil.copyfileobj`` of the upload to the temp dir
* ``preprocess_s``     ``validate_and_convert_audio`` (ffmpeg convert + checks)
* ``stt_s``            ``ai_pipeline.transcribe_audio_detailed`` (Whisper)
* ``llm_s``            ``ai_pipeline._call_ollama_llm`` (Ollama chat incl. retries)
* ``rules_s``          rest of ``parse_complaint_text`` (rules + rate lookup)
* ``db_write_s``       ``AsyncSession.commit`` + ``AsyncSession.refresh``
* ``server_total_s``   ASGI entry -> final response body sent

Startup events record Whisper/Ollama initialisation and every
``whisper.load_model`` call, tagged with whether it happened during startup or
while serving a request (used to prove "load once" vs "load per request").

Usage (normally launched by bench/_common.BenchServer):
    python bench/instrumented_server.py --port 8765
"""
from __future__ import annotations

import argparse
import contextvars
import json
import os
import shutil
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any, Callable, Dict, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

STAGE_LOG = Path(os.environ.get("BENCH_STAGE_LOG", "stages.jsonl"))
_write_lock = threading.Lock()
CURRENT: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("bench_ctx", default=None)
PHASE = {"value": "import"}


def emit(record: Dict[str, Any]) -> None:
    record.setdefault("wall_time", time.time())
    with _write_lock:
        with open(STAGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _add(key: str, value: float) -> None:
    ctx = CURRENT.get()
    if ctx is not None:
        ctx[key] = ctx.get(key, 0.0) + value


# --- Patch model loaders before the app imports them -----------------------
import whisper  # noqa: E402

_orig_load_model = whisper.load_model


def _counted_load_model(*args: Any, **kwargs: Any):
    t0 = time.perf_counter()
    model = _orig_load_model(*args, **kwargs)
    emit({"type": "whisper_load_model", "phase": PHASE["value"],
          "duration_s": round(time.perf_counter() - t0, 3),
          "in_request": CURRENT.get() is not None,
          "args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}})
    return model


whisper.load_model = _counted_load_model

import ollama  # noqa: E402

_orig_chat = ollama.Client.chat


def _timed_chat(self, *args: Any, **kwargs: Any):
    t0 = time.perf_counter()
    try:
        resp = _orig_chat(self, *args, **kwargs)
    except Exception as exc:
        _add("ollama_chat_errors", 1)
        emit({"type": "ollama_chat_error", "error": f"{type(exc).__name__}: {exc}"[:300],
              "duration_s": round(time.perf_counter() - t0, 3)})
        raise
    dur = time.perf_counter() - t0
    ctx = CURRENT.get()
    if ctx is not None:
        ctx.setdefault("ollama_calls", []).append({
            "duration_s": round(dur, 3),
            # Ollama reports these in nanoseconds; converted to seconds.
            "load_duration_s": _ns(resp, "load_duration"),
            "prompt_eval_s": _ns(resp, "prompt_eval_duration"),
            "eval_s": _ns(resp, "eval_duration"),
            "total_duration_s": _ns(resp, "total_duration"),
            "prompt_eval_count": _get(resp, "prompt_eval_count"),
            "eval_count": _get(resp, "eval_count"),
        })
    return resp


def _get(resp: Any, key: str) -> Any:
    try:
        return resp.get(key) if hasattr(resp, "get") else getattr(resp, key, None)
    except Exception:
        return None


def _ns(resp: Any, key: str) -> Optional[float]:
    val = _get(resp, key)
    return round(val / 1e9, 3) if isinstance(val, (int, float)) else None


ollama.Client.chat = _timed_chat

# --- Import the real application --------------------------------------------
import main  # noqa: E402
import routers.complaints as complaints_router  # noqa: E402
from ai_pipeline import ai_pipeline as pipeline  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402


def _timed(key: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            _add(key, time.perf_counter() - t0)
    return wrapper


# Upload save (route uses the module-level ``shutil`` name).
def _timed_copyfileobj(src: Any, dst: Any, *args: Any) -> None:
    ctx = CURRENT.get()
    t0 = time.perf_counter()
    if ctx is not None and "copy_start" not in ctx:
        ctx["copy_start"] = t0
    shutil.copyfileobj(src, dst, *args)
    _add("save_s", time.perf_counter() - t0)


complaints_router.shutil = types.SimpleNamespace(copyfileobj=_timed_copyfileobj, rmtree=shutil.rmtree)
complaints_router.validate_and_convert_audio = _timed("preprocess_s", complaints_router.validate_and_convert_audio)

_orig_stt = pipeline.transcribe_audio_detailed


def _timed_stt(path: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    res = _orig_stt(path)
    _add("stt_s", time.perf_counter() - t0)
    ctx = CURRENT.get()
    if ctx is not None:
        ctx["stt_text"] = res.get("text", "")
        ctx["stt_language"] = res.get("language")
        ctx["stt_confidence_proxy"] = res.get("confidence")
        ctx["stt_error"] = res.get("error")
    return res


pipeline.transcribe_audio_detailed = _timed_stt

_orig_llm = pipeline._call_ollama_llm


def _timed_llm(text: str):
    t0 = time.perf_counter()
    out = _orig_llm(text)
    _add("llm_s", time.perf_counter() - t0)
    ctx = CURRENT.get()
    if ctx is not None:
        ctx["llm_returned_json"] = out is not None
    return out


pipeline._call_ollama_llm = _timed_llm

_orig_parse = pipeline.parse_complaint_text


def _timed_parse(text: str):
    t0 = time.perf_counter()
    out = _orig_parse(text)
    _add("parse_total_s", time.perf_counter() - t0)
    ctx = CURRENT.get()
    if ctx is not None:
        ctx["category"] = out.get("category")
        ctx["urgency"] = out.get("urgency")
        ctx["needs_review"] = out.get("needs_review")
        ctx["extraction_confidence"] = out.get("extraction_confidence")
    return out


pipeline.parse_complaint_text = _timed_parse

_orig_commit = AsyncSession.commit
_orig_refresh = AsyncSession.refresh


async def _timed_commit(self, *a: Any, **k: Any):
    t0 = time.perf_counter()
    try:
        return await _orig_commit(self, *a, **k)
    finally:
        _add("db_write_s", time.perf_counter() - t0)


async def _timed_refresh(self, *a: Any, **k: Any):
    t0 = time.perf_counter()
    try:
        return await _orig_refresh(self, *a, **k)
    finally:
        _add("db_write_s", time.perf_counter() - t0)


AsyncSession.commit = _timed_commit
AsyncSession.refresh = _timed_refresh

_orig_initialize = pipeline.initialize


def _timed_initialize() -> None:
    PHASE["value"] = "startup"
    t0 = time.perf_counter()
    _orig_initialize()
    emit({"type": "pipeline_initialize", "duration_s": round(time.perf_counter() - t0, 3),
          "whisper_loaded": pipeline.whisper_loaded, "ollama_available": pipeline.ollama_available})
    PHASE["value"] = "serving"


pipeline.initialize = _timed_initialize


class StageTimingASGI:
    """Pure ASGI wrapper: runs in the same task as the endpoint so the
    contextvar set here is visible to the patched functions above."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/api/complaints/voice":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        t0 = time.perf_counter()
        ctx: Dict[str, Any] = {"bench_id": headers.get("x-bench-id"), "t0": t0}
        token = CURRENT.set(ctx)
        status_holder: Dict[str, Any] = {}

        async def send_wrapper(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            CURRENT.reset(token)
            end = time.perf_counter()
            parse_total = ctx.pop("parse_total_s", None)
            llm = ctx.get("llm_s")
            copy_start = ctx.pop("copy_start", None)
            ctx.pop("t0", None)
            record = {
                "type": "voice_request",
                "status": status_holder.get("status"),
                "receive_parse_s": round(copy_start - t0, 4) if copy_start else None,
                "server_total_s": round(end - t0, 4),
                "rules_s": round(parse_total - (llm or 0.0), 4) if parse_total is not None else None,
                "parse_total_s": round(parse_total, 4) if parse_total is not None else None,
            }
            for key, val in ctx.items():
                record[key] = round(val, 4) if isinstance(val, float) else val
            emit(record)


def main_cli() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    emit({"type": "server_boot", "pid": os.getpid(), "port": args.port,
          "database_url": os.environ.get("DATABASE_URL")})
    # Single worker, no reload: mirrors `uvicorn main:app` defaults.
    uvicorn.run(StageTimingASGI(main.app), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main_cli()
