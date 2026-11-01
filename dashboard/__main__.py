"""Sobe o Streamlit com a porta do .env: python -m dashboard"""
import subprocess
import sys
from pathlib import Path

from app.config import settings

script = Path(__file__).resolve().parent / "app.py"
subprocess.run(
    [sys.executable, "-m", "streamlit", "run", str(script),
     "--server.port", str(settings.dashboard_port)],
    check=False,
)
