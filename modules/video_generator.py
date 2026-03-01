"""
video_generator.py — Video generation with three providers:

  1. LivePortrait (local, free, GPU-driven — preferred when weights are present)
  2. Google Veo 3.1  (cloud, primary API fallback)
  3. Kling AI        (cloud, final fallback via JWT REST API)

Generates talking-head / avatar videos from an avatar image + audio file.
"""

import base64
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)


class VideoGenerator:
    """
    Video generation dispatcher.
    
    Tries Google Veo first, falls back to Kling AI.
    """

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or config.VIDEO_GEN_PROVIDER
        self._google = None
        self._kling = None

        logger.info(f"🎬 VideoGenerator initialized — provider: {self.provider}")

    def generate(
        self,
        image_path: Path,
        prompt: str = "A person talking naturally to the camera",
        output_path: Optional[Path] = None,
        audio_path: Optional[Path] = None,
        progress_callback=None,
    ) -> Path:
        """
        Generate video with auto-fallback between providers.

        Provider priority:
          liveportrait → google → kling

        Args:
            image_path:        Avatar image (PNG/JPG).
            prompt:            Text prompt describing the desired video.
            output_path:       Destination MP4 path (auto-generated if None).
            audio_path:        Path to an audio file (.wav/.mp3) used by
                               LivePortrait to drive lip-sync. Required when
                               provider is 'liveportrait'.
            progress_callback: Optional callable(msg: str, pct: float).
        """
        if output_path is None:
            output_path = config.OUTPUT_DIR / "generated_video.mp4"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build ordered list of providers to try
        if self.provider == "liveportrait":
            provider_chain = ["liveportrait", "google", "kling"]
        elif self.provider == "google":
            provider_chain = ["google", "kling"]
        elif self.provider == "kling":
            provider_chain = ["kling", "google"]
        else:
            logger.warning(f"Unknown provider '{self.provider}', defaulting to google → kling")
            provider_chain = ["google", "kling"]

        last_error: Optional[Exception] = None
        for provider in provider_chain:
            try:
                logger.info(f"🎬 Trying provider: {provider}")
                if provider == "liveportrait":
                    return self._generate_liveportrait(
                        image_path, audio_path, output_path, progress_callback
                    )
                elif provider == "google":
                    return self._generate_google(
                        image_path, prompt, output_path, progress_callback
                    )
                elif provider == "kling":
                    return self._generate_kling(
                        image_path, prompt, output_path, progress_callback
                    )
            except Exception as e:
                logger.warning(f"⚠️ {provider} failed: {e}")
                last_error = e
                if provider != provider_chain[-1]:
                    logger.info(f"🔄 Trying next provider...")

        raise RuntimeError(
            f"All video providers failed. Last error: {last_error}"
        )

    # ── Google Veo 3.1 ──────────────────────────────────────

    def _generate_google(
        self, image_path: Path, prompt: str, output_path: Path, progress_callback=None
    ) -> Path:
        """Generate video using Google Veo 3.1 via google-genai SDK."""
        from google import genai
        from google.genai import types

        api_key = config.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set. Get one at https://aistudio.google.com/apikey")

        client = genai.Client(api_key=api_key)

        logger.info("🎬 [Google Veo 3.1] Generating video...")
        logger.info(f"   Image: {image_path}")
        logger.info(f"   Prompt: {prompt[:80]}...")

        if progress_callback:
            progress_callback("Uploading image to Google...", 0.1)

        # Read image and create Image object
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        suffix = image_path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime_type = mime_map.get(suffix, "image/png")

        image = types.Image(image_bytes=image_bytes, mime_type=mime_type)

        if progress_callback:
            progress_callback("Submitting to Veo 3.1...", 0.2)

        # Submit video generation request
        operation = client.models.generate_videos(
            model="veo-3.1-generate-preview",
            prompt=prompt,
            image=image,
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",          # Portrait for Reels
            ),
        )

        logger.info("   📤 Job submitted, polling for completion...")
        if progress_callback:
            progress_callback("Video generating (this takes a few minutes)...", 0.3)

        # Poll until done — with Rich progress bar
        max_wait = 600  # 10 minutes
        elapsed = 0
        poll_interval = 10

        try:
            from rich.live import Live
            from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

            progress_bar = Progress(
                SpinnerColumn("dots"),
                TextColumn("[magenta]Video Gen (Veo 3.1)[/magenta]"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                TextColumn("[dim]~3-5 min typical[/dim]"),
            )
            task = progress_bar.add_task("veo", total=max_wait)

            with Live(progress_bar, refresh_per_second=2):
                while not operation.done:
                    time.sleep(poll_interval)
                    elapsed += poll_interval
                    operation = client.operations.get(operation)

                    pct = min(elapsed, int(max_wait * 0.95))
                    progress_bar.update(task, completed=pct)

                    if progress_callback:
                        p = min(0.3 + (elapsed / max_wait) * 0.55, 0.85)
                        progress_callback(f"Generating... ({elapsed}s)", p)

                    if elapsed >= max_wait:
                        raise TimeoutError(f"Google Veo timed out after {max_wait}s")

                progress_bar.update(task, completed=max_wait)

        except ImportError:
            # Fallback without Rich
            while not operation.done:
                time.sleep(poll_interval)
                elapsed += poll_interval
                operation = client.operations.get(operation)
                logger.info(f"   ⏳ Polling... ({elapsed}s elapsed)")

                if progress_callback:
                    p = min(0.3 + (elapsed / max_wait) * 0.55, 0.85)
                    progress_callback(f"Generating... ({elapsed}s)", p)

                if elapsed >= max_wait:
                    raise TimeoutError(f"Google Veo timed out after {max_wait}s")

        # Download the generated video
        logger.info("   📥 Downloading video from Google...")
        if progress_callback:
            progress_callback("Downloading video...", 0.9)

        generated_video = operation.response.generated_videos[0]
        client.files.download(file=generated_video.video)
        generated_video.video.save(str(output_path))

        logger.info(f"   ✅ Video saved: {output_path}")
        if progress_callback:
            progress_callback("Video ready!", 1.0)

        return output_path

    # ── Kling AI ────────────────────────────────────────────

    def _generate_kling(
        self, image_path: Path, prompt: str, output_path: Path, progress_callback=None
    ) -> Path:
        """Generate video using Kling AI direct API with JWT auth."""
        import jwt as pyjwt

        access_key = config.KLING_ACCESS_KEY
        secret_key = config.KLING_SECRET_KEY
        if not access_key or not secret_key:
            raise ValueError("KLING_ACCESS_KEY / KLING_SECRET_KEY not set")

        logger.info("🎬 [Kling AI] Generating video...")
        logger.info(f"   Image: {image_path}")
        logger.info(f"   Prompt: {prompt[:80]}...")

        # Generate JWT token
        now = int(time.time())
        payload = {
            "iss": access_key,
            "exp": now + 1800,  # 30 minutes
            "nbf": now - 5,
        }
        token = pyjwt.encode(payload, secret_key, algorithm="HS256",
                             headers={"alg": "HS256", "typ": "JWT"})

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        if progress_callback:
            progress_callback("Uploading image to Kling AI...", 0.1)

        # Convert image to base64
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        suffix = image_path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime_type = mime_map.get(suffix, "image/png")

        # Submit task
        api_base = "https://api.klingai.com/v1"
        create_payload = {
            "model_name": "kling-v1",
            "image": image_b64,  # Kling expects raw base64 string without data: URL prefix
            "prompt": prompt,
            "cfg_scale": 0.5,
            "mode": "std",
            "aspect_ratio": "9:16",
            "duration": "5",
        }

        if progress_callback:
            progress_callback("Submitting to Kling AI...", 0.2)

        timeout = httpx.Timeout(30.0, read=300.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{api_base}/videos/image2video", json=create_payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"Kling API returned no task_id: {data}")

        logger.info(f"   📤 Task submitted: {task_id}")

        if progress_callback:
            progress_callback("Video generating...", 0.3)

        # Poll for completion
        max_wait = 600
        elapsed = 0
        poll_interval = 10
        video_url = None

        with httpx.Client(timeout=timeout) as client:
            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval

                # Regenerate JWT (in case it expires)
                now = int(time.time())
                payload = {"iss": access_key, "exp": now + 1800, "nbf": now - 5}
                token = pyjwt.encode(payload, secret_key, algorithm="HS256",
                                     headers={"alg": "HS256", "typ": "JWT"})
                headers["Authorization"] = f"Bearer {token}"

                resp = client.get(f"{api_base}/videos/image2video/{task_id}", headers=headers)
                resp.raise_for_status()
                status_data = resp.json()

                task_status = status_data.get("data", {}).get("task_status", "")
                logger.info(f"   ⏳ Status: {task_status} ({elapsed}s elapsed)")

                if task_status == "succeed":
                    works = status_data.get("data", {}).get("task_result", {}).get("videos", [])
                    if works:
                        video_url = works[0].get("url")
                    break
                elif task_status == "failed":
                    msg = status_data.get("data", {}).get("task_status_msg", "Unknown")
                    raise RuntimeError(f"Kling video generation failed: {msg}")

                if progress_callback:
                    progress = min(0.3 + (elapsed / max_wait) * 0.55, 0.85)
                    progress_callback(f"Generating... ({elapsed}s)", progress)

        if not video_url:
            raise RuntimeError("Kling API returned no video URL")

        # Download video
        logger.info(f"   📥 Downloading video...")
        if progress_callback:
            progress_callback("Downloading video...", 0.9)

        with httpx.Client(timeout=timeout) as client:
            with client.stream("GET", video_url) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)

        logger.info(f"   ✅ Video saved: {output_path}")
        if progress_callback:
            progress_callback("Video ready!", 1.0)

        return output_path

    # ── LivePortrait (local) ─────────────────────────────────

    def _generate_liveportrait(
        self,
        image_path: Path,
        audio_path: Optional[Path],
        output_path: Path,
        progress_callback=None,
    ) -> Path:
        """
        Generate a talking-head video locally using LivePortrait.

        LivePortrait animates a portrait image using a driving video.  Because
        it expects a *video* driver (not a raw audio file), we first convert
        the audio into a silent black-frame video that carries the audio track,
        then run LivePortrait inference so it lip-syncs from the audio.

        Weight location  : third_party/LivePortrait/pretrained_weights/
        Model page       : https://github.com/KwaiVGI/LivePortrait
        VRAM requirement : ~4-5 GB on RTX 3050 6 GB with --flag_do_crop
        """
        lp_root = Path(__file__).parent.parent / "third_party" / "LivePortrait"
        inference_script = lp_root / "inference.py"

        if not inference_script.exists():
            raise FileNotFoundError(
                f"LivePortrait inference script not found at {inference_script}. "
                "Make sure you have cloned the repo into third_party/LivePortrait."
            )

        # Verify pretrained weights exist
        weights_dir = lp_root / "pretrained_weights"
        if not any(weights_dir.iterdir()) if weights_dir.exists() else True:
            raise FileNotFoundError(
                f"LivePortrait pretrained weights not found in {weights_dir}. "
                "Download them from https://huggingface.co/KwaiVGI/LivePortrait "
                "and place them in third_party/LivePortrait/pretrained_weights/."
            )

        if not shutil.which("ffmpeg"):
            raise EnvironmentError(
                "ffmpeg not found in PATH. Install FFmpeg and ensure it is on PATH."
            )

        # ── Step 1: Build a driving video from audio ─────────
        # LivePortrait needs a driving *video*. We create a black-frame video
        # with the audio embedded so the audio drive passes through.
        driving_video = output_path.with_suffix(".driving.mp4")
        if audio_path and Path(audio_path).exists():
            logger.info("   🎵 Creating driving video from audio...")
            if progress_callback:
                progress_callback("Preparing driving video from audio...", 0.05)

            # Detect audio duration
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True, text=True, check=True,
            )
            duration = float(probe.stdout.strip())

            # Create black-frame video with audio
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", f"color=black:size=512x512:rate=25:duration={duration}",
                    "-i", str(audio_path),
                    "-c:v", "libx264", "-c:a", "aac",
                    "-shortest",
                    str(driving_video),
                ],
                check=True, capture_output=True,
            )
            logger.info(f"   ✅ Driving video created ({duration:.1f}s)")
        else:
            logger.warning(
                "No audio_path provided for LivePortrait — using a 5-second silent driving video."
            )
            if progress_callback:
                progress_callback("Creating silent driving video...", 0.05)
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "color=black:size=512x512:rate=25:duration=5",
                    "-c:v", "libx264",
                    str(driving_video),
                ],
                check=True, capture_output=True,
            )

        # ── Step 2: Run LivePortrait inference ───────────────
        lp_output_dir = output_path.parent / "liveportrait_out"
        lp_output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("   🎨 Running LivePortrait inference (this may take a minute)...")
        if progress_callback:
            progress_callback("Running LivePortrait — generating video...", 0.2)

        cmd = [
            sys.executable,              # same Python env
            str(inference_script),
            "--source", str(image_path),
            "--driving", str(driving_video),
            "--output-dir", str(lp_output_dir),
            "--flag-do-crop",            # crop face region — reduces VRAM
            "--flag-pasteback",          # paste animated face back onto original bg
        ]

        logger.info(f"   Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=str(lp_root),            # must run from LP root so its src/ imports work
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"LivePortrait stderr:\n{result.stderr[-2000:]}")
            raise RuntimeError(
                f"LivePortrait inference failed (exit {result.returncode}).\n"
                f"Stderr (last 2000 chars):\n{result.stderr[-2000:]}"
            )

        logger.info(f"   LivePortrait stdout:\n{result.stdout[-500:]}")

        if progress_callback:
            progress_callback("Merging audio into final video...", 0.85)

        # ── Step 3: Find LP output and mux in the audio ──────
        # LivePortrait writes <driving_stem>_<source_stem>.mp4 into output-dir
        lp_files = list(lp_output_dir.glob("*.mp4"))
        if not lp_files:
            raise RuntimeError(
                f"LivePortrait did not produce any .mp4 in {lp_output_dir}. "
                f"Stdout:\n{result.stdout[-500:]}"
            )
        lp_video = sorted(lp_files)[-1]   # take the latest

        if audio_path and Path(audio_path).exists():
            # Mux the original audio into the LP video
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(lp_video),
                    "-i", str(audio_path),
                    "-c:v", "copy", "-c:a", "aac",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest",
                    str(output_path),
                ],
                check=True, capture_output=True,
            )
        else:
            shutil.copy2(lp_video, output_path)

        # Cleanup temp files
        try:
            driving_video.unlink(missing_ok=True)
        except Exception:
            pass

        logger.info(f"   ✅ LivePortrait video saved: {output_path}")
        if progress_callback:
            progress_callback("Video ready!", 1.0)

        return output_path

    # ── Utilities ───────────────────────────────────────────

    @staticmethod
    def list_models() -> dict:
        """List available video generation providers."""
        return {
            "liveportrait": "LivePortrait (local GPU - free, no API key needed)",
            "google": "Google Veo 3.1 (cloud - primary API)",
            "kling": "Kling AI (cloud - fallback)",
        }


# -- Standalone test --
if __name__ == "__main__":
    import sys as _sys
    # Allow running directly: python modules/video_generator.py
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    import config  # re-import with corrected path
    logging.basicConfig(level=logging.INFO)
    print("Available providers:")
    for k, v in VideoGenerator.list_models().items():
        print(f"  {k:15s}  {v}")
    print()
    print(f"Current provider   : {config.VIDEO_GEN_PROVIDER}")
    print(f"Google API key set : {'Yes' if config.GOOGLE_API_KEY else 'No'}")
    print(f"Kling keys set     : {'Yes' if config.KLING_ACCESS_KEY else 'No'}")

    lp_weights = (
        Path(__file__).parent.parent / "third_party" / "LivePortrait" / "pretrained_weights"
    )
    lp_weights_ok = lp_weights.exists() and any(lp_weights.iterdir())
    print(f"LivePortrait weights: {'[OK]' if lp_weights_ok else '[MISSING] -- download from https://huggingface.co/KwaiVGI/LivePortrait'}")
