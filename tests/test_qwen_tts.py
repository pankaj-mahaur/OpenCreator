"""
Quick smoke test for local Qwen3-TTS voice cloning.
Run: python _test_qwen_tts.py

This will:
  1. Try voice cloning if VOICE_CLONING=true AND voice_samples/my_voice.wav exists
  2. Otherwise test Edge TTS (always works, no GPU needed)
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s — %(message)s"
)

# ── Check packages ────────────────────────────────────────────
print("=" * 55)
print("  Qwen3-TTS Integration Test")
print("=" * 55)

missing = []
for pkg, import_name in [("qwen-tts", "qwen_tts"), ("soundfile", "soundfile"), ("torch", "torch")]:
    try:
        __import__(import_name)
        print(f"  ✅ {pkg}")
    except ImportError:
        print(f"  ❌ {pkg} — NOT INSTALLED")
        missing.append(pkg)

if missing:
    print(f"\n  ⚠️  Missing packages: {', '.join(missing)}")
    print(f"  Run: pip install {' '.join(missing)}")
    print()

# ── Check voice sample ────────────────────────────────────────
import config

ref_audio = config.VOICE_SAMPLES_DIR / "my_voice.wav"
print(f"\n  Voice sample:    {'✅ Found' if ref_audio.exists() else '❌ Missing'} ({ref_audio})")
print(f"  VOICE_CLONING:   {config.VOICE_CLONING}")
print(f"  QWEN_TTS_MODEL:  {config.QWEN_TTS_MODEL}")
print(f"  QWEN_TTS_DEVICE: {config.QWEN_TTS_DEVICE}")
print(f"  REF_TEXT set:    {'Yes' if config.VOICE_CLONE_REF_TEXT else 'No (x-vector mode)'}")
print()

# ── Run TTS ───────────────────────────────────────────────────
from modules.voice_cloner import VoiceCloner

output = Path("output/_test_qwen_tts.wav")
test_text = "Hello! This is a test of the OpenCreator voice cloning system. How does it sound?"

print(f"  Test text: \"{test_text[:60]}...\"")
print(f"  Output:    {output}")
print()

try:
    cloner = VoiceCloner()
    cloner.generate(test_text, output)

    if output.exists() and output.stat().st_size > 0:
        size_kb = output.stat().st_size / 1024
        print(f"\n  ✅ SUCCESS — {output} ({size_kb:.1f} KB)")
        print(f"  🎧 Play it to check the voice quality!")
    else:
        print("\n  ❌ FAILED — output file missing or empty")
        sys.exit(1)

except Exception as e:
    print(f"\n  ❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
