"""Daily vertical video (Reels / Shorts / Facebook): scenes in the poster style + optional Marathi voice-over + ffmpeg.

Voice-over uses Google Cloud Text-to-Speech (mr-IN) when GOOGLE_TTS_API_KEY is set; otherwise the video is silent
(captions are in the picture). Only real app content is shown: the topic's points and real tenders found today.
"""
from __future__ import annotations

import base64
import logging
import re
import shutil
import subprocess
import time
import tempfile
from pathlib import Path

import httpx

from agents import logger, poster_pro
from config import get_settings

logging.getLogger("httpx").setLevel(logging.WARNING)  # the TTS request URL contains the API key
HOOK_SECONDS, POINT_SECONDS, CTA_SECONDS = 4.0, 6.0, 7.0   # 3 points -> about 29 seconds
FADE = 0.3
OUT_W, OUT_H, FPS = 720, 1280, 24


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def build_specs(headline: str, points: list[str], rows: list[dict] | None, link: str, lang: str = "mr") -> list[dict]:
    """Scenes: hook, one per point (or per real tender), call to action. `say` is what the voice reads."""
    specs = [{"kind": "hook", "text": headline, "say": headline, "min": HOOK_SECONDS, "date": None}]
    if rows:
        for row in rows[:3]:
            if lang == "en":
                say = f"Closing date {row['date']}. Details in the app." if row.get("date") else "See the details in the app."
            else:
                say = f"शेवटची तारीख {row['date']}. सविस्तर ॲपमध्ये." if row.get("date") else "सविस्तर ॲपमध्ये पाहा."
            specs.append({"kind": "point", "text": row["title"], "say": say, "min": POINT_SECONDS, "date": row.get("date")})
    else:
        for point in points[:3]:
            specs.append({"kind": "point", "text": point, "say": point, "min": POINT_SECONDS, "date": None})
    specs.append({"kind": "cta", "text": "", "link": link, "min": CTA_SECONDS, "date": None,
                  "say": ("TenderBot AI. Try it free for fifteen days. Message us on WhatsApp to get started." if lang == "en"
                          else "TenderBot AI. पंधरा दिवस मोफत ट्रायल. आजच सुरू करा.")})
    return specs


def tts(text: str, lang: str = "mr") -> bytes | None:
    s = get_settings()
    if not s.google_tts_api_key or not text.strip():
        return None
    try:
        r = httpx.post("https://texttospeech.googleapis.com/v1/text:synthesize", timeout=30,
                       params={"key": s.google_tts_api_key},
                       json={"input": {"text": text}, "voice": {"languageCode": "en-IN" if lang == "en" else "mr-IN",
                                       "name": s.google_tts_voice_en if lang == "en" else s.google_tts_voice},
                             "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.95}})
        return base64.b64decode(r.json()["audioContent"])
    except Exception as exc:  # never log the response/URL (contains the key)
        logger.warning("voice-over not created: %s", type(exc).__name__)
        return None


def _duration(ffmpeg: str, path: Path) -> float:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _heygen_video(specs: list[dict]) -> tuple[bytes, float] | None:
    """AI avatar video from HeyGen (needs an API plan, credits and a Marathi voice id). None on any problem."""
    s = get_settings()
    if not (s.heygen_api_key and s.heygen_avatar_id and s.heygen_voice_id_mr):
        logger.warning("HeyGen not used: HEYGEN_API_KEY / HEYGEN_AVATAR_ID / HEYGEN_VOICE_ID_MR missing")
        return None
    text = " ".join(sp["say"] for sp in specs if sp.get("say"))      # only our own fixed words and today's real tender dates
    headers = {"X-Api-Key": s.heygen_api_key, "Content-Type": "application/json"}
    payload = {"video_inputs": [{
        "character": {"type": "avatar", "avatar_id": s.heygen_avatar_id, "avatar_style": "normal"},
        "voice": {"type": "text", "input_text": text, "voice_id": s.heygen_voice_id_mr},
        "background": {"type": "color", "value": "#0b2a4a"}}],
        "dimension": {"width": OUT_W, "height": OUT_H}}
    try:
        created = httpx.post("https://api.heygen.com/v2/video/generate", headers=headers, json=payload, timeout=60)
        video_id = (created.json().get("data") or {}).get("video_id")
        if created.status_code != 200 or not video_id:
            logger.warning("HeyGen rejected the request (http %s): %s", created.status_code, str(created.json().get("error"))[:160])
            return None
        deadline = time.time() + s.heygen_timeout_minutes * 60
        while time.time() < deadline:
            time.sleep(15)
            data = httpx.get("https://api.heygen.com/v1/video_status.get", headers=headers, timeout=30,
                             params={"video_id": video_id}).json().get("data") or {}
            if data.get("status") == "completed" and data.get("video_url"):
                return httpx.get(data["video_url"], timeout=180).content, float(data.get("duration") or 0)
            if data.get("status") == "failed":
                logger.warning("HeyGen video failed: %s", str(data.get("error"))[:160])
                return None
        logger.warning("HeyGen video timed out")
    except Exception as exc:  # never log the request (it carries the API key header)
        logger.warning("HeyGen video not created: %s", type(exc).__name__)
    return None


LAST_ERROR: str = ""


def _fail(reason: str) -> None:
    global LAST_ERROR
    LAST_ERROR = reason[:200]


def make_video(headline: str, points: list[str], rows: list[dict] | None, link_display: str,
               background: bytes | None, contact: str = "", lang: str = "mr") -> tuple[bytes, float] | None:
    """Daily video: HeyGen when VIDEO_PROVIDER=heygen (Marathi only), otherwise (or if HeyGen fails) the built-in ffmpeg video."""
    if get_settings().video_provider == "heygen" and lang == "mr":
        made = _heygen_video(build_specs(headline, points, rows, link_display, lang))
        if made:
            return made
        logger.warning("falling back to the built-in video")
    return _make_local_video(headline, points, rows, link_display, background, contact, lang)


def _make_local_video(headline: str, points: list[str], rows: list[dict] | None, link_display: str,
                      background: bytes | None, contact: str = "", lang: str = "mr") -> tuple[bytes, float] | None:
    """Returns (mp4 bytes, seconds) or None. Never raises: a failed video must not stop the daily poster."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        _fail("ffmpeg missing")
        return None
    try:
        specs = build_specs(headline, points, rows, link_display, lang)
        total = sum(1 for sp in specs if sp["kind"] == "point")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            durations, audio_files = [], []
            for i, sp in enumerate(specs):
                frame = poster_pro.render_scene(sp["kind"], sp["text"], i, total, link_display, sp.get("date"), background, contact, lang)
                (tmp_path / f"f{i}.png").write_bytes(frame)
                voice, dur = tts(sp["say"], lang), sp["min"]
                if voice:
                    mp3 = tmp_path / f"a{i}.mp3"
                    mp3.write_bytes(voice)
                    audio_files.append(mp3)
                    dur = max(dur, _duration(ffmpeg, mp3) + 0.7)
                else:
                    audio_files.append(None)
                durations.append(round(dur, 2))

            cmd, filters, v_labels, a_labels, n_in = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"], [], [], [], 0
            for i, dur in enumerate(durations):
                cmd += ["-loop", "1", "-framerate", str(FPS), "-t", str(dur), "-i", str(tmp_path / f"f{i}.png")]
            audio_index = {}
            for i, mp3 in enumerate(audio_files):
                if mp3:
                    cmd += ["-i", str(mp3)]
                    audio_index[i] = len(durations) + len(audio_index)
            for i, dur in enumerate(durations):
                filters.append(f"[{i}:v]scale={OUT_W}:{OUT_H},setsar=1,fade=t=in:st=0:d={FADE},"
                               f"fade=t=out:st={max(dur - FADE, 0)}:d={FADE},format=yuv420p[v{i}]")
                v_labels.append(f"[v{i}]")
                if i in audio_index:
                    filters.append(f"[{audio_index[i]}:a]aresample=24000,apad=whole_dur={dur}[a{i}]")
                else:
                    filters.append(f"anullsrc=r=24000:cl=mono,atrim=0:{dur}[a{i}]")
                a_labels.append(f"[a{i}]")
            filters.append("".join(v_labels) + f"concat=n={len(durations)}:v=1:a=0[v]")
            filters.append("".join(a_labels) + f"concat=n={len(durations)}:v=0:a=1[a]")
            out = tmp_path / "out.mp4"
            cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0 or not out.exists():
                logger.warning("video encoding failed: %s", proc.stderr[-300:])
                _fail("encoding failed: " + proc.stderr[-120:].strip().replace("\n", " "))
                return None
            return out.read_bytes(), float(sum(durations))
    except Exception as exc:
        logger.warning("video not created: %s", type(exc).__name__)
        _fail(f"{type(exc).__name__}: {str(exc)[:80]}")
        return None
