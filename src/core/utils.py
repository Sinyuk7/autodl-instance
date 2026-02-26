"""
工具函数
"""
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional


def setup_logger(log_file: Path) -> logging.Logger:
    """配置全局日志，终端输出 INFO，文件输出 DEBUG"""
    _logger = logging.getLogger("autodl_setup")
    _logger.setLevel(logging.DEBUG)
    
    # 避免重复添加 handler
    if _logger.handlers:
        return _logger

    # 终端 Handler (INFO 级别，清爽输出)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
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


def kill_process_by_name(pattern: str, exclude_pid: Optional[int] = None) -> None:
    """根据进程名模式清理进程，用于处理 Ctrl+Z 或异常退出残留的进程"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = [int(p) for p in result.stdout.strip().split('\n') if p]
            if exclude_pid:
                pids = [p for p in pids if p != exclude_pid]
            
            if pids:
                logger.info(f">>> [Cleanup] 检测到 {len(pids)} 个匹配 '{pattern}' 的残留进程，正在清理...")
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                logger.info(">>> [Cleanup] 清理完成")
    except FileNotFoundError:
        # Windows 没有 pgrep，跳过
        pass


def release_port(port: int) -> None:
    """释放指定端口，确保服务能正常启动"""
    try:
        result = subprocess.run(
            ["fuser", "-k", "-9", f"{port}/tcp"],
            capture_output=True, text=True, check=False,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"  -> 已释放端口 {port} 上的残留进程")
            return
    except Exception:
        pass
    
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, check=False,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                subprocess.run(["kill", "-9", pid], capture_output=True, check=False)
            logger.info(f"  -> 已释放端口 {port} 上的残留进程")
    except Exception:
        pass
