"""Speech to text for web calls (ADR-0019). Groq's hosted Whisper when GROQ_API_KEY is set (the Vercel function,
which cannot carry a model); else a local Whisper model, the optional `voice` extra, so no audio leaves the machine;
else VOICE_PROVIDER and the collector types instead. The audio is transcribed in memory, never stored or logged."""

import io
import re
from functools import cache

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.money import format_inr

try:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]  # the package ships no type hints
except ImportError:  # installed without the voice extra
    WhisperModel = None

SMALL = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen".split()
    )
}
SMALL |= {w: 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}
SCALE = {
    "thousand": 1_000,
    "lakh": 1_00_000,
    "lakhs": 1_00_000,
    "lac": 1_00_000,
    "crore": 1_00_00_000,
    "crores": 1_00_00_000,
}
_SMALL = "|".join(SMALL)
_ANY = "|".join([*SMALL, "hundred", *SCALE])
# A run starts with a number word ("two lakh"), never a bare scale ("2 lakh" is already digits).
NUMBER_RUN = re.compile(rf"\b(?:{_SMALL})\b[\s-]*(?:(?:and\s+)?(?:{_ANY})\b[\s-]*)*", re.I)


def words_to_digits(text: str) -> str:
    """Spoken numbers as digits, so the amount parser reads them: "two lakh fifty thousand" -> "2,50,000".
    Amounts of a thousand or more get Indian comma grouping, which marks them as money for parse_amounts."""

    def value(m: re.Match[str]) -> str:
        total = current = 0
        for w in re.findall(r"[a-z]+", m.group().lower()):
            if w in SMALL:
                current += SMALL[w]
            elif w == "hundred":
                current = (current or 1) * 100
            elif w in SCALE:
                total += (current or 1) * SCALE[w]
                current = 0
        n = total + current
        tail = " " if m.group()[-1].isspace() else ""
        return (format_inr(n * 100)[1:] if n >= 1000 else str(n)) + tail

    return NUMBER_RUN.sub(value, text)


# Biases spelling towards Indian amounts ("two lakh rupees", not "to a lacropies"); a hint, never a fact.
HINT = "Payment call in Indian English. Amounts in rupees, lakh and crore, e.g. two lakh rupees, fifty thousand rupees."


@cache
def _model(name: str) -> WhisperModel:
    if WhisperModel is None:
        raise AppError(
            ErrorCode.VOICE_PROVIDER, "Speech input is not installed on this server; type the reply instead."
        )
    return WhisperModel(name, device="cpu", compute_type="int8")


GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _groq(audio: bytes, mime: str, s: Settings) -> str:
    ext = (
        "ogg" if "ogg" in mime else "mp4" if "mp4" in mime else "webm"
    )  # Groq reads the format from the name
    try:
        r = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {s.groq_api_key}"},
            files={"file": (f"speech.{ext}", audio, mime or "audio/webm")},
            data={"model": s.groq_stt_model, "language": "en", "prompt": HINT, "response_format": "json"},
            timeout=20,
        )
    except httpx.HTTPError:
        raise AppError(
            ErrorCode.VOICE_PROVIDER, "Speech service unreachable; type the reply instead."
        ) from None
    if r.status_code != 200:
        raise AppError(
            ErrorCode.VOICE_PROVIDER, f"Speech service refused the clip ({r.status_code}); type instead."
        )
    return str(r.json().get("text", ""))


def _local(audio: bytes, s: Settings) -> str:
    segments, _ = _model(s.whisper_model).transcribe(
        io.BytesIO(audio), language="en", vad_filter=True, beam_size=1, initial_prompt=HINT
    )
    return " ".join(str(seg.text).strip() for seg in segments)


def transcribe(audio: bytes, s: Settings, mime: str = "audio/webm") -> str:
    """What was said, in English, numbers as digits; "" when the clip holds no speech."""
    said = _groq(audio, mime, s) if s.groq_api_key else _local(audio, s)
    return words_to_digits(said.strip())
