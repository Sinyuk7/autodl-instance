from pathlib import Path
from unittest.mock import patch

from src.lib.utils import save_yaml
from src.status import collect_doctor_checks, collect_quick_checks


def _runtime(tmp_path: Path, project: Path, base: Path):
    config = tmp_path / "config.yaml"
    config.write_text("base_dir: test\n", encoding="utf-8")
    return type("Runtime", (), {
        "code_root": project,
        "base_dir": base,
        "workspace_dir": base / "autodl-workspace",
        "workspace_data_dir": base / "comfyui-workspace",
        "models_dir": base / "models",
        "comfy_dir": tmp_path / "ComfyUI",
        "config_file": config,
        "secrets_file": tmp_path / "secrets.yaml",
        "local_config": {},
        "local_secrets": {},
    })()


def test_status_empty_environment_reports_problems(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    project.mkdir()
    base.mkdir()
    runtime = _runtime(tmp_path, project, base)

    with patch("src.status.resolve_runtime_config", return_value=runtime):
        checks = collect_quick_checks(
            project_root=project,
            base_dir=base,
            workspace_dir=runtime.workspace_dir,
            workspace_data_dir=runtime.workspace_data_dir,
            models_dir=runtime.models_dir,
            comfy_dir=runtime.comfy_dir,
        )

    by_name = {check.name: check for check in checks}
    assert by_name["ComfyUI"].status == "WARN"
    assert by_name["workspace data"].status == "FAIL"
    assert by_name["models symlink"].status == "WARN"
    assert by_name["model-lock"].status == "WARN"


def test_status_reports_persistent_workspace_and_model_state(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    workspace_data = base / "comfyui-workspace"
    models = base / "models"
    project.mkdir()
    comfy.mkdir()
    workspace_data.mkdir(parents=True)
    models.mkdir()
    (comfy / "models").symlink_to(models)
    save_yaml(workspace_data / "model-lock.yaml", {"models": []})
    runtime = _runtime(tmp_path, project, base)

    with patch("src.status.resolve_runtime_config", return_value=runtime):
        checks = collect_quick_checks(
            project_root=project,
            base_dir=base,
            workspace_dir=runtime.workspace_dir,
            workspace_data_dir=workspace_data,
            models_dir=models,
            comfy_dir=comfy,
        )

    by_name = {check.name: check for check in checks}
    assert by_name["workspace data"].status == "OK"
    assert by_name["models symlink"].status == "OK"
    assert by_name["model-lock"].status == "OK"


def test_doctor_includes_disk_and_credentials_checks(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    project.mkdir()
    base.mkdir()
    runtime = _runtime(tmp_path, project, base)

    with patch("src.status.resolve_runtime_config", return_value=runtime):
        checks = collect_doctor_checks(
            project_root=project,
            base_dir=base,
            workspace_dir=runtime.workspace_dir,
            workspace_data_dir=runtime.workspace_data_dir,
            models_dir=runtime.models_dir,
            comfy_dir=runtime.comfy_dir,
        )

    names = {check.name for check in checks}
    assert {"data disk", "HF token", "CivitAI token", "network"} <= names
