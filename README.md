# 🎬 Sovereign Instagram Content Agent

**Fully automated Instagram Reels pipeline — research, script, voice clone, AI avatar, edit, publish.**

100% local. Zero recurring cost. Runs on your RTX 3050 4GB.

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Copy env template
copy .env.example .env
# Edit .env with your settings

# 3. Install Ollama + model
# Download from https://ollama.com
ollama pull llama3.2:3b

# 4. Setup assets
# - Record 5s+ voice sample → voice_samples/my_voice.wav
# - Take front-facing photo  → assets/my_photo.png

# 5. Install TTS engines
pip install git+https://github.com/SWivid/F5-TTS.git
pip install TTS

# 6. Clone third-party models
mkdir third_party
cd third_party
git clone https://github.com/OpenTalker/SadTalker.git
git clone https://github.com/KwaiVGI/LivePortrait.git
git clone https://github.com/sczhou/CodeFormer.git
cd ..

# 6. Run!
python main.py --topic "Latest AI tools" --dry-run
```

## Usage

```bash
# Full pipeline (dry run — no publish)
python main.py --topic "Why AI will change everything" --dry-run

# Test individual steps
python main.py --topic "Test" --step research
python main.py --topic "Test" --step script
python main.py --topic "Test" --step voice

# Launch dashboard
streamlit run dashboard/app.py

# List all runs
python main.py --list

# Approve and publish a run
python main.py --approve <run_id>
```

## Pipeline

```
Topic → 🔍 Research (DuckDuckGo)
      → 📝 Script  (Ollama Llama 3.2)
      → 🎙️ Voice   (F5-TTS / XTTS-v2)
      → 🎭 Motion  (SadTalker → proxy)
      → 🖼️ Avatar  (LivePortrait → retarget)
      → 🔧 Restore (CodeFormer → fix)
      → 🎬 Edit    (Whisper captions + MoviePy)
      → 👤 Review  (Streamlit dashboard)
      → 📱 Publish (Instagrapi stealth)
```

## VRAM Tetris

Each step runs sequentially with GPU cleanup between steps.
A 4GB GPU can run a pipeline that needs ~20GB total:

| Step | Model | VRAM |
|--|--|--|
| Script | Llama 3.2 3B | ~2.5GB |
| Voice | F5-TTS (primary) / XTTS-v2 | ~3GB / ~4-6GB |
| Motion | SadTalker | ~3GB |
| Avatar | LivePortrait (fp16) | ~4GB |
| Restore | CodeFormer | ~2GB |
| Captions | faster-whisper | ~1.5GB |

## Tech Stack

|  | Tool | Cost |
|--|--|--|
| 🔍 | DuckDuckGo + BeautifulSoup | Free |
| 🧠 | Ollama + Llama 3.2 3B | Free |
| 🎙️ | F5-TTS + XTTS-v2 | Free |
| 🎭 | SadTalker | Free |
| 🖼️ | LivePortrait | Free |
| 🔧 | CodeFormer | Free |
| 📝 | faster-whisper | Free |
| 🎬 | MoviePy + FFmpeg | Free |
| 📊 | Streamlit | Free |
| 📱 | Instagrapi | Free |

## License

MIT
