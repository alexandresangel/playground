"""Production entry point; run from the service root containing config and VERSION."""

from pathlib import Path

from capture.application import create_app

app = create_app(Path.cwd())
