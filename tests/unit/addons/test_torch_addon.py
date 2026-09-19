"""Unit tests for TorchAddon."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.addons.torch_engine.plugin import TorchAddon
from src.core.interface import AppContext
from src.core.ports import CommandResult


class TestSetup:
    """Tests for the setup hook."""

    def test_target_python_prefers_active_conda(self, tmp_path: Path, monkeypatch):
        conda_python = tmp_path / "miniconda3" / "bin" / "python3"
        conda_python.parent.mkdir(parents=True)
        conda_python.touch()
        monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "miniconda3"))

        assert TorchAddon()._get_target_python() == str(conda_python)

    def test_passes_addon_name_to_task_runner(self, app_context: AppContext):
        addon = TorchAddon()

        with patch("src.addons.torch_engine.plugin.TaskRunner.run_tasks", return_value=True) as run_tasks:
            with patch.object(addon, "_get_target_python", return_value=sys.executable):
                with patch.object(addon, "_is_torch_cuda_ready", return_value=True):
                    with patch.object(addon, "_get_torch_cuda_info", return_value="torch=2.6.0"):
                        addon.setup(app_context)

        run_tasks.assert_called_once()
        assert run_tasks.call_args.args[2] == addon.name

    def test_skip_when_cuda_ready(self, app_context: AppContext, mock_runner):
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="torch=2.6.0, cuda_raw='13.0'",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        with patch.object(addon, "_get_target_python", return_value=sys.executable):
            addon.setup(app_context)

        mock_runner.assert_not_called_with("uv pip install")
        assert app_context.artifacts.torch_installed is True

    def test_installs_when_cuda_not_ready(self, app_context: AppContext, mock_runner):
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="580.42.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        with patch.object(addon, "_get_target_python", return_value=sys.executable):
            addon.setup(app_context)

        install = mock_runner.assert_called_with(f"uv pip install --python {sys.executable}")
        assert "--upgrade" not in install.cmd
        assert app_context.artifacts.torch_installed is True

    def test_exits_when_driver_insufficient(self, app_context: AppContext, mock_runner):
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="470.82.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()

        with patch.object(addon, "_get_target_python", return_value=sys.executable):
            with pytest.raises(SystemExit) as excinfo:
                addon.setup(app_context)

        assert excinfo.value.code == 1

    def test_reads_manifest_config(self, app_context: AppContext, mock_runner):
        app_context.addon_manifests["torch_engine"] = {
            "min_driver_version": 600,
            "min_cuda_version": 14.0,
            "index_url": "https://custom.pytorch.org/whl",
            "packages": ["torch-custom"],
        }
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        with patch.object(addon, "_get_target_python", return_value=sys.executable):
            addon.setup(app_context)

        assert addon.min_driver == 600
        assert addon.min_cuda == 14.0
        assert addon.index_url == "https://custom.pytorch.org/whl"


class TestStart:
    """Tests for the start hook."""

    def test_start_does_nothing(self, app_context: AppContext):
        addon = TorchAddon()
        addon.start(app_context)


class TestStop:
    """Tests for the stop hook."""

    def test_stop_does_nothing(self, app_context: AppContext):
        addon = TorchAddon()
        addon.stop(app_context)
