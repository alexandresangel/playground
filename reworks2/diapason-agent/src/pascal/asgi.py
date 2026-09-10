"""ASGI entry point. Launch from the project root with existing company config."""
from pathlib import Path
from pascal.application import create_app

app = create_app(Path.cwd())
