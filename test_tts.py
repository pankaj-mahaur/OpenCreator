"""
test_tts.py — Quick TTS / Voice Clone test
==========================================
Generates ~10 seconds of speech and saves it to output/test_audio.wav

Two modes:
  - Edge TTS (default, no GPU, instant):
      python test_tts.py

  - Qwen3-TTS voice clone (needs GPU + voice_samples/my_voice.wav):
      python test_tts.py --clone

Usage:
  python test_tts.py [--clone] [--text "Custom text here"]
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

sys.path.insert(0, str(Path(__file__).parent))
import config
from modules.voice_cloner import VoiceCloner

# ~10 seconds of natural-sounding speech at avg 130 wpm
DEFAULT_TEXT = (
    "Hey everyone, welcome back to the channel. "
    "Today I want to share something really interesting that I've been looking into lately. "
    "It's going to change the way you think about artificial intelligence. Let's dive right in."
)

def main():
    parser = argparse.ArgumentParser(description="TTS / Voice Clone test")
    parser.add_argument("--clone", action="store_true", help="Use Qwen3-TTS voice cloning")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Text to synthesize")
    parser.add_argument("--voice", default=config.EDGE_TTS_VOICE, help="Edge TTS voice name")
    parser.add_argument("--ref", default=None, help="Path to reference audio for cloning")
    args = parser.parse_args()

    output_path = config.OUTPUT_DIR / "test_audio.wav"

    if args.clone:
        ref = Path(args.ref) if args.ref else config.VOICE_SAMPLES_DIR / "my_voice.wav"
        if not ref.exists():
            print(f"\n[!] Voice sample not found: {ref}")
            print(f"    Record yourself speaking ~10s and save it to: {ref}")
            print("    Then re-run with --clone\n")
            sys.exit(1)
        print(f"\n[Qwen3-TTS] Cloning voice from: {ref}")
        cloner = VoiceCloner(use_cloning=True)
        cloner.generate(args.text, output_path, reference_audio=ref)
    else:
        print(f"\n[Edge TTS] Voice: {args.voice}")
        cloner = VoiceCloner(voice=args.voice, use_cloning=False)
        cloner.generate(args.text, output_path)

    print(f"\n[OK] Audio saved to: {output_path}")
    print(f"     Size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"\n     Text ({len(args.text)} chars):\n     {args.text[:80]}...")


if __name__ == "__main__":
    main()
