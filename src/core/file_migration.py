"""Data-preserving filesystem migration helpers."""
import errno
import os
import shutil
import uuid
from pathlib import Path


def move_path_safely(source: Path, destination: Path) -> None:
    """Move a path without exposing a partial cross-filesystem copy."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, destination)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise

    temporary = destination.parent / f".{destination.name}.autodl-tmp-{uuid.uuid4().hex}"
    try:
        if source.is_symlink():
            temporary.symlink_to(source.readlink())
        elif source.is_dir():
            shutil.copytree(source, temporary, symlinks=True)
        else:
            shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        if temporary.is_symlink() or temporary.is_file():
            temporary.unlink(missing_ok=True)
        elif temporary.exists():
            shutil.rmtree(temporary)
        raise

    if source.is_symlink() or source.is_file():
        source.unlink()
    else:
        shutil.rmtree(source)
