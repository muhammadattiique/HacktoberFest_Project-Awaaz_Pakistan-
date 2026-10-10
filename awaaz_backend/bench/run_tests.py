"""Phase 0 baseline: run the existing backend test suite and record pass/fail.

Runs pytest in awaaz_backend against a TEMPORARY SQLite DB (DATABASE_URL
override) so the real awaaz.db is never touched, and runs the frontend lint
(oxlint via `npm run lint`). Parses both summaries and writes
results/baseline/tests.json.

Run from awaaz_backend with the baseline venv:
    python bench\run_tests.py
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import re
import shutil

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
FRONTEND = BACKEND.parent / "awaaz_pakistan"
OUT = HERE / "results" / "baseline" / "tests.json"


def run_frontend_lint() -> dict:
    """Run `npm run lint` (oxlint) in the frontend and parse the result."""
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        return {"status": "NOT MEASURED: npm not found on PATH"}
    if not (FRONTEND / "node_modules").exists():
        return {"status": "NOT MEASURED: node_modules missing; run 'npm install' in awaaz_pakistan"}
    proc = subprocess.run([npm, "run", "lint"], cwd=str(FRONTEND), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    warnings = errors = None
    m = re.search(r"Found\s+(\d+)\s+warnings?\s+and\s+(\d+)\s+errors?", out)
    if m:
        warnings, errors = int(m.group(1)), int(m.group(2))
    return {
        "command": "npm run lint (oxlint)",
        "cwd": str(FRONTEND),
        "return_code": proc.returncode,
        "passed": proc.returncode == 0,
        "warnings": warnings,
        "errors": errors,
        "summary_line": next((ln for ln in out.splitlines() if "Found" in ln), out.strip()[-200:]),
    }


def main() -> None:
    tmp_db = Path(tempfile.gettempdir()) / "awaaz_bench_pytest.db"
    tmp_db.unlink(missing_ok=True)

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db.as_posix()}"
    # Keep model init cheap/offline-tolerant; tests don't exercise Whisper/Ollama.

    # The suite instantiates TestClient(app) at module scope WITHOUT a `with`
    # block, so the FastAPI lifespan (which calls init_db) never runs and the
    # schema is only present because the committed awaaz.db already has tables.
    # To measure the suite against a throwaway DB we create the schema first,
    # exactly as init_db would at startup. This is a harness setup step only.
    init_cmd = [
        sys.executable, "-c",
        "import asyncio; from db.session import init_db; asyncio.run(init_db())",
    ]
    init_proc = subprocess.run(init_cmd, cwd=str(BACKEND), env=env, capture_output=True, text=True)

    cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "tests"]
    proc = subprocess.run(cmd, cwd=str(BACKEND), env=env, capture_output=True, text=True)
    stdout = proc.stdout
    stderr = proc.stderr

    # Parse the pytest summary line, e.g. "12 passed, 1 warning in 3.21s".
    summary = {}
    last_lines = [ln for ln in stdout.splitlines() if ln.strip()]
    tail = last_lines[-1] if last_lines else ""
    for key in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed", "warning", "warnings"):
        m = re.search(rf"(\d+)\s+{key}\b", tail)
        if m:
            summary[key] = int(m.group(1))

    frontend_lint = run_frontend_lint()

    # Frontend lint (oxlint via npm script). Non-blocking metadata.
    frontend_dir = BACKEND.parent / "awaaz_pakistan"
    lint = {"command": "npm run lint (oxlint)", "cwd": str(frontend_dir)}
    try:
        lproc = subprocess.run(
            ["cmd", "/c", "npm run lint"] if os.name == "nt" else ["npm", "run", "lint"],
            cwd=str(frontend_dir), capture_output=True, text=True, timeout=300,
        )
        lout = (lproc.stdout + lproc.stderr)
        import re as _re
        m = _re.search(r"Found\s+(\d+)\s+warnings?\s+and\s+(\d+)\s+errors?", lout)
        lint.update({
            "return_code": lproc.returncode,
            "passed": lproc.returncode == 0,
            "warnings": int(m.group(1)) if m else None,
            "errors": int(m.group(2)) if m else None,
            "summary_line": next((ln for ln in lout.splitlines() if "Found" in ln), ""),
        })
    except Exception as exc:
        lint["status"] = f"NOT MEASURED: {exc}"

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "frontend_lint": lint,
        "backend_pytest": {
            "command": "python -m pytest -q tests",
            "cwd": str(BACKEND),
            "database_url_override": env["DATABASE_URL"],
            "note": "Temporary SQLite DB used; real awaaz.db untouched.",
            "schema_init_before_run": {
                "performed": True,
                "reason": "tests/test_api.py instantiates TestClient(app) without a 'with' block, so the FastAPI lifespan (init_db) never runs; schema is created explicitly for a clean temp DB.",
                "return_code": init_proc.returncode,
                "stderr_tail": "\n".join([ln for ln in init_proc.stderr.splitlines() if ln.strip()][-8:]),
            },
            "finding_tests_depend_on_preexisting_db": "Without this init step, 8 DB-backed tests fail with 'no such table: complaints' against a fresh DB. They pass in the repo only because the committed awaaz.db already contains tables.",
            "return_code": proc.returncode,
            "passed": proc.returncode == 0,
            "summary_counts": summary,
            "summary_line": tail,
            "stdout_tail": "\n".join(last_lines[-25:]),
            "stderr_tail": "\n".join([ln for ln in stderr.splitlines() if ln.strip()][-15:]),
        },
        "frontend_lint": frontend_lint,
    }

    tmp_db.unlink(missing_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(json.dumps(result["backend_pytest"]["summary_counts"], indent=2))
    print(tail)


if __name__ == "__main__":
    main()
