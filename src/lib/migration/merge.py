"""Explicit directory merging; target files win and source conflicts are retained."""
import filecmp
from pathlib import Path
from src.core.file_migration import move_path_safely
from src.core.utils import logger


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()

def _unique_path(path: Path) -> Path:
    if not _path_exists(path):
        return path
    index = 1
    while _path_exists(path.with_name(f"{path.name}.{index}")):
        index += 1
    return path.with_name(f"{path.name}.{index}")

def _preserve_conflict(source: Path, conflict_path: Path) -> None:
    conflict_path.parent.mkdir(parents=True, exist_ok=True)
    destination = _unique_path(conflict_path)
    move_path_safely(source, destination)
    logger.warning("  -> [WARN] 冲突文件已保留: %s", destination)

def merge_directory(source: Path, target: Path, conflicts: Path) -> None:
    """Merge without overwriting the persistent target."""
    target.mkdir(parents=True, exist_ok=True)
    for item in list(source.iterdir()):
        destination = target / item.name
        conflict = conflicts / item.name
        destination_exists = _path_exists(destination)

        if item.is_symlink():
            if (
                destination.is_symlink()
                and item.resolve() == destination.resolve()
            ):
                item.unlink()
            elif destination_exists:
                _preserve_conflict(item, conflict)
            else:
                move_path_safely(item, destination)
            continue

        if item.is_dir():
            if destination_exists and (destination.is_symlink() or not destination.is_dir()):
                _preserve_conflict(item, conflict)
                continue
            merge_directory(item, destination, conflict)
            item.rmdir()
            continue

        if destination_exists:
            if (
                item.is_file()
                and destination.is_file()
                and filecmp.cmp(item, destination, shallow=False)
            ):
                item.unlink()
            else:
                _preserve_conflict(item, conflict)
        else:
            move_path_safely(item, destination)
