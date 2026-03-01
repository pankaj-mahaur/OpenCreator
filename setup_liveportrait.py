"""
setup_liveportrait.py
=====================
One-shot setup for local LivePortrait video generation.

Runs:
  1. pip install of all LivePortrait Python dependencies
  2. Download of pretrained model weights from HuggingFace (~1.5 GB for human models)

Usage:
    python setup_liveportrait.py

Notes:
  - Requires an internet connection for the first run.
  - onnxruntime-gpu requires a CUDA-capable GPU. On CPU-only machines,
    replace onnxruntime-gpu with onnxruntime in requirements.txt.
  - insightface may require Microsoft C++ Build Tools on Windows:
    https://visualstudio.microsoft.com/visual-cpp-build-tools/
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
LP_ROOT = ROOT / "third_party" / "LivePortrait"
WEIGHTS_ROOT = LP_ROOT / "pretrained_weights"

# ---------------------------------------------------------------------------
# 1. Pip dependencies
# ---------------------------------------------------------------------------
LP_DEPS = [
    "onnxruntime-gpu>=1.18",   # GPU inference; swap to onnxruntime if no GPU
    "insightface>=0.7",        # face detection (needs C++ build tools on Windows)
    "tyro>=0.8",
    "pyyaml>=6.0",
    "opencv-python>=4.9",
    "scipy>=1.13",
    "imageio>=2.34",
    "imageio-ffmpeg>=0.5",
    "scikit-image>=0.24",
    "lmdb>=1.4",
    "tqdm>=4.66",
    "pykalman>=0.9.7",
    "albumentations>=1.4",
]


def install_deps():
    print("\n[1/2] Installing LivePortrait dependencies...\n")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + LP_DEPS
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(
            "\n[!] Some dependencies failed to install.\n"
            "    If insightface failed, install Visual C++ Build Tools first:\n"
            "    https://visualstudio.microsoft.com/visual-cpp-build-tools/\n"
            "    Then re-run this script."
        )
        sys.exit(1)
    print("\n[OK] Dependencies installed.")


# ---------------------------------------------------------------------------
# 2. Weight download
# ---------------------------------------------------------------------------
# HuggingFace repo: KwaiVGI/LivePortrait
# Human model weights only (animals not needed for talking-head video)

HUMAN_BASE = WEIGHTS_ROOT / "liveportrait" / "base_models"
HUMAN_RETARGET = WEIGHTS_ROOT / "liveportrait" / "retargeting_models"

# Maps local relative path -> HuggingFace raw URL
HF_BASE = "https://huggingface.co/KwaiVGI/LivePortrait/resolve/main/pretrained_weights"

WEIGHT_FILES = {
    # Base models
    HUMAN_BASE / "appearance_feature_extractor.pth": f"{HF_BASE}/liveportrait/base_models/appearance_feature_extractor.pth",
    HUMAN_BASE / "motion_extractor.pth":             f"{HF_BASE}/liveportrait/base_models/motion_extractor.pth",
    HUMAN_BASE / "spade_generator.pth":              f"{HF_BASE}/liveportrait/base_models/spade_generator.pth",
    HUMAN_BASE / "warping_module.pth":               f"{HF_BASE}/liveportrait/base_models/warping_module.pth",
    # Retargeting / stitching
    HUMAN_RETARGET / "stitching_retargeting_module.pth": f"{HF_BASE}/liveportrait/retargeting_models/stitching_retargeting_module.pth",
    # insightface buffalo_l landmark/detection models (auto-downloaded by insightface on first use)
    # — no manual download needed; insightface fetches from its own CDN.
}


def download_weights():
    print("\n[2/2] Downloading pretrained weights...\n")

    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests

    total = len(WEIGHT_FILES)
    for idx, (dest, url) in enumerate(WEIGHT_FILES.items(), 1):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"  [{idx}/{total}] Already exists, skipping: {dest.name}")
            continue

        print(f"  [{idx}/{total}] Downloading {dest.name} ...")
        try:
            r = requests.get(url, stream=True, timeout=120)
            r.raise_for_status()
            total_bytes = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes:
                        pct = downloaded / total_bytes * 100
                        print(f"\r      {pct:5.1f}%  ({downloaded // 1_048_576} / {total_bytes // 1_048_576} MB)", end="", flush=True)
            print(f"\r      [OK] {dest.name} ({downloaded // 1_048_576} MB)          ")
        except Exception as e:
            print(f"\n      [ERROR] Failed to download {dest.name}: {e}")
            print(f"      Manual URL: {url}")

    print("\n[OK] All weights downloaded.")


# ---------------------------------------------------------------------------
# 3. Quick smoke test
# ---------------------------------------------------------------------------
def smoke_test():
    print("\n[3/3] Smoke test...\n")
    sys.path.insert(0, str(ROOT))

    try:
        import config
        from modules.video_generator import VideoGenerator
        vg = VideoGenerator(provider="liveportrait")
        print("  VideoGenerator(liveportrait) initialised OK")
    except Exception as e:
        print(f"  [ERROR] {e}")
        return

    # Check weights
    missing = [p for p in WEIGHT_FILES if not Path(p).exists()]
    if missing:
        print(f"\n  [WARN] {len(missing)} weight file(s) still missing:")
        for m in missing:
            print(f"    - {m}")
    else:
        print("  All weight files present.")

    print("\n  Ready to use! Set VIDEO_GEN_PROVIDER=liveportrait in your .env")


if __name__ == "__main__":
    print("=" * 60)
    print("  LivePortrait Local Setup")
    print("=" * 60)

    if not LP_ROOT.exists():
        print(f"\n[ERROR] LivePortrait not found at {LP_ROOT}")
        print("  Run: git clone https://github.com/KwaiVGI/LivePortrait.git third_party/LivePortrait")
        sys.exit(1)

    install_deps()
    download_weights()
    smoke_test()

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
