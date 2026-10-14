# ADR-0019: Web calls hear the customer through a local Whisper model; the model phrases replies without figures

- Status: Accepted
- Date: 2026-10-14
- Task: HACK-012
- Deciders: Savitha Sista (engineer)
- Area: voice, LLM, privacy
- Reversibility: cheap (typed turns still work; `phrase()` falls back to the code-written line)

## Context

Web calls used Chrome's built-in speech recognition (Web Speech API). On the engineer's Linux machine it returned
nothing, so the agent never heard the customer and repeated its opening line. The calls also read as scripted:
every agent line was a fixed sentence.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Local Whisper, faster-whisper `base` in the api container (chosen) | adds a dependency and about 150 MB to the image; CPU latency | no key, audio never leaves the machine |
| Groq hosted Whisper over httpx | a new account and key; audio leaves the machine | lowest latency, no image growth |
| OpenAI transcription | paid key; audio leaves the machine | teams already on OpenAI |
| Keep the browser's speech recognition | unreliable on Linux and Chromium, no control over errors | Chrome on Windows or macOS only |

For replies: keep fixed lines (safe, scripted) or let the model phrase them (chosen).

## Decision

- The browser records one utterance at a time (MediaRecorder, silence detection with an AnalyserNode, 800 ms end
  of speech) and posts it to `POST /calls/{id}/audio` (web calls only, 2 MB cap). `app/channels/stt.py`
  transcribes in memory with `WhisperModel(WHISPER_MODEL, cpu, int8)`, a vocabulary hint for lakh and crore, and
  turns spoken numbers into digits. The audio is never stored or logged. The text then takes the same path as a
  typed turn: intent by rules and the classifier, action by code.
- Each agent line after the opening goes through `voice.phrase()`: every figure is masked as `[[n]]`, the model
  (prompt `voice_phrase` v1) rewrites the line, code puts the figures back, and a reply that drops, repeats or
  invents a figure is refused. `verify()` then checks the line as before. Any failure returns the code-written line.
- The opening line stays code-written; it carries the "automated assistant" disclosure.
- `av` is pinned below 16: faster-whisper 1.2 passes an argument av 16 removed.

## Consequences

- Measured on one synthetic clip: 1.3 s for the first transcription, 0.4 s warm (`base`, CPU). "two lakh" was
  heard as "to your lakh" from a synthetic voice; real voices are not yet measured (no WER test set yet).
- Phrased replies need `LLM_MODE=live`; in replay mode lines stay code-written.
- Not built: barge-in (talking over the agent), streaming partial transcripts, server-side voice output.
