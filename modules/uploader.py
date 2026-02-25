"""
uploader.py — Upload video to Cloudflare R2 (S3-compatible) for hosting.

Cloudflare R2 free tier: 10GB storage, no egress fees.
Used to host the final video before Instagram fetches it.
"""

import logging
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class Uploader:
    """Upload files to Cloudflare R2 (S3-compatible storage)."""

    def __init__(self):
        self.client = None

    def _get_client(self):
        """Lazy-initialize the S3 client for R2."""
        if self.client is None:
            if not config.R2_ACCESS_KEY_ID:
                raise ValueError(
                    "R2 credentials not set. Configure in .env:\n"
                    "  R2_ACCESS_KEY_ID=\n"
                    "  R2_SECRET_ACCESS_KEY=\n"
                    "  R2_BUCKET_NAME=\n"
                    "  R2_ENDPOINT_URL="
                )

            import boto3
            self.client = boto3.client(
                "s3",
                endpoint_url=config.R2_ENDPOINT_URL,
                aws_access_key_id=config.R2_ACCESS_KEY_ID,
                aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
                region_name="auto",
            )
        return self.client

    def upload(self, file_path: Path, key: Optional[str] = None) -> str:
        """
        Upload a file to R2 and return the public URL.

        Args:
            file_path: Local file to upload
            key: S3 key (defaults to filename)

        Returns:
            Public URL of the uploaded file
        """
        file_path = Path(file_path)
        key = key or file_path.name

        logger.info(f"☁️ Uploading {file_path.name} to R2...")

        client = self._get_client()
        client.upload_file(
            str(file_path),
            config.R2_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": self._get_content_type(file_path)},
        )

        public_url = f"{config.R2_PUBLIC_URL}/{key}"
        logger.info(f"✅ Uploaded: {public_url}")
        return public_url

    def _get_content_type(self, path: Path) -> str:
        """Get MIME type for file."""
        suffix = path.suffix.lower()
        return {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(suffix, "application/octet-stream")


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uploader = Uploader()
    url = uploader.upload(config.OUTPUT_DIR / "test_final.mp4")
    print(f"Public URL: {url}")
