"""ComfyAddon 单元测试"""
from pathlib import Path
from unittest.mock import patch

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
        # 验证 artifacts
        comfy_dir = app_context.base_dir / "ComfyUI"
        assert app_context.artifacts.comfy_dir == comfy_dir
        assert app_context.artifacts.custom_nodes_dir == comfy_dir / "custom_nodes"

    def test_skip_when_already_installed(self, app_context: AppContext, mock_runner):
        """已安装时跳过：状态已标记时不重复安装"""
        app_context.state.mark_completed(StateKey.COMFY_INSTALLED)

        with patch("shutil.which", return_value="/usr/bin/comfy"):
            addon = ComfyAddon()
            addon.setup(app_context)

        # artifacts 仍应设置
        assert app_context.artifacts.comfy_dir == app_context.base_dir / "ComfyUI"
        # 不应调用安装命令
        mock_runner.assert_not_called_with("comfy --workspace")

    def test_raises_when_uv_missing(self, app_context: AppContext):
        """依赖缺失：uv 不可用时应报错"""
        app_context.artifacts.uv_bin = None

        with patch("shutil.which", return_value=None):
            addon = ComfyAddon()
            with pytest.raises(RuntimeError, match="uv 未安装"):
                addon.setup(app_context)


class TestStart:
    """start 钩子测试"""

    def test_starts_successfully(self, app_context: AppContext, mock_runner):
        """正常启动：释放端口并启动服务"""
        app_context.artifacts.comfy_dir = app_context.base_dir / "ComfyUI"

        with patch("src.addons.comfy_core.plugin.release_port") as mock_release:
            addon = ComfyAddon()
            addon.start(app_context)

        mock_release.assert_called_with(6006)
        # 验证调用了启动命令
        assert any("launch" in cmd for cmd in mock_runner.all_commands)

    def test_handles_keyboard_interrupt(self, app_context: AppContext, mock_runner):
        """中断处理：KeyboardInterrupt 不应抛出异常"""
        from unittest.mock import MagicMock
        from src.core.ports import CommandResult

        def side_effect(*args, **kwargs):
            raise KeyboardInterrupt()

        mock_runner.run = MagicMock(side_effect=side_effect)

        with patch("src.addons.comfy_core.plugin.release_port"):
            addon = ComfyAddon()
            addon.start(app_context)  # 不应抛出异常


class TestSync:
    """sync 钩子测试"""

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 为空实现"""
        addon = ComfyAddon()
        addon.sync(app_context)  # 不应抛出异常
