from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.runtime import require_managed_storage_mount


def test_storage_alias_checks_resolved_mount(tmp_path):
    real = tmp_path / "mounted-storage"
    real.mkdir()
    alias = tmp_path / "autodl-fs"
    alias.symlink_to(real, target_is_directory=True)
    with patch("src.core.runtime.MANAGED_STORAGE_ROOTS", (alias,)):
        with patch.object(Path, "is_mount", lambda self: self == real):
            require_managed_storage_mount(alias / "ComfyUI/output")
        with patch.object(Path, "is_mount", lambda self: False):
            with pytest.raises(RuntimeError, match="not mounted"):
                require_managed_storage_mount(alias / "ComfyUI/output")


def test_custom_storage_path_does_not_require_mount(tmp_path: Path):
    require_managed_storage_mount(tmp_path / "workspace")


def test_managed_storage_path_requires_mount():
    with patch("pathlib.Path.is_mount", return_value=False):
        with pytest.raises(RuntimeError, match="storage is not mounted"):
            require_managed_storage_mount(Path("/root/autodl-tmp/models"))
