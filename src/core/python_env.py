"""Resolve the Python environment shared by ComfyUI and its addons."""
import os
import shutil
import sys
from pathlib import Path


def resolve_target_python() -> str:
    """Return the host Python used by ComfyUI and package installers."""
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        for executable in ("python3", "python"):
            candidate = Path(conda_prefix) / "bin" / executable
            if candidate.exists():
                return str(candidate)

    return shutil.which("python3") or shutil.which("python") or sys.executable
