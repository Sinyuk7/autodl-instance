"""
测试用 Mock 实现

提供 ICommandRunner 和 IStateManager 的测试替身，
用于单元测试中隔离外部依赖（subprocess、文件系统）。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.core.ports import ICommandRunner, IStateManager, CommandResult


@dataclass
class CallRecord:
    """记录一次调用"""
    cmd: str
    cwd: Optional[Path] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)


class MockRunner(ICommandRunner):
    """
    模拟命令执行器
    
    - 记录所有调用，可在测试中断言
    - 支持通过 stub_results 预设特定命令的返回值
    - 默认返回 returncode=0 的成功结果
    """
    
    def __init__(self):
        self.calls: List[CallRecord] = []
        self.realtime_calls: List[CallRecord] = []
        # key: 命令前缀或完整命令，value: 预设的 CommandResult
        self.stub_results: Dict[str, CommandResult] = {}
    
    def _find_stub(self, cmd_str: str) -> Optional[CommandResult]:
        """查找匹配的预设结果（精确匹配 → 前缀匹配）"""
        if cmd_str in self.stub_results:
            return self.stub_results[cmd_str]
        for pattern, result in self.stub_results.items():
            if cmd_str.startswith(pattern):
                return result
        return None
    
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
        self.calls.append(CallRecord(
            cmd=cmd_str,
            cwd=cwd,
            kwargs={"timeout": timeout, "check": check, "shell": shell, "capture_output": capture_output},
        ))
        
        stub = self._find_stub(cmd_str)
        if stub:
            return stub
        
        return CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=cmd_str,
        )
    
    def run_realtime(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
    ) -> int:
        cmd_str = " ".join(cmd)
        self.realtime_calls.append(CallRecord(cmd=cmd_str, cwd=cwd))
        
        stub = self._find_stub(cmd_str)
        if stub:
            return stub.returncode
        return 0
    
    # ===== 测试辅助方法 =====
    
    def assert_called_with(self, substring: str) -> CallRecord:
        """断言至少有一次调用包含指定子串"""
        for call in self.calls + self.realtime_calls:
            if substring in call.cmd:
                return call
        all_cmds = [c.cmd for c in self.calls + self.realtime_calls]
        raise AssertionError(
            f"没有找到包含 '{substring}' 的调用。\n"
            f"实际调用列表:\n" + "\n".join(f"  - {c}" for c in all_cmds)
        )
    
    def assert_not_called_with(self, substring: str) -> None:
        """断言没有调用包含指定子串"""
        for call in self.calls + self.realtime_calls:
            if substring in call.cmd:
                raise AssertionError(
                    f"意外发现包含 '{substring}' 的调用: {call.cmd}"
                )
    
    @property
    def all_commands(self) -> List[str]:
        """所有调用的命令列表"""
        return [c.cmd for c in self.calls + self.realtime_calls]
    
    def was_called_with_pattern(self, pattern: str) -> bool:
        """检查是否有调用匹配指定的正则表达式模式"""
        import re
        for call in self.calls + self.realtime_calls:
            if re.search(pattern, call.cmd):
                return True
        return False


class MockStateManager(IStateManager):
    """
    内存中的状态管理器
    
    使用 Set 跟踪已完成的 Key，无需文件系统。
    """
    
    def __init__(self, pre_completed: Optional[Set[str]] = None):
        self._completed: Set[str] = set()
        if pre_completed:
            for key in pre_completed:
                k = key.value if hasattr(key, 'value') else key
                self._completed.add(k)
    
    def is_completed(self, key: str) -> bool:
        k = key.value if hasattr(key, 'value') else key
        return k in self._completed
    
    def mark_completed(self, key: str) -> None:
        k = key.value if hasattr(key, 'value') else key
        self._completed.add(k)
    
    def clear(self, key: str) -> None:
        k = key.value if hasattr(key, 'value') else key
        self._completed.discard(k)
    
    @property
    def completed_keys(self) -> Set[str]:
        """所有已完成的 Key"""
        return self._completed.copy()
