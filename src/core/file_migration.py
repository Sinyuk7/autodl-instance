"""Data-preserving filesystem migration helpers."""
import ctypes
import errno
import os
import shutil
import uuid
from pathlib import Path


def rename_without_replace(source: Path, destination: Path) -> None:
    """Linux atomic no-clobber rename; unsupported filesystems fail closed."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise OSError(errno.ENOTSUP, "Atomic no-clobber rename is unavailable")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def move_path_safely(source: Path, destination: Path) -> None:
    """Move a path without exposing a partial cross-filesystem copy."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        rename_without_replace(source, destination)
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
        rename_without_replace(temporary, destination)
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
