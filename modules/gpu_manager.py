"""
gpu_manager.py — VRAM Tetris: GPU memory management for sequential model loading.

The RTX 3050 has 4GB VRAM. Each AI model needs 2-4GB. The solution:
never run two models simultaneously. Load → Execute → Unload → Cleanup.

Usage:
    from modules.gpu_manager import gpu_cleanup, get_device, log_vram

    # Before loading a model
    gpu_cleanup()
    device = get_device()

    # After model is done
    del model
    gpu_cleanup()
"""

import gc
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def get_device() -> str:
    """Return 'cuda' if GPU is available, else 'cpu'."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def gpu_cleanup():
    """
    Aggressive GPU memory cleanup — the heart of VRAM Tetris.

    Call this AFTER deleting model objects and BEFORE loading the next model.
    Sequence: Python GC → PyTorch cache clear → CUDA synchronize.
    """
    gc.collect()

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info(f"🧹 GPU cleanup done. VRAM free: {get_vram_free():.0f} MB")
    except ImportError:
        pass


def get_vram_free() -> float:
    """Return free VRAM in MB."""
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return free / (1024 ** 2)
    except ImportError:
        pass
    return 0.0


def get_vram_total() -> float:
    """Return total VRAM in MB."""
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return total / (1024 ** 2)
    except ImportError:
        pass
    return 0.0


def get_vram_used() -> float:
    """Return used VRAM in MB."""
    return get_vram_total() - get_vram_free()


def log_vram(label: str = ""):
    """Log current VRAM usage."""
    total = get_vram_total()
    used = get_vram_used()
    free = get_vram_free()
    prefix = f"[{label}] " if label else ""
    logger.info(f"{prefix}📊 VRAM: {used:.0f}/{total:.0f} MB used ({free:.0f} MB free)")


@contextmanager
def gpu_session(model_name: str):
    """
    Context manager for VRAM Tetris. Cleans GPU before and after.

    Usage:
        with gpu_session("Chatterbox-Turbo"):
            model = load_model()
            result = model.generate(...)
            del model
    """
    logger.info(f"🔄 Starting GPU session: {model_name}")
    gpu_cleanup()
    log_vram(f"Before {model_name}")

    try:
        yield
    finally:
        gpu_cleanup()
        log_vram(f"After {model_name}")
        logger.info(f"✅ GPU session complete: {model_name}")
