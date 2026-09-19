from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
import types

from src.cli import main
from src.lib.utils import load_yaml, save_yaml


def test_autodl_init_writes_global_config(tmp_path: Path):
    config = tmp_path / "config.yaml"
    base = tmp_path / "autodl-tmp"

    main(["init", "--config-file", str(config), "--base-dir", str(base)])

    data = load_yaml(config)
    assert data["base_dir"] == str(base)
    assert data["workspace_dir"] == str(base / "autodl-workspace")
    assert data["workspace_data_dir"] == str(base / "comfyui-workspace")
    assert data["models_dir"] == str(base / "models")


def test_autodl_setup_dispatches_lifecycle():
    with patch("src.main.main") as lifecycle:
        main(["setup", "--debug", "--until", "workspace"])
    lifecycle.assert_called_once()


def test_autodl_model_forwards_help_to_model_cli():
    fake_downloader = types.ModuleType("src.addons.models.downloader")
    fake_downloader.main = MagicMock()
    sys.modules["src.addons.models.downloader"] = fake_downloader
    try:
        main(["model", "--help"])
        fake_downloader.main.assert_called_once()
    finally:
        sys.modules.pop("src.addons.models.downloader", None)


def test_autodl_config_set_show_unset_preserves_unknown_keys(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    save_yaml(config, {"unknown": "kept"})

    main(["config", "--config-file", str(config), "set", "workspace-dir", str(tmp_path / "workspace")])
    data = load_yaml(config)
    assert data["unknown"] == "kept"
    assert data["workspace_dir"] == str((tmp_path / "workspace").resolve())

    main(["config", "--config-file", str(config), "show"])
    assert "workspace_dir" in capsys.readouterr().out

    main(["config", "--config-file", str(config), "unset", "workspace-dir"])
    data = load_yaml(config)
    assert "workspace_dir" not in data
    assert data["unknown"] == "kept"


def test_autodl_config_path(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    main(["config", "--config-file", str(config), "path"])
    assert str(config) in capsys.readouterr().out


def test_autodl_secrets_set_list_unset(tmp_path: Path, capsys):
    secrets = tmp_path / "autodl-instance" / "secrets.yaml"
    main(["secrets", "--secrets-file", str(secrets), "set", "hf-token", "hf_secret"])

    assert load_yaml(secrets)["hf_token"] == "hf_secret"
    assert oct(secrets.parent.stat().st_mode & 0o777) == "0o700"
    assert oct(secrets.stat().st_mode & 0o777) == "0o600"

    main(["secrets", "--secrets-file", str(secrets), "list"])
    output = capsys.readouterr().out
    assert "hf-token: set" in output
    assert "civitai-token: unset" in output

    main(["secrets", "--secrets-file", str(secrets), "unset", "hf-token"])
    assert "hf_token" not in load_yaml(secrets)
