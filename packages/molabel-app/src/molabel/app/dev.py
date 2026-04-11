"""Development server launcher — starts FastAPI + frontend dev server together."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


def _find_project_root() -> Path:
    """Walk up from CWD to find the uv workspace root.

    Looks for a ``pyproject.toml`` that contains a ``[tool.uv.workspace]``
    section, which marks the monorepo root.
    """
    candidate = Path.cwd().resolve()
    for directory in [candidate, *candidate.parents]:
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text():
            return directory
    # Fallback: assume CWD is the root.
    return candidate


def main() -> None:
    """Start both FastAPI and Vite dev servers.

    The FastAPI server runs on port 8000 with auto-reload.
    The Vite frontend dev server runs on port 5173.
    Ctrl-C (SIGINT) or SIGTERM cleanly shuts down both processes.
    """
    project_root = _find_project_root()
    frontend_dir = project_root / "frontend"

    env = {**os.environ}

    # SE-012: respect MOLABEL_HOST / MOLABEL_PORT for network binding.
    host = env.get("MOLABEL_HOST", "127.0.0.1")
    port = env.get("MOLABEL_PORT", "8000")

    print(f"[molabel-dev] Project root: {project_root}")
    print(f"[molabel-dev] Starting FastAPI on {host}:{port} …")
    print("[molabel-dev] Starting Vite   on :5173 …")

    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "molabel.app.main:app",
            "--reload",
            "--host",
            host,
            "--port",
            port,
        ],
        cwd=str(project_root),
        env=env,
    )

    vite_proc = subprocess.Popen(
        ["npx", "vite", "--port", "5173"],
        cwd=str(frontend_dir),
        env=env,
    )

    def shutdown(sig: int, _frame: object) -> None:
        print(f"\n[molabel-dev] Received signal {sig}, shutting down …")
        api_proc.terminate()
        vite_proc.terminate()
        api_proc.wait(timeout=5)
        vite_proc.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for either process to exit, then tear down the other.
    try:
        api_proc.wait()
    finally:
        vite_proc.terminate()
        vite_proc.wait(timeout=5)
