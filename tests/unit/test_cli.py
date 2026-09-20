from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
import types

from src.cli import main
from src.lib.utils import load_yaml, save_yaml


def test_autodl_init_writes_global_config(tmp_path: Path):
    config = tmp_path / "config.yaml"
    base = tmp_path / "autodl-tmp"
    shared = tmp_path / "autodl-fs" / "ComfyUI"
    local = base / "ComfyUI"

    with patch("src.lib.network.invalidate_network_cache") as invalidate, \
         patch("src.lib.network.setup_network") as setup_network:
        main([
            "init", "--config-file", str(config), "--base-dir", str(base),
            "--comfy-dir", str(tmp_path / "ComfyUI"),
            "--models-dir", str(shared / "models"),
            "--output-dir", str(shared / "output"),
            "--downloads-dir", str(local / "downloads"),
            "--cache-dir", str(local / "cache"),
            "--temp-dir", str(local / "temp"),
        ])

    data = load_yaml(config)
    assert data["base_dir"] == str(base)
    assert data["workspace_dir"] == str(base / "autodl-workspace")
    assert data["workspace_data_dir"] == str(base / "comfyui-workspace")
    assert data["models_dir"] == str(shared / "models")
    assert data["output_dir"] == str(shared / "output")
    assert data["downloads_dir"] == str(local / "downloads")
    assert data["cache_dir"] == str(local / "cache")
    assert data["temp_dir"] == str(local / "temp")
    invalidate.assert_not_called()
    setup_network.assert_called_once_with(config_file=config)


def test_autodl_setup_dispatches_lifecycle():
    with patch("src.main.main") as lifecycle:
        main(["setup", "--debug"])
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


def init_args(tmp_path):
    return ["init", "--config-file", str(tmp_path / "config.yaml"),
            "--base-dir", str(tmp_path / "local"),
            "--comfy-dir", str(tmp_path / "ComfyUI"),
            "--models-dir", str(tmp_path / "shared/models"),
            "--output-dir", str(tmp_path / "shared/output"),
            "--downloads-dir", str(tmp_path / "local/downloads"),
            "--cache-dir", str(tmp_path / "local/cache"),
            "--temp-dir", str(tmp_path / "local/temp")]


def test_init_repeat_does_not_rewrite_config(tmp_path):
    args = init_args(tmp_path)
    with patch("src.lib.network.setup_network"):
        main(args)
        config = tmp_path / "config.yaml"
        before = config.stat().st_mtime_ns
        main(["init", "--config-file", str(config)])
        assert config.stat().st_mtime_ns == before


def test_init_preserves_root_files_and_starts_proxy(tmp_path):
    source = tmp_path / "ComfyUI/output"
    source.mkdir(parents=True)
    (source / "keep.png").write_bytes(b"keep")
    with patch("src.lib.network.setup_network") as network:
        main(init_args(tmp_path))
        network.assert_called_once()
    assert (source / "keep.png").read_bytes() == b"keep"
    assert not source.is_symlink()


def test_migrate_cli_preserves_models_without_network(tmp_path):
    from types import SimpleNamespace
    source = tmp_path / "ComfyUI/models/a"
    source.mkdir(parents=True)
    (source / "model.bin").write_bytes(b"model")
    config = tmp_path / "config.yaml"
    runtime = SimpleNamespace(comfy_dir=source.parent.parent, models_dir=tmp_path / "shared/models",
                              output_dir=tmp_path / "shared/output",
                              workspace_data_dir=tmp_path / "local/user-data")
    with patch("src.cli.resolve_runtime_config", return_value=runtime) as resolve, \
         patch("src.lib.network.setup_network") as network:
        main(["migrate", "--config-file", str(config)])
        assert resolve.call_args.kwargs["config_file"] == config
        network.assert_not_called()
    assert not source.is_symlink()
    assert (source / "model.bin").read_bytes() == b"model"
    assert not (runtime.models_dir / "a/model.bin").exists()


def test_init_environment_paths_match_runtime_without_persisting_override(tmp_path, monkeypatch):
    override = tmp_path / "override-models"
    monkeypatch.setenv("AUTODL_MODELS_DIR", str(override))
    (tmp_path / "ComfyUI/models/a").mkdir(parents=True)
    with patch("src.lib.network.setup_network"):
        main(init_args(tmp_path))
    assert not (tmp_path / "ComfyUI/models/a").is_symlink()
    assert load_yaml(tmp_path / "config.yaml")["models_dir"] == str(tmp_path / "shared/models")


def test_shared_storage_defaults_are_direct_children():
    from src.core.runtime import DEFAULT_MODELS_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_CACHE_DIR
    assert DEFAULT_MODELS_DIR == Path("/root/autodl-fs/models")
    assert DEFAULT_OUTPUT_DIR == Path("/root/autodl-fs/output")
    assert DEFAULT_CACHE_DIR == Path("/root/autodl-tmp/ComfyUI/cache")


def test_init_configures_fixed_paths_when_comfy_installed(tmp_path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    (comfy / "main.py").touch()
    with patch("src.lib.network.setup_network"):
        main(init_args(tmp_path))
        config = load_yaml(comfy / "extra_model_paths.yaml")
        assert config["autodl_local_models"]["base_path"] == str(tmp_path / "local/ComfyUI/models")
        assert config["autodl_canonical_models"]["base_path"] == str(tmp_path / "shared/models")
        before = (comfy / "extra_model_paths.yaml").stat().st_mtime_ns
        main(init_args(tmp_path))
        assert (comfy / "extra_model_paths.yaml").stat().st_mtime_ns == before
