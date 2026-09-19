"""Resumable directory transfer for boot initialization (writers must be stopped)."""
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from src.core.file_migration import rename_without_replace


def snapshot(root: Path) -> dict:
    """Hash regular files; never follow symlinks or special files."""
    result = {}
    for item in sorted(root.iterdir()):
        if item.is_symlink():
            raise RuntimeError(f"迁移目录包含软链接，需手动处理: {item}")
        if item.is_dir():
            result[item.name] = ["directory"]
            for name, value in snapshot(item).items():
                result[f"{item.name}/{name}"] = value
        elif item.is_file():
            digest = hashlib.sha256()
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
            result[item.name] = ["file", item.stat().st_size, digest.hexdigest()]
        else:
            raise RuntimeError(f"迁移目录包含特殊文件，需手动处理: {item}")
    return result


def save_record(path: Path, record: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(record, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def record_path(state_dir: Path, source: Path) -> Path:
    return state_dir / (hashlib.sha256(os.fsencode(source.absolute())).hexdigest() + ".json")


def transfer_directory(source: Path, target: Path, state_dir: Path) -> None:
    """Copy, verify, publish without replacement, then prune verified source data.

    A journal binds recovery to the inode of our own published directory. Partial
    source cleanup can resume; unrelated pre-existing destinations never qualify.
    """
    journal = record_path(state_dir, source)
    if journal.exists():
        record = json.loads(journal.read_text())
        if record["source"] != str(source) or record["target"] != str(target):
            raise RuntimeError(f"未完成迁移的路径配置已变更: {journal}")
    else:
        if source.is_symlink() or not source.is_dir():
            raise RuntimeError(f"迁移源不是实体目录: {source}")
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
                raise RuntimeError(f"迁移目标不为空: {target}")
            target.rmdir()  # Atomic refusal if another writer populated it.
        record = {"source": str(source), "target": str(target),
                  "temporary": str(target.parent / f".autodl-transfer-{uuid.uuid4().hex}"),
                  "manifest": snapshot(source), "identity": None}
        save_record(journal, record)
    temporary = Path(record["temporary"])
    if temporary.parent != target.parent or not temporary.name.startswith(".autodl-transfer-"):
        raise RuntimeError(f"无效迁移记录: {journal}")
    if record["identity"] is None:
        # Only this journal's incomplete copy can be discarded and rebuilt.
        if temporary.is_symlink():
            raise RuntimeError(f"临时目录被替换为链接: {temporary}")
        if temporary.exists():
            shutil.rmtree(temporary)
        if source.is_symlink() or snapshot(source) != record["manifest"]:
            raise RuntimeError(f"源数据已变化，保留数据并停止迁移: {source}")
        shutil.copytree(source, temporary, symlinks=True)
        if snapshot(temporary) != record["manifest"] or snapshot(source) != record["manifest"]:
            raise RuntimeError(f"复制校验失败，保留源数据: {source}")
        stat = temporary.stat()
        record["identity"] = [stat.st_dev, stat.st_ino]
        save_record(journal, record)
    if not target.exists() and not target.is_symlink():
        rename_without_replace(temporary, target)
    stat = target.lstat()
    if target.is_symlink() or [stat.st_dev, stat.st_ino] != record["identity"]:
        raise RuntimeError(f"目标不是本次迁移创建的目录，拒绝覆盖: {target}")
    if snapshot(target) != record["manifest"]:
        raise RuntimeError(f"迁移目标已变化，保留源数据: {target}")
    if source.is_symlink():
        if source.resolve() != target.resolve():
            raise RuntimeError(f"源链接指向已变更: {source}")
    elif source.exists():
        remaining = snapshot(source)
        if any(record["manifest"].get(name) != value for name, value in remaining.items()):
            raise RuntimeError(f"源数据已变化，保留数据并停止迁移: {source}")
        # Delete only verified entries; interrupted cleanup resumes from a subset.
        for name in sorted(remaining, key=lambda name: (name.count("/"), name), reverse=True):
            item = source / name
            if remaining[name][0] == "directory":
                item.rmdir()
            else:
                item.unlink()
        source.rmdir()
    if not source.is_symlink():
        source.symlink_to(target)
    journal.unlink()
