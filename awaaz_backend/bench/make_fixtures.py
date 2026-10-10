"""Phase 0 baseline: synthetic audio fixture generation.

Generates SYNTHETIC speech clips of exactly 10s / 30s / 60s using Windows SAPI
(System.Speech) via PowerShell, concatenates whole civic-domain sentences with
short gaps, pads with silence to the exact target duration, and encodes to
Ogg/Opus (what browser MediaRecorder produces) with the imageio-ffmpeg static
binary.

ALL fixtures are SYNTHETIC English TTS, NOT real citizen audio. They are for
latency/throughput measurement only and must NOT be used for Urdu WER claims
(only English SAPI voices are installed on this machine). See fixtures/manifest.json.

Reproduce (from awaaz_backend, with the baseline venv on PATH):
    python bench\\make_fixtures.py
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(BACKEND))

TARGETS = [10, 30, 60]
GAP_S = 0.3
SAMPLE_RATE = 16000

# Synthetic civic complaints (English, with local place / agency names). Short
# and long sentences mix so first-fit packing fills each target closely.
SENTENCES: List[str] = [
    "The potato vendor in G-9 Markaz is charging two hundred rupees per kilo.",
    "The official rate list says potatoes should be one hundred rupees.",
    "There is an open manhole in front of the school in Satellite Town.",
    "The sewage line has been overflowing on our street for three days.",
    "We have had twelve hours of load shedding every day this week.",
    "The water supply from WASA has been cut off since Monday morning.",
    "The streetlights near Raja Bazaar are broken and the road is dark at night.",
    "A milk shop in Saddar is selling milk mixed with water.",
    "There is a large pothole on the main road near the hospital.",
    "Garbage has not been collected in our area for two weeks.",
    "The gas pressure from SNGPL is very low during the morning hours.",
    "The flour mill dealer is selling a bag of atta above the notified price.",
    "Please send the municipal team to clean the blocked drain near the market.",
    "The electricity bill from LESCO is much higher than our actual usage.",
    "Chicken is being sold for seven hundred rupees per kilo in Commercial Market.",
    "The tandoor in Aabpara is charging thirty rupees for one roti.",
    "Children cannot walk to school because the footpath is flooded with sewage.",
    "The vegetable market in I-10 is not displaying the official rate list.",
    "Please take action quickly.",
    "The drain is blocked again.",
    "Thank you.",
]

PS_TEMPLATE = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = ($s.GetInstalledVoices() | Where-Object { $_.Enabled } | Select-Object -First 1).VoiceInfo.Name
$s.SelectVoice($voice)
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$items = Get-Content -Raw -Encoding UTF8 '__JOBS__' | ConvertFrom-Json
foreach ($it in $items) {
  $s.SetOutputToWaveFile($it.path, $fmt)
  $s.Speak($it.text)
}
$s.SetOutputToNull()
$s.Dispose()
Write-Output $voice
"""


def ffmpeg_bin() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def synthesize(sentences: List[str], workdir: Path) -> Tuple[List[Path], str]:
    jobs = [{"path": str(workdir / f"s{i:02d}.wav"), "text": t} for i, t in enumerate(sentences)]
    jobs_file = workdir / "jobs.json"
    jobs_file.write_text(json.dumps(jobs), encoding="utf-8")
    script = workdir / "tts.ps1"
    script.write_text(PS_TEMPLATE.replace("__JOBS__", str(jobs_file)), encoding="utf-8")
    res = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, timeout=600,
    )
    if res.returncode != 0:
        raise SystemExit(f"SAPI TTS failed: {res.stderr}")
    voice = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else "unknown"
    return [Path(j["path"]) for j in jobs], voice


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        assert wf.getframerate() == SAMPLE_RATE and wf.getnchannels() == 1 and wf.getsampwidth() == 2
        return wf.readframes(wf.getnframes())


def build_clip(pcms: List[bytes], target_s: int, start: int) -> Tuple[bytes, List[int]]:
    """First-fit: walk sentences once from ``start``, adding each that still fits."""
    gap = b"\x00\x00" * int(GAP_S * SAMPLE_RATE)
    limit = target_s * SAMPLE_RATE * 2
    out = bytearray(gap)
    used: List[int] = []
    for k in range(len(pcms)):
        i = (start + k) % len(pcms)
        chunk = pcms[i] + gap
        if len(out) + len(chunk) <= limit:
            out += chunk
            used.append(i)
    out += b"\x00" * (limit - len(out))  # pad with silence to the exact duration
    return bytes(out), used


def probe_duration(ffmpeg: str, path: Path) -> float:
    res = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-f", "null", "-"],
                         capture_output=True, text=True, timeout=60)
    dur = 0.0
    for line in res.stderr.splitlines():
        if "time=" in line:
            t = line.split("time=")[-1].split()[0]
            try:
                h, m, s = t.split(":")
                dur = float(h) * 3600 + float(m) * 60 + float(s)
            except ValueError:
                pass
    return round(dur, 2)


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("NOT MEASURED: fixture generation requires Windows SAPI (System.Speech).")
    ffmpeg = ffmpeg_bin()
    if not (shutil.which(ffmpeg) or Path(ffmpeg).exists()):
        raise SystemExit("NOT MEASURED: no ffmpeg binary found (PATH or imageio-ffmpeg).")

    FIXTURES.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="awaaz_tts_"))
    try:
        wavs, voice = synthesize(SENTENCES, work)
        pcms = [read_pcm(p) for p in wavs]
        entries = []
        for n, target in enumerate(TARGETS):
            pcm, used = build_clip(pcms, target, start=n * 5)
            raw = work / f"clip_{target}.wav"
            with wave.open(str(raw), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
            out = FIXTURES / f"synthetic_en_{target}s.ogg"
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
                   "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", str(out)]
            subprocess.run(cmd, check=True, timeout=120)
            speech_s = sum(len(pcms[i]) for i in used) / (SAMPLE_RATE * 2)
            entries.append({
                "id": f"synthetic_en_{target}s",
                "file": out.name,
                "synthetic": True,
                "target_duration_s": target,
                "measured_duration_s": probe_duration(ffmpeg, out),
                "speech_duration_s": round(speech_s, 2),
                "trailing_silence_padding": True,
                "language": "en",
                "codec": "opus 32 kb/s in ogg, mono",
                "bytes": out.stat().st_size,
                "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                "reference_transcript": " ".join(SENTENCES[i] for i in used),
            })
            print(f"[fixtures] {out.name}: {entries[-1]['measured_duration_s']}s, {len(used)} sentences")
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": "bench/make_fixtures.py (Windows SAPI System.Speech + ffmpeg)",
            "tts_voice": voice,
            "ffmpeg": ffmpeg,
            "ALL_SYNTHETIC": True,
            "note": ("Synthetic English TTS speech for latency/throughput only. Not representative of real "
                     "citizen recordings (no Urdu/regional speech, no background noise, studio-clean signal). "
                     "Do not use for WER claims about Urdu."),
            "fixtures": entries,
        }
        (FIXTURES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"[fixtures] wrote {FIXTURES / 'manifest.json'}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
