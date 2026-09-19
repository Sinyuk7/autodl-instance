"""Constrain model files and sidecars to their configured storage root."""
from pathlib import Path


def safe_target(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or '..' in path.parts:
        raise ValueError('Model path must be relative and cannot contain ..')
    root = root.resolve()
    target = root / path
    if target.resolve() == root or root not in target.resolve().parents:
        raise ValueError('Model path escapes its storage directory')
    if target.is_symlink():
        raise ValueError('Refusing to overwrite a symlink')
    for sidecar in (Path(str(target) + '.aria2'), target.with_name('.' + target.name + '.meta')):
        if sidecar.is_symlink():
            raise ValueError('Refusing a symlink sidecar')
    return target
