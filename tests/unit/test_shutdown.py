from unittest.mock import patch

import pytest

from src.core.results import PipelineResult
from src.shutdown import main


def test_shutdown_exits_nonzero_on_sync_failure(monkeypatch):
    result = PipelineResult(action="sync")
    result.add_failure("userdata", "Git push 失败", "git push")

    monkeypatch.setattr("sys.argv", ["shutdown.py"])
    with patch("src.shutdown.setup_logger"), \
         patch("src.shutdown.setup_network"), \
         patch("src.shutdown.create_context"), \
         patch("src.shutdown.execute", return_value=result), \
         patch("src.shutdown.stop_proxy") as stop_proxy:
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1
    stop_proxy.assert_called_once()


def test_shutdown_success_stops_proxy(monkeypatch):
    monkeypatch.setattr("sys.argv", ["shutdown.py"])
    with patch("src.shutdown.setup_logger"), \
         patch("src.shutdown.setup_network"), \
         patch("src.shutdown.create_context"), \
         patch("src.shutdown.execute", return_value=PipelineResult(action="sync")), \
         patch("src.shutdown.stop_proxy") as stop_proxy:
        main()

    stop_proxy.assert_called_once()
