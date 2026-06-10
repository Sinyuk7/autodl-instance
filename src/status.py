"""
Project status and doctor CLI.

All checks are read-only. The module intentionally avoids setup_network() so
doctor does not start proxy processes or mutate runtime state.
"""
import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from src.addons.models.config import get_lock_file, get_models_base
from src.addons.models.status import collect_lock_status
from src.lib.network.config import AUTODL_TURBO_SCRIPT, ENV_CIVITAI_TOKEN, ENV_HF_ENDPOINT, ENV_HF_TOKEN
from src.lib.network.state import get_cached_network_decision
from src.lib.utils import format_size, load_yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = Path("/root/autodl-tmp")
COMFY_DIR = Path("/root/ComfyUI")
BACKUP_DIR_NAME = "my-comfyui-backup"


@dataclass
class StatusCheck:
    name: str
    status: str
    detail: str

    @property
    def is_problem(self) -> bool:
        return self.status in ("WARN", "FAIL")


def _status_markup(status: str) -> str:
    if status == "OK":
        return "[green]OK[/green]"
    if status == "WARN":
        return "[yellow]WARN[/yellow]"
    if status == "SKIP":
        return "[dim]SKIP[/dim]"
    return "[red]FAIL[/red]"


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _run_git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        output = (result.stdout or result.stderr).strip()
        return output if result.returncode == 0 else f"失败: {output}"
    except Exception as e:
        return f"失败: {e}"


def collect_quick_checks(
    project_root: Path = PROJECT_ROOT,
    base_dir: Path = BASE_DIR,
    comfy_dir: Path = COMFY_DIR,
) -> List[StatusCheck]:
    """Collect fast readiness checks for status/start."""
    backup_dir = project_root / BACKUP_DIR_NAME
    lock_file = get_lock_file(project_root)
    models_base = get_models_base(base_dir / "models")
    comfy_models = comfy_dir / "models"

    checks: List[StatusCheck] = []

    checks.append(StatusCheck(
        "ComfyUI",
        "OK" if comfy_dir.exists() else "WARN",
        str(comfy_dir) if comfy_dir.exists() else f"目录不存在: {comfy_dir}",
    ))

    if comfy_models.is_symlink() and comfy_models.resolve() == models_base.resolve():
        checks.append(StatusCheck("models symlink", "OK", f"{comfy_models} -> {models_base}"))
    elif comfy_models.exists():
        checks.append(StatusCheck("models symlink", "WARN", f"{comfy_models} 未指向 {models_base}"))
    else:
        checks.append(StatusCheck("models symlink", "WARN", f"{comfy_models} 不存在"))

    if backup_dir.exists():
        repo_status = "Git repo" if (backup_dir / ".git").exists() else "local only"
        status = "OK" if (backup_dir / ".git").exists() else "WARN"
        checks.append(StatusCheck("userdata", status, f"{backup_dir} ({repo_status})"))
    else:
        checks.append(StatusCheck("userdata", "FAIL", f"目录不存在: {backup_dir}"))

    if lock_file.exists():
        lock_items = collect_lock_status(lock_file=lock_file, models_base=models_base)
        missing = sum(1 for item in lock_items if item["status"] == "缺失")
        drifted = sum(1 for item in lock_items if item["status"] == "漂移")
        status = "OK" if missing == 0 and drifted == 0 else "WARN"
        checks.append(StatusCheck(
            "model-lock",
            status,
            f"{lock_file}；缺失 {missing}，漂移 {drifted}",
        ))
    else:
        checks.append(StatusCheck("model-lock", "WARN", f"未找到: {lock_file}"))

    snapshots_dir = backup_dir / "user" / "__manager" / "snapshots"
    snapshots = sorted(snapshots_dir.glob("*_snapshot.json")) if snapshots_dir.exists() else []
    if snapshots:
        checks.append(StatusCheck("node snapshot", "OK", snapshots[-1].name))
    else:
        checks.append(StatusCheck("node snapshot", "WARN", f"未找到 snapshot: {snapshots_dir}"))

    return checks


def collect_doctor_checks(
    project_root: Path = PROJECT_ROOT,
    base_dir: Path = BASE_DIR,
    comfy_dir: Path = COMFY_DIR,
) -> List[StatusCheck]:
    """Collect deeper read-only diagnostics."""
    checks = collect_quick_checks(project_root, base_dir, comfy_dir)
    backup_dir = project_root / BACKUP_DIR_NAME

    if (backup_dir / ".git").exists():
        branch = _run_git(["branch", "--show-current"], backup_dir) or "unknown"
        dirty = _run_git(["status", "--porcelain"], backup_dir)
        remote = _run_git(["remote", "-v"], backup_dir)
        checks.append(StatusCheck("git branch", "OK", branch))
        checks.append(StatusCheck("git dirty", "WARN" if dirty else "OK", dirty or "工作区干净"))
        checks.append(StatusCheck("git remote", "OK" if remote else "WARN", remote or "未配置 remote"))
    else:
        checks.append(StatusCheck("git", "WARN", f"{backup_dir} 不是 Git repo"))

    download_secrets = load_yaml(project_root / "src" / "lib" / "download" / "secrets.yaml")
    api_keys = download_secrets.get("api_keys", {}) if isinstance(download_secrets, dict) else {}
    hf_ready = bool(os.environ.get(ENV_HF_TOKEN) or api_keys.get("hf_api_token"))
    civitai_ready = bool(os.environ.get(ENV_CIVITAI_TOKEN) or api_keys.get("civitai_api_token"))
    checks.append(StatusCheck("HF token", "OK" if hf_ready else "SKIP", "已配置" if hf_ready else "未配置"))
    checks.append(StatusCheck("CivitAI token", "OK" if civitai_ready else "SKIP", "已配置" if civitai_ready else "未配置"))

    system_manifest = load_yaml(project_root / "src" / "addons" / "system" / "manifest.yaml")
    hf_endpoint = os.environ.get(ENV_HF_ENDPOINT) or system_manifest.get("huggingface_mirror")
    checks.append(StatusCheck("HF mirror", "OK" if hf_endpoint else "WARN", str(hf_endpoint or "未配置")))

    decision = get_cached_network_decision()
    turbo_detail = f"network cache={decision or 'none'}, turbo={'exists' if AUTODL_TURBO_SCRIPT.exists() else 'missing'}"
    checks.append(StatusCheck("network", "OK" if decision or AUTODL_TURBO_SCRIPT.exists() else "WARN", turbo_detail))

    disk_target = base_dir if base_dir.exists() else base_dir.parent
    try:
        usage = shutil.disk_usage(disk_target)
        checks.append(StatusCheck(
            "data disk",
            "OK" if usage.free > 5 * 1024 * 1024 * 1024 else "WARN",
            f"free={format_size(usage.free // 1024)}, total={format_size(usage.total // 1024)}",
        ))
    except OSError as e:
        checks.append(StatusCheck("data disk", "WARN", f"无法读取磁盘空间: {e}"))

    for cache_dir in [
        Path.home() / ".cache" / "huggingface",
        Path.home() / ".cache" / "torch",
        Path.home() / ".cache" / "uv",
    ]:
        size = _dir_size(cache_dir)
        checks.append(StatusCheck(
            f"cache {cache_dir.name}",
            "OK" if size < 5 * 1024 * 1024 * 1024 else "WARN",
            f"{cache_dir}: {format_size(size // 1024)}",
        ))

    return checks


def print_checks(title: str, checks: Iterable[StatusCheck]) -> None:
    from src.lib import ui

    rows = [[_status_markup(check.status), check.name, check.detail] for check in checks]
    ui.print_table(title=title, columns=["状态", "检查项", "说明"], rows=rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDL ComfyUI 工作区状态检查")
    parser.add_argument("command", nargs="?", choices=["status", "doctor"], default="status")
    args = parser.parse_args()

    if args.command == "doctor":
        print_checks("Doctor 深度检查", collect_doctor_checks())
    else:
        print_checks("工作区状态", collect_quick_checks())


if __name__ == "__main__":
    main()
