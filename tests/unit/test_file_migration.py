import errno
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.file_migration import move_path_safely, rename_without_replace


def test_cross_filesystem_move_publishes_complete_file(tmp_path: Path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "target" / "destination.bin"
    source.write_bytes(b"complete-data")
    real_replace = rename_without_replace
    calls = 0

    def replace_with_cross_device_first(src, dst):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EXDEV, "cross-device link")
        return real_replace(src, dst)

    with patch("src.core.file_migration.rename_without_replace", side_effect=replace_with_cross_device_first):
        move_path_safely(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"complete-data"
    assert not list(destination.parent.glob("*.autodl-tmp-*"))


def test_cross_filesystem_copy_failure_keeps_source(tmp_path: Path):
    source = tmp_path / "source.bin"
    destination = tmp_path / "target" / "destination.bin"
    source.write_bytes(b"original-data")

    with patch("src.core.file_migration.rename_without_replace", side_effect=OSError(errno.EXDEV, "cross-device link")), \
         patch("src.core.file_migration.shutil.copy2", side_effect=OSError("copy failed")):
        with pytest.raises(OSError, match="copy failed"):
            move_path_safely(source, destination)

    assert source.read_bytes() == b"original-data"
    assert not destination.exists()


def test_move_refuses_existing_destination(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.write_bytes(b"source")
    destination.write_bytes(b"target")
    with pytest.raises(FileExistsError):
        move_path_safely(source, destination)
    assert source.read_bytes() == b"source"
    assert destination.read_bytes() == b"target"


def test_cross_device_publish_race_preserves_both_files(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.write_bytes(b"source")
    calls = 0

    def competing_writer(src, dst):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EXDEV, "cross-device")
        destination.write_bytes(b"concurrent")
        rename_without_replace(src, dst)

    with patch("src.core.file_migration.rename_without_replace", side_effect=competing_writer):
        with pytest.raises(FileExistsError):
            move_path_safely(source, destination)
    assert source.read_bytes() == b"source"
    assert destination.read_bytes() == b"concurrent"
    assert not list(tmp_path.glob(".*.autodl-tmp-*"))
