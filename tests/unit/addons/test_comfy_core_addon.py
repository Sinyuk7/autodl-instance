"""ComfyAddon 单元测试"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.addons.comfy_core.plugin import ComfyAddon
from src.core.interface import AppContext
from src.core.schema import StateKey


class TestSetup:
    """setup 钩子测试"""

    def test_fresh_install_success(self, app_context: AppContext, mock_runner, tmp_path: Path):
        """全新安装：应安装 comfy-cli 和 ComfyUI，设置状态和 artifacts"""
        uv_bin = tmp_path / "uv"
        uv_bin.touch()
        app_context.artifacts.uv_bin = uv_bin

        with patch("shutil.which", return_value=None):
            addon = ComfyAddon()
            addon.setup(app_context)

        # 验证状态
        assert app_context.state.is_completed(StateKey.COMFY_INSTALLED)
        # 验证 artifacts - comfy_dir 现在来自 context.comfy_dir（系统盘）
        comfy_dir = app_context.comfy_dir
        assert app_context.artifacts.comfy_dir == comfy_dir
        assert app_context.artifacts.output_dir == app_context.workspace_data_dir / "output"
        cli_install = mock_runner.assert_called_with("comfy-cli==1.20.0")
        assert "--index-url https://pypi.org/simple" in cli_install.cmd
        install = mock_runner.assert_called_with("comfy --workspace")
        assert "--skip-prompt install" in install.cmd
        assert "--version 0.36.0" in install.cmd
        assert "--nvidia --cuda-version 13.0" in install.cmd
        assert "--skip-torch-or-directml" in install.cmd
        assert install.kwargs["capture_output"] is False

    def test_skip_when_already_installed(self, app_context: AppContext, mock_runner):
        """已安装时跳过：状态已标记时不重复安装"""
        uv_bin = app_context.base_dir / "uv"
        uv_bin.touch()
        app_context.artifacts.uv_bin = uv_bin
        (app_context.comfy_dir / "main.py").touch()
        app_context.state.mark_completed(StateKey.COMFY_INSTALLED)

        with patch("shutil.which", return_value="/usr/bin/comfy"):
            addon = ComfyAddon()
            addon.setup(app_context)

        # artifacts 仍应设置 - comfy_dir 来自 context.comfy_dir
        assert app_context.artifacts.comfy_dir == app_context.comfy_dir
        # 不应调用安装命令
        mock_runner.assert_not_called_with("comfy --workspace")

    def test_raises_when_uv_missing(self, app_context: AppContext):
        """依赖缺失：uv 不可用时应报错"""
        app_context.artifacts.uv_bin = None

        with patch("shutil.which", return_value=None):
            addon = ComfyAddon()
            with pytest.raises(RuntimeError, match="uv 未安装"):
                addon.setup(app_context)

    def test_partial_install_restores_dependencies(self, app_context: AppContext, mock_runner, tmp_path: Path):
        uv_bin = tmp_path / "uv"
        uv_bin.touch()
        app_context.artifacts.uv_bin = uv_bin
        app_context.comfy_dir.mkdir(parents=True, exist_ok=True)
        (app_context.comfy_dir / "main.py").touch()

        ComfyAddon().setup(app_context)

        install = mock_runner.assert_called_with("comfy --workspace")
        assert "--restore" in install.cmd
        assert app_context.state.is_completed(StateKey.COMFY_INSTALLED)


class TestStart:
    """start 钩子测试"""

    def test_starts_successfully(self, app_context: AppContext, mock_runner):
        """正常启动：释放端口并启动服务"""
        app_context.artifacts.comfy_dir = app_context.base_dir / "ComfyUI"

        with patch("src.addons.comfy_core.plugin.ensure_port_available") as mock_check:
            addon = ComfyAddon()
            addon.start(app_context)

        mock_check.assert_called_with(6006)
        # 验证调用了启动命令
        assert any("launch" in cmd for cmd in mock_runner.all_commands)

    def test_handles_keyboard_interrupt(self, app_context: AppContext, mock_runner):
        """中断处理：KeyboardInterrupt 不应抛出异常"""
        def side_effect(*args, **kwargs):
            raise KeyboardInterrupt()

        mock_runner.run = MagicMock(side_effect=side_effect)

        with patch("src.addons.comfy_core.plugin.ensure_port_available"):
            addon = ComfyAddon()
            addon.start(app_context)  # 不应抛出异常


class TestStop:
    """stop 钩子测试"""

    def test_stop_only_stops_owned_listener(self, app_context: AppContext):
        addon = ComfyAddon()
        with patch(
            "src.addons.comfy_core.plugin.stop_owned_comfy_listener",
            return_value=[123],
        ) as mock_stop:
            result = addon.stop(app_context)

        mock_stop.assert_called_once_with(6006, app_context.comfy_dir)
        assert result.status == "success"
