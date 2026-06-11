from pathlib import Path

from src.core.runtime import (
    DEFAULT_USERDATA_NAME,
    find_legacy_userdata_dirs,
    resolve_runtime_config,
    should_warn_legacy_userdata,
    write_data_repo_metadata,
)
from src.lib.utils import load_yaml, save_yaml


def test_resolve_runtime_config_uses_global_config(tmp_path: Path):
    code_root = tmp_path / "code"
    code_root.mkdir()
    config_file = tmp_path / "config.yaml"
    save_yaml(config_file, {
        "base_dir": str(tmp_path / "data"),
        "workspace_dir": str(tmp_path / "workspace"),
        "userdata_dir": str(tmp_path / "userdata"),
        "comfy_dir": str(tmp_path / "ComfyUI"),
        "models_dir": str(tmp_path / "models"),
        "userdata_repo": "git@example.com:user/repo.git",
    })

    runtime = resolve_runtime_config(code_root, config_file=config_file)

    assert runtime.code_root == code_root.resolve()
    assert runtime.base_dir == (tmp_path / "data").resolve()
    assert runtime.workspace_dir == (tmp_path / "workspace").resolve()
    assert runtime.userdata_dir == (tmp_path / "userdata").resolve()
    assert runtime.comfy_dir == (tmp_path / "ComfyUI").resolve()
    assert runtime.models_dir == (tmp_path / "models").resolve()
    assert runtime.secrets_file.name == "secrets.yaml"
    assert runtime.local_config["userdata_repo"] == "git@example.com:user/repo.git"


def test_resolve_runtime_config_env_overrides_config(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    save_yaml(config_file, {"base_dir": str(tmp_path / "from-config")})
    monkeypatch.setenv("AUTODL_BASE_DIR", str(tmp_path / "from-env"))

    runtime = resolve_runtime_config(tmp_path / "code", config_file=config_file)

    assert runtime.base_dir == (tmp_path / "from-env").resolve()
    assert runtime.userdata_dir == runtime.base_dir / DEFAULT_USERDATA_NAME


def test_resolve_runtime_config_loads_local_secrets(tmp_path: Path):
    secrets_file = tmp_path / "secrets.yaml"
    save_yaml(secrets_file, {"hf_token": "secret"})

    runtime = resolve_runtime_config(tmp_path / "code", secrets_file=secrets_file)

    assert runtime.secrets_file == secrets_file
    assert runtime.local_secrets["hf_token"] == "secret"


def test_should_warn_legacy_userdata_when_old_layout_exists(tmp_path: Path):
    code_root = tmp_path / "code"
    old_userdata = code_root / DEFAULT_USERDATA_NAME
    old_userdata.mkdir(parents=True)
    new_userdata = tmp_path / "data" / DEFAULT_USERDATA_NAME

    assert should_warn_legacy_userdata(code_root, new_userdata)
    assert not should_warn_legacy_userdata(code_root, old_userdata)


def test_find_legacy_userdata_dirs_checks_old_source_checkout(tmp_path: Path):
    code_root = tmp_path / "package-root"
    base = tmp_path / "autodl-tmp"
    old = base / "autodl-instance" / DEFAULT_USERDATA_NAME
    new_userdata = base / DEFAULT_USERDATA_NAME
    old.mkdir(parents=True)

    legacy_dirs = find_legacy_userdata_dirs(code_root, base, new_userdata)

    assert legacy_dirs == [old]


def test_write_data_repo_metadata(tmp_path: Path):
    userdata = tmp_path / "userdata"

    write_data_repo_metadata(userdata, tool_version="9.9.9", config={"models_dir": "/models"})

    meta = userdata / ".autodl-instance"
    assert (meta / "data-schema-version").read_text(encoding="utf-8").strip() == "1"
    assert (meta / "tool-version").read_text(encoding="utf-8").strip() == "9.9.9"
    assert load_yaml(meta / "config.yaml")["models_dir"] == "/models"
