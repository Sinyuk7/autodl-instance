from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.runtime import require_managed_storage_mount


def test_custom_storage_path_does_not_require_mount(tmp_path: Path):
    require_managed_storage_mount(tmp_path / "workspace")


def test_managed_storage_path_requires_mount():
    with patch("pathlib.Path.is_mount", return_value=False):
        with pytest.raises(RuntimeError, match="storage is not mounted"):
            require_managed_storage_mount(Path("/root/autodl-tmp/models"))
