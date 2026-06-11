"""Sync the active local Clash profile into the backup repo and push it."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from src.core.runtime import resolve_runtime_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME = resolve_runtime_config(PROJECT_ROOT)
DEFAULT_PROFILES_DIR = Path.home() / ".config" / "clash" / "profiles"
DEFAULT_REPO_DIR = _RUNTIME.userdata_dir
TARGET_CONFIG_RELATIVE = Path("mihomo") / "config.yaml"


@dataclass(frozen=True)
class ActiveProfile:
    """Metadata for the currently selected Clash profile."""

    name: str
    file_name: str
    path: Path


def load_yaml(path: Path) -> dict:
    """Load a YAML document from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_userdata_repo_url(manifest_path: Path) -> str:
    """Read the backup repo URL from userdata manifest configuration."""
    data = load_yaml(manifest_path)
    return str(data.get("userdata_repo", "")).strip()


def get_active_profile(profiles_dir: Path) -> ActiveProfile:
    """Resolve the current Clash profile using list.yml's active index."""
    list_file = profiles_dir / "list.yml"
    if not list_file.exists():
        raise FileNotFoundError(f"Clash profile index not found: {list_file}")

    data = load_yaml(list_file)
    files = data.get("files")
    index = data.get("index")

    if not isinstance(files, list) or not files:
        raise ValueError(f"No Clash profiles declared in {list_file}")
    if not isinstance(index, int) or index < 0 or index >= len(files):
        raise ValueError(f"Invalid active Clash profile index in {list_file}: {index}")

    entry = files[index]
    file_name = str(entry.get("time", "")).strip()
    if not file_name:
        raise ValueError(f"Active Clash profile entry is missing its file name in {list_file}")

    profile_path = profiles_dir / file_name
    if not profile_path.exists():
        raise FileNotFoundError(f"Active Clash profile file not found: {profile_path}")

    return ActiveProfile(
        name=str(entry.get("name", file_name)).strip() or file_name,
        file_name=file_name,
        path=profile_path,
    )


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command and capture output."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def git_output(result: subprocess.CompletedProcess[str]) -> str:
    """Return stderr first, then stdout for concise error reporting."""
    return result.stderr.strip() or result.stdout.strip()


def has_any_repo_changes(repo_dir: Path) -> bool:
    """Check whether the repo has any staged/unstaged/untracked changes."""
    status = run_git(["status", "--porcelain"], repo_dir)
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {git_output(status)}")
    return bool(status.stdout.strip())


def has_tracking_branch(repo_dir: Path) -> bool:
    """Return True if the current branch tracks an upstream branch."""
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], repo_dir)
    return upstream.returncode == 0


def is_rebase_in_progress(repo_dir: Path) -> bool:
    """Detect whether git rebase is currently in progress."""
    git_dir = repo_dir / ".git"
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def abort_rebase(repo_dir: Path) -> None:
    """Abort rebase when repository is left in an in-progress state."""
    if not is_rebase_in_progress(repo_dir):
        return
    abort = run_git(["rebase", "--abort"], repo_dir)
    if abort.returncode != 0:
        raise RuntimeError(f"git rebase --abort failed: {git_output(abort)}")


def stash_local_changes(repo_dir: Path, reason: str) -> bool:
    """Stash local changes and return whether a new stash entry was created."""
    stash = run_git(["stash", "push", "-u", "-m", reason], repo_dir)
    if stash.returncode != 0:
        raise RuntimeError(f"git stash failed: {git_output(stash)}")
    return "No local changes to save" not in stash.stdout


def restore_stash(repo_dir: Path) -> None:
    """Try restoring the latest stash entry, warn when conflicts occur."""
    pop = run_git(["stash", "pop"], repo_dir)
    if pop.returncode != 0:
        print(f"Warning: git stash pop failed, stash entry was kept for manual recovery: {git_output(pop)}")


def pull_remote_updates(repo_dir: Path) -> None:
    """Pull latest updates from upstream, with merge fallback when rebase fails."""
    if not has_tracking_branch(repo_dir):
        print("Current branch has no upstream; skipping pre-sync pull")
        return

    pull_rebase = run_git(["pull", "--rebase"], repo_dir)
    if pull_rebase.returncode == 0:
        return

    rebase_error = git_output(pull_rebase)
    abort_rebase(repo_dir)

    pull_merge = run_git(["pull", "--no-rebase", "--no-edit"], repo_dir)
    if pull_merge.returncode == 0:
        print("git pull --rebase failed; recovered with merge pull")
        return

    raise RuntimeError(
        "git pull failed (rebase + merge fallback): "
        f"{rebase_error}; {git_output(pull_merge)}"
    )


def sync_repo_with_remote(repo_dir: Path, reason: str) -> None:
    """Safely sync repo with upstream while preserving local uncommitted changes."""
    stashed = False
    if has_any_repo_changes(repo_dir):
        stashed = stash_local_changes(repo_dir, reason)
        if stashed:
            print("Stashed local changes before pulling remote updates")

    try:
        pull_remote_updates(repo_dir)
    finally:
        if stashed:
            restore_stash(repo_dir)


def get_default_remote(repo_dir: Path) -> str:
    """Get the first configured git remote name."""
    remote = run_git(["remote"], repo_dir)
    if remote.returncode != 0:
        raise RuntimeError(f"git remote failed: {git_output(remote)}")
    for line in remote.stdout.splitlines():
        name = line.strip()
        if name:
            return name
    return ""


def push_current_branch(repo_dir: Path) -> subprocess.CompletedProcess[str]:
    """Push current branch; auto-set upstream when missing."""
    push = run_git(["push"], repo_dir)
    if push.returncode == 0:
        return push

    text = f"{push.stdout}\n{push.stderr}".lower()
    if "no upstream branch" in text or "set upstream" in text:
        remote = get_default_remote(repo_dir)
        if not remote:
            return push
        return run_git(["push", "-u", remote, "HEAD"], repo_dir)
    return push


def should_retry_push_with_sync(output: str) -> bool:
    """Detect push failures likely caused by remote divergence."""
    text = output.lower()
    return (
        "non-fast-forward" in text
        or "fetch first" in text
        or "failed to push some refs" in text
        or "[rejected]" in text
    )


def ensure_backup_repo(repo_dir: Path, repo_url: str) -> None:
    """Make sure the backup directory is a git clone of the configured repo."""
    if (repo_dir / ".git").exists():
        return

    if not repo_url:
        raise RuntimeError(
            f"{repo_dir} is not a git repo, and userdata_repo is not configured. "
            "Run: autodl config set userdata-repo <git-url>"
        )

    if repo_dir.exists() and any(repo_dir.iterdir()):
        backup_root = Path(tempfile.gettempdir()) / "autodl-instance-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_dir = backup_root / f"{repo_dir.name}_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(str(repo_dir), str(backup_dir))
        print(f"Backed up existing non-git directory to {backup_dir}")

    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    clone = subprocess.run(
        ["git", "clone", repo_url, str(repo_dir)],
        text=True,
        capture_output=True,
        check=False,
    )
    if clone.returncode != 0:
        raise RuntimeError(f"git clone failed: {git_output(clone)}")


def write_active_profile(profile: ActiveProfile, repo_dir: Path) -> Path:
    """Copy the active Clash profile into the backup repo's mihomo config file."""
    target = repo_dir / TARGET_CONFIG_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(profile.path, target)
    return target


def has_staged_or_worktree_changes(repo_dir: Path, target: Path) -> bool:
    """Check whether the target file differs in the git worktree."""
    status = run_git(["status", "--porcelain", "--", str(target.relative_to(repo_dir))], repo_dir)
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {git_output(status)}")
    return bool(status.stdout.strip())


def commit_and_push(repo_dir: Path, target: Path, message: str) -> bool:
    """Commit and push the synced config if the target file changed."""
    relative_target = str(target.relative_to(repo_dir))
    add = run_git(["add", "--", relative_target], repo_dir)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {git_output(add)}")

    diff = run_git(["diff", "--cached", "--quiet", "--", relative_target], repo_dir)
    if diff.returncode == 0:
        return False
    if diff.returncode not in (0, 1):
        raise RuntimeError(f"git diff failed: {git_output(diff)}")

    commit = run_git(["commit", "-m", message, "--", relative_target], repo_dir)
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {git_output(commit)}")

    push = push_current_branch(repo_dir)
    if push.returncode == 0:
        return True

    push_error = git_output(push)
    if should_retry_push_with_sync(push_error):
        print("Push was rejected by remote changes; pulling latest and retrying push")
        sync_repo_with_remote(repo_dir, reason="sync-clash pre-push reconcile")
        retry = push_current_branch(repo_dir)
        if retry.returncode == 0:
            return True
        raise RuntimeError(f"git push failed after retry: {git_output(retry)}")

    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push_error}")
    return True


def build_commit_message(profile: ActiveProfile) -> str:
    """Create a concise commit message for profile syncs."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"Sync mihomo config from {profile.name} at {timestamp}"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Sync the current local Clash profile into my-comfyui-backup/mihomo/config.yaml",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=DEFAULT_PROFILES_DIR,
        help=f"Clash profiles directory (default: {DEFAULT_PROFILES_DIR})",
    )
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=DEFAULT_REPO_DIR,
        help=f"Backup repo directory (default: {DEFAULT_REPO_DIR})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional legacy userdata manifest path",
    )
    parser.add_argument(
        "--message",
        type=str,
        default="",
        help="Optional git commit message override",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Only update the file locally without committing or pushing",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    profiles_dir = args.profiles_dir.expanduser().resolve()
    repo_dir = args.repo_dir.expanduser().resolve()

    profile = get_active_profile(profiles_dir)
    repo_url = str(_RUNTIME.local_config.get("userdata_repo", "")).strip()
    if not repo_url and args.manifest:
        manifest_path = args.manifest.expanduser().resolve()
        repo_url = get_userdata_repo_url(manifest_path) if manifest_path.exists() else ""

    print(f"Active Clash profile: {profile.name} ({profile.file_name})")
    ensure_backup_repo(repo_dir, repo_url)
    if not args.no_push:
        sync_repo_with_remote(repo_dir, reason="sync-clash preflight")
    target = write_active_profile(profile, repo_dir)
    print(f"Updated {target}")

    if args.no_push:
        print("Skipping git commit/push because --no-push was provided")
        return 0

    if not has_staged_or_worktree_changes(repo_dir, target):
        print("No config changes detected; nothing to commit")
        return 0

    message = args.message or build_commit_message(profile)
    changed = commit_and_push(repo_dir, target, message)
    if changed:
        print("Committed and pushed mihomo config update")
    else:
        print("No staged diff detected; nothing pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
