"""Speech to text for web calls (ADR-0019): a local Whisper model, so no audio leaves the machine and no key is
needed. The audio is transcribed in memory and never stored or logged."""

import io
import re
from functools import cache

from faster_whisper import WhisperModel  # type: ignore[import-untyped]  # the package ships no type hints

from app.core.money import format_inr

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
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(audio: bytes, model: str) -> str:
    """What was said, in English; "" when the clip holds no speech (the VAD filter drops silence and noise)."""
    segments, _ = _model(model).transcribe(
        io.BytesIO(audio), language="en", vad_filter=True, beam_size=1, initial_prompt=HINT
    )
    return words_to_digits(" ".join(str(s.text).strip() for s in segments).strip())
