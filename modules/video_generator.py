"""
video_generator.py — API-based video generation via FAL.ai.

Generates talking head / avatar videos using cloud APIs.
Supports multiple models: Kling 1.6, Wan 2.1, MiniMax (Hailuo).
"""

import base64
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)

# ── Model Endpoints ────────────────────────────────────────
# FAL.ai model IDs for different video generation models
MODELS = {
    "kling-1.6": {
        "endpoint": "fal-ai/kling-video/v1.6/standard/image-to-video",
        "name": "Kling 1.6 Standard",
        "max_duration": 10,  # seconds
    },
    "wan": {
        "endpoint": "fal-ai/wan/v2.1/image-to-video",
        "name": "Wan 2.1",
        "max_duration": 5,
    },
    "minimax": {
        "endpoint": "fal-ai/minimax-video/image-to-video",
        "name": "MiniMax Hailuo",
        "max_duration": 6,
    },
}


class VideoGenerator:
    """Generate talking head videos using FAL.ai API."""

    def __init__(self, model: Optional[str] = None):
        self.model_key = model or config.VIDEO_GEN_MODEL
        if self.model_key not in MODELS:
            logger.warning(f"Unknown model '{self.model_key}', falling back to kling-1.6")
            self.model_key = "kling-1.6"

        self.model = MODELS[self.model_key]
        self.api_key = config.FAL_API_KEY
        self.base_url = "https://queue.fal.run"
        self.timeout = httpx.Timeout(30.0, read=300.0)

        if not self.api_key:
            raise ValueError(
                "FAL_API_KEY not set. Get one at https://fal.ai and add to .env"
            )

        logger.info(f"🎬 VideoGenerator initialized with {self.model['name']}")

    def _get_headers(self) -> dict:
        """Get API request headers."""
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def _image_to_data_url(self, image_path: Path) -> str:
        """Convert a local image to a base64 data URL."""
        suffix = image_path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/png")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    def generate(
        self,
        image_path: Path,
        prompt: str = "A person talking naturally to the camera, professional lighting, studio background",
        output_path: Optional[Path] = None,
        progress_callback=None,
    ) -> Path:
        """
        Generate a video from an image using FAL.ai.

        Args:
            image_path: Path to the source image (avatar photo)
            prompt: Text prompt describing the desired video
            output_path: Where to save the output video
            progress_callback: Optional callback(status, progress) for UI updates

        Returns:
            Path to the generated video file
        """
        if output_path is None:
            output_path = config.OUTPUT_DIR / "generated_video.mp4"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"🎬 Generating video with {self.model['name']}...")
        logger.info(f"   Image: {image_path}")
        logger.info(f"   Prompt: {prompt[:80]}...")

        if progress_callback:
            progress_callback("Submitting to API...", 0.1)

        # Step 1: Submit the job
        request_id = self._submit_job(image_path, prompt)
        logger.info(f"   📤 Job submitted: {request_id}")

        if progress_callback:
            progress_callback("Video generating...", 0.3)

        # Step 2: Poll until complete
        result = self._poll_result(request_id, progress_callback)

        # Step 3: Download the video
        video_url = self._extract_video_url(result)
        if not video_url:
            raise RuntimeError("API returned no video URL in response")

        logger.info(f"   📥 Downloading video...")
        if progress_callback:
            progress_callback("Downloading video...", 0.9)

        self._download_video(video_url, output_path)

        logger.info(f"   ✅ Video saved: {output_path}")
        if progress_callback:
            progress_callback("Video ready!", 1.0)

        return output_path

    def _submit_job(self, image_path: Path, prompt: str) -> str:
        """Submit a video generation job to FAL.ai queue."""
        endpoint = f"{self.base_url}/{self.model['endpoint']}"

        image_url = self._image_to_data_url(image_path)

        payload = {
            "image_url": image_url,
            "prompt": prompt,
        }

        # Add model-specific params
        if self.model_key == "kling-1.6":
            payload["duration"] = "5"   # 5 or 10 seconds
        elif self.model_key == "minimax":
            payload["prompt_optimizer"] = True

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(endpoint, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()

        request_id = data.get("request_id")
        if not request_id:
            raise RuntimeError(f"No request_id in response: {data}")

        return request_id

    def _poll_result(self, request_id: str, progress_callback=None) -> dict:
        """Poll FAL.ai for job completion."""
        status_url = f"{self.base_url}/{self.model['endpoint']}/requests/{request_id}/status"
        result_url = f"{self.base_url}/{self.model['endpoint']}/requests/{request_id}"

        max_wait = 600  # 10 minutes max
        poll_interval = 5  # seconds
        elapsed = 0

        with httpx.Client(timeout=self.timeout) as client:
            while elapsed < max_wait:
                try:
                    resp = client.get(status_url, headers=self._get_headers())
                    resp.raise_for_status()
                    status_data = resp.json()

                    status = status_data.get("status", "UNKNOWN")
                    logger.info(f"   ⏳ Status: {status} ({elapsed}s elapsed)")

                    if status == "COMPLETED":
                        # Fetch the result
                        result_resp = client.get(result_url, headers=self._get_headers())
                        result_resp.raise_for_status()
                        return result_resp.json()

                    elif status in ("FAILED", "CANCELLED"):
                        error = status_data.get("error", "Unknown error")
                        raise RuntimeError(f"Video generation failed: {error}")

                    # Update progress
                    if progress_callback:
                        progress = min(0.3 + (elapsed / max_wait) * 0.5, 0.85)
                        progress_callback(f"Generating... ({elapsed}s)", progress)

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"   ⚠️ Status endpoint 404, retrying...")
                    else:
                        raise

                time.sleep(poll_interval)
                elapsed += poll_interval

        raise TimeoutError(f"Video generation timed out after {max_wait}s")

    def _extract_video_url(self, result: dict) -> Optional[str]:
        """Extract the video URL from the API result."""
        # FAL.ai typically returns video in result.video.url or result.video_url
        if "video" in result:
            video = result["video"]
            if isinstance(video, dict):
                return video.get("url")
            elif isinstance(video, str):
                return video

        if "video_url" in result:
            return result["video_url"]

        # Some models return in output
        if "output" in result:
            output = result["output"]
            if isinstance(output, dict):
                return output.get("video", {}).get("url") or output.get("video_url")

        logger.error(f"Could not find video URL in result: {list(result.keys())}")
        return None

    def _download_video(self, url: str, output_path: Path):
        """Download video from URL to local file."""
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)

    @staticmethod
    def list_models() -> dict:
        """List available video generation models."""
        return {k: v["name"] for k, v in MODELS.items()}


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Available models:", VideoGenerator.list_models())
    # To test: set FAL_API_KEY in .env and run:
    # gen = VideoGenerator()
    # gen.generate(Path("assets/my_photo.png"), output_path=Path("output/test_gen.mp4"))
