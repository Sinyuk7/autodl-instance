"""
工具函数
"""
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def setup_logger(log_file: Path, debug: bool = False) -> logging.Logger:
    """配置全局日志，终端输出 INFO（debug 模式输出 DEBUG），文件输出 DEBUG"""
    _logger = logging.getLogger("autodl_setup")
    _logger.setLevel(logging.DEBUG)
    
    # 避免重复添加 handler
    if _logger.handlers:
        # 如果 debug 模式，更新已有 console handler 的级别
        if debug:
            for h in _logger.handlers:
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                    h.setLevel(logging.DEBUG)
        return _logger

    # 终端 Handler (INFO 级别，debug 模式输出 DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)

    # 文件 Handler (DEBUG 级别，详细日志)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    _logger.addHandler(console_handler)
    _logger.addHandler(file_handler)
    
    return _logger


logger = logging.getLogger("autodl_setup")


def listening_pids(port: int) -> list[int]:
    """Return listener PIDs without changing process state."""
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, check=False,
            timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"无法安全检查端口 {port}: {exc}") from exc

    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"无法安全检查端口 {port}: lsof exit code {result.returncode}"
        )
    return sorted({int(pid) for pid in result.stdout.split() if pid.isdigit()})


def ensure_port_available(port: int) -> None:
    """Refuse to start when a port is occupied; never kill its listener."""
    pids = listening_pids(port)
    if pids:
        raise RuntimeError(
            f"端口 {port} 已被 PID {', '.join(map(str, pids))} 占用；"
            "请先确认进程归属，不会自动终止"
        )


def _is_owned_comfy_process(pid: int, comfy_dir: Path, python_env_dir: Path) -> bool:
    """Check cwd, exact script/interpreter arguments and the real executable."""
    proc_dir = Path("/proc") / str(pid)
    try:
        cwd = (proc_dir / "cwd").resolve(strict=True)
        executable = (proc_dir / "exe").resolve(strict=True)
        args = (proc_dir / "cmdline").read_bytes().split(b"\0")
        decoded = [os.fsdecode(arg) for arg in args if arg]
        python = python_env_dir / "bin/python"
        if len(decoded) < 2 or cwd != comfy_dir.resolve(strict=True):
            return False
        # Resolving argv[0] alone loses the venv identity when Python is a symlink.
        if Path(os.path.abspath(decoded[0])) != Path(os.path.abspath(python)):
            return False
        return (
            executable == python.resolve(strict=True)
            and (cwd / decoded[1]).resolve(strict=True)
            == (comfy_dir / "main.py").resolve(strict=True)
        )
    except (OSError, ValueError, RuntimeError):
        return False


def _process_identity(pid: int) -> str | None:
    """Return Linux starttime; an exited or zombie process has no live identity."""
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    # comm may itself contain spaces or parentheses; fields after it start at 3.
    fields = stat[stat.rfind(")") + 2:].split()
    if len(fields) < 20:
        raise RuntimeError(f"无法读取 PID {pid} 的进程身份")
    return None if fields[0] in {"Z", "X"} else fields[19]


def stop_owned_comfy_listener(
    port: int, comfy_dir: Path, python_env_dir: Path, *, timeout: float = 10.0,
) -> list[int]:
    """Validate every listener, send SIGTERM and wait for confirmed exit."""
    if timeout < 0:
        raise ValueError("Stop timeout must not be negative")
    targets = {}
    for pid in listening_pids(port):
        identity = _process_identity(pid)
        if identity is None:
            continue
        if not _is_owned_comfy_process(pid, comfy_dir, python_env_dir):
            raise RuntimeError(
                f"拒绝停止端口 {port}：PID {pid} 无法确认属于目标 ComfyUI"
            )
        if _process_identity(pid) != identity:
            raise RuntimeError(f"拒绝停止：PID {pid} 的进程身份已变化")
        targets[pid] = identity

    stopped = []
    for pid, identity in targets.items():
        current = _process_identity(pid)
        if current is None:
            continue
        if current != identity or not _is_owned_comfy_process(pid, comfy_dir, python_env_dir):
            raise RuntimeError(f"拒绝停止：PID {pid} 的进程身份或归属已变化")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        stopped.append(pid)

    deadline = time.monotonic() + timeout
    pending = dict(targets)
    while pending:
        pending = {
            pid: identity for pid, identity in pending.items()
            if _process_identity(pid) == identity
        }
        if not pending:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"等待 ComfyUI 退出超时（{timeout:g} 秒），PID: "
                + ", ".join(map(str, pending))
                + "；未发送 SIGKILL"
            )
        time.sleep(min(0.1, remaining))
    return stopped
