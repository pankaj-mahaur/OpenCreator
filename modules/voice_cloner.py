"""
voice_cloner.py — Voice synthesis with local Qwen3-TTS voice cloning.

Qwen3-TTS: Zero-shot voice cloning from a reference audio sample, runs
            fully locally on your GPU using the `qwen-tts` package.
Edge TTS:   Free fallback when voice cloning is disabled or unavailable.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class VoiceCloner:
    """Generate speech audio, optionally cloning your voice via local Qwen3-TTS."""

    def __init__(self, voice: Optional[str] = None, use_cloning: Optional[bool] = None):
        self.voice = voice or config.EDGE_TTS_VOICE
        self.use_cloning = use_cloning if use_cloning is not None else config.VOICE_CLONING

        # Lazy-loaded Qwen3 TTS model and cached clone prompt
        self._qwen_model = None
        self._voice_clone_prompt = None

        mode = "Qwen3-TTS (local voice cloning)" if self.use_cloning else f"Edge TTS ({self.voice})"
        logger.info(f"🎙️ VoiceCloner: {mode}")

    # ── Public API ────────────────────────────────────────────

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
            try:
                self._synthesize_qwen_tts(text, output_path, ref_audio, language or "English")
            except Exception as e:
                logger.warning(f"   ⚠️ Qwen3-TTS failed ({e}), falling back to Edge TTS")
                asyncio.run(self._synthesize_edge_tts(text, output_path))
        else:
            if self.use_cloning and not ref_audio.exists():
                logger.warning(f"   ⚠️ No voice sample at {ref_audio}, using Edge TTS")
                logger.warning(f"   💡 Record yourself and save to: {ref_audio}")
            asyncio.run(self._synthesize_edge_tts(text, output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            size_kb = output_path.stat().st_size / 1024
            logger.info(f"   ✅ Audio: {output_path.name} ({size_kb:.1f} KB)")
            return output_path
        else:
            raise RuntimeError(f"TTS failed — output missing: {output_path}")

    # ── Qwen3 TTS (local) ─────────────────────────────────────

    def _load_qwen_model(self):
        """Lazy-load the Qwen3-TTS model (only done once per session)."""
        if self._qwen_model is not None:
            return self._qwen_model

        logger.info(f"   📦 Loading Qwen3-TTS model: {config.QWEN_TTS_MODEL}")
        logger.info(f"   🖥️  Device: {config.QWEN_TTS_DEVICE}")
        logger.info("   ⏳ First run will download model weights (~3.5 GB)...")

        try:
            import torch
            from qwen_tts import Qwen3TTSModel

            dtype = torch.bfloat16

            # Try loading with flash_attention_2 first (faster, requires compatible GPU)
            try:
                self._qwen_model = Qwen3TTSModel.from_pretrained(
                    config.QWEN_TTS_MODEL,
                    device_map=config.QWEN_TTS_DEVICE,
                    dtype=dtype,
                    attn_implementation="flash_attention_2",
                )
            except Exception:
                # Fall back to standard attention (works on all GPUs)
                logger.info("   ℹ️  flash_attention_2 unavailable, using standard attention")
                self._qwen_model = Qwen3TTSModel.from_pretrained(
                    config.QWEN_TTS_MODEL,
                    device_map=config.QWEN_TTS_DEVICE,
                    dtype=dtype,
                )

            logger.info("   ✅ Qwen3-TTS model loaded")
            return self._qwen_model

        except ImportError as e:
            raise ImportError(
                "qwen-tts not installed. Run: pip install qwen-tts soundfile"
            ) from e

    def _get_clone_prompt(self, ref_audio: Path):
        """Build and cache the voice clone prompt from the reference audio."""
        if self._voice_clone_prompt is not None:
            return self._voice_clone_prompt

        model = self._load_qwen_model()

        ref_text = config.VOICE_CLONE_REF_TEXT or None
        x_vector_only = not bool(ref_text)

        if x_vector_only:
            logger.info("   ℹ️  No VOICE_CLONE_REF_TEXT set — using x-vector mode")
        else:
            logger.info("   📝 Using reference transcript for higher-quality cloning")

        logger.info(f"   🎯 Building voice clone prompt from: {ref_audio.name}")
        self._voice_clone_prompt = model.create_voice_clone_prompt(
            ref_audio=str(ref_audio),
            ref_text=ref_text,
            x_vector_only_mode=x_vector_only,
        )

        logger.info("   ✅ Voice clone prompt cached for this session")
        return self._voice_clone_prompt

    def _synthesize_qwen_tts(self, text: str, output_path: Path, ref_audio: Path, language: str):
        """Local voice cloning via Qwen3-TTS with progress display."""
        import soundfile as sf
        import threading

        model = self._load_qwen_model()
        clone_prompt = self._get_clone_prompt(ref_audio)

        # Estimate time: ~0.5s per char on RTX 3050 with 1.7B model
        est_seconds = max(30, int(len(text) * 0.5))
        logger.info(f"   🎬 Synthesizing with cloned voice ({language})...")
        logger.info(f"   ⏱️  Estimated time: ~{est_seconds // 60}m {est_seconds % 60}s for {len(text)} chars")

        # Run TTS in a thread so we can show progress
        result = {"wavs": None, "sr": None, "error": None}

        def tts_worker():
            try:
                wavs, sr = model.generate_voice_clone(
                    text=text,
                    language=language,
                    voice_clone_prompt=clone_prompt,
                )
                result["wavs"] = wavs
                result["sr"] = sr
            except Exception as e:
                result["error"] = e

        thread = threading.Thread(target=tts_worker)
        thread.start()

        # Show progress while waiting
        try:
            from rich.live import Live
            from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

            progress = Progress(
                SpinnerColumn("dots"),
                TextColumn("[cyan]Voice Cloning[/cyan]"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                TextColumn(f"[dim]ETA ~{est_seconds // 60}m {est_seconds % 60}s[/dim]"),
            )

            task = progress.add_task("tts", total=est_seconds)

            with Live(progress, refresh_per_second=2):
                elapsed = 0
                while thread.is_alive():
                    thread.join(timeout=1.0)
                    elapsed += 1
                    # Cap at 95% until actually done
                    pct = min(elapsed, int(est_seconds * 0.95))
                    progress.update(task, completed=pct)

                # Mark complete
                progress.update(task, completed=est_seconds)

        except ImportError:
            # Fallback: simple waiting log
            elapsed = 0
            while thread.is_alive():
                thread.join(timeout=10.0)
                elapsed += 10
                pct = min(95, int((elapsed / est_seconds) * 100))
                logger.info(f"   ⏳ Voice cloning... {pct}% ({elapsed}s / ~{est_seconds}s)")

        if result["error"]:
            raise result["error"]

        sf.write(str(output_path), result["wavs"][0], result["sr"])
        logger.info("   ✅ Qwen3-TTS voice cloning complete")

    # ── Edge TTS fallback ─────────────────────────────────────

    async def _synthesize_edge_tts(self, text: str, output_path: Path):
        """Free fallback — Microsoft Edge TTS (no GPU needed)."""
        import edge_tts

        logger.info(f"   🔊 Edge TTS ({self.voice})")
        await edge_tts.Communicate(text, self.voice).save(str(output_path))

    # ── Helpers ───────────────────────────────────────────────

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
