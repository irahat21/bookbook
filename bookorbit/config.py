"""Settings read from .env (CLAUDE.md: configuration lives in .env, never in code).

A tiny KEY=VALUE parser is used instead of python-dotenv so Phase 1 needs no
extra package. Real environment variables override the file.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "DATA_DIR": str(PROJECT_ROOT / "data"),
    # mock | real  -- "real" models arrive in Phase 3 (see docs/ASSUMPTIONS.md)
    "BIOMETRIC_MODE": "mock",
    "LLM_MODE": "mock",
    "COVER_MODE": "mock",
    "OLLAMA_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3.2:3b",
    "OLLAMA_EMBED_MODEL": "nomic-embed-text",
    # BIOMETRIC_MODE=real (SRS 4.7): YOLOv8 face-detector weights (not shipped with ultralytics)
    "YOLO_FACE_WEIGHTS": str(PROJECT_ROOT / "models" / "yolov8n-face.pt"),
    # COVER_MODE=real (SRS 4.9): OpenCLIP model and its pretrained weights
    "OPENCLIP_MODEL": "ViT-B-32",
    "OPENCLIP_PRETRAINED": "laion2b_s34b_b79k",
}


def _read_env_file(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config(env_path: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_read_env_file(env_path or PROJECT_ROOT / ".env"))
    for key in DEFAULTS:
        if key in os.environ:
            cfg[key] = os.environ[key]
    return cfg
