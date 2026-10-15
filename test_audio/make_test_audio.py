"""Generate spoken test-complaint audio (one .wav per language) via Windows SAPI.

NOTE: this machine has only ENGLISH SAPI voices installed. The English complaint
will transcribe cleanly. Non-English text ("spoken" by an English voice) will
sound wrong and will NOT transcribe reliably -- those files are provided only so
the UPLOAD path can be exercised; for real regional-language voice tests, record
with the mic or use the written-complaint box.
"""
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "awaaz_backend"
sys.path.insert(0, str(BACKEND))

SAMPLE_RATE = 16000

# Multi-item complaints, one per language.
COMPLAINTS = {
    "english": "Hello sir, in the Raja Bazaar market the shopkeeper is selling potatoes at one hundred fifty rupees per kilo, onions at two hundred rupees per kilo, tomatoes at two hundred fifty rupees per kilo, and sugar at one hundred eighty rupees per kilo. The official rates are much lower. Please take action against this overcharging.",
    "urdu": "آلو ایک سو پچاس روپے کلو، پیاز دو سو روپے کلو، ٹماٹر دو سو پچاس روپے کلو اور چینی ایک سو اسی روپے کلو بیچ رہے ہیں۔ سرکاری ریٹ بہت کم ہے۔ برائے مہربانی کارروائی کریں۔",
    "punjabi": "دکاندار آلو اک سو پنجاہ روپے کلو، پیاز دو سو روپے کلو تے ٹماٹر دو سو پنجاہ روپے کلو بیچ ریا اے۔ سرکاری ریٹ گھٹ اے۔ مہربانی کرکے کارروائی کرو۔",
    "sindhi": "دڪاندار آلو هڪ سؤ پنجاهه رپيا ڪلو، بصر ٻه سؤ رپيا ڪلو ۽ ٽماٽا ٻه سؤ پنجاهه رپيا ڪلو ۾ وڪڻي رهيو آهي. سرڪاري اگهه گهٽ آهي. مهرباني ڪري ڪارروائي ڪريو.",
    "balochi": "Dukandar aaloo yak sad panjah rupay kilo, pyaaz do sad rupay kilo, tamatar do sad panjah rupay kilo kanag ent. Sarkari nerkh kam int. Mehrbani kanet action begiret.",
    "pashto": "دوکاندار الو يو سل پنځوس روپۍ کيلو، پياز دوه سوه روپۍ کيلو او ټماټر دوه سوه پنځوس روپۍ کيلو خرڅوي. سرکاري نرخ کم دی. مهرباني وکړئ کارروايي وکړئ.",
}

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


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Requires Windows SAPI.")
    out_dir = HERE
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="awaaz_testaudio_"))

    jobs = [{"path": str(work / f"{lang}.wav"), "text": txt} for lang, txt in COMPLAINTS.items()]
    jobs_file = work / "jobs.json"
    jobs_file.write_text(json.dumps(jobs), encoding="utf-8")
    script = work / "tts.ps1"
    script.write_text(PS_TEMPLATE.replace("__JOBS__", str(jobs_file)), encoding="utf-8")

    res = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, timeout=600,
    )
    if res.returncode != 0:
        raise SystemExit(f"SAPI TTS failed: {res.stderr}")
    voice = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else "unknown"
    print(f"[audio] SAPI voice used: {voice}")

    ffmpeg = ffmpeg_bin()
    for lang in COMPLAINTS:
        wav = work / f"{lang}.wav"
        if not wav.exists():
            print(f"[audio] WARN: {lang}.wav not produced")
            continue
        # Keep a wav copy and also encode an ogg (what the browser produces).
        import shutil as _sh
        _sh.copyfile(wav, out_dir / f"complaint_{lang}.wav")
        out_ogg = out_dir / f"complaint_{lang}.ogg"
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
             "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", str(out_ogg)],
            check=True, timeout=120,
        )
        with wave.open(str(wav), "rb") as wf:
            dur = round(wf.getnframes() / float(wf.getframerate()), 1)
        print(f"[audio] complaint_{lang}.wav / .ogg  ({dur}s)")

    _sh2 = __import__("shutil")
    _sh2.rmtree(work, ignore_errors=True)
    print(f"[audio] done -> {out_dir}")


if __name__ == "__main__":
    main()
