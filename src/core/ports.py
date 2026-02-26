"""
端口（接口）定义
所有与外部世界交互的能力都在这里声明
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CommandResult:
    """命令执行结果"""
    returncode: int
    stdout: str
    stderr: str
    command: str


class ICommandRunner(ABC):
    """命令执行接口"""
    
    @abstractmethod
    def run(
        self, 
        cmd: List[str] | str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
        check: bool = True,
        shell: bool = False,
        capture_output: bool = True,
    ) -> CommandResult:
        """执行命令并返回结果"""
        ...
    
    @abstractmethod
    def run_realtime(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
    ) -> int:
        """实时输出的命令执行，返回 returncode"""
        ...


class IStateManager(ABC):
    """状态持久化接口"""
    
    @abstractmethod
    def is_completed(self, key: str) -> bool:
        """检查指定任务是否已完成"""
        ...
    
    @abstractmethod
    def mark_completed(self, key: str) -> None:
        """标记指定任务为已完成"""
        ...
    
    @abstractmethod
    def clear(self, key: str) -> None:
        """清除指定任务的完成状态"""
        ...
