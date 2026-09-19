from pathlib import Path
from unittest.mock import patch

import pytest

from src.lib.migration import MigrationManager
from src.lib.migration.transfer import record_path, rename_without_replace


@pytest.fixture
def pending(tmp_path):
    comfy = tmp_path / "ComfyUI"
    left = comfy / "models/a"
    left.mkdir(parents=True)
    (left / "model").write_bytes(b"original")
    manager = MigrationManager(comfy, tmp_path / "shared/models", tmp_path / "shared/output",
                               tmp_path / "local/user")
    return manager, left, manager.models_dir / "a"


def test_copy_failure_keeps_source_and_retry_recovers(pending):
    manager, left, right = pending
    with patch("src.lib.migration.transfer.shutil.copytree", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            manager.initialize()
    assert (left / "model").read_bytes() == b"original"
    assert not right.exists()
    manager.initialize()
    assert left.is_symlink()
    assert (right / "model").read_bytes() == b"original"


def test_interruption_after_publish_recovers_from_journal(pending):
    manager, left, right = pending

    def publish_then_interrupt(source, destination):
        rename_without_replace(source, destination)
        raise RuntimeError("interrupted")

    with patch("src.lib.migration.transfer.rename_without_replace", side_effect=publish_then_interrupt):
        with pytest.raises(RuntimeError, match="interrupted"):
            manager.initialize()
    assert not left.is_symlink() and right.is_dir()
    manager.initialize()
    assert left.is_symlink()
    assert not record_path(manager.state_dir, left).exists()


def test_interruption_during_source_cleanup_recovers(pending):
    manager, left, right = pending
    (left / "second").write_bytes(b"second")
    unlink = Path.unlink
    count = 0

    def unlink_then_interrupt(path, *args, **kwargs):
        nonlocal count
        result = unlink(path, *args, **kwargs)
        if path.parent == left:
            count += 1
            if count == 1:
                raise RuntimeError("cleanup interrupted")
        return result

    with patch.object(Path, "unlink", unlink_then_interrupt):
        with pytest.raises(RuntimeError, match="cleanup interrupted"):
            manager.initialize()
    assert len(list(left.iterdir())) == 1
    manager.initialize()
    assert left.is_symlink()
    assert (right / "model").read_bytes() == b"original"
    assert (right / "second").read_bytes() == b"second"


def test_link_failure_recovers_when_source_already_removed(pending):
    manager, left, right = pending
    with patch.object(Path, "symlink_to", side_effect=OSError("link failed")):
        with pytest.raises(OSError, match="link failed"):
            manager.initialize()
    assert not left.exists() and right.exists()
    manager.initialize()
    assert left.is_symlink()


def test_competing_destination_is_not_overwritten(pending):
    manager, left, right = pending

    def competing_writer(source, destination):
        destination.mkdir()
        (destination / "other").write_bytes(b"other")
        rename_without_replace(source, destination)

    with patch("src.lib.migration.transfer.rename_without_replace", side_effect=competing_writer):
        with pytest.raises(FileExistsError):
            manager.initialize()
    with pytest.raises(RuntimeError, match="不是本次迁移"):
        manager.initialize()
    assert (left / "model").read_bytes() == b"original"
    assert (right / "other").read_bytes() == b"other"


def test_source_change_after_publish_stops_cleanup(pending):
    manager, left, right = pending

    def publish_then_change(source, destination):
        rename_without_replace(source, destination)
        (left / "model").write_bytes(b"changed")

    with patch("src.lib.migration.transfer.rename_without_replace", side_effect=publish_then_change):
        with pytest.raises(RuntimeError, match="源数据已变化"):
            manager.initialize()
    assert (left / "model").read_bytes() == b"changed"
    assert (right / "model").read_bytes() == b"original"


def test_nested_symlink_never_followed(pending, tmp_path):
    manager, left, right = pending
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep")
    (left / "link").symlink_to(outside)
    with pytest.raises(RuntimeError, match="包含软链接"):
        manager.initialize()
    assert outside.read_bytes() == b"keep"
    assert (left / "link").is_symlink()
    assert not right.exists()
