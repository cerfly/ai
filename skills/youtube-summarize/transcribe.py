#!/usr/bin/env python3
"""Transcribe an audio file to timestamped text with faster-whisper.

Usage:
    python3 transcribe.py <audio_file> [model] [iso639_language]

    model          tiny | base | small | medium   (default: small)
    iso639_language e.g. zh, en, ja  (omit for auto-detect)

Output: <audio_file_without_ext>.txt next to the input, one `[start-end] text`
line per recognized segment. The first run downloads the model into the
huggingface cache (~/.cache/huggingface) and can take many minutes on a slow
link; subsequent runs are local and fast.

Auto-transcription has word errors (homophones, dropped characters), especially
long tail audio. Treat output as approximate.
"""

import sys
import time


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: transcribe.py <audio_file> [model] [iso639_language]", file=sys.stderr)
        return 2

    audio_path = sys.argv[1]
    model_name = sys.argv[2] if len(sys.argv) > 2 else "small"
    language = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        print(
            "faster-whisper is not installed. Bootstrap pip, then run:\n"
            "  python3 -m pip install --user --only-binary :all: faster-whisper\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 1

    print(f"Loading {model_name} model (first run downloads it)...", flush=True)
    t0 = time.time()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    print(f"Model ready in {time.time() - t0:.0f}s", flush=True)

    print("Transcribing...", flush=True)
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )

    out_path = audio_path.rsplit(".", 1)[0] + ".txt"
    lines = []
    if language is None:
        lines.append(
            f"# detected language: {info.language} (probability={info.language_probability:.2f})"
        )
    for seg in segments:
        text = " ".join(seg.text.split())  # collapse stray whitespace
        lines.append(f"[{seg.start:.1f}-{seg.end:.1f}] {text}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Done in {time.time() - t0:.0f}s -> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())