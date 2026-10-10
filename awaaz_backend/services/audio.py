import os
import sys
import shutil
import logging
import subprocess
import wave
from pathlib import Path
from typing import Tuple, Optional
from fastapi import HTTPException, status
from config import settings

logger = logging.getLogger(__name__)

# Directory that holds the interpreter's own scripts (where a pip-installed
# ffmpeg binary would live on Windows).
VENV_SCRIPTS = Path(sys.executable).parent

# Make sure the interpreter's script directory is importable by subprocesses.
_current_path = os.environ.get("PATH", "")
if str(VENV_SCRIPTS) not in _current_path:
    os.environ["PATH"] = f"{VENV_SCRIPTS}{os.pathsep}{_current_path}"

# imageio-ffmpeg ships a static ffmpeg build; use it as the last-resort fallback
# so audio processing still works on machines without a system ffmpeg.
try:
    import imageio_ffmpeg

    IMAGEIO_FFMPEG = Path(imageio_ffmpeg.get_ffmpeg_exe())
except Exception:  # pragma: no cover - optional dependency
    IMAGEIO_FFMPEG = None


def get_ffmpeg_binary() -> str:
    """Resolve an ffmpeg executable path.

    Resolution order:
    1. ``ffmpeg`` on PATH.
    2. ``ffmpeg.exe`` next to the running interpreter.
    3. The static binary bundled with ``imageio-ffmpeg``.
    4. Bare ``"ffmpeg"`` (lets the OS raise a clear error downstream).
    """
    bin_path = shutil.which("ffmpeg")
    if bin_path:
        return bin_path

    candidate = VENV_SCRIPTS / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if candidate.exists():
        return str(candidate)

    if IMAGEIO_FFMPEG and IMAGEIO_FFMPEG.exists():
        return str(IMAGEIO_FFMPEG)

    return "ffmpeg"


def get_audio_duration_wave(wav_path: str) -> Optional[float]:
    """Calculates duration of a WAV file directly using the standard wave library."""
    try:
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return round(frames / float(rate), 2)
    except Exception as e:
        logger.debug(f"Direct wave duration check failed: {e}")
    return None


def get_audio_duration_ffmpeg(file_path: str) -> float:
    """Gets audio duration using ffmpeg output."""
    ffmpeg_bin = get_ffmpeg_binary()
    cmd = [
        ffmpeg_bin,
        "-i", file_path,
        "-f", "null",
        "-"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        # Parse Duration: 00:00:03.45 from stderr
        output = proc.stderr
        for line in output.splitlines():
            if "Duration:" in line:
                dur_str = line.split("Duration:")[1].split(",")[0].strip()
                parts = dur_str.split(":")
                if len(parts) == 3:
                    h, m, s = parts
                    return round(float(h) * 3600 + float(m) * 60 + float(s), 2)
    except Exception as e:
        logger.warning(f"ffmpeg duration probe failed: {e}")
    return 0.0


def is_audio_silent(wav_path: str) -> bool:
    """Checks if audio is silent using ffmpeg volumedetect filter."""
    ffmpeg_bin = get_ffmpeg_binary()
    cmd = [
        ffmpeg_bin,
        "-i", wav_path,
        "-af", "volumedetect",
        "-vn",
        "-sn",
        "-dn",
        "-f", "null",
        "-"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        output = proc.stderr
        for line in output.splitlines():
            if "max_volume:" in line:
                # e.g., max_volume: -91.0 dB
                val_str = line.split("max_volume:")[1].replace("dB", "").strip()
                max_vol = float(val_str)
                # If peak volume is quieter than -55 dB, treat as silence
                if max_vol <= -55.0:
                    return True
    except Exception as e:
        logger.debug(f"Volume detection check failed: {e}")
    return False


def validate_and_convert_audio(
    input_file_path: str,
    output_wav_path: str
) -> Tuple[bool, float, str]:
    """
    Validates audio file and converts it to 16kHz mono WAV for Whisper.
    Returns:
        (is_valid: bool, duration_seconds: float, message: str)
    """
    input_path = Path(input_file_path)
    if not input_path.exists():
        return False, 0.0, "Input audio file does not exist."

    file_size = input_path.stat().st_size
    if file_size == 0:
        return False, 0.0, "Audio file is empty (0 bytes)."

    if file_size > settings.UPLOAD_MAX_BYTES:
        max_mb = settings.UPLOAD_MAX_BYTES / (1024 * 1024)
        return False, 0.0, f"Audio file exceeds maximum size limit ({max_mb:.0f} MB)."

    ffmpeg_bin = get_ffmpeg_binary()

    # Convert to 16kHz 16-bit mono PCM WAV
    cmd = [
        ffmpeg_bin,
        "-y",               # Overwrite output
        "-i", input_file_path,
        "-vn",              # Disable video
        "-acodec", "pcm_s16le",
        "-ar", "16000",     # 16kHz sample rate for Whisper
        "-ac", "1",         # Mono
        output_wav_path
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False
        )
        if result.returncode != 0:
            err_msg = result.stderr.decode(errors="ignore") if isinstance(result.stderr, bytes) else str(result.stderr)
            logger.error(f"FFmpeg conversion failed: {err_msg}")
            return False, 0.0, "Audio conversion failed. Unsupported audio codec or corrupted file."
    except Exception as e:
        logger.exception(f"FFmpeg execution failed: {e}")
        return False, 0.0, f"Audio processing error: {str(e)}"

    # Check converted duration
    duration = get_audio_duration_wave(output_wav_path)
    if duration is None or duration == 0.0:
        duration = get_audio_duration_ffmpeg(output_wav_path)

    if duration < settings.AUDIO_MIN_DURATION_SECONDS:
        return False, duration, f"Audio duration ({duration}s) is too short. Minimum is {settings.AUDIO_MIN_DURATION_SECONDS}s."

    if duration > settings.AUDIO_MAX_DURATION_SECONDS:
        return False, duration, f"Audio duration ({duration}s) exceeds maximum allowed {settings.AUDIO_MAX_DURATION_SECONDS}s."

    # Check silence
    if is_audio_silent(output_wav_path):
        return False, duration, "Audio file contains only silence."

    return True, duration, "Success"

