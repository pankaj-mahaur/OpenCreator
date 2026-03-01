"""
config.py — Central configuration for the OpenCreator pipeline.

Loads all settings from .env, provides defaults, and exposes
typed configuration to every module.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────
load_dotenv()

# ── Paths ──────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
OUTPUT_DIR = ROOT_DIR / "output"
ASSETS_DIR = ROOT_DIR / "assets"
VOICE_SAMPLES_DIR = ROOT_DIR / "voice_samples"
SESSIONS_DIR = ROOT_DIR / "sessions"

# Ensure dirs exist
for d in [OUTPUT_DIR, ASSETS_DIR, VOICE_SAMPLES_DIR, SESSIONS_DIR]:
    d.mkdir(exist_ok=True)

# ── LLM ────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" or "openai"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# ── Voice ──────────────────────────────────────────────────
# Set VOICE_CLONING=true to enable local Qwen3-TTS voice cloning (requires CUDA GPU)
# Falls back to Edge TTS if cloning is disabled or no GPU is available
VOICE_CLONING = os.getenv("VOICE_CLONING", "false").lower() == "true"
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-ChristopherNeural")

# ── Qwen3 TTS (local voice cloning) ───────────────────────
QWEN_TTS_MODEL = os.getenv("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
QWEN_TTS_DEVICE = os.getenv("QWEN_TTS_DEVICE", "cuda:0")  # Use "cpu" if no GPU
# Transcript of your reference audio — improves clone quality significantly.
# Leave blank to use x_vector_only mode (no transcript, slightly lower quality).
VOICE_CLONE_REF_TEXT = os.getenv("VOICE_CLONE_REF_TEXT", "")

# ── Video Generation ───────────────────────────────────────
# Provider: "liveportrait" (local GPU, free) | "google" (Veo 3.1) | "kling"
VIDEO_GEN_PROVIDER = os.getenv("VIDEO_GEN_PROVIDER", "liveportrait")
AVATAR_PHOTO_PATH = Path(os.getenv("AVATAR_PHOTO_PATH", "assets/my_photo.png"))

# Google Veo 3.1
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Kling AI (fallback)
KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY", "")

# Legacy FAL.ai (deprecated, kept for backward compat)
FAL_API_KEY = os.getenv("FAL_API_KEY", "")

# ── B-Roll ─────────────────────────────────────────────────
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# ── Instagram (for future use) ────────────────────────────
IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
IG_SESSION_PATH = Path(os.getenv("IG_SESSION_PATH", "sessions/session.json"))

# ── Web UI ─────────────────────────────────────────────────
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8501"))

# ── Video Settings ─────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

# ── Content Settings ───────────────────────────────────────
MAX_SCRIPT_DURATION = 90    # seconds
MIN_SCRIPT_DURATION = 30    # seconds
TARGET_SCRIPT_DURATION = 60 # seconds
