"""TorchAddon 单元测试"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.addons.torch_engine.plugin import TorchAddon
from src.core.interface import AppContext
from src.core.ports import CommandResult


class TestSetup:
    """setup 钩子测试"""

    def test_skip_when_cuda_ready(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 已就绪时应跳过安装，设置 artifacts"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0, stdout="torch=2.6.0, cuda_raw='13.0'", stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        # 不应调用安装命令
        mock_runner.assert_not_called_with("uv pip install")
        # 验证 artifacts
        assert app_context.artifacts.torch_installed is True

    def test_installs_when_cuda_not_ready(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 未就绪时应执行安装"""
        # 模拟 CUDA 未就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1, stdout="", stderr="", command=f"{sys.executable} -c",
        )
        # 模拟驱动版本满足要求
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0, stdout="580.42.01", stderr="", command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        # 应调用安装命令
        mock_runner.assert_called_with("uv pip install")
        assert app_context.artifacts.torch_installed is True

    def test_exits_when_driver_insufficient(
        self, app_context: AppContext, mock_runner
    ):
        """驱动版本不足时应退出"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1, stdout="", stderr="", command=f"{sys.executable} -c",
        )
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0, stdout="470.82.01", stderr="", command="nvidia-smi",
        )

        addon = TorchAddon()

        with pytest.raises(SystemExit) as excinfo:
            addon.setup(app_context)

        assert excinfo.value.code == 1

    def test_reads_manifest_config(
        self, app_context: AppContext, mock_runner
    ):
        """应从 manifest 读取配置"""
        app_context.addon_manifests["torch_engine"] = {
            "min_driver_version": 600,
            "min_cuda_version": 14.0,
            "index_url": "https://custom.pytorch.org/whl",
            "packages": ["torch-custom"],
        }
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0, stdout="", stderr="", command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        assert addon.min_driver == 600
        assert addon.min_cuda == 14.0
        assert addon.index_url == "https://custom.pytorch.org/whl"


class TestStart:
    """start 钩子测试"""

    def test_start_does_nothing(self, app_context: AppContext):
        """start 为空实现"""
        addon = TorchAddon()
        addon.start(app_context)  # 不应抛出异常


class TestSync:
    """sync 钩子测试"""

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 为空实现"""
        addon = TorchAddon()
        addon.sync(app_context)  # 不应抛出异常
