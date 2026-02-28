# 🎬 OpenCreator

Automated AI video content pipeline — from topic to finished reel.

**Research → Script → Voice → Video → Edit**

## What It Does

1. **Research** — Searches DuckDuckGo and scrapes top results
2. **Script** — Generates viral-format scripts via Ollama (local LLM)
3. **Voice** — Edge TTS (free/fast) or Qwen3-TTS local voice cloning (zero-shot, GPU)
4. **Video** — Generates talking-head video via FAL.ai API (Kling 1.6 / Wan 2.1 / MiniMax)
5. **Edit** — FFmpeg compositing with karaoke-style captions

## Quick Start

```bash
# Clone
git clone git@github.com:pankaj-mahaur/OpenCreator.git
cd OpenCreator

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — add your FAL_API_KEY

# Run via CLI
python main.py --topic "Why AI will change everything"

# Or start the Web UI
python main.py --serve
# Open http://127.0.0.1:8501
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) running locally (`ollama serve`)
- [FFmpeg](https://ffmpeg.org) installed and in PATH
- FAL.ai API key (for video generation) — [get one here](https://fal.ai)
- Avatar photo at `assets/my_photo.png`

## CLI Usage

```bash
python main.py --topic "AI news"                  # Full pipeline
python main.py --topic "AI news" --dry-run         # Skip publish
python main.py --topic "AI news" --model wan       # Use Wan 2.1
python main.py --list                              # List all runs
python main.py --serve                             # Start web UI
```

## Configuration (.env)

| Variable | Description | Default |
|---|---|---|
| `FAL_API_KEY` | FAL.ai API key (required for video gen) | — |
| `OLLAMA_MODEL` | Ollama model for script writing | `llama3.2:1b` |
| `EDGE_TTS_VOICE` | Microsoft Edge TTS voice | `en-US-ChristopherNeural` |
| `VIDEO_GEN_MODEL` | Video model: `kling-1.6`, `wan`, `minimax` | `kling-1.6` |
| `VOICE_CLONING` | Enable local Qwen3-TTS voice cloning | `false` |
| `EDGE_TTS_VOICE` | Microsoft Edge TTS voice (fallback) | `en-US-ChristopherNeural` |
| `QWEN_TTS_MODEL` | HuggingFace model ID for voice cloning | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| `QWEN_TTS_DEVICE` | Torch device for Qwen3-TTS | `cuda:0` |
| `VOICE_CLONE_REF_TEXT` | Transcript of your reference audio | `` (x-vector mode) |

## Project Structure

```
├── main.py              # CLI entry point
├── config.py            # Central configuration
├── orchestrator.py      # Pipeline coordinator
├── modules/
│   ├── researcher.py    # DuckDuckGo research
│   ├── scriptwriter.py  # LLM script generation
│   ├── voice_cloner.py  # TTS (Edge/F5-TTS)
│   ├── video_generator.py  # FAL.ai video API
│   └── video_editor.py  # FFmpeg editing + captions
├── dashboard/
│   ├── app.py           # Flask web backend
│   └── templates/
│       └── index.html   # Web UI
└── .env.example         # Config template
```

## License

MIT
