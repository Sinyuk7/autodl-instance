from unittest.mock import patch
from pathlib import Path

import pytest

from src.core.results import PipelineResult
from src.shutdown import main


def runtime(tmp_path: Path):
    return type("Runtime", (), {
        "code_root": tmp_path / "code",
        "base_dir": tmp_path / "data",
        "workspace_dir": tmp_path / "workspace",
        "userdata_dir": tmp_path / "userdata",
        "models_dir": tmp_path / "models",
        "comfy_dir": tmp_path / "ComfyUI",
        "config_file": tmp_path / "config.yaml",
        "local_config": {},
    })()


def test_shutdown_exits_nonzero_on_sync_failure(monkeypatch, tmp_path):
    result = PipelineResult(action="sync")
    result.add_failure("userdata", "Git push 失败", "git push")

    monkeypatch.setattr("sys.argv", ["shutdown.py"])
    with patch("src.shutdown.resolve_runtime_config", return_value=runtime(tmp_path)), \
         patch("src.shutdown.setup_logger"), \
         patch("src.shutdown.setup_network"), \
         patch("src.shutdown.sync_proxy_config"), \
         patch("src.shutdown.create_context"), \
         patch("src.shutdown.execute", return_value=result), \
         patch("src.shutdown.stop_proxy") as stop_proxy:
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1
    stop_proxy.assert_called_once()


def test_shutdown_success_stops_proxy(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["shutdown.py"])
    with patch("src.shutdown.resolve_runtime_config", return_value=runtime(tmp_path)), \
         patch("src.shutdown.setup_logger"), \
         patch("src.shutdown.setup_network"), \
         patch("src.shutdown.sync_proxy_config"), \
         patch("src.shutdown.create_context"), \
         patch("src.shutdown.execute", return_value=PipelineResult(action="sync")), \
         patch("src.shutdown.stop_proxy") as stop_proxy:
        main()

    stop_proxy.assert_called_once()
