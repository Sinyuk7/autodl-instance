"""SystemAddon 单元测试"""
from pathlib import Path
from unittest.mock import patch

import pytest

from src.addons.system.plugin import SystemAddon
from src.core.interface import AppContext


class TestSetup:
    """setup 钩子测试"""

    def test_fresh_install_success(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """全新安装：应安装 uv、生成 bin 脚本，设置 artifacts"""
        # 设置 fake home
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        with patch("shutil.which", return_value="/usr/bin/lsof"):
            addon = SystemAddon()
            addon.setup(app_context)

        # 验证 artifacts
        assert app_context.artifacts.uv_bin == uv_path / "uv"
        expected_bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        assert app_context.artifacts.bin_dir == expected_bin_dir
        assert expected_bin_dir.exists()

    def test_installs_uv_when_not_exists(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """uv 不存在时应执行安装"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        with patch("shutil.which", return_value="/usr/bin/lsof"):
            addon = SystemAddon()
            addon.setup(app_context)

        # 验证调用了安装脚本
        assert mock_runner.was_called_with_pattern("curl.*uv/install.sh")

    def test_skips_uv_install_when_exists(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """uv 已存在时应跳过安装"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        with patch("shutil.which", return_value="/usr/bin/lsof"):
            addon = SystemAddon()
            addon.setup(app_context)

        # 验证未调用安装命令
        assert not mock_runner.was_called_with_pattern("curl")


class TestStart:
    """start 钩子测试"""

    def test_start_does_nothing(self, app_context: AppContext):
        """start 为空实现"""
        addon = SystemAddon()
        addon.start(app_context)  # 不应抛出异常


class TestSync:
    """sync 钩子测试"""

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 为空实现"""
        addon = SystemAddon()
        addon.sync(app_context)  # 不应抛出异常
