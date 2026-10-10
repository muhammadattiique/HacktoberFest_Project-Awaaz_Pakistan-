"""Shared helpers for the Awaaz Pakistan baseline benchmarks.

Nothing in this package modifies application source. Every benchmark runs the
backend against a throw-away SQLite database inside a temporary directory, so
the repository's ``awaaz.db`` is never opened.
"""
from __future__ import annotations

import json
import math
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BENCH_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BENCH_DIR.parent
REPO_DIR = BACKEND_DIR.parent
FIXTURES_DIR = BENCH_DIR / "fixtures"
DEFAULT_RESULTS_DIR = BENCH_DIR / "results" / "baseline"


# App settings (config.Settings fields) that must NOT leak in from the caller's
# shell, so a baseline always reflects the repository defaults. To benchmark a
# different value on purpose, set AWAAZ_BENCH_SET_<NAME>, e.g.
#   $env:AWAAZ_BENCH_SET_WHISPER_MODEL = "small"
APP_SETTING_KEYS = (
    "APP_NAME", "APP_VERSION", "ENVIRONMENT", "DEBUG", "API_PREFIX",
    "WHISPER_MODEL", "WHISPER_DEVICE", "UPLOAD_MAX_BYTES", "AUDIO_MIN_DURATION_SECONDS",
    "AUDIO_MAX_DURATION_SECONDS", "OLLAMA_MODEL", "OLLAMA_BASE_URL", "OLLAMA_TIMEOUT",
    "DATABASE_URL", "RATE_LIST_PATH", "CORS_ORIGINS",
)
SET_PREFIX = "AWAAZ_BENCH_SET_"


def clean_app_env(base: Optional[Dict[str, str]] = None) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    """Return (env, removed_inherited_overrides, explicit_bench_overrides)."""
    env = dict(os.environ if base is None else base)
    removed = {k: env.pop(k) for k in list(env) if k.upper() in APP_SETTING_KEYS}
    explicit = {k[len(SET_PREFIX):]: v for k, v in env.items() if k.startswith(SET_PREFIX)}
    env.update(explicit)
    return env, removed, explicit


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def results_dir() -> Path:
    """Results go to $AWAAZ_BENCH_RESULTS or bench/results/baseline."""
    path = Path(os.environ.get("AWAAZ_BENCH_RESULTS", DEFAULT_RESULTS_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(name: str, payload: Dict[str, Any]) -> Path:
    path = results_dir() / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[bench] wrote {path}")
    return path


def percentile(values: Iterable[float], pct: float) -> Optional[float]:
    """Linear-interpolated percentile (same method as numpy's default)."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    rank = (pct / 100.0) * (len(data) - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return data[lo]
    return data[lo] + (data[hi] - data[lo]) * (rank - lo)


def summarize(values: Iterable[float], digits: int = 3) -> Dict[str, Any]:
    data = [v for v in values if v is not None]
    if not data:
        return {"n": 0, "median": None, "p95": None, "max": None, "min": None, "mean": None}
    r = lambda v: None if v is None else round(v, digits)  # noqa: E731
    return {
        "n": len(data),
        "min": r(min(data)),
        "median": r(percentile(data, 50)),
        "p95": r(percentile(data, 95)),
        "max": r(max(data)),
        "mean": r(sum(data) / len(data)),
    }


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fixture_manifest() -> Dict[str, Any]:
    manifest = FIXTURES_DIR / "manifest.json"
    if not manifest.exists():
        raise SystemExit(f"Missing {manifest}. Run bench/make_fixtures.py first.")
    return json.loads(manifest.read_text(encoding="utf-8"))


class BenchServer:
    """Starts the instrumented backend in the background and stops it on exit.

    The server process runs with ``cwd`` set to a fresh temp directory and
    ``DATABASE_URL`` pointing at a temp SQLite file, so neither the repo's
    ``awaaz.db`` nor any ``.env`` in the backend folder is used.
    """

    def __init__(self, port: Optional[int] = None, seed: bool = False, startup_timeout: float = 600.0,
                 ffmpeg_shim: bool = True):
        self.port = port or free_port()
        self.seed = seed
        self.ffmpeg_shim = ffmpeg_shim
        self.shim_info: Dict[str, Any] = {"enabled": False}
        self.startup_timeout = startup_timeout
        self.tmp = Path(tempfile.mkdtemp(prefix="awaaz_bench_"))
        self.db_path = self.tmp / "bench.db"
        self.stage_log = self.tmp / "stages.jsonl"
        self.server_log = self.tmp / "server.log"
        self.proc: Optional[subprocess.Popen] = None
        self.startup_wall_s: Optional[float] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def env(self) -> Dict[str, str]:
        env, _, _ = clean_app_env()
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{self.db_path.as_posix()}"
        env["BENCH_STAGE_LOG"] = str(self.stage_log)
        env["PYTHONPATH"] = str(BACKEND_DIR)
        env["PYTHONIOENCODING"] = "utf-8"
        if self.shim_info.get("enabled"):
            env["PATH"] = self.shim_info["dir"] + os.pathsep + env.get("PATH", "")
        return env

    def _prepare_ffmpeg_shim(self) -> None:
        """openai-whisper's ``load_audio`` shells out to a bare ``ffmpeg``; the
        app's imageio-ffmpeg fallback only covers services/audio.py. When no
        ffmpeg is on PATH, expose the imageio binary as ``ffmpeg.exe`` in a temp
        dir prepended to the *server process* PATH (environment only - no
        source change)."""
        if not self.ffmpeg_shim:
            self.shim_info = {"enabled": False, "reason": "disabled (as-is environment run)",
                              "ffmpeg_on_path": shutil.which("ffmpeg")}
            return
        if shutil.which("ffmpeg"):
            self.shim_info = {"enabled": False, "reason": "ffmpeg already on PATH", "ffmpeg_on_path": shutil.which("ffmpeg")}
            return
        try:
            import imageio_ffmpeg

            src = Path(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception as exc:
            self.shim_info = {"enabled": False, "reason": f"imageio-ffmpeg unavailable: {exc}"}
            return
        shim_dir = self.tmp / "ffmpeg_shim"
        shim_dir.mkdir(exist_ok=True)
        dst = shim_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        try:
            os.link(src, dst)
            how = "hardlink"
        except OSError:
            shutil.copy2(src, dst)
            how = "copy"
        self.shim_info = {"enabled": True, "dir": str(shim_dir), "source": str(src), "method": how}

    def _seed(self) -> None:
        cmd = [sys.executable, str(BACKEND_DIR / "scripts" / "seed_demo_data.py")]
        res = subprocess.run(cmd, cwd=self.tmp, env=self.env(), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=300)
        if res.returncode != 0:
            raise RuntimeError(f"Seeding temp DB failed:\n{res.stdout}\n{res.stderr}")

    def start(self) -> "BenchServer":
        import httpx

        self._prepare_ffmpeg_shim()
        if self.seed:
            self._seed()
        cmd = [sys.executable, str(BENCH_DIR / "instrumented_server.py"), "--port", str(self.port)]
        self._log_fh = open(self.server_log, "w", encoding="utf-8", errors="replace")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        t0 = time.perf_counter()
        self.proc = subprocess.Popen(cmd, cwd=self.tmp, env=self.env(), stdout=self._log_fh,
                                     stderr=subprocess.STDOUT, creationflags=flags)
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Server exited early (code {self.proc.returncode}). Log: {self.server_log}")
            try:
                if httpx.get(self.base_url + "/", timeout=2.0).status_code == 200:
                    self.startup_wall_s = round(time.perf_counter() - t0, 3)
                    print(f"[bench] server up on {self.base_url} after {self.startup_wall_s}s (pid {self.proc.pid})")
                    return self
            except Exception:
                pass
            time.sleep(0.5)
        self.stop()
        raise RuntimeError("Server did not become ready in time")

    def stage_events(self) -> List[Dict[str, Any]]:
        if not self.stage_log.exists():
            return []
        out = []
        for line in self.stage_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def stop(self, keep_tmp: bool = False) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if getattr(self, "_log_fh", None):
            self._log_fh.close()
        if not keep_tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
            print(f"[bench] server stopped, temp dir removed ({self.tmp})")

    def __enter__(self) -> "BenchServer":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop(keep_tmp=os.environ.get("AWAAZ_BENCH_KEEP_TMP") == "1")


class ResourceSampler:
    """Samples CPU% and RSS of the server process tree and of Ollama processes.

    CPU% is psutil's per-process value (100 = one logical core fully busy), so
    on a 12-thread CPU the ceiling is 1200. ``label`` tags each sample with the
    benchmark phase that was running when it was taken.
    """

    def __init__(self, server_pid: int, interval_s: float = 0.25):
        import psutil
        import threading

        self.psutil = psutil
        self.server = psutil.Process(server_pid)
        self.interval = interval_s
        self.label = "idle"
        self.samples: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._procs: Dict[int, Any] = {}
        self.t0 = time.perf_counter()

    def _tracked(self) -> Dict[str, List[Any]]:
        groups: Dict[str, List[Any]] = {"server_tree": [], "ollama": []}
        try:
            groups["server_tree"] = [self.server] + self.server.children(recursive=True)
        except self.psutil.Error:
            pass
        for p in self.psutil.process_iter(["name"]):
            if (p.info.get("name") or "").lower().startswith("ollama"):
                groups["ollama"].append(p)
        return groups

    def _run(self) -> None:
        while not self._stop.is_set():
            groups = self._tracked()
            sample: Dict[str, Any] = {"t_s": round(time.perf_counter() - self.t0, 3), "label": self.label}
            for name, procs in groups.items():
                cpu = rss = 0.0
                for p in procs:
                    cached = self._procs.setdefault(p.pid, p)
                    try:
                        cpu += cached.cpu_percent(None)
                        rss += cached.memory_info().rss
                    except self.psutil.Error:
                        continue
                sample[f"{name}_cpu_pct"] = round(cpu, 1)
                sample[f"{name}_rss_mb"] = round(rss / 1024 ** 2, 1)
            sample["system_cpu_pct"] = self.psutil.cpu_percent(None)
            sample["system_ram_used_pct"] = self.psutil.virtual_memory().percent
            self.samples.append(sample)
            self._stop.wait(self.interval)

    def start(self) -> "ResourceSampler":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def summary_by_label(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        labels = sorted({s["label"] for s in self.samples})
        # The first sample of each process primes psutil's CPU counter (always 0) - drop it.
        samples = self.samples[1:]
        for label in labels:
            rows = [s for s in samples if s["label"] == label]
            if not rows:
                continue
            entry: Dict[str, Any] = {"n_samples": len(rows), "duration_s": round(len(rows) * self.interval, 2)}
            for key in ("server_tree_cpu_pct", "server_tree_rss_mb", "ollama_cpu_pct", "ollama_rss_mb",
                        "system_cpu_pct", "system_ram_used_pct"):
                vals = [r[key] for r in rows if key in r]
                entry[key] = {"mean": round(sum(vals) / len(vals), 1) if vals else None,
                              "p95": round(percentile(vals, 95), 1) if vals else None,
                              "max": round(max(vals), 1) if vals else None}
            out[label] = entry
        return out


def host_info_short() -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
    }
