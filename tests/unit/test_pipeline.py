"""
Pipeline 执行流程测试

验证:
- create_pipeline 返回正确的插件顺序
- execute 函数的 --until 和 --only 参数
- sync 逆序执行
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.main import create_pipeline, execute
from src.core.interface import AppContext


class TestCreatePipeline:
    """create_pipeline 测试"""

    def test_returns_correct_order(self):
        """应返回 7 个插件，顺序正确"""
        pipeline = create_pipeline()

        assert len(pipeline) == 7

        names = [p.name for p in pipeline]
        assert names == [
            "system",
            "git_config",
            "torch_engine",
            "comfy_core",
            "userdata",
            "nodes",
            "models",
        ]

    def test_all_have_name_property(self):
        """每个插件都应有 name 属性"""
        pipeline = create_pipeline()
        for addon in pipeline:
            assert hasattr(addon, "name")
            assert isinstance(addon.name, str)
            assert len(addon.name) > 0


class TestExecute:
    """execute 函数测试"""

    def test_setup_calls_all_plugins(self, app_context):
        """setup 应按顺序调用所有插件"""
        ctx = app_context
        called = []

        # Patch 所有插件的 setup 方法
        with patch("src.main.create_pipeline") as mock_pipeline:
            mock_addons = []
            for name in ["system", "git_config", "torch_engine", "comfy_core", "userdata", "nodes", "models"]:
                addon = MagicMock()
                addon.name = name
                addon.setup = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
                mock_addons.append(addon)
            mock_pipeline.return_value = mock_addons

            execute("setup", ctx)

        assert called == ["system", "git_config", "torch_engine", "comfy_core", "userdata", "nodes", "models"]

    def test_sync_reverses_order(self, app_context):
        """sync 应逆序执行"""
        ctx = app_context
        called = []

        with patch("src.main.create_pipeline") as mock_pipeline:
            mock_addons = []
            for name in ["system", "git_config", "comfy_core"]:
                addon = MagicMock()
                addon.name = name
                addon.sync = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
                mock_addons.append(addon)
            mock_pipeline.return_value = mock_addons

            execute("sync", ctx)

        assert called == ["comfy_core", "git_config", "system"]

    def test_until_stops_at_target(self, app_context):
        """--until 应在目标插件后停止"""
        ctx = app_context
        called = []

        with patch("src.main.create_pipeline") as mock_pipeline:
            mock_addons = []
            for name in ["system", "git_config", "torch_engine", "comfy_core"]:
                addon = MagicMock()
                addon.name = name
                addon.setup = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
                mock_addons.append(addon)
            mock_pipeline.return_value = mock_addons

            execute("setup", ctx, until="git_config")

        assert called == ["system", "git_config"]

    def test_only_runs_single_plugin(self, app_context):
        """--only 应只执行指定插件"""
        ctx = app_context
        called = []

        with patch("src.main.create_pipeline") as mock_pipeline:
            mock_addons = []
            for name in ["system", "git_config", "comfy_core"]:
                addon = MagicMock()
                addon.name = name
                addon.setup = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
                mock_addons.append(addon)
            mock_pipeline.return_value = mock_addons

            execute("setup", ctx, only="git_config")

        assert called == ["git_config"]

    def test_only_with_unknown_plugin_exits(self, app_context):
        """--only 指定未知插件应报错退出"""
        ctx = app_context

        with patch("src.main.create_pipeline") as mock_pipeline:
            mock_addons = []
            for name in ["system", "git_config"]:
                addon = MagicMock()
                addon.name = name
                mock_addons.append(addon)
            mock_pipeline.return_value = mock_addons

            with pytest.raises(SystemExit) as exc_info:
                execute("setup", ctx, only="unknown_plugin")
            
            assert exc_info.value.code == 1
