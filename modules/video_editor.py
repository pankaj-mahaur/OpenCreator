"""
video_editor.py — FFmpeg-based video editing with captions.

Pipeline:
1. faster-whisper → word-level timestamps
2. Generate ASS subtitle file with karaoke-style captions
3. FFmpeg: composite avatar video + audio + captions → final 9:16 Reel
"""

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


def _check_ffmpeg():
    """Verify FFmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            logger.info(f"   🔧 {version_line}")
            return True
    except FileNotFoundError:
        pass
    raise RuntimeError(
        "FFmpeg not found. Install from https://ffmpeg.org or run: winget install ffmpeg"
    )


class VideoEditor:
    """Auto-edit pipeline: video + audio + captions → final Instagram Reel."""

    def __init__(self):
        _check_ffmpeg()

    def edit(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        caption_style: str = "karaoke",
    ) -> Path:
        """
        Full auto-edit pipeline.

        Args:
            video_path: The generated avatar/talking head video
            audio_path: Voice audio file
            output_path: Final output .mp4
            caption_style: "karaoke" (word-highlight) or "simple" (sentence blocks)

        Returns:
            Path to the final edited video
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"🎬 Starting video edit pipeline...")
        logger.info(f"   Video: {video_path}")
        logger.info(f"   Audio: {audio_path}")

        # Step 1: Transcribe audio for captions
        word_timestamps = self._transcribe(audio_path)
        logger.info(f"   📝 Transcribed {len(word_timestamps)} words")

        # Step 2: Generate ASS subtitle file
        ass_path = output_path.parent / f"{output_path.stem}_captions.ass"
        if caption_style == "karaoke":
            self._build_karaoke_ass(word_timestamps, ass_path)
        else:
            self._build_simple_ass(word_timestamps, ass_path)

        # Step 3: Get audio duration
        audio_duration = self._get_duration(audio_path)
        video_duration = self._get_duration(video_path)

        # Step 4: FFmpeg composite
        self._composite_ffmpeg(
            video_path=video_path,
            audio_path=audio_path,
            subtitle_path=ass_path,
            output_path=output_path,
            audio_duration=audio_duration,
            video_duration=video_duration,
        )

        if output_path.exists() and output_path.stat().st_size > 0:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"   ✅ Final video: {output_path.name} ({size_mb:.1f} MB)")
            return output_path
        else:
            raise RuntimeError(f"FFmpeg output missing: {output_path}")

    def _transcribe(self, audio_path: Path) -> list[dict]:
        """
        Transcribe audio with word-level timestamps using faster-whisper.

        Returns list of: [{"word": "Hello", "start": 0.5, "end": 0.8}, ...]
        """
        try:
            from faster_whisper import WhisperModel

            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language="en",
            )

            words = []
            for segment in segments:
                if segment.words:
                    for w in segment.words:
                        words.append({
                            "word": w.word.strip(),
                            "start": round(w.start, 3),
                            "end": round(w.end, 3),
                        })

            return words

        except ImportError:
            logger.warning("faster-whisper not installed, generating captions without word timestamps")
            return []
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return []

    def _get_duration(self, file_path: Path) -> float:
        """Get duration of audio/video file using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(file_path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception as e:
            logger.warning(f"Could not get duration of {file_path}: {e}")
            return 60.0  # fallback

    def _build_karaoke_ass(self, words: list[dict], output_path: Path):
        """
        Build karaoke-style ASS subtitle file.
        Groups words into lines of ~5 words, highlights current word.
        """
        if not words:
            self._build_empty_ass(output_path)
            return

        header = self._ass_header()
        events = []

        # Group words into lines of ~5
        group_size = 5
        for i in range(0, len(words), group_size):
            group = words[i:i + group_size]
            start_time = group[0]["start"]
            end_time = group[-1]["end"]

            # For each word in the group, create a highlight event
            for j, word in enumerate(group):
                # Build the line with current word highlighted
                parts = []
                for k, w in enumerate(group):
                    if k == j:
                        # Highlighted word — yellow, bold
                        parts.append(r"{\c&H00FFFF&\b1}" + w["word"] + r"{\c&HFFFFFF&\b0}")
                    else:
                        parts.append(w["word"])

                line_text = " ".join(parts)
                w_start = self._seconds_to_ass_time(word["start"])
                w_end = self._seconds_to_ass_time(word["end"])

                events.append(f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{line_text}")

        content = header + "\n".join(events) + "\n"
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"   📝 Karaoke captions: {len(events)} events → {output_path.name}")

    def _build_simple_ass(self, words: list[dict], output_path: Path):
        """Build simple sentence-block ASS captions."""
        if not words:
            self._build_empty_ass(output_path)
            return

        header = self._ass_header()
        events = []

        # Group into ~8 word chunks
        group_size = 8
        for i in range(0, len(words), group_size):
            group = words[i:i + group_size]
            text = " ".join(w["word"] for w in group)
            start = self._seconds_to_ass_time(group[0]["start"])
            end = self._seconds_to_ass_time(group[-1]["end"])
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        content = header + "\n".join(events) + "\n"
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"   📝 Simple captions: {len(events)} blocks → {output_path.name}")

    def _build_empty_ass(self, output_path: Path):
        """Create empty ASS file (no captions)."""
        content = self._ass_header()
        output_path.write_text(content, encoding="utf-8")

    def _ass_header(self) -> str:
        """Generate ASS subtitle file header."""
        return f"""[Script Info]
Title: Auto Captions
ScriptType: v4.00+
PlayResX: {config.VIDEO_WIDTH}
PlayResY: {config.VIDEO_HEIGHT}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,56,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.CC)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def _composite_ffmpeg(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
        audio_duration: float,
        video_duration: float,
    ):
        """
        Composite final video with FFmpeg.

        - Loops/trims video to match audio duration
        - Scales to 9:16 (1080x1920) with blurred padding
        - Burns in ASS captions
        - Muxes with audio
        """
        logger.info(f"   🔧 FFmpeg compositing...")
        logger.info(f"      Video: {video_duration:.1f}s, Audio: {audio_duration:.1f}s")

        # Build filter complex
        # 1. Loop video if shorter than audio
        # 2. Scale to fit 9:16 with blurred background padding
        # 3. Burn in subtitles
        
        sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", r"\:")

        filter_parts = []

        # If video is shorter than audio, loop it
        if video_duration < audio_duration:
            loop_count = int(audio_duration / video_duration) + 1
            stream_loop = f"-stream_loop {loop_count}"
        else:
            stream_loop = ""

        cmd = [
            "ffmpeg", "-y",
        ]

        # Add stream loop if needed
        if stream_loop:
            cmd.extend(stream_loop.split())

        cmd.extend([
            "-i", str(video_path),
            "-i", str(audio_path),
            "-filter_complex",
            (
                # Scale video to fill width, pad to 9:16
                f"[0:v]scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
                f"ass='{sub_path_escaped}'[outv]"
            ),
            "-map", "[outv]",
            "-map", "1:a",
            "-t", str(audio_duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-r", str(config.VIDEO_FPS),
            str(output_path),
        ])

        logger.info(f"      Running FFmpeg...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[-500:]}")
            raise RuntimeError(f"FFmpeg failed with return code {result.returncode}")

        logger.info(f"      ✅ FFmpeg composite done")


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    editor = VideoEditor()
    print("VideoEditor initialized OK. FFmpeg found.")
