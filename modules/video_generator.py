"""
video_generator.py — Video generation via Google Veo 3.1 (primary) + Kling AI (fallback).

Generates talking-head / avatar videos from an image + prompt.
Google Veo 3.1 is used by default (free credits via AI Studio).
Kling AI direct API is the fallback (JWT auth).
"""

import base64
import logging
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
        progress_callback=None,
    ) -> Path:
        """Generate video with auto-fallback between providers."""
        if output_path is None:
            output_path = config.OUTPUT_DIR / "generated_video.mp4"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Try primary provider
        try:
            if self.provider == "google":
                return self._generate_google(image_path, prompt, output_path, progress_callback)
            elif self.provider == "kling":
                return self._generate_kling(image_path, prompt, output_path, progress_callback)
            else:
                logger.warning(f"Unknown provider '{self.provider}', trying google")
                return self._generate_google(image_path, prompt, output_path, progress_callback)

        except Exception as e:
            logger.warning(f"⚠️ {self.provider} failed: {e}")

            # Fallback
            fallback = "kling" if self.provider == "google" else "google"
            logger.info(f"🔄 Falling back to {fallback}...")

            try:
                if fallback == "google":
                    return self._generate_google(image_path, prompt, output_path, progress_callback)
                else:
                    return self._generate_kling(image_path, prompt, output_path, progress_callback)
            except Exception as e2:
                raise RuntimeError(f"All video providers failed. Primary: {e}, Fallback: {e2}")

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
                person_generation="allow_all",
            ),
        )

        logger.info("   📤 Job submitted, polling for completion...")
        if progress_callback:
            progress_callback("Video generating (this takes a few minutes)...", 0.3)

        # Poll until done
        max_wait = 600  # 10 minutes
        elapsed = 0
        poll_interval = 10

        while not operation.done:
            time.sleep(poll_interval)
            elapsed += poll_interval
            operation = client.operations.get(operation)

            if progress_callback:
                progress = min(0.3 + (elapsed / max_wait) * 0.55, 0.85)
                progress_callback(f"Generating... ({elapsed}s)", progress)

            logger.info(f"   ⏳ Polling... ({elapsed}s elapsed)")

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
            "image": f"data:{mime_type};base64,{image_b64}",
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

    # ── Utilities ───────────────────────────────────────────

    @staticmethod
    def list_models() -> dict:
        """List available video generation providers."""
        return {
            "google": "Google Veo 3.1 (Primary)",
            "kling": "Kling AI (Fallback)",
        }


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Available providers:", VideoGenerator.list_models())
    print(f"Current provider: {config.VIDEO_GEN_PROVIDER}")
    print(f"Google API key set: {'Yes' if config.GOOGLE_API_KEY else 'No'}")
    print(f"Kling keys set: {'Yes' if config.KLING_ACCESS_KEY else 'No'}")
