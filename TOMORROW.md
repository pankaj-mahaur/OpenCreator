# OpenCreator — Issues To Fix Tomorrow

> Session date: 2026-03-01

---

## 1. 🔴 LivePortrait silently skipped at runtime [CRITICAL]

**Symptom:**  
When `VIDEO_GEN_PROVIDER=liveportrait`, the pipeline falls through to Google Veo → Kling  
without any visible LivePortrait error. The terminal shows:

```
INFO  🎬 Trying provider: liveportrait   ← starts
INFO  🎬 Trying provider: google         ← immediately falls back, no LP error logged
```

**Root cause (suspected):**  
`_generate_liveportrait()` raises an exception (likely `FileNotFoundError` for weights or  
an `ffprobe` subprocess failure) but the exception message is swallowed by the fallback  
chain. Need to surface this error clearly before falling back.

**Fix plan:**  
- Add `logger.exception(...)` (not just `logger.warning`) inside the liveportrait try-block  
  so the full traceback is printed even when falling back.
- Run with `VIDEO_GEN_PROVIDER=liveportrait` AND temporarily disable the fallback to force  
  the error to surface.
- Likely culprits to check:
  - `ffprobe` not found on PATH → install FFmpeg or add to PATH
  - LivePortrait `inference.py` CLI arg names (check `--flag-do-crop` vs `--flag_do_crop`)
  - `pretrained_weights` path resolution when subprocess is run from LP root

---

## 2. 🟡 Google API key invalid

**Symptom:**  
```
API_KEY_INVALID — API key not valid. Please pass a valid API key.
```

**Fix:**  
Update `.env` → `GOOGLE_API_KEY=<valid key from https://aistudio.google.com/apikey>`  
(Low priority since we're moving to local LP generation anyway)

---

## 3. 🟡 Kling AI rate-limited (429)

**Symptom:**  
```
HTTP 429 Too Many Requests → https://api.klingai.com/v1/videos/image2video
```

**Fix:**  
- Wait for Kling rate limit window to reset (free tier is very limited)
- Or add retry-with-backoff logic in `_generate_kling()`  
(Low priority — fallback only)

---

## 4. 🟡 `requests` version mismatch warning

**Symptom:**  
```
RequestsDependencyWarning: urllib3 (2.5.0) or chardet (6.0.0)/charset_normalizer doesn't 
match a supported version
```

**Fix:**  
```bash
pip install --upgrade requests urllib3 charset-normalizer
```

---

## 5. 📋 End-to-end test once LP is working

Once issue #1 is fixed, validate the full pipeline:

```bash
# Put a clear frontal portrait photo here first:
# assets/my_photo.png

python main.py --topic "Test topic"
```

Expected: TTS audio → LP animates avatar → final MP4 in `output/`

---

## Quick debug commands for tomorrow

```bash
# 1. Surface the real LivePortrait error:
python -c "
import sys, logging
logging.basicConfig(level=logging.DEBUG)
sys.path.insert(0, '.')
from pathlib import Path
from modules.video_generator import VideoGenerator
vg = VideoGenerator(provider='liveportrait')
# bypass fallback — call LP directly:
vg._generate_liveportrait(
    image_path=Path('assets/my_photo.png'),
    audio_path=None,
    output_path=Path('output/lp_test.mp4'),
)
"

# 2. Check ffprobe is on PATH:
ffprobe -version

# 3. Check LP inference.py args:
python third_party/LivePortrait/inference.py --help
```
