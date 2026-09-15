---
name: youtube-summarize
description: "Summarize a YouTube video from its URL. Use when the user shares a YouTube link and asks for a summary, key points, contents, deep dive, or the actual spoken content. Walks from cheap metadata extraction, through caption download, down to local audio transcription with faster-whisper when no captions exist. Trigger keywords: youtube, summarize video, video summary, transcript, 视频总结, video contents."
---

# YouTube Video Summarization

Turn a YouTube URL into a faithful summary of the actual video content.

## Workflow overview

Proceed top-to-bottom, stopping as soon as a step yields enough to summarize faithfully. Do NOT jump straight to transcription — the cheap steps often suffice and are much faster.

```
1. Metadata + description extraction   (seconds)   -> often has full chapter breakdown
2. Existing coverage via web search     (seconds)   -> context for niche/analysis videos
3. Caption download if available        (minutes)   -> verbatim transcript
4. Local Audio transcription            (10-40 min) -> last resort, no captions
```

## Step 0 — When the user wants a summary but no URL

Ask for the link first. Summaries require the video; without it, refusing to guess.

## Step 1 — Metadata and description (cheap)

Fetch the page and extract the real (often chaptered) description with yt-dlp, which is far more reliable than the webfetch-rendered page:

```bash
yt-dlp --skip-download --print "%(title)s\n\n%(description)s\n\nDURATION: %(duration_string)s" "URL"
```

The description frequently contains a timestamped chapter list (`00:00 ...`, `01:02 ...`). These map 1:1 to narration segments and let you summarize accurately without a transcript.

If the user gave a `&t=NNNs` or `#t=NNms` position, note which chapter it falls inside and highlight that section.

If yt-dlp is missing: `python3 -m pip install --user yt-dlp` (or `curl -sSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o ~/.local/bin/yt-dlp && chmod +x ~/.local/bin/yt-dlp`).

## Step 2 — Web search for context

Run a web search for the video title (or a distinctive phrase of it) to surface related articles / mirrors / discussions. Useful for analysis channels where the same story is covered in text form. English, Chinese, Japanese titles all search fine. Do NOT substitute this for actual video content when the user asked for the video itself.

## Step 3 — Captions (verbatim, when present)

```bash
yt-dlp --skip-download --list-subs "URL"
```

- If subtitle tracks (manual or auto-generated) exist, download them:
  ```bash
  yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "ALL" --sub-format "vtt/json3" -o "/tmp/opencode/vid-%(id)s" "URL"
  ```
  Prefer `vtt` and pick the language that matches the video (check page metadata or `--list-subs` output).
- VTT is timestamped; skip the webvtt header lines (`WEBVTT`, `Kind:`, blank lines, cue numbers) when reading. If a raw fast-stream / m3u8 listing shows "no subtitles", the transcript must come from Step 4.
- Note: yt-dlp may emit warnings about a missing JS runtime — subtitles can still be listed/downloaded; ignore unless it actually errors.

## Step 4 — Local audio transcription (no captions)

Only when captions are genuinely absent. Downloads the audio and transcribes it locally with `faster-whisper`. Works entirely offline after the one-time model download. Typical case: 30 min video -> ~15 min wall time (mostly model download on first run, then fast CPU transcription).

### 4a. Download + prep audio (use /tmp/opencode for all scratch files)

```bash
mkdir -p /tmp/opencode
yt-dlp -f "bestaudio/best" -o "/tmp/opencode/audio.%(ext)s" "URL"
/usr/bin/ffmpeg -y -i /tmp/opencode/audio.webm -ar 16000 -ac 1 -c:a pcm_s16le /tmp/opencode/audio.wav
```

Trap: a `~/bin/ffmpeg` (or `/home/$USER/bin/ffmpeg`) can exist and be broken (segfaults instantly, prints nothing). Use the system binary: `which -a ffmpeg`, prefer `/usr/bin/ffmpeg`. Validate with `/usr/bin/ffmpeg -version`. If an output file doesn't appear, the binary is likely crashing — switch.

### 4b. Ensure python3 + pip

```bash
python3 -m pip --version
```

- If "No module named pip", try `python3 -m ensurepip --user`.
- If ensurepip is also missing (minimal installs), bootstrap:
  ```bash
  curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/opencode/get-pip.py && python3 /tmp/opencode/get-pip.py --user
  ```
- Afterwards: `python3 -m pip install --user --only-binary :all: faster-whisper`. On slow connections this can take 5-10 min — use a LONG bash timeout (>= 600000ms) and don't assume failure. `.local/bin` needs to be on PATH or call via `python3 -m pip`.

### 4c. Transcribe

```bash
python3 "<SKILL_DIR>/transcribe.py" /tmp/opencode/audio.wav small [iso639-lang]
```

- Model sizes: `tiny` (fast, poor), `base` (fast, mediocre), `small` (balanced — default), `medium` (best accuracy, slow without GPU).
- Pass a language code when you know it (e.g. `zh` for Chinese commentary, `ja` for Japanese) for cleaner output; omit to auto-detect.
- The first run downloads the model (~466MB for `small` in ~/.cache/huggingface) — allow very long timeouts (up to 60+ min total on slow links).
- Output: a `*.txt` next to the audio with `[start-end]` timestamps per segment. Read it with the Read tool; segments may be numerous.
- If pip/faster-whisper is a hard blocker, an alternative route is building whisper.cpp (`git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git && make -j8` — requires cmake/gcc) then `./main -m models/ggml-small.bin -l zh -f audio.wav`. Python route is simpler and requires no compilation; prefer it.

### 4d. Model fidelity honesty

Auto-transcription is NOT verbatim. `.local` homophones and dropped characters are common in noisy/commentary audio (e.g. 熵增 -> 商增, 维护 -> 遗留/维保). When quoting the content, paraphrase rather than presenting possibly-mangled words as exact quotes. Trust chapter timestamps and the general argument structure; treat individual phrases as approximate.

## Step 5 — Write the summary

Structure it so the user can scan and jump:

1. **One-line identification** — title, channel, language, duration.
2. **Thesis** — the core claim in 1-2 sentences.
3. **Chapter-by-chapter breakdown** — use the description's chapter titles when available, mapped to what the transcript actually said. Keep each chapter tight (3-6 bullets max). Add a `[chapter timestamps]`.
4. **Key data points** — every concrete number/figure cited in the video, listed separately.
5. **Caveats** — state plainly what came from metadata vs. transcript, and that transcribed numbers/quotes are approximate if they came from Step 4.

Respond in the same language the user is writing in (not necessarily the video's). Keep it scannable; bold only the load-bearing terms. If a chapter falls outside the transcript coverage (e.g. video longer than transcribed window), say so instead of inventing content.

## Environment notes (this machine)

- Working system ffmpeg: `/usr/bin/ffmpeg` (`~/bin/ffmpeg` segfaults).
- yt-dlp present at `~/.local/bin/yt-dlp`; needs a JS runtime warning is harmless.
- faster-whisper is NOT yet installed system-wide; it gets installed per use into `~/.local/lib/python3.10/site-packages` via the bootstrap above. After first install it stays available.
- Scratch/download dir: `/tmp/opencode` (pre-approved temp area).