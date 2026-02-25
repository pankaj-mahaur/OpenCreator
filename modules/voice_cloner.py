"""
voice_cloner.py — Voice synthesis with voice cloning via FAL.ai F5-TTS.

F5-TTS: Zero-shot voice cloning from a reference audio sample (API).
Edge TTS: Free fallback when no voice sample exists.
"""

import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)


class VoiceCloner:
    """Generate speech audio with voice cloning."""

    def __init__(self, voice: Optional[str] = None, use_cloning: bool = True):
        self.voice = voice or config.EDGE_TTS_VOICE
        # F5-TTS voice cloning needs FAL.ai credits — disabled by default
        # Set VOICE_CLONING=true in .env once you have FAL.ai credits
        self.use_cloning = use_cloning and bool(config.FAL_API_KEY) and os.getenv("VOICE_CLONING", "").lower() == "true"
        self.api_key = config.FAL_API_KEY
        self.base_url = "https://queue.fal.run"
        self.timeout = httpx.Timeout(30.0, read=300.0)

        mode = "F5-TTS voice cloning (FAL.ai)" if self.use_cloning else f"Edge TTS ({self.voice})"
        logger.info(f"🎙️ VoiceCloner: {mode}")

    def generate(
        self,
        text: str,
        output_path: Path,
        reference_audio: Optional[Path] = None,
        language: Optional[str] = None,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        logger.info(f"🎙️ Generating speech ({len(text)} chars) → {output_path.name}")

        ref_audio = reference_audio or config.VOICE_SAMPLES_DIR / "my_voice.wav"

        if self.use_cloning and ref_audio.exists():
            self._synthesize_f5tts(text, output_path, ref_audio)
        else:
            if self.use_cloning and not ref_audio.exists():
                logger.warning(f"   ⚠️ No voice sample at {ref_audio}, using Edge TTS")
            asyncio.run(self._synthesize_edge_tts(text, output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            size_kb = output_path.stat().st_size / 1024
            logger.info(f"   ✅ Audio: {output_path.name} ({size_kb:.1f} KB)")
            return output_path
        else:
            raise RuntimeError(f"TTS failed — output missing: {output_path}")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def _audio_to_data_url(self, path: Path) -> str:
        mime = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}.get(
            path.suffix.lower(), "audio/wav"
        )
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"

    def _synthesize_f5tts(self, text: str, output_path: Path, ref_audio: Path):
        """Voice cloning via FAL.ai F5-TTS API."""
        logger.info(f"   🎯 Cloning voice from: {ref_audio.name}")

        endpoint = f"{self.base_url}/fal-ai/f5-tts"
        payload = {
            "gen_text": text,
            "ref_audio_url": self._audio_to_data_url(ref_audio),
            "model_type": "F5-TTS",
            "remove_silence": True,
        }

        with httpx.Client(timeout=self.timeout) as client:
            # Submit
            logger.info("   📤 Submitting to F5-TTS...")
            resp = client.post(endpoint, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            request_id = data.get("request_id")
            if not request_id:
                raise RuntimeError(f"No request_id: {data}")

            logger.info(f"   ⏳ Job: {request_id}")

            # Poll
            status_url = f"{endpoint}/requests/{request_id}/status"
            result_url = f"{endpoint}/requests/{request_id}"

            for elapsed in range(0, 300, 3):
                time.sleep(3)
                sr = client.get(status_url, headers=self._headers())
                sr.raise_for_status()
                status = sr.json().get("status", "UNKNOWN")
                logger.info(f"   ⏳ {status} ({elapsed+3}s)")

                if status == "COMPLETED":
                    rr = client.get(result_url, headers=self._headers())
                    rr.raise_for_status()
                    result = rr.json()

                    audio_info = result.get("audio_url", {})
                    url = audio_info.get("url") if isinstance(audio_info, dict) else audio_info
                    if not url:
                        raise RuntimeError(f"No audio URL: {result}")

                    logger.info("   📥 Downloading audio...")
                    audio = client.get(url)
                    audio.raise_for_status()
                    output_path.write_bytes(audio.content)
                    logger.info("   ✅ Voice cloning complete")
                    return

                elif status in ("FAILED", "CANCELLED"):
                    raise RuntimeError(f"F5-TTS failed: {sr.json().get('error', status)}")

            raise TimeoutError("F5-TTS timed out after 300s")

    async def _synthesize_edge_tts(self, text: str, output_path: Path):
        """Free fallback — Microsoft Edge TTS."""
        import edge_tts
        logger.info(f"   🔊 Edge TTS ({self.voice})")
        await edge_tts.Communicate(text, self.voice).save(str(output_path))

    @staticmethod
    def list_voices() -> list[str]:
        return [
            "en-US-ChristopherNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-AriaNeural",
            "en-GB-RyanNeural",
            "en-IN-PrabhatNeural",
        ]
