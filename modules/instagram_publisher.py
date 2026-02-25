"""
instagram_publisher.py — Stealth Instagram publishing via Instagrapi.

Uses the private mobile API (reverse-engineered) for full Reels support.
Implements stealth protocols to avoid detection:
- Session persistence (login once, reuse session)
- Device fingerprint emulation
- Randomized delays (heuristic timing)
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class InstagramPublisher:
    """Publish Reels to Instagram with stealth protocols."""

    def __init__(self):
        self.client = None
        self.session_path = config.IG_SESSION_PATH

    def _get_client(self):
        """
        Get or create Instagrapi client with session persistence.

        First tries to load existing session. If that fails, logs in
        with credentials and saves the session for future use.
        """
        if self.client is not None:
            return self.client

        try:
            from instagrapi import Client
        except ImportError:
            raise ImportError("instagrapi not installed. Run: pip install instagrapi")

        cl = Client()

        # Set consistent device to avoid "suspicious login"
        cl.set_device({
            "app_version": "269.0.0.18.75",
            "android_version": 31,
            "android_release": "12.0",
            "dpi": "420dpi",
            "resolution": "1080x2400",
            "manufacturer": "Samsung",
            "device": "SM-G991B",
            "model": "samsung",
            "cpu": "exynos2100",
            "version_code": "314665256",
        })

        # Try to load existing session
        if self.session_path.exists():
            try:
                logger.info("📱 Loading saved Instagram session...")
                cl.load_settings(str(self.session_path))
                cl.login(config.IG_USERNAME, config.IG_PASSWORD)
                cl.get_timeline_feed()  # Verify session works
                logger.info("✅ Instagram session restored")
                self.client = cl
                return cl
            except Exception as e:
                logger.warning(f"Saved session expired, re-logging in: {e}")

        # Fresh login
        if not config.IG_USERNAME or not config.IG_PASSWORD:
            raise ValueError(
                "Instagram credentials not set. Configure in .env:\n"
                "  IG_USERNAME=your_username\n"
                "  IG_PASSWORD=your_password"
            )

        logger.info("🔑 Logging into Instagram (fresh session)...")
        cl.login(config.IG_USERNAME, config.IG_PASSWORD)

        # Save session for future use
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(str(self.session_path))
        logger.info(f"💾 Session saved: {self.session_path}")

        self.client = cl
        return cl

    def publish_reel(
        self,
        video_path: Path,
        caption: str,
        thumbnail_path: Optional[Path] = None,
        hashtags: Optional[list[str]] = None,
        delay: bool = True,
    ) -> dict:
        """
        Publish a Reel to Instagram.

        Args:
            video_path: Path to the final .mp4 video
            caption: Instagram caption text
            thumbnail_path: Optional custom thumbnail image
            hashtags: List of hashtags to append to caption
            delay: If True, add random delay before posting (stealth)

        Returns:
            dict with {media_id, code, url}
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Build full caption with hashtags
        full_caption = caption
        if hashtags:
            tag_str = " ".join(
                tag if tag.startswith("#") else f"#{tag}"
                for tag in hashtags
            )
            full_caption = f"{caption}\n\n{tag_str}"

        # Stealth: random delay before posting
        if delay:
            delay_seconds = random.uniform(30, 120)
            logger.info(f"⏳ Stealth delay: {delay_seconds:.0f}s before posting...")
            time.sleep(delay_seconds)

        logger.info(f"📱 Publishing Reel: {video_path.name}")

        cl = self._get_client()

        try:
            media = cl.clip_upload(
                path=str(video_path),
                caption=full_caption,
                thumbnail=str(thumbnail_path) if thumbnail_path else None,
            )

            result = {
                "media_id": media.id,
                "code": media.code,
                "url": f"https://www.instagram.com/reel/{media.code}/",
            }

            logger.info(f"✅ Published! {result['url']}")

            # Save updated session
            cl.dump_settings(str(self.session_path))

            return result

        except Exception as e:
            logger.error(f"❌ Publish failed: {e}")
            raise

    def is_configured(self) -> bool:
        """Check if Instagram credentials are configured."""
        return bool(config.IG_USERNAME and config.IG_PASSWORD)


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pub = InstagramPublisher()
    if pub.is_configured():
        print("Instagram is configured. Ready to publish.")
    else:
        print("Instagram not configured. Set IG_USERNAME and IG_PASSWORD in .env")
