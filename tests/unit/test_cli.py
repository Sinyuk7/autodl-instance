from pathlib import Path
from unittest.mock import patch
import sys
import types
from unittest.mock import MagicMock

from src.cli import main
from src.lib.utils import load_yaml, save_yaml


def test_autodl_init_writes_global_config(tmp_path: Path):
    config = tmp_path / "config.yaml"
    base = tmp_path / "autodl-tmp"

    main([
        "init",
        "--config-file", str(config),
        "--base-dir", str(base),
        "--userdata-repo", "git@example.com:user/my-comfyui-backup.git",
    ])

    data = load_yaml(config)
    assert data["base_dir"] == str(base)
    assert data["workspace_dir"] == str(base / "autodl-workspace")
    assert data["userdata_dir"] == str(base / "my-comfyui-backup")
    assert data["models_dir"] == str(base / "models")
    assert data["userdata_repo"] == "git@example.com:user/my-comfyui-backup.git"


def test_autodl_setup_dispatches_lifecycle():
    with patch("src.main.main") as lifecycle:
        main(["setup", "--debug", "--until", "userdata"])

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

    main([
        "config",
        "--config-file", str(config),
        "set", "userdata-repo", "git@example.com:user/repo.git",
    ])
    main([
        "config",
        "--config-file", str(config),
        "set", "workspace-dir", str(tmp_path / "workspace"),
    ])

    data = load_yaml(config)
    assert data["unknown"] == "kept"
    assert data["userdata_repo"] == "git@example.com:user/repo.git"
    assert data["workspace_dir"] == str((tmp_path / "workspace").resolve())

    main(["config", "--config-file", str(config), "show"])
    output = capsys.readouterr().out
    assert "userdata_repo" in output

    main(["config", "--config-file", str(config), "unset", "userdata-repo"])
    data = load_yaml(config)
    assert "userdata_repo" not in data
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


def test_autodl_migrate_detect_old_layout_is_read_only(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    base = tmp_path / "autodl-tmp"
    old_userdata = base / "autodl-instance" / "my-comfyui-backup"
    old_userdata.mkdir(parents=True)
    save_yaml(config, {
        "base_dir": str(base),
        "userdata_dir": str(base / "my-comfyui-backup"),
    })

    with patch("src.cli._code_root", return_value=tmp_path / "package-root"):
        main(["migrate", "--config-file", str(config), "detect-old-layout"])

    output = capsys.readouterr().out
    assert str(old_userdata) in output
    assert old_userdata.exists()
