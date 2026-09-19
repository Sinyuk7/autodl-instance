from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.data_layout import DataLayout


@pytest.fixture
def layout(tmp_path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    return DataLayout(comfy, tmp_path / "shared/models", tmp_path / "shared/output",
                      tmp_path / "local/user")


def test_init_repeatedly_preserves_target_data(layout):
    layout.models_dir.mkdir(parents=True)
    model = layout.models_dir / "model.bin"
    model.write_bytes(b"existing")
    (layout.comfy_dir / "output").mkdir()
    layout.initialize()
    first = (layout.comfy_dir / "models").lstat()
    layout.initialize()
    assert (layout.comfy_dir / "models").lstat().st_ino == first.st_ino
    assert model.read_bytes() == b"existing"
    for source, target in layout.links:
        assert source.is_symlink() and source.resolve() == target


@pytest.mark.parametrize("kind", ["nonempty", "file", "wrong_link", "broken_link"])
def test_init_preflights_all_sources_before_writes(layout, tmp_path, kind):
    source = layout.comfy_dir / "user"
    if kind == "nonempty":
        source.mkdir()
        (source / "keep").write_bytes(b"keep")
    elif kind == "file":
        source.write_bytes(b"keep")
    else:
        other = tmp_path / "old-user"
        if kind == "wrong_link":
            other.mkdir()
        source.symlink_to(other)
    with pytest.raises(RuntimeError):
        layout.initialize()
    assert not layout.models_dir.exists()
    assert not (layout.comfy_dir / "models").exists()
    assert source.exists() or source.is_symlink()


def test_init_missing_mount_does_not_write(layout):
    with patch("src.core.data_layout.require_managed_storage_mount", side_effect=RuntimeError("unmounted")):
        with pytest.raises(RuntimeError, match="unmounted"):
            layout.initialize()
    assert not layout.models_dir.exists()


def test_init_before_install_does_not_create_checkout(layout):
    layout.comfy_dir.rmdir()
    layout.initialize()
    assert not layout.comfy_dir.exists()
    assert layout.models_dir.is_dir()


def test_migrate_preserves_conflicts_then_init_links(layout):
    source = layout.comfy_dir / "models"
    source.mkdir()
    layout.models_dir.mkdir(parents=True)
    (source / "same").write_bytes(b"same")
    (layout.models_dir / "same").write_bytes(b"same")
    (source / "model.bin").write_bytes(b"source")
    (layout.models_dir / "model.bin").write_bytes(b"target")
    conflicts = layout.models_dir.parent / ".autodl-model-conflicts"
    conflicts.mkdir()
    (conflicts / "model.bin").write_bytes(b"older-conflict")
    layout.migrate()
    layout.migrate()
    assert not source.is_symlink() and not list(source.iterdir())
    assert (layout.models_dir / "model.bin").read_bytes() == b"target"
    assert (conflicts / "model.bin").read_bytes() == b"older-conflict"
    assert (conflicts / "model.bin.1").read_bytes() == b"source"
    layout.initialize()
    assert source.is_symlink()


@pytest.mark.parametrize("target", ["same", "nested", "comfy"])
def test_reject_overlapping_paths(layout, target):
    models = {"same": layout.output_dir, "nested": layout.output_dir / "models",
              "comfy": layout.comfy_dir / "models"}[target]
    with pytest.raises(RuntimeError, match="重叠"):
        DataLayout(layout.comfy_dir, models, layout.output_dir, layout.user_dir).initialize()
