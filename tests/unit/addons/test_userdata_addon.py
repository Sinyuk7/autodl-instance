from pathlib import Path

from src.addons.userdata.plugin import UserdataAddon
from src.core.interface import AppContext
from src.lib.utils import load_yaml


def test_userdata_setup_uses_external_userdata_dir(app_context: AppContext, tmp_path: Path):
    userdata = tmp_path / "external-data"
    comfy = tmp_path / "ComfyUI"
    (comfy / "user").mkdir(parents=True)
    (comfy / "script_examples").mkdir(parents=True)
    app_context.userdata_dir = userdata
    app_context.models_dir = tmp_path / "models"
    app_context.workspace_dir = tmp_path / "workspace"
    app_context.artifacts.comfy_dir = comfy
    app_context.addon_manifests["userdata"] = {
        "sync_dirs": ["user", "script_examples"],
        "userdata_repo": "",
    }

    UserdataAddon().setup(app_context)

    assert app_context.artifacts.userdata_dir == userdata
    assert (userdata / "user").exists()
    assert (userdata / "script_examples").exists()
    assert (comfy / "user").is_symlink()
    assert (comfy / "script_examples").is_symlink()
    meta = userdata / ".autodl-instance"
    assert (meta / "tool-version").exists()
    assert load_yaml(meta / "config.yaml")["models_dir"] == str(app_context.models_dir)


def test_userdata_sync_missing_external_dir_fails(app_context: AppContext, tmp_path: Path):
    app_context.userdata_dir = tmp_path / "missing-data"

    result = UserdataAddon().sync(app_context)

    assert result.status == "failure"
    assert str(app_context.userdata_dir) in result.message


def test_userdata_repo_from_local_config_overrides_manifest(app_context: AppContext, mock_runner, tmp_path: Path):
    userdata = tmp_path / "custom-data"
    app_context.userdata_dir = userdata
    app_context.local_config["userdata_repo"] = "git@example.com:user/custom.git"
    app_context.addon_manifests["userdata"] = {
        "sync_dirs": [],
        "userdata_repo": "",
    }
    mock_runner.stub_results["git clone"] = mock_runner.run(["true"])
    mock_runner.calls.clear()

    UserdataAddon().setup(app_context)

    assert mock_runner.assert_called_with("git clone").cwd == userdata.parent
    assert any(cmd.endswith("custom.git custom-data") for cmd in mock_runner.all_commands)


def test_userdata_repo_manifest_is_not_runtime_default(app_context: AppContext, mock_runner, tmp_path: Path):
    userdata = tmp_path / "local-data"
    app_context.userdata_dir = userdata
    app_context.addon_manifests["userdata"] = {
        "sync_dirs": [],
        "userdata_repo": "git@example.com:user/manifest.git",
    }

    UserdataAddon().setup(app_context)

    mock_runner.assert_not_called_with("git clone")
    assert userdata.exists()
