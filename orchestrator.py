"""
orchestrator.py — Sequential pipeline coordinator.

Runs the content creation pipeline step-by-step:
Research → Script → Voice → Video Gen → Edit → Done

No GPU management needed — all heavy lifting done via APIs.
"""

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ── Pipeline State ─────────────────────────────────────────
@dataclass
class PipelineState:
    """Tracks the state of a content generation run."""
    id: str = ""
    topic: str = ""
    status: str = "pending"  # pending, running, review, failed
    current_step: str = ""
    progress: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    error: str = ""

    # Outputs
    research_context: str = ""
    script_title: str = ""
    script_text: str = ""
    script_caption: str = ""
    script_hashtags: list = field(default_factory=list)
    audio_path: str = ""
    generated_video_path: str = ""
    final_video_path: str = ""

    def save(self, output_dir: Path):
        """Save state to JSON for the UI."""
        self.updated_at = datetime.now().isoformat()
        state_file = output_dir / self.id / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)

    @classmethod
    def load(cls, state_file: Path) -> "PipelineState":
        """Load state from JSON file."""
        with open(state_file) as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Pipeline Steps ─────────────────────────────────────────
STEPS = [
    ("research", "🔍 Research", 0.10),
    ("script", "📝 Script", 0.20),
    ("voice", "🎙️ Voice", 0.35),
    ("video_gen", "🎬 Video Gen", 0.75),
    ("edit", "✂️ Edit", 0.95),
    ("done", "✅ Done", 1.0),
]


class Orchestrator:
    """
    Sequential pipeline orchestrator.

    Runs each step one at a time, saving state after each step
    for the web UI to monitor progress.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or config.OUTPUT_DIR

    def run(
        self,
        topic: str,
        dry_run: bool = False,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        progress_callback=None,
    ) -> PipelineState:
        """
        Run the content pipeline.

        Args:
            topic: Content topic to create a Reel about
            dry_run: If True, skip publishing
            model: Video generation model override
            voice: Edge TTS voice override
            progress_callback: Optional callback(step, status, progress) for UI

        Returns:
            PipelineState with all outputs and file paths
        """
        state = PipelineState(
            id=uuid.uuid4().hex[:12],
            topic=topic,
            status="running",
            created_at=datetime.now().isoformat(),
        )

        run_dir = self.output_dir / state.id
        run_dir.mkdir(parents=True, exist_ok=True)
        state.save(self.output_dir)

        def update(step: str, status: str, progress: float):
            state.current_step = step
            state.progress = progress
            state.save(self.output_dir)
            if progress_callback:
                progress_callback(step, status, progress)

        try:
            # ── Step 1: Research ──────────────────────────
            update("research", "Researching topic...", 0.05)
            logger.info("🔍 Step 1/5: Research")

            from modules.researcher import Researcher
            researcher = Researcher()
            research = researcher.research(topic)
            state.research_context = research.to_context()

            update("research", "Research complete", 0.10)

            # ── Step 2: Script ────────────────────────────
            update("script", "Writing script...", 0.12)
            logger.info("📝 Step 2/5: Script")

            from modules.scriptwriter import ScriptWriter
            writer = ScriptWriter()
            script = writer.generate(topic, state.research_context)

            state.script_title = script.title
            state.script_text = script.to_narration()
            state.script_caption = script.caption
            state.script_hashtags = script.hashtags

            update("script", "Script complete", 0.20)
            logger.info(f"   Title: {script.title}")

            # ── Step 3: Voice ─────────────────────────────
            update("voice", "Generating voice...", 0.22)
            logger.info("🎙️ Step 3/5: Voice")

            from modules.voice_cloner import VoiceCloner
            cloner = VoiceCloner(voice=voice)
            audio_path = run_dir / "voice.mp3"
            cloner.generate(
                text=state.script_text,
                output_path=audio_path,
            )
            state.audio_path = str(audio_path)

            update("voice", "Voice complete", 0.35)

            # ── Step 4: Video Generation ──────────────────
            update("video_gen", "Generating video (API)...", 0.38)
            logger.info("🎬 Step 4/5: Video Generation")

            from modules.video_generator import VideoGenerator

            video_prompt = (
                f"A person talking naturally and expressively to the camera about {topic}. "
                "Professional lighting, clean background, slight head movements, "
                "natural facial expressions, engaging presentation style."
            )

            generator = VideoGenerator(model=model)
            generated_video = run_dir / "generated.mp4"

            def video_progress(status, progress):
                overall = 0.38 + (progress * 0.37)  # Map 0-1 to 0.38-0.75
                update("video_gen", status, overall)

            generator.generate(
                image_path=config.AVATAR_PHOTO_PATH,
                prompt=video_prompt,
                output_path=generated_video,
                progress_callback=video_progress,
            )
            state.generated_video_path = str(generated_video)

            update("video_gen", "Video generated", 0.75)

            # ── Step 5: Edit ──────────────────────────────
            update("edit", "Editing video + captions...", 0.78)
            logger.info("✂️ Step 5/5: Edit")

            from modules.video_editor import VideoEditor
            editor = VideoEditor()
            final_video = run_dir / "final.mp4"
            editor.edit(
                video_path=generated_video,
                audio_path=audio_path,
                output_path=final_video,
            )
            state.final_video_path = str(final_video)

            update("edit", "Edit complete", 0.95)

            # ── Done ──────────────────────────────────────
            state.status = "review"
            state.progress = 1.0
            state.current_step = "done"
            state.save(self.output_dir)

            logger.info(f"\n✅ Pipeline complete!")
            logger.info(f"   ID: {state.id}")
            logger.info(f"   Title: {state.script_title}")
            logger.info(f"   Video: {state.final_video_path}")

        except Exception as e:
            logger.error(f"❌ Pipeline failed at step '{state.current_step}': {e}")
            state.status = "failed"
            state.error = str(e)
            state.save(self.output_dir)

        return state

    def list_runs(self) -> list[PipelineState]:
        """List all pipeline runs."""
        runs = []
        for state_file in self.output_dir.glob("*/state.json"):
            try:
                runs.append(PipelineState.load(state_file))
            except Exception:
                continue
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs

    def get_run(self, run_id: str) -> Optional[PipelineState]:
        """Get a specific run by ID."""
        state_file = self.output_dir / run_id / "state.json"
        if state_file.exists():
            return PipelineState.load(state_file)
        return None


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    orch = Orchestrator()
    print("Orchestrator ready.")
    print(f"Steps: {[s[0] for s in STEPS]}")
    print(f"Past runs: {len(orch.list_runs())}")
