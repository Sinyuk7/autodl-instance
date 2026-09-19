from unittest.mock import MagicMock, patch

import pytest

from src.main import create_pipeline, execute
from src.core.results import PluginResult


PLUGIN_NAMES = ["system", "torch_engine", "comfy_core", "workspace", "nodes", "models"]


def test_create_pipeline_returns_current_order():
    assert [addon.name for addon in create_pipeline()] == PLUGIN_NAMES


def test_setup_calls_all_plugins(app_context):
    called = []
    addons = []
    for name in PLUGIN_NAMES:
        addon = MagicMock()
        addon.name = name
        addon.setup = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
        addons.append(addon)
    with patch("src.main.create_pipeline", return_value=addons):
        execute("setup", app_context)
    assert called == PLUGIN_NAMES


def test_stop_collects_failures_and_continues(app_context):
    called = []
    first = MagicMock()
    first.name = "first"
    first.stop = MagicMock(side_effect=lambda ctx: called.append("first"))
    failing = MagicMock()
    failing.name = "failing"
    failing.stop = MagicMock(side_effect=RuntimeError("boom"))
    last = MagicMock()
    last.name = "last"
    last.stop = MagicMock(side_effect=lambda ctx: called.append("last"))
    with patch("src.main.create_pipeline", return_value=[first, failing, last]):
        result = execute("stop", app_context)
    assert called == ["first", "last"]
    assert not result.ok
    assert result.failures[0].plugin == "failing"


def test_stop_records_plugin_warning(app_context):
    addon = MagicMock()
    addon.name = "nodes"
    addon.stop = MagicMock(return_value=PluginResult.warning("snapshot failed"))
    with patch("src.main.create_pipeline", return_value=[addon]):
        result = execute("stop", app_context)
    assert result.ok
    assert result.warnings[0].message == "snapshot failed"


def test_until_stops_at_target(app_context):
    called = []
    addons = []
    for name in PLUGIN_NAMES:
        addon = MagicMock()
        addon.name = name
        addon.setup = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
        addons.append(addon)
    with patch("src.main.create_pipeline", return_value=addons):
        execute("setup", app_context, until="workspace")
    assert called == PLUGIN_NAMES[:4]


def test_only_runs_single_plugin(app_context):
    called = []
    addons = []
    for name in PLUGIN_NAMES:
        addon = MagicMock()
        addon.name = name
        addon.setup = MagicMock(side_effect=lambda ctx, n=name: called.append(n))
        addons.append(addon)
    with patch("src.main.create_pipeline", return_value=addons):
        execute("setup", app_context, only="workspace")
    assert called == ["workspace"]


def test_only_with_unknown_plugin_exits(app_context):
    with patch("src.main.create_pipeline", return_value=[]):
        with pytest.raises(SystemExit) as exc_info:
            execute("setup", app_context, only="unknown")
    assert exc_info.value.code == 1
