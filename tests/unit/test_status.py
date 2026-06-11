from pathlib import Path
from unittest.mock import patch

from src.status import collect_doctor_checks, collect_quick_checks
from src.lib.utils import save_yaml


def test_status_empty_environment_reports_problems(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    project.mkdir()
    base.mkdir()

    checks = collect_quick_checks(
        project_root=project,
        base_dir=base,
        workspace_dir=base / "autodl-workspace",
        userdata_dir=base / "my-comfyui-backup",
        models_dir=base / "models",
        comfy_dir=comfy,
    )
    by_name = {check.name: check for check in checks}

    assert by_name["ComfyUI"].status == "WARN"
    assert by_name["userdata"].status == "FAIL"
    assert by_name["model-lock"].status == "WARN"


def test_status_local_backup_counts_missing_models(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    backup = base / "my-comfyui-backup"
    models = base / "models"
    project.mkdir()
    base.mkdir()
    comfy.mkdir()
    models.mkdir()
    backup.mkdir()
    (backup / "user" / "__manager" / "snapshots").mkdir(parents=True)
    (backup / "user" / "__manager" / "snapshots" / "2026_snapshot.json").write_text("{}")
    save_yaml(backup / "model-lock.yaml", {
        "models": [{
            "model": "missing",
            "paths": [{"path": "unet/missing.safetensors"}],
            "hashes": [{"hash": "x", "type": "SHA256"}],
        }]
    })

    checks = collect_quick_checks(
        project_root=project,
        base_dir=base,
        workspace_dir=base / "autodl-workspace",
        userdata_dir=backup,
        models_dir=models,
        comfy_dir=comfy,
    )
    by_name = {check.name: check for check in checks}

    assert by_name["userdata"].status == "WARN"
    assert "缺失 1" in by_name["model-lock"].detail
    assert by_name["node snapshot"].status == "OK"


def test_doctor_git_backup_reports_git_state(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    backup = base / "my-comfyui-backup"
    project.mkdir()
    base.mkdir()
    comfy.mkdir()
    (base / "models").mkdir()
    (backup / ".git").mkdir(parents=True)

    checks = collect_doctor_checks(
        project_root=project,
        base_dir=base,
        workspace_dir=base / "autodl-workspace",
        userdata_dir=backup,
        models_dir=base / "models",
        comfy_dir=comfy,
    )
    names = {check.name for check in checks}

    assert "git branch" in names
    assert "git dirty" in names
    assert "data disk" in names


def test_status_reports_runtime_config_and_data_repo_version(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    workspace = base / "autodl-workspace"
    backup = base / "my-comfyui-backup"
    config = tmp_path / "config.yaml"
    project.mkdir()
    workspace.mkdir(parents=True)
    (base / "models").mkdir()
    backup.mkdir()
    meta = backup / ".autodl-instance"
    meta.mkdir()
    (meta / "tool-version").write_text("1.2.3\n", encoding="utf-8")
    config.write_text("userdata_repo: git@example.com:user/repo.git\n", encoding="utf-8")

    runtime = type("Runtime", (), {
        "code_root": project,
        "base_dir": base,
        "workspace_dir": workspace,
        "userdata_dir": backup,
        "models_dir": base / "models",
        "comfy_dir": tmp_path / "ComfyUI",
        "config_file": config,
        "secrets_file": tmp_path / "secrets.yaml",
        "local_config": {"userdata_repo": "git@example.com:user/repo.git"},
        "local_secrets": {},
    })()

    with patch("src.status.resolve_runtime_config", return_value=runtime):
        checks = collect_quick_checks(
            project_root=project,
            base_dir=base,
            workspace_dir=workspace,
            userdata_dir=backup,
            models_dir=base / "models",
            comfy_dir=tmp_path / "ComfyUI",
        )

    by_name = {check.name: check for check in checks}
    assert by_name["config path"].status == "OK"
    assert by_name["userdata repo"].detail == "git@example.com:user/repo.git"
    assert by_name["data repo expected version"].detail == "1.2.3"


def test_doctor_detects_old_layout_without_mutating(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    backup = base / "my-comfyui-backup"
    old = base / "autodl-instance" / "my-comfyui-backup"
    project.mkdir()
    backup.mkdir(parents=True)
    old.mkdir(parents=True)
    (base / "models").mkdir()

    checks = collect_doctor_checks(
        project_root=project,
        base_dir=base,
        workspace_dir=base / "autodl-workspace",
        userdata_dir=backup,
        models_dir=base / "models",
        comfy_dir=tmp_path / "ComfyUI",
    )

    by_name = {check.name: check for check in checks}
    assert by_name["old layout"].status == "WARN"
    assert str(old) in by_name["old layout"].detail
    assert old.exists()
