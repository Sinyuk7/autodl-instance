from pathlib import Path

from src.status import collect_doctor_checks, collect_quick_checks
from src.lib.utils import save_yaml


def test_status_empty_environment_reports_problems(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    project.mkdir()
    base.mkdir()

    checks = collect_quick_checks(project_root=project, base_dir=base, comfy_dir=comfy)
    by_name = {check.name: check for check in checks}

    assert by_name["ComfyUI"].status == "WARN"
    assert by_name["userdata"].status == "FAIL"
    assert by_name["model-lock"].status == "WARN"


def test_status_local_backup_counts_missing_models(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    backup = project / "my-comfyui-backup"
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

    checks = collect_quick_checks(project_root=project, base_dir=base, comfy_dir=comfy)
    by_name = {check.name: check for check in checks}

    assert by_name["userdata"].status == "WARN"
    assert "缺失 1" in by_name["model-lock"].detail
    assert by_name["node snapshot"].status == "OK"


def test_doctor_git_backup_reports_git_state(tmp_path: Path):
    project = tmp_path / "project"
    base = tmp_path / "autodl-tmp"
    comfy = tmp_path / "ComfyUI"
    backup = project / "my-comfyui-backup"
    project.mkdir()
    base.mkdir()
    comfy.mkdir()
    (base / "models").mkdir()
    (backup / ".git").mkdir(parents=True)

    checks = collect_doctor_checks(project_root=project, base_dir=base, comfy_dir=comfy)
    names = {check.name for check in checks}

    assert "git branch" in names
    assert "git dirty" in names
    assert "data disk" in names
