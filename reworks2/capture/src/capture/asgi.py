"""ASGI entry point. Launch from the project root with existing company config."""
from pathlib import Path
from capture.application import create_app

app = create_app(Path.cwd())
