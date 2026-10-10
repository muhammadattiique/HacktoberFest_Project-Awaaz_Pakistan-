"""Concurrency behaviour of POST /api/complaints/voice at 5 / 20 / 50 uploads.

For each level N, N uploads of the 10 s fixture are fired at once (asyncio +
httpx). While they run, a probe sends ``GET /`` (the cheapest existing route;
there is no /health endpoint) every 250 ms and records its latency: if the
event loop is blocked by in-request Whisper/LLM work, probe latency rises to
the length of a whole STT+LLM run.

Writes results/baseline/concurrency.json.

Usage:  python bench/concurrency_bench.py [--levels 5 20 50] [--fixture synthetic_en_10s]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

BENCH_DIR = Path(__file__).resolve().parent
sys.path[:0] = [str(BENCH_DIR), str(BENCH_DIR.parent)]

import httpx  # noqa: E402

from _common import (BACKEND_DIR, FIXTURES_DIR, BenchServer, ResourceSampler,  # noqa: E402
                     fixture_manifest, host_info_short, summarize, utc_now, write_json)

FRONTEND_AXIOS_TIMEOUT_S = 35.0  # awaaz_pakistan/src/lib/api.js apiClient timeout


async def upload(client: httpx.AsyncClient, url: str, fname: str, data: bytes, t_start: float) -> Dict[str, Any]:
    bench_id = uuid.uuid4().hex
    t0 = time.perf_counter()
    try:
        r = await client.post(url, files={"audio": (fname, data, "audio/ogg")}, headers={"X-Bench-Id": bench_id})
        status, err = r.status_code, None
        detail = r.text[:200] if r.status_code >= 400 else None
    except Exception as exc:
        status, err, detail = None, type(exc).__name__, str(exc)[:200]
    t1 = time.perf_counter()
    return {"bench_id": bench_id, "status": status, "error_type": err, "detail": detail,
            "latency_s": round(t1 - t0, 3), "completed_at_s": round(t1 - t_start, 3)}


async def probe(client: httpx.AsyncClient, url: str, stop: asyncio.Event, t_start: float,
                interval: float = 0.25) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    while not stop.is_set():
        t0 = time.perf_counter()
        try:
            r = await client.get(url)
            status = r.status_code
        except Exception as exc:
            status = type(exc).__name__
        t1 = time.perf_counter()
        out.append({"sent_at_s": round(t0 - t_start, 3), "latency_s": round(t1 - t0, 4), "status": status})
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    return out


async def run_level(base_url: str, n: int, fname: str, data: bytes, timeout_s: float) -> Dict[str, Any]:
    limits = httpx.Limits(max_connections=n + 10, max_keepalive_connections=n + 10)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), limits=limits) as up_client, \
            httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as probe_client:
        # Unloaded probe baseline (2 s).
        stop0 = asyncio.Event()
        t_b = time.perf_counter()
        base_task = asyncio.create_task(probe(probe_client, base_url + "/", stop0, t_b))
        await asyncio.sleep(2.0)
        stop0.set()
        baseline = await base_task

        stop = asyncio.Event()
        t_start = time.perf_counter()
        probe_task = asyncio.create_task(probe(probe_client, base_url + "/", stop, t_start))
        results = await asyncio.gather(*[upload(up_client, base_url + "/api/complaints/voice", fname, data, t_start)
                                         for _ in range(n)])
        wall = time.perf_counter() - t_start
        stop.set()
        probes = await probe_task

    ok = [r for r in results if r["status"] == 201]
    lat_ok = [r["latency_s"] for r in ok]
    lat_all = [r["latency_s"] for r in results]
    errors = Counter((str(r["status"]) if r["error_type"] is None else r["error_type"]) for r in results if r["status"] != 201)
    return {
        "concurrency": n,
        "wall_time_s": round(wall, 3),
        "success_201": len(ok),
        "failures": n - len(ok),
        "failure_types": dict(errors),
        "throughput_req_per_s": round(len(ok) / wall, 3) if wall else None,
        "latency_success_s": summarize(lat_ok, 3),
        "latency_all_s": summarize(lat_all, 3),
        "p50_s": summarize(lat_all, 3)["median"],
        "p95_s": summarize(lat_all, 3)["p95"],
        "would_exceed_frontend_axios_timeout_35s": sum(1 for v in lat_all if v > FRONTEND_AXIOS_TIMEOUT_S),
        "probe_unloaded_latency_s": summarize([p["latency_s"] for p in baseline], 4),
        "probe_under_load_latency_s": summarize([p["latency_s"] for p in probes], 4),
        "probe_under_load_count": len(probes),
        "probe_over_1s": sum(1 for p in probes if p["latency_s"] > 1.0),
        "requests": results,
        "probes_under_load": probes,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[5, 20, 50])
    ap.add_argument("--fixture", default="synthetic_en_10s")
    ap.add_argument("--timeout", type=float, default=1800.0, help="client timeout per request (s)")
    args = ap.parse_args()

    fx = next(f for f in fixture_manifest()["fixtures"] if f["id"] == args.fixture)
    data = (FIXTURES_DIR / fx["file"]).read_bytes()

    levels: List[Dict[str, Any]] = []
    srv = BenchServer()
    srv.start()
    try:
        sampler = ResourceSampler(srv.proc.pid).start()
        # Warm Ollama + Whisper so level 5 is not dominated by a cold start.
        sampler.label = "warmup"
        with httpx.Client(timeout=900) as c:
            warm = c.post(srv.base_url + "/api/complaints/voice",
                          files={"audio": (fx["file"], data, "audio/ogg")})
        for n in args.levels:
            sampler.label = f"concurrency_{n}"
            print(f"[concurrency] level {n} ...")
            res = asyncio.run(run_level(srv.base_url, n, fx["file"], data, args.timeout))
            print(f"[concurrency] level {n}: ok={res['success_201']} fail={res['failures']} "
                  f"p50={res['p50_s']} p95={res['p95_s']} probe_max={res['probe_under_load_latency_s']['max']}")
            levels.append(res)
        sampler.label = "idle_end"
        time.sleep(2)
        sampler.stop()
        events = srv.stage_events()
    finally:
        srv.stop()

    by_id = {e["bench_id"]: e for e in events if e.get("type") == "voice_request" and e.get("bench_id")}
    for lvl in levels:
        stt, llm, tot = [], [], []
        for r in lvl["requests"]:
            ev = by_id.get(r["bench_id"], {})
            r["server_stt_s"] = ev.get("stt_s")
            r["server_llm_s"] = ev.get("llm_s")
            r["server_total_s"] = ev.get("server_total_s")
            r["llm_returned_json"] = ev.get("llm_returned_json")
            stt.append(ev.get("stt_s"))
            llm.append(ev.get("llm_s"))
            tot.append(ev.get("server_total_s"))
        lvl["server_stage_s"] = {"stt_s": summarize(stt, 3), "llm_s": summarize(llm, 3),
                                 "server_total_s": summarize(tot, 3)}
        lvl["llm_fallback_count"] = sum(1 for r in lvl["requests"] if r.get("llm_returned_json") is False)

    load_events = [e for e in events if e.get("type") == "whisper_load_model"]
    route_src = (BACKEND_DIR / "routers" / "complaints.py").read_text(encoding="utf-8")
    write_json("concurrency.json", {
        "generated_at": utc_now(),
        "method": {
            "fixture": f"{fx['id']} ({fx['measured_duration_s']} s, SYNTHETIC)",
            "server": "bench/instrumented_server.py: uvicorn 1 worker, temp SQLite DB, repo-default settings, ffmpeg shim on PATH",
            "client": "asyncio.gather of N httpx.AsyncClient POSTs fired together; client timeout "
                      f"{args.timeout}s so server behaviour (not client timeouts) is measured",
            "event_loop_probe": "GET / every 250 ms during the burst (no /health route exists); "
                                "2 s unloaded probe baseline before each level",
            "frontend_timeout_note": "would_exceed_frontend_axios_timeout_35s counts requests whose measured latency "
                                     "exceeds apiClient's 35 s timeout in awaaz_pakistan/src/lib/api.js",
        },
        "host": host_info_short(),
        "warmup_status": warm.status_code,
        "findings": {
            "whisper_and_llm_inside_request_cycle": (
                "ai_pipeline.transcribe_audio_detailed" in route_src and "ai_pipeline.parse_complaint_text" in route_src),
            "voice_handler_is_async_def_calling_sync_blocking_code": "async def submit_voice_complaint" in route_src,
            "whisper_load_model_calls_total": len(load_events),
            "whisper_load_model_calls_during_requests": sum(1 for e in load_events if e.get("in_request")),
            "models_loaded_at": "startup (FastAPI lifespan -> ai_pipeline.initialize)" if load_events and not any(
                e.get("in_request") for e in load_events) else "see whisper_load_model events",
            "whisper_serialised_by_threading_lock": "with self._whisper_lock:" in
                                                    (BACKEND_DIR / "ai_pipeline.py").read_text(encoding="utf-8"),
        },
        "whisper_load_events": load_events,
        "resource_by_phase": sampler.summary_by_label(),
        "levels": levels,
    })


if __name__ == "__main__":
    main()
