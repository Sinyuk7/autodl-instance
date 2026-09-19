"""
工具函数
"""
import logging
import os
import signal
import subprocess
import sys
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


def _is_owned_comfy_process(pid: int, comfy_dir: Path) -> bool:
    """Require both the expected cwd and a Python main.py command line."""
    proc_dir = Path("/proc") / str(pid)
    try:
        cwd = (proc_dir / "cwd").resolve(strict=True)
        args = (proc_dir / "cmdline").read_bytes().split(b"\0")
    except (FileNotFoundError, PermissionError, OSError):
        return False

    decoded = [arg.decode(errors="replace") for arg in args if arg]
    if not decoded or cwd != comfy_dir.resolve():
        return False
    executable = Path(decoded[0]).name.lower()
    has_main = any(Path(arg).name == "main.py" for arg in decoded[1:])
    return "python" in executable and has_main


def stop_owned_comfy_listener(port: int, comfy_dir: Path) -> list[int]:
    """SIGTERM listeners only after proving that all belong to this ComfyUI."""
    pids = listening_pids(port)
    foreign = [pid for pid in pids if not _is_owned_comfy_process(pid, comfy_dir)]
    if foreign:
        raise RuntimeError(
            f"拒绝停止端口 {port}：PID {', '.join(map(str, foreign))} "
            "无法确认属于目标 ComfyUI"
        )

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    return pids
