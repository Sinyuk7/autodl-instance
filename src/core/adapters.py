"""
适配器 - 生产环境的接口实现
"""
import subprocess
from pathlib import Path
from typing import List, Optional

from src.core.ports import ICommandRunner, IStateManager, CommandResult
from src.core.utils import logger


class SubprocessRunner(ICommandRunner):
    """生产环境命令执行器"""
    
    def run(
        self,
        cmd: List[str] | str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
        check: bool = True,
        shell: bool = False,
        capture_output: bool = True,
    ) -> CommandResult:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        logger.debug(f"[CMD] {cmd_str}")
        
        result = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            shell=shell,
            capture_output=capture_output,
            text=True,
        )
        
        if result.stdout:
            logger.debug(f"[STDOUT] {result.stdout.strip()}")
        if result.stderr:
            logger.debug(f"[STDERR] {result.stderr.strip()}")
        
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        
        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            command=cmd_str,
        )
    
    def run_realtime(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
    ) -> int:
        """实时输出的命令执行"""
        logger.debug(f"[CMD:REALTIME] {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        if process.stdout:
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    logger.info(f"     {line}")
        
        return process.wait()


class FileStateManager(IStateManager):
    """基于文件的状态管理器"""
    
    def __init__(self, base_dir: Path):
        self.state_dir = base_dir / ".autodl_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_path(self, key: str) -> Path:
        # StateKey 继承自 str，可直接作为字符串使用
        return self.state_dir / f"{key}.done"
    
    def is_completed(self, key: str) -> bool:
        return self._get_path(key).exists()
    
    def mark_completed(self, key: str) -> None:
        self._get_path(key).touch()
    
    def clear(self, key: str) -> None:
        path = self._get_path(key)
        if path.exists():
            path.unlink()
