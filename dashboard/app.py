"""
dashboard/app.py — Flask web UI for the content automation pipeline.

Provides a simple web interface to:
- Enter a topic and start the pipeline
- Monitor real-time progress
- View/download generated videos
- Browse past runs
"""

import json
import logging
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import config
from orchestrator import Orchestrator, PipelineState

logger = logging.getLogger(__name__)

# Track running jobs
_running_jobs: dict[str, PipelineState] = {}
_job_lock = threading.Lock()


def create_app() -> Flask:
    """Create and configure the Flask app."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )

    orch = Orchestrator()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/generate", methods=["POST"])
    def generate():
        """Start a new pipeline run."""
        data = request.get_json()
        topic = data.get("topic", "").strip()
        model = data.get("model", None)
        voice = data.get("voice", None)

        if not topic:
            return jsonify({"error": "Topic is required"}), 400

        # Run pipeline in background thread
        def run_in_background():
            state = orch.run(
                topic=topic,
                dry_run=True,
                model=model,
                voice=voice,
                progress_callback=lambda step, status, progress: _update_job(state.id, step, status, progress),
            )
            with _job_lock:
                _running_jobs[state.id] = state

        # Create initial state to return ID immediately
        import uuid
        from datetime import datetime

        temp_id = uuid.uuid4().hex[:12]

        def run_with_tracking():
            state = orch.run(
                topic=topic,
                dry_run=True,
                model=model,
                voice=voice,
            )
            with _job_lock:
                _running_jobs[state.id] = state

        # We need to get the state ID before the thread starts
        # So we create the orchestrator run directly
        state = PipelineState(
            id=temp_id,
            topic=topic,
            status="running",
            current_step="starting",
            progress=0.0,
        )

        with _job_lock:
            _running_jobs[temp_id] = state

        def background_run():
            try:
                result = orch.run(topic=topic, dry_run=True, model=model, voice=voice)
                with _job_lock:
                    _running_jobs[temp_id] = result
                    # Also keep old ID pointing to result
                    if result.id != temp_id:
                        _running_jobs[result.id] = result
            except Exception as e:
                with _job_lock:
                    state.status = "failed"
                    state.error = str(e)
                    _running_jobs[temp_id] = state

        thread = threading.Thread(target=background_run, daemon=True)
        thread.start()

        return jsonify({"run_id": temp_id, "status": "started"})

    @app.route("/api/status/<run_id>")
    def status(run_id):
        """Get pipeline run status."""
        # Check in-memory first
        with _job_lock:
            if run_id in _running_jobs:
                state = _running_jobs[run_id]
                return jsonify({
                    "id": state.id if state.id != run_id else run_id,
                    "topic": state.topic,
                    "status": state.status,
                    "current_step": state.current_step,
                    "progress": state.progress,
                    "error": state.error,
                    "script_title": state.script_title,
                    "final_video_path": state.final_video_path,
                    "real_id": state.id,
                })

        # Check on disk
        state = orch.get_run(run_id)
        if state:
            return jsonify({
                "id": state.id,
                "topic": state.topic,
                "status": state.status,
                "current_step": state.current_step,
                "progress": state.progress,
                "error": state.error,
                "script_title": state.script_title,
                "final_video_path": state.final_video_path,
                "real_id": state.id,
            })

        return jsonify({"error": "Run not found"}), 404

    @app.route("/api/runs")
    def runs():
        """List all pipeline runs."""
        all_runs = orch.list_runs()
        return jsonify([
            {
                "id": r.id,
                "topic": r.topic,
                "status": r.status,
                "progress": r.progress,
                "created_at": r.created_at,
                "script_title": r.script_title,
            }
            for r in all_runs[:50]
        ])

    @app.route("/api/video/<run_id>")
    def video(run_id):
        """Serve a generated video."""
        # Check for final video
        video_path = config.OUTPUT_DIR / run_id / "final.mp4"
        if video_path.exists():
            return send_file(str(video_path), mimetype="video/mp4")

        # Check for generated video (pre-edit)
        gen_path = config.OUTPUT_DIR / run_id / "generated.mp4"
        if gen_path.exists():
            return send_file(str(gen_path), mimetype="video/mp4")

        return jsonify({"error": "Video not found"}), 404

    @app.route("/api/models")
    def models():
        """List available video generation models."""
        from modules.video_generator import VideoGenerator
        return jsonify(VideoGenerator.list_models())

    @app.route("/api/voices")
    def voices():
        """List available TTS voices."""
        from modules.voice_cloner import VoiceCloner
        return jsonify(VoiceCloner.list_voices())

    return app


def _update_job(run_id: str, step: str, status: str, progress: float):
    """Update in-memory job state."""
    with _job_lock:
        if run_id in _running_jobs:
            state = _running_jobs[run_id]
            state.current_step = step
            state.progress = progress
