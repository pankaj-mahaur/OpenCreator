"""
download_weights.py
===================
Downloads all LivePortrait pretrained weights from HuggingFace.

Official repo: https://huggingface.co/KlingTeam/LivePortrait
(KwaiVGI/LivePortrait redirects here as of 2025)

Run:
    python download_weights.py
"""
import subprocess
import sys
from pathlib import Path

LP_ROOT = Path(__file__).parent / "third_party" / "LivePortrait"
WEIGHTS_DIR = LP_ROOT / "pretrained_weights"

HF_REPO = "KlingTeam/LivePortrait"
HF_BASE = f"https://huggingface.co/{HF_REPO}/resolve/main/pretrained_weights"

# All files needed for HUMAN portrait animation (not animals)
REQUIRED_FILES = [
    # LivePortrait core models
    "liveportrait/base_models/appearance_feature_extractor.pth",
    "liveportrait/base_models/motion_extractor.pth",
    "liveportrait/base_models/spade_generator.pth",
    "liveportrait/base_models/warping_module.pth",
    "liveportrait/retargeting_models/stitching_retargeting_module.pth",
    "liveportrait/landmark.onnx",
    # InsightFace face detection models
    "insightface/models/buffalo_l/2d106det.onnx",
    "insightface/models/buffalo_l/det_10g.onnx",
]


def ensure_hf_hub():
    """Install huggingface_hub[cli] if not present."""
    try:
        import huggingface_hub  # noqa
    except ImportError:
        print("Installing huggingface_hub...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "huggingface_hub[cli]"],
            check=True,
        )


def download_with_hf_cli():
    """Use huggingface-cli to download the full weights folder (recommended)."""
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading weights from {HF_REPO} to {WEIGHTS_DIR} ...")
    print("(This is ~1.5 GB — will take a few minutes)\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "huggingface_hub.commands.huggingface_cli",
            "download",
            HF_REPO,
            "--local-dir", str(WEIGHTS_DIR),
            "--exclude", "*.git*", "README.md", "docs", "*animals*",
        ],
        cwd=str(LP_ROOT),
    )
    return result.returncode == 0


def download_with_requests():
    """Fallback: download each file individually via requests."""
    try:
        import requests
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
        import requests

    print(f"\nDownloading {len(REQUIRED_FILES)} weight files individually...\n")
    errors = []
    for rel in REQUIRED_FILES:
        dest = WEIGHTS_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists() and dest.stat().st_size > 100_000:
            print(f"  [SKIP] {rel}  ({dest.stat().st_size // 1_048_576} MB already)")
            continue

        url = f"{HF_BASE}/{rel}"
        print(f"  [DL]   {Path(rel).name} ...", flush=True)
        try:
            r = requests.get(url, stream=True, timeout=300)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r         {done // 1_048_576}/{total // 1_048_576} MB", end="", flush=True)
            print(f"\r  [OK]   {Path(rel).name}  ({done // 1_048_576} MB)          ")
        except Exception as e:
            print(f"\r  [ERR]  {Path(rel).name}: {e}")
            errors.append(rel)

    if errors:
        print(f"\n[!] {len(errors)} file(s) failed:")
        for e in errors:
            print(f"    {e}")
        print(f"\n    Manual URL: https://huggingface.co/{HF_REPO}/tree/main/pretrained_weights")
        return False
    return True


def verify():
    """Check all required files are present."""
    print("\nVerifying weights...")
    missing = []
    for rel in REQUIRED_FILES:
        dest = WEIGHTS_DIR / rel
        if not dest.exists() or dest.stat().st_size < 100_000:
            missing.append(rel)
        else:
            print(f"  [OK] {rel}  ({dest.stat().st_size // 1_048_576} MB)")

    if missing:
        print(f"\n[!] {len(missing)} file(s) still missing:")
        for m in missing:
            print(f"    {m}")
        return False

    print("\nAll weights present and accounted for.")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("  LivePortrait Weight Downloader")
    print(f"  Repo: {HF_REPO}")
    print("=" * 60)

    ensure_hf_hub()

    # Try huggingface-cli first (handles auth, resume, etc.)
    ok = download_with_hf_cli()
    if not ok:
        print("\n[!] huggingface-cli failed, falling back to direct download...")
        ok = download_with_requests()

    verify()
