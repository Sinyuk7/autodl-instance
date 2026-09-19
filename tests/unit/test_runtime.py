from pathlib import Path

from src.core.runtime import resolve_runtime_config
from src.lib.utils import save_yaml


def test_resolve_runtime_config_uses_global_config(tmp_path: Path):
    code_root = tmp_path / "code"
    code_root.mkdir()
    config_file = tmp_path / "config.yaml"
    save_yaml(config_file, {
        "base_dir": str(tmp_path / "data"),
        "workspace_dir": str(tmp_path / "workspace"),
        "workspace_data_dir": str(tmp_path / "workspace-data"),
        "comfy_dir": str(tmp_path / "ComfyUI"),
        "models_dir": str(tmp_path / "models"),
    })

    runtime = resolve_runtime_config(code_root, config_file=config_file)

    assert runtime.code_root == code_root.resolve()
    assert runtime.base_dir == (tmp_path / "data").resolve()
    assert runtime.workspace_dir == (tmp_path / "workspace").resolve()
    assert runtime.workspace_data_dir == (tmp_path / "workspace-data").resolve()
    assert runtime.comfy_dir == (tmp_path / "ComfyUI").resolve()
    assert runtime.models_dir == (tmp_path / "models").resolve()


def test_resolve_runtime_config_env_overrides_config(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    save_yaml(config_file, {"base_dir": str(tmp_path / "from-config")})
    monkeypatch.setenv("AUTODL_BASE_DIR", str(tmp_path / "from-env"))

    runtime = resolve_runtime_config(tmp_path / "code", config_file=config_file)

    assert runtime.base_dir == (tmp_path / "from-env").resolve()
    assert runtime.workspace_dir == runtime.base_dir / "autodl-workspace"
    assert runtime.workspace_data_dir == runtime.base_dir / "comfyui-workspace"
    assert runtime.models_dir == runtime.base_dir / "models"


def test_resolve_runtime_config_loads_local_secrets(tmp_path: Path):
    secrets_file = tmp_path / "secrets.yaml"
    save_yaml(secrets_file, {"hf_token": "secret"})

    runtime = resolve_runtime_config(tmp_path / "code", secrets_file=secrets_file)

    assert runtime.secrets_file == secrets_file
    assert runtime.local_secrets["hf_token"] == "secret"
