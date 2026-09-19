"""Process ownership checks for ComfyUI lifecycle commands."""
import signal
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.utils import ensure_port_available, stop_owned_comfy_listener


def test_start_refuses_occupied_port_without_killing() -> None:
    with patch("src.core.utils.listening_pids", return_value=[42]), patch(
        "src.core.utils.os.kill"
    ) as kill, pytest.raises(RuntimeError, match="不会自动终止"):
        ensure_port_available(6006)
    kill.assert_not_called()


def test_stop_refuses_unowned_listener(tmp_path: Path) -> None:
    with patch("src.core.utils.listening_pids", return_value=[42]), patch(
        "src.core.utils._is_owned_comfy_process", return_value=False
    ), patch("src.core.utils.os.kill") as kill, pytest.raises(
        RuntimeError, match="无法确认属于目标 ComfyUI"
    ):
        stop_owned_comfy_listener(6006, tmp_path)
    kill.assert_not_called()


def test_stop_sends_sigterm_to_owned_listener(tmp_path: Path) -> None:
    with patch("src.core.utils.listening_pids", return_value=[42]), patch(
        "src.core.utils._is_owned_comfy_process", return_value=True
    ), patch("src.core.utils.os.kill") as kill:
        assert stop_owned_comfy_listener(6006, tmp_path) == [42]
    kill.assert_called_once_with(42, signal.SIGTERM)
