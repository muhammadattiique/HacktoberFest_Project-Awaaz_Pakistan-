"""End-to-end latency + resource usage through the REAL voice upload endpoint.

Starts the instrumented backend (temp SQLite DB) in the background, sends each
fixture to ``POST /api/complaints/voice`` sequentially, and joins the client
wall time with the server-side stage timings recorded by
``instrumented_server.py``. psutil samples the server process tree and the
Ollama processes during the whole run.

Writes results/baseline/latency.json and results/baseline/resource.json.

Usage:  python bench/latency_bench.py [--iterations 3]
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

BENCH_DIR = Path(__file__).resolve().parent
sys.path[:0] = [str(BENCH_DIR), str(BENCH_DIR.parent)]

import httpx  # noqa: E402

from _common import (FIXTURES_DIR, BenchServer, ResourceSampler, fixture_manifest,  # noqa: E402
                     host_info_short, summarize, utc_now, write_json)

STAGES = ["upload_s", "receive_parse_s", "save_s", "preprocess_s", "stt_s", "llm_s", "rules_s",
          "db_write_s", "server_total_s", "client_total_s", "client_minus_server_s"]


def post_voice(client: httpx.Client, base_url: str, fixture: Dict[str, Any]) -> Dict[str, Any]:
    bench_id = uuid.uuid4().hex
    data = (FIXTURES_DIR / fixture["file"]).read_bytes()
    t0 = time.perf_counter()
    try:
        resp = client.post(f"{base_url}/api/complaints/voice",
                           files={"audio": (fixture["file"], data, "audio/ogg")},
                           headers={"X-Bench-Id": bench_id})
        status, body = resp.status_code, resp.text[:400]
        error = None
    except Exception as exc:
        status, body, error = None, None, f"{type(exc).__name__}: {exc}"
    return {"bench_id": bench_id, "fixture": fixture["id"], "status": status,
            "client_total_s": round(time.perf_counter() - t0, 4), "error": error,
            "response_excerpt": body}


def merge(req: Dict[str, Any], events: Dict[str, Dict[str, Any]], audio_s: float) -> Dict[str, Any]:
    ev = events.get(req["bench_id"], {})
    row = dict(req)
    for k, v in ev.items():
        if k not in ("type", "bench_id", "wall_time", "status"):
            row[k] = v
    if ev.get("receive_parse_s") is not None and ev.get("save_s") is not None:
        row["upload_s"] = round(ev["receive_parse_s"] + ev["save_s"], 4)
    if ev.get("server_total_s") is not None:
        row["client_minus_server_s"] = round(req["client_total_s"] - ev["server_total_s"], 4)
    if ev.get("stt_s"):
        row["stt_real_time_factor"] = round(ev["stt_s"] / audio_s, 3)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--idle-seconds", type=float, default=5.0)
    ap.add_argument("--skip-as-is", action="store_true", help="skip the no-ffmpeg-shim as-is run")
    ap.add_argument("--no-ffmpeg-shim", action="store_true", help="main run without the PATH ffmpeg shim")
    args = ap.parse_args()

    manifest = fixture_manifest()
    fixtures = manifest["fixtures"]

    # 1) As-is environment: no ffmpeg shim. Records what a citizen would get on
    #    this machine today if ffmpeg is not on PATH.
    as_is: Dict[str, Any] = {"skipped": True}
    if not args.skip_as_is:
        srv0 = BenchServer(ffmpeg_shim=False)
        srv0.start()
        try:
            with httpx.Client(timeout=httpx.Timeout(900.0)) as client:
                reqs0 = [post_voice(client, srv0.base_url, fx) for fx in fixtures]
            ev0 = {e["bench_id"]: e for e in srv0.stage_events()
                   if e.get("type") == "voice_request" and e.get("bench_id")}
        finally:
            srv0.stop()
        as_is = {
            "ffmpeg_shim": srv0.shim_info,
            "requests": [merge(r, ev0, f["measured_duration_s"]) for r, f in zip(reqs0, fixtures)],
        }
        print(f"[latency] as-is statuses: {[r['status'] for r in as_is['requests']]}")

    # 2) Main measurement.
    requests: List[Dict[str, Any]] = []
    srv = BenchServer(ffmpeg_shim=not args.no_ffmpeg_shim)
    srv.start()
    try:
        sampler = ResourceSampler(srv.proc.pid).start()
        sampler.label = "idle_after_startup"
        time.sleep(args.idle_seconds)
        with httpx.Client(timeout=httpx.Timeout(900.0)) as client:
            # First request after startup is reported separately (Ollama may
            # need to load the model into memory; first Whisper call warms up).
            sampler.label = "cold_first_request"
            cold = post_voice(client, srv.base_url, fixtures[0])
            cold["phase"] = "cold"
            requests.append(cold)
            for fx in fixtures:
                for i in range(args.iterations):
                    sampler.label = fx["id"]
                    r = post_voice(client, srv.base_url, fx)
                    r["phase"] = "warm"
                    r["iteration"] = i + 1
                    requests.append(r)
                    print(f"[latency] {fx['id']} #{i + 1}: status={r['status']} total={r['client_total_s']}s")
        sampler.label = "idle_end"
        time.sleep(3)
        sampler.stop()
        events = srv.stage_events()
    finally:
        srv.stop()

    by_id = {e["bench_id"]: e for e in events if e.get("type") == "voice_request" and e.get("bench_id")}
    durations = {f["id"]: f["measured_duration_s"] for f in fixtures}
    rows = [merge(r, by_id, durations[r["fixture"]]) for r in requests]

    per_clip: Dict[str, Any] = {}
    for fx in fixtures:
        warm = [r for r in rows if r["fixture"] == fx["id"] and r["phase"] == "warm"]
        per_clip[fx["id"]] = {
            "audio_duration_s": fx["measured_duration_s"],
            "upload_bytes": fx["bytes"],
            "n": len(warm),
            "status_codes": sorted({str(r["status"]) for r in warm}),
            "llm_returned_json_count": sum(1 for r in warm if r.get("llm_returned_json")),
            "stages": {s: summarize([r.get(s) for r in warm], 4) for s in STAGES},
            "stt_real_time_factor": summarize([r.get("stt_real_time_factor") for r in warm], 3),
        }

    load_events = [e for e in events if e.get("type") in ("whisper_load_model", "pipeline_initialize")]
    payload = {
        "generated_at": utc_now(),
        "method": {
            "endpoint": "POST /api/complaints/voice (real route, routers/complaints.py)",
            "server": "bench/instrumented_server.py: uvicorn, 1 worker, no reload, temp SQLite DB, repo-default settings",
            "client": "httpx sync client on the same machine (loopback)",
            "iterations_per_clip": args.iterations,
            "fixtures": "bench/fixtures/manifest.json (ALL SYNTHETIC English TTS)",
            "stage_definitions": {
                "upload_s": "receive_parse_s + save_s (server-side: body receive + multipart parse + write to temp file)",
                "preprocess_s": "validate_and_convert_audio: ffmpeg to 16 kHz mono WAV + duration + silence checks",
                "stt_s": "ai_pipeline.transcribe_audio_detailed (openai-whisper)",
                "llm_s": "ai_pipeline._call_ollama_llm (Ollama chat, up to 2 attempts)",
                "rules_s": "parse_complaint_text minus llm_s (rule engine + rate lookup)",
                "db_write_s": "AsyncSession.commit + AsyncSession.refresh",
                "server_total_s": "ASGI entry to last response byte (server-side)",
                "client_minus_server_s": "client wall time minus server_total_s (loopback transfer + client overhead)",
            },
            "stats": "median/p95 are linear-interpolated percentiles; with n=3 p95 is close to max",
        },
        "host": host_info_short(),
        "ffmpeg_shim_main_run": srv.shim_info,
        "as_is_without_ffmpeg_on_path": as_is,
        "server_startup_wall_s": srv.startup_wall_s,
        "model_load_events": load_events,
        "whisper_loads_during_requests": sum(1 for e in load_events
                                             if e.get("type") == "whisper_load_model" and e.get("in_request")),
        "cold_first_request": rows[0],
        "per_clip": per_clip,
        "requests": rows,
    }
    write_json("latency.json", payload)

    write_json("resource.json", {
        "generated_at": utc_now(),
        "method": ("psutil sampling every 0.25 s of the uvicorn server process tree (includes ffmpeg children) "
                   "and of all processes named ollama* (the LLM runs out-of-process in Ollama). "
                   "CPU% is per-process psutil (100 = one logical core; ceiling = 100 x logical cores). "
                   "Samples are labelled by the latency phase running at the time."),
        "logical_cores": __import__("psutil").cpu_count(logical=True),
        "by_phase": sampler.summary_by_label(),
        "samples": sampler.samples,
    })


if __name__ == "__main__":
    main()
