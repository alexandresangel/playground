"""Production entry point; run from the service root containing config and static/."""

from pathlib import Path

from pascal.application import create_app

app = create_app(Path.cwd())
