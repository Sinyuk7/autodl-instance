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
from src.core.runtime import (
    DEFAULT_BASE_DIR,
    DEFAULT_COMFY_DIR,
    DEFAULT_USERDATA_NAME,
    find_legacy_userdata_dirs,
    load_local_secrets,
    read_expected_tool_version,
    resolve_runtime_config,
    get_tool_version,
)
from src.lib.network.config import AUTODL_TURBO_SCRIPT, ENV_CIVITAI_TOKEN, ENV_HF_ENDPOINT, ENV_HF_TOKEN
from src.lib.network.state import get_cached_network_decision
from src.lib.utils import format_size, load_yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME = resolve_runtime_config(PROJECT_ROOT)
BASE_DIR = DEFAULT_BASE_DIR
COMFY_DIR = DEFAULT_COMFY_DIR
BACKUP_DIR_NAME = DEFAULT_USERDATA_NAME


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
    workspace_dir: Path | None = None,
    userdata_dir: Path | None = None,
    models_dir: Path | None = None,
    comfy_dir: Path = COMFY_DIR,
) -> List[StatusCheck]:
    """Collect fast readiness checks for status/start."""
    workspace = workspace_dir or _RUNTIME.workspace_dir
    backup_dir = userdata_dir or _RUNTIME.userdata_dir
    runtime = resolve_runtime_config(project_root)
    config = runtime.local_config
    lock_file = get_lock_file(backup_dir)
    models_base = get_models_base(models_dir or _RUNTIME.models_dir or (base_dir / "models"))
    comfy_models = comfy_dir / "models"

    checks: List[StatusCheck] = []

    checks.append(StatusCheck("tool version", "OK", get_tool_version()))
    checks.append(StatusCheck(
        "config path",
        "OK" if runtime.config_file.exists() else "WARN",
        str(runtime.config_file) if runtime.config_file.exists() else f"未找到: {runtime.config_file}",
    ))
    checks.append(StatusCheck(
        "userdata repo",
        "OK" if config.get("userdata_repo") else "WARN",
        str(config.get("userdata_repo") or "未配置"),
    ))
    checks.append(StatusCheck("code root", "OK" if project_root.exists() else "WARN", str(project_root)))
    checks.append(StatusCheck("workspace", "OK" if workspace.exists() else "WARN", str(workspace)))

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
        expected_version = read_expected_tool_version(backup_dir)
        checks.append(StatusCheck(
            "data repo expected version",
            "OK" if expected_version else "SKIP",
            expected_version or "未记录",
        ))
    else:
        checks.append(StatusCheck("userdata", "FAIL", f"目录不存在: {backup_dir}"))
        checks.append(StatusCheck("data repo expected version", "SKIP", "userdata 不存在"))

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
    workspace_dir: Path | None = None,
    userdata_dir: Path | None = None,
    models_dir: Path | None = None,
    comfy_dir: Path = COMFY_DIR,
) -> List[StatusCheck]:
    """Collect deeper read-only diagnostics."""
    checks = collect_quick_checks(
        project_root=project_root,
        base_dir=base_dir,
        workspace_dir=workspace_dir,
        userdata_dir=userdata_dir,
        models_dir=models_dir,
        comfy_dir=comfy_dir,
    )
    backup_dir = userdata_dir or _RUNTIME.userdata_dir
    runtime = resolve_runtime_config(project_root)

    if (backup_dir / ".git").exists():
        branch = _run_git(["branch", "--show-current"], backup_dir) or "unknown"
        dirty = _run_git(["status", "--porcelain"], backup_dir)
        remote = _run_git(["remote", "-v"], backup_dir)
        checks.append(StatusCheck("git branch", "OK", branch))
        checks.append(StatusCheck("git dirty", "WARN" if dirty else "OK", dirty or "工作区干净"))
        checks.append(StatusCheck("git remote", "OK" if remote else "WARN", remote or "未配置 remote"))
    else:
        checks.append(StatusCheck("git", "WARN", f"{backup_dir} 不是 Git repo"))

    local_secrets = load_local_secrets(runtime.secrets_file)
    hf_ready = bool(os.environ.get(ENV_HF_TOKEN) or local_secrets.get("hf_token"))
    civitai_ready = bool(os.environ.get(ENV_CIVITAI_TOKEN) or local_secrets.get("civitai_token"))
    checks.append(StatusCheck("HF token", "OK" if hf_ready else "SKIP", "已配置" if hf_ready else "未配置"))
    checks.append(StatusCheck("CivitAI token", "OK" if civitai_ready else "SKIP", "已配置" if civitai_ready else "未配置"))

    system_manifest = load_yaml(project_root / "src" / "addons" / "system" / "manifest.yaml")
    hf_endpoint = os.environ.get(ENV_HF_ENDPOINT) or system_manifest.get("huggingface_mirror")
    checks.append(StatusCheck("HF mirror", "OK" if hf_endpoint else "WARN", str(hf_endpoint or "未配置")))

    decision = get_cached_network_decision()
    turbo_detail = f"network cache={decision or 'none'}, turbo={'exists' if AUTODL_TURBO_SCRIPT.exists() else 'missing'}"
    checks.append(StatusCheck("network", "OK" if decision or AUTODL_TURBO_SCRIPT.exists() else "WARN", turbo_detail))

    legacy_dirs = find_legacy_userdata_dirs(project_root, base_dir, backup_dir)
    if legacy_dirs:
        checks.append(StatusCheck(
            "old layout",
            "WARN",
            f"检测到 {', '.join(str(path) for path in legacy_dirs)}；当前写入 {backup_dir}；不会自动移动或删除",
        ))
    else:
        checks.append(StatusCheck("old layout", "OK", "未检测到旧布局数据目录"))

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

    runtime = resolve_runtime_config(PROJECT_ROOT)
    if args.command == "doctor":
        print_checks(
            "Doctor 深度检查",
            collect_doctor_checks(
                project_root=runtime.code_root,
                base_dir=runtime.base_dir,
                workspace_dir=runtime.workspace_dir,
                userdata_dir=runtime.userdata_dir,
                models_dir=runtime.models_dir,
                comfy_dir=runtime.comfy_dir,
            ),
        )
    else:
        print_checks(
            "工作区状态",
            collect_quick_checks(
                project_root=runtime.code_root,
                base_dir=runtime.base_dir,
                workspace_dir=runtime.workspace_dir,
                userdata_dir=runtime.userdata_dir,
                models_dir=runtime.models_dir,
                comfy_dir=runtime.comfy_dir,
            ),
        )


if __name__ == "__main__":
    main()
