from unittest.mock import patch

import pytest

from src.lib.migration import MigrationManager


@pytest.fixture
def layout(tmp_path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    return MigrationManager(comfy, tmp_path / "shared/models", tmp_path / "shared/output",
                            tmp_path / "local/user")


@pytest.mark.parametrize("root", ["models", "output"])
@pytest.mark.parametrize("left_state,right_state", [
    ("empty", "full"), ("missing", "full"), ("full", "missing"),
    ("full", "empty"), ("empty", "empty"), ("empty", "missing")])
def test_safe_directory_cases_and_repeat(layout, root, left_state, right_state):
    left = layout.comfy_dir / root / "a"
    right = getattr(layout, root + "_dir") / "a"
    for path, state in [(left, left_state), (right, right_state)]:
        if state != "missing":
            path.mkdir(parents=True)
        if state == "full":
            (path / "data").write_bytes(b"data")
    layout.initialize()
    assert left.is_symlink() and left.resolve() == right
    if "full" in (left_state, right_state):
        assert (right / "data").read_bytes() == b"data"
    inode = left.lstat().st_ino
    layout.initialize()
    assert left.lstat().st_ino == inode
    assert not (layout.comfy_dir / root).is_symlink()


@pytest.mark.parametrize("explicit", [False, True])
def test_root_files_untouched_in_both_modes(layout, explicit):
    for source, target in layout.links[:2]:
        source.mkdir(parents=True)
        target.mkdir(parents=True)
        (source / "root.bin").write_bytes(b"local-root")
        (target / "root.bin").write_bytes(b"shared-root")
        (source / "a").mkdir()
        (target / "a").mkdir()
        (target / "a/data").write_bytes(b"shared")
    paths = [p / "root.bin" for pair in layout.links[:2] for p in pair]
    before = [(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in paths]
    layout.run(merge_conflicts=explicit)
    assert before == [(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in paths]


def test_both_nonempty_skip_then_explicit_merge(layout, caplog):
    left = layout.comfy_dir / "models/a"
    right = layout.models_dir / "a"
    left.mkdir(parents=True)
    right.mkdir(parents=True)
    (left / "model").write_bytes(b"source")
    (right / "model").write_bytes(b"target")
    layout.initialize()
    assert not left.is_symlink()
    assert (left / "model").read_bytes() == b"source"
    assert "双方目录都有内容" in caplog.text
    layout.migrate()
    assert left.is_symlink()
    assert (right / "model").read_bytes() == b"target"
    conflict = right.parent.parent / ".autodl-model-conflicts/a/model"
    assert conflict.read_bytes() == b"source"
    layout.migrate()
    assert conflict.read_bytes() == b"source"


def test_new_subdirectory_is_picked_up_next_boot(layout):
    layout.initialize()
    left = layout.comfy_dir / "models/c"
    left.mkdir()
    (left / "new.bin").write_bytes(b"new")
    layout.initialize()
    assert left.is_symlink()
    assert (layout.models_dir / "c/new.bin").read_bytes() == b"new"


def test_hidden_file_is_not_empty(layout):
    left, right = layout.comfy_dir / "models/a", layout.models_dir / "a"
    left.mkdir(parents=True)
    right.mkdir(parents=True)
    (left / ".keep").touch()
    (right / "model").touch()
    layout.initialize()
    assert not left.is_symlink()
    assert (left / ".keep").exists()


@pytest.mark.parametrize("kind", ["wrong_link", "broken_link", "target_link", "target_file", "source_file"])
def test_child_conflicts_preserved_and_other_children_continue(layout, tmp_path, kind):
    left, right = layout.comfy_dir / "models/a", layout.models_dir / "a"
    left.parent.mkdir(parents=True)
    right.parent.mkdir(parents=True)
    other = tmp_path / "other"
    if kind == "target_link":
        left.mkdir()
        other.mkdir()
        right.symlink_to(other)
    elif kind == "target_file":
        left.mkdir()
        right.write_bytes(b"keep")
    elif kind == "source_file":
        left.write_bytes(b"keep")
        right.mkdir()
    else:
        if kind == "wrong_link":
            other.mkdir()
        left.symlink_to(other)
    (left.parent / "b").mkdir()
    layout.initialize()
    assert (left.parent / "b").is_symlink()
    if kind == "target_file":
        assert right.read_bytes() == b"keep"
    elif kind == "source_file":
        assert left.read_bytes() == b"keep"
    elif kind == "target_link":
        assert right.is_symlink() and not left.is_symlink()
    else:
        assert left.readlink() == other


def test_nonempty_user_does_not_block_models(layout):
    user = layout.comfy_dir / "user"
    user.mkdir()
    (user / "db").write_bytes(b"keep")
    (layout.models_dir / "a").mkdir(parents=True)
    layout.initialize()
    assert (layout.comfy_dir / "models/a").is_symlink()
    assert (user / "db").read_bytes() == b"keep" and not user.is_symlink()


def test_missing_mount_does_not_write(layout):
    with patch("src.lib.migration.manager.require_managed_storage_mount", side_effect=RuntimeError("unmounted")):
        with pytest.raises(RuntimeError, match="unmounted"):
            layout.initialize()
    assert not layout.models_dir.exists()


def test_before_install_does_not_create_checkout(layout):
    layout.comfy_dir.rmdir()
    layout.initialize()
    assert not layout.comfy_dir.exists()
    assert layout.models_dir.is_dir()


@pytest.mark.parametrize("target", ["same", "nested", "comfy"])
def test_reject_overlapping_paths(layout, target):
    models = {"same": layout.output_dir, "nested": layout.output_dir / "models",
              "comfy": layout.comfy_dir / "models"}[target]
    with pytest.raises(RuntimeError, match="重叠"):
        MigrationManager(layout.comfy_dir, models, layout.output_dir, layout.user_dir).initialize()


def test_concurrent_initialization_refused(layout):
    with layout._locked():
        with pytest.raises(RuntimeError, match="另一个"):
            layout.initialize()


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("root", ["models", "output"])
def test_hidden_direct_children_are_never_managed(layout, explicit, root):
    source = layout.comfy_dir / root
    target = getattr(layout, root + "_dir")
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    paths = []
    for parent, names in [(source, [".ipynb_checkpoints", ".local-only"]),
                          (target, [".ipynb_checkpoints", ".shared-only"])]:
        for name in names:
            child = parent / name
            child.mkdir()
            (child / "keep").write_text(str(parent))
            paths.extend([child, child / "keep"])
        (parent / ".hidden-file").write_bytes(b"keep")
        (parent / ".hidden-link").symlink_to(parent / "absent")
        paths.extend([parent / ".hidden-file", parent / ".hidden-link"])
    before = [(p.lstat().st_ino, p.lstat().st_mtime_ns) for p in paths]
    (source / "visible").mkdir()
    layout.run(merge_conflicts=explicit)
    layout.run(merge_conflicts=explicit)
    assert (source / "visible").is_symlink()
    assert not (source / ".shared-only").exists()
    assert not (target / ".local-only").exists()
    assert before == [(p.lstat().st_ino, p.lstat().st_mtime_ns) for p in paths]
    assert (source / ".ipynb_checkpoints/keep").read_text() == str(source)
    assert (target / ".ipynb_checkpoints/keep").read_text() == str(target)


@pytest.mark.parametrize("explicit", [False, True])
def test_hidden_contents_of_visible_directory_are_preserved(layout, explicit):
    source = layout.comfy_dir / "models/checkpoints"
    (source / ".ipynb_checkpoints").mkdir(parents=True)
    (source / ".ipynb_checkpoints/keep").write_bytes(b"hidden-data")
    (source / ".meta").write_bytes(b"metadata")
    layout.run(merge_conflicts=explicit)
    assert source.is_symlink()
    target = layout.models_dir / "checkpoints"
    assert (target / ".ipynb_checkpoints/keep").read_bytes() == b"hidden-data"
    assert (target / ".meta").read_bytes() == b"metadata"
